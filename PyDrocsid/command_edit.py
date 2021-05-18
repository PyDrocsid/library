import asyncio
from typing import Optional, Union

from discord import Message, NotFound, TextChannel, Forbidden, HTTPException
from discord.ext.commands import Bot, Context

from PyDrocsid.environment import RESPONSE_LINK_TTL
from PyDrocsid.logger import get_logger
from PyDrocsid.redis import redis

logger = get_logger(__name__)


async def link_response(msg: Union[Message, Context], *response_messages: Message):
    """Create a link from message to a given list of bot responses and add it to redis."""

    if not response_messages:
        return

    if isinstance(msg, Context):
        msg = msg.message

    # save channel:message pairs in redis
    await redis.lpush(
        key := f"bot_response:channel={msg.channel.id},msg={msg.id}",
        *[f"{msg.channel.id}:{msg.id}" for msg in response_messages],
    )
    await redis.expire(key, RESPONSE_LINK_TTL)


async def handle_edit(bot: Bot, message: Message):
    """Delete linked bot responses of a command message and execute new command."""

    if message.author.bot:
        return

    await handle_delete(bot, message.channel.id, message.id)
    for reaction in message.reactions:
        if reaction.me:
            await reaction.remove(bot.user)
    await bot.process_commands(message)


async def handle_delete(bot: Bot, channel_id: int, message_id: int):
    """Delete linked bot responses of a command message."""

    responses = await redis.lrange(key := f"bot_response:channel={channel_id},msg={message_id}", 0, -1)
    await redis.delete(key)

    channel: Optional[TextChannel] = bot.get_channel(channel_id)
    if not channel:
        logger.warning("could not find channel %s", channel_id)
        return

    async def delete_message(chn_id, msg_id):
        if not (chn := bot.get_channel(chn_id)):
            logger.warning("could not delete message %s in unknown channel %s", msg_id, chn_id)
            return

        try:
            message: Message = await chn.fetch_message(int(msg_id))
            await message.delete()
        except (NotFound, Forbidden, HTTPException):
            logger.warning("could not delete message %s in #%s (%s)", msg_id, chn.name, chn.id)

    await asyncio.gather(*[delete_message(*map(int, r.split(":"))) for r in responses])

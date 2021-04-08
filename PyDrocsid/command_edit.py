import asyncio
from typing import Optional, Union

from discord import Message, NotFound, TextChannel, Forbidden, HTTPException
from discord.ext.commands import Bot, Context

from PyDrocsid.environment import RESPONSE_LINK_TTL
from PyDrocsid.logger import get_logger
from PyDrocsid.redis import redis

logger = get_logger(__name__)


async def link_response(msg: Union[Message, Context], *response_messages: Message):
    if not response_messages:
        return

    if isinstance(msg, Context):
        msg = msg.message

    await redis.lpush(
        key := f"bot_response:channel={msg.channel.id},msg={msg.id}",
        *[msg.id for msg in response_messages],
    )
    await redis.expire(key, RESPONSE_LINK_TTL)


async def handle_edit(bot: Bot, message: Message):
    if message.author.bot:
        return

    await handle_delete(bot, message.channel.id, message.id)
    for reaction in message.reactions:
        if reaction.me:
            await reaction.remove(bot.user)
    await bot.process_commands(message)


async def handle_delete(bot: Bot, channel_id: int, message_id: int):
    responses = await redis.lrange(key := f"bot_response:channel={channel_id},msg={message_id}", 0, -1)
    await redis.delete(key)

    channel: Optional[TextChannel] = bot.get_channel(channel_id)
    if not channel:
        logger.warning("could not find channel %s", channel_id)
        return

    async def delete_message(msg_id):
        try:
            message: Message = await channel.fetch_message(int(msg_id))
            await message.delete()
        except (NotFound, Forbidden, HTTPException):
            logger.warning("could not delete message %s in #%s (%s)", msg_id, channel.name, channel.id)

    await asyncio.gather(*map(delete_message, responses))

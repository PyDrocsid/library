import asyncio
from typing import cast

from discord import DMChannel, Forbidden, HTTPException, Message, NotFound, TextChannel, Thread
from discord.abc import GuildChannel, PrivateChannel, Snowflake
from discord.ext.commands.bot import Bot
from discord.ext.commands.context import Context

from PyDrocsid.environment import RESPONSE_LINK_TTL
from PyDrocsid.logger import get_logger
from PyDrocsid.redis import redis


logger = get_logger(__name__)


async def link_response(msg: Message | Context[Bot], *response_messages: Message) -> None:
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


async def handle_edit(bot: Bot, message: Message) -> None:
    """Delete linked bot responses of a command message and execute new command."""

    if message.author.bot:
        return

    await handle_delete(bot, message.channel.id, message.id)
    for reaction in message.reactions:
        if reaction.me:
            await reaction.remove(cast(Snowflake, bot.user))


async def _get_channel(bot: Bot, channel_id: int) -> GuildChannel | PrivateChannel | Thread | None:
    if channel := bot.get_channel(channel_id):
        return channel

    try:
        return await bot.fetch_channel(channel_id)
    except (HTTPException, NotFound, Forbidden):
        return None


async def handle_delete(bot: Bot, channel_id: int, message_id: int) -> None:
    """Delete linked bot responses of a command message."""

    responses = await redis.lrange(key := f"bot_response:channel={channel_id},msg={message_id}", 0, -1)
    await redis.delete(key)

    async def delete_message(chn_id: int, msg_id: int) -> None:
        if not isinstance(chn := await _get_channel(bot, chn_id), (TextChannel, Thread, DMChannel)):
            logger.warning("could not delete message %s in unknown channel %s", msg_id, chn_id)
            return

        try:
            message: Message = await chn.fetch_message(int(msg_id))
            await message.delete()
        except (NotFound, Forbidden, HTTPException):
            logger.warning("could not delete message %s in #%s (%s)", msg_id, chn.name, chn.id)

    await asyncio.gather(*[delete_message(*map(int, r.split(":"))) for r in responses])

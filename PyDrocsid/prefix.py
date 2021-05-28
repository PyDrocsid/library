from __future__ import annotations

from contextvars import ContextVar
from enum import auto, Flag
from typing import Union, Optional, Iterable

from discord import Guild, Message
from discord.ext.commands import check, Context, CheckFailure, Bot
from sqlalchemy import Column, BigInteger, String

from PyDrocsid.database import db, delete
from PyDrocsid.settings import Settings
from PyDrocsid.translations import t


t = t.g


class PrefixSettings(Settings):
    prefix = "."


async def get_prefix(guild: Guild) -> str:
    """Get bot prefix."""

    return await PrefixSettings.prefix.get(guild)


async def set_prefix(guild: Guild, new_prefix: str):
    """Set bot prefix."""

    await PrefixSettings.prefix.set(guild, new_prefix)


class GlobalPrefix(db.Base):
    __tablename__ = "global_prefix"

    prefix: Union[Column, str] = Column(String(64), primary_key=True, unique=True)
    guild_id: Union[Column, int] = Column(BigInteger, unique=True)

    @staticmethod
    async def get_prefix(guild_id: int) -> Optional[str]:
        if row := await db.get(GlobalPrefix, guild_id=guild_id):
            return row.prefix

        return None

    @staticmethod
    async def get_guild(prefix: str) -> Optional[int]:
        if row := await db.get(GlobalPrefix, prefix=prefix):
            return row.guild_id

        return None

    @staticmethod
    async def set_prefix(guild_id: int, prefix: str) -> GlobalPrefix:
        if not (row := await db.get(GlobalPrefix, guild_id=guild_id)):
            row = GlobalPrefix(guild_id=guild_id, prefix=prefix)
            await db.add(row)
        else:
            row.prefix = prefix

        return row

    @staticmethod
    async def clear_prefix(guild_id: int):
        await db.exec(delete(GlobalPrefix).filter_by(guild_id=guild_id))


class GuildContext(Flag):
    GUILD = auto()
    PRIVATE_GUILD = auto()
    PRIVATE_GLOBAL = auto()


_guild: ContextVar[Optional[Guild]] = ContextVar("guild", default=None)


async def get_guild_context(
    bot: Bot,
    message: Message,
    prefix: Optional[str] = None,
) -> tuple[GuildContext, Optional[Guild], Optional[str]]:
    if message.guild:
        return GuildContext.GUILD, message.channel.guild, None

    if not prefix:
        prefix = message.content.split(" ")[0]

    if not (guild_id := await GlobalPrefix.get_guild(prefix)):
        return GuildContext.PRIVATE_GLOBAL, None, None
    if not (guild := bot.get_guild(guild_id)):
        return GuildContext.PRIVATE_GLOBAL, None, None

    return GuildContext.PRIVATE_GUILD, guild, prefix


async def fetch_prefix(bot: Bot, msg: Message) -> Iterable[str]:
    bot_mention = [f"<@!{bot.user.id}> ", f"<@{bot.user.id}> "]

    guild_context, guild, prefix = await get_guild_context(bot, msg)
    if guild_context == GuildContext.GUILD:
        return [await get_prefix(msg.channel.guild), *bot_mention]
    if guild_context == GuildContext.PRIVATE_GLOBAL:
        return ["", *bot_mention]

    _guild.set(guild)
    return [prefix + " "]


def get_guild(ctx: Union[Context, Message, None]) -> Optional[Guild]:
    if isinstance(ctx, (Context, Message)) and ctx.guild:
        return ctx.guild
    if guild := _guild.get():
        return guild
    return None


def check_guild_context(allowed_guild_context: GuildContext):
    @check
    async def inner(ctx: Context):
        guild_context, *_ = await get_guild_context(ctx.bot, ctx.message, prefix=ctx.prefix)
        if guild_context in allowed_guild_context:
            return True

        allowed = []
        if GuildContext.GUILD in allowed_guild_context:
            allowed.append(t.wrong_guild_context.guild)
        if GuildContext.PRIVATE_GUILD in allowed_guild_context:
            allowed.append(t.wrong_guild_context.private_guild)
        if GuildContext.PRIVATE_GLOBAL in allowed_guild_context:
            allowed.append(t.wrong_guild_context.private_global)

        *allowed, last = allowed
        lst = (", ".join(allowed) + " " + t.wrong_guild_context.conj + " ") * bool(allowed) + last
        raise CheckFailure(t.wrong_guild_context.error_message(lst))

    return inner

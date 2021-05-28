from __future__ import annotations

from contextvars import ContextVar
from enum import auto, Flag
from typing import Union, Optional, Iterable

from discord import Guild, Message
from discord.ext.commands import check, Context, CheckFailure, Bot
from sqlalchemy import Column, BigInteger, String

from PyDrocsid.database import db
from PyDrocsid.environment import CACHE_TTL
from PyDrocsid.redis import redis
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
        if (result := await redis.get(f"global_prefix:guild_id={guild_id}")) is not None:
            return result or None

        result = None
        if row := await db.get(GlobalPrefix, guild_id=guild_id):
            result = row.prefix

        await redis.setex(f"global_prefix:guild_id={guild_id}", CACHE_TTL, result or "")

        return result

    @staticmethod
    async def get_guild(prefix: str) -> Optional[int]:
        if (result := await redis.get(f"global_prefix:prefix={prefix}")) is not None:
            result = int(result)
            return result if result != -1 else None

        result = None
        if row := await db.get(GlobalPrefix, prefix=prefix):
            result = row.guild_id

        await redis.setex(f"global_prefix:prefix={prefix}", CACHE_TTL, result or -1)

        return result

    @staticmethod
    async def set_prefix(guild_id: int, prefix: str) -> GlobalPrefix:
        old_prefix = None
        if not (row := await db.get(GlobalPrefix, guild_id=guild_id)):
            row = GlobalPrefix(guild_id=guild_id, prefix=prefix)
            await db.add(row)
        else:
            old_prefix = row.prefix
            row.prefix = prefix

        p = redis.pipeline()
        if old_prefix:
            p.setex(f"global_prefix:prefix={old_prefix}", CACHE_TTL, -1)
        p.setex(f"global_prefix:guild_id={guild_id}", CACHE_TTL, prefix)
        p.setex(f"global_prefix:prefix={prefix}", CACHE_TTL, guild_id)
        await p.execute()

        return row

    @staticmethod
    async def clear_prefix(guild_id: int):
        row: Optional[GlobalPrefix] = await db.get(GlobalPrefix, guild_id=guild_id)
        if not row:
            return

        p = redis.pipeline()
        p.setex(f"global_prefix:guild_id={guild_id}", CACHE_TTL, "")
        p.setex(f"global_prefix:prefix={row.prefix}", CACHE_TTL, -1)
        await p.execute()

        await db.delete(row)


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

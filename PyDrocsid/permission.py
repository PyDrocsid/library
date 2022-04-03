from __future__ import annotations

import sys
from collections import namedtuple
from contextvars import ContextVar
from enum import Enum
from typing import Awaitable, Callable, Iterable, cast

from discord import Member, User
from discord.ext.commands.bot import Bot
from discord.ext.commands.context import Context
from discord.ext.commands.core import check
from discord.ext.commands.errors import CheckFailure
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import Mapped

from PyDrocsid.database import Base, db
from PyDrocsid.environment import CACHE_TTL
from PyDrocsid.redis import redis
from PyDrocsid.translations import t


# context variable for overriding the permission level of the user who invoked the current command
permission_override: ContextVar[BasePermissionLevel] = ContextVar("permission_override")


class PermissionModel(Base):
    __tablename__ = "permissions"

    permission: Mapped[str] = Column(String(64), primary_key=True, unique=True)
    level: Mapped[int] = Column(Integer)

    @staticmethod
    async def create(permission: str, level: int) -> PermissionModel:
        row = PermissionModel(permission=permission, level=level)
        await db.add(row)
        return row

    @staticmethod
    async def get(permission: str, default: int) -> int:
        """Get the configured level of a given permission."""

        if await redis.exists(rkey := f"permissions:{permission}"):
            return int(await redis.get(rkey))

        if (row := await db.get(PermissionModel, permission=permission)) is None:
            row = await PermissionModel.create(permission, default)

        await redis.setex(rkey, CACHE_TTL, row.level)

        return row.level

    @staticmethod
    async def set(permission: str, level: int) -> PermissionModel:
        """Configure the level of a given permission."""

        await redis.setex(f"permissions:{permission}", CACHE_TTL, level)

        if (row := await db.get(PermissionModel, permission=permission)) is None:
            return await PermissionModel.create(permission, level)

        row.level = level
        return row


class BasePermission(Enum):
    @property
    def description(self) -> str:
        raise NotImplementedError

    @property
    def cog(self) -> str:
        return cast(str, sys.modules[self.__class__.__module__].__package__).split(".")[-1]

    @property
    def fullname(self) -> str:
        return self.cog + "." + self.name

    @property
    def _default_level(self) -> BasePermissionLevel:
        from PyDrocsid.config import Config

        # get default level from overrides or use the global default
        return Config.DEFAULT_PERMISSION_OVERRIDES.get(self.cog, {}).get(self.name, Config.DEFAULT_PERMISSION_LEVEL)

    async def resolve(self) -> BasePermissionLevel:
        """Get the configured permission level of this permission."""

        from PyDrocsid.config import Config

        value: int = await PermissionModel.get(self.fullname, self._default_level.level)
        for level in Config.PERMISSION_LEVELS:  # type: BasePermissionLevel
            if level.level == value:
                return level
        raise ValueError(f"permission level not found: {value}")

    async def set(self, level: BasePermissionLevel) -> None:
        """Configure the permission level of this permission."""

        await PermissionModel.set(self.fullname, level.level)

    async def check_permissions(self, member: User | Member) -> bool:
        """Return whether this permission is granted to a given member."""

        return await (await self.resolve()).check_permissions(member)

    @property
    def check(self) -> Callable[[Context[Bot]], Awaitable[bool]]:
        """Decorator for bot commands to require this permission when invoking this command."""

        return check_permission_level(self)


PermissionLevel = namedtuple("PermissionLevel", ["level", "aliases", "description", "guild_permissions", "roles"])


class BasePermissionLevel(Enum):
    @property
    def level(self) -> int:
        return cast(int, self.value.level)

    @property
    def aliases(self) -> list[str]:
        return cast(list[str], self.value.aliases)

    @property
    def description(self) -> str:
        return cast(str, self.value.description)

    @property
    def guild_permissions(self) -> list[str]:
        return cast(list[str], self.value.guild_permissions)

    @property
    def roles(self) -> list[str]:
        return cast(list[str], self.value.roles)

    @classmethod
    async def get_permission_level(cls, member: User | Member) -> BasePermissionLevel:
        """Get the permission level of a given member without (takes permission_override into account)."""

        if override := permission_override.get(None):
            return override

        return await cls._get_permission_level(member)

    @classmethod
    async def _get_permission_level(cls, member: User | Member) -> BasePermissionLevel:
        """Get the permission level of a given member."""

        raise NotImplementedError

    async def check_permissions(self, member: User | Member) -> bool:
        """Return whether this permission level is granted to a given member."""

        level: BasePermissionLevel = await self.get_permission_level(member)
        return level.level >= self.level

    @property
    def check(self) -> Callable[[Context[Bot]], Awaitable[bool]]:
        """Decorator for bot commands to require this permission level when invoking this command."""

        return check_permission_level(self)

    @classmethod
    def max(cls) -> BasePermissionLevel:
        """Returns the highest permission level available."""

        return max(cast(Iterable[BasePermissionLevel], cls), key=lambda x: x.level)


def check_permission_level(level: BasePermission | BasePermissionLevel) -> Callable[[Context[Bot]], Awaitable[bool]]:
    """Discord commmand check to require a given level when invoking the command."""

    async def inner(ctx: Context[Bot]) -> bool:
        member: User | Member = ctx.author
        if not isinstance(member, Member):
            member = ctx.bot.guilds[0].get_member(ctx.author.id) or member
        if not await level.check_permissions(member):
            raise CheckFailure(t.g.not_allowed)

        return True

    inner.level = level  # type: ignore

    return cast(Callable[[Context[Bot]], Awaitable[bool]], check(inner))

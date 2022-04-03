from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Type, TypeVar, cast

from sqlalchemy import Column, String
from sqlalchemy.orm import Mapped

from PyDrocsid.async_thread import lock_deco
from PyDrocsid.database import Base, db
from PyDrocsid.environment import CACHE_TTL
from PyDrocsid.redis import redis


if not TYPE_CHECKING:
    from aenum import NoAliasEnum as Enum
else:
    from enum import Enum

Value = TypeVar("Value", str, int, float, bool)


class SettingsModel(Base):
    __tablename__ = "settings"

    key: Mapped[str] = Column(String(64), primary_key=True, unique=True)
    value: Mapped[str] = Column(String(256))

    @staticmethod
    async def _create(key: str, value: Value) -> SettingsModel:
        row = SettingsModel(key=key, value=str(int(value) if isinstance(value, bool) else value))
        await db.add(row)
        return row

    @staticmethod
    @lock_deco
    async def get(dtype: Type[Value], key: str, default: Value) -> Value:
        """Get the value of a given setting."""

        if await redis.exists(rkey := f"settings:{key}"):
            out = await redis.get(rkey)
        else:
            if (row := await db.get(SettingsModel, key=key)) is None:
                row = await SettingsModel._create(key, default)
            out = row.value
            await redis.setex(rkey, CACHE_TTL, out)

        return dtype(int(out) if dtype is bool else out)

    @staticmethod
    @lock_deco
    async def set(dtype: Type[Value], key: str, value: Value) -> SettingsModel:
        """Set the value of a given setting."""

        rkey = f"settings:{key}"
        if (row := await db.get(SettingsModel, key=key)) is None:
            row = await SettingsModel._create(key, value)
            await redis.setex(rkey, CACHE_TTL, row.value)
            return row

        row.value = str(int(value) if dtype is bool else value)
        await redis.setex(rkey, CACHE_TTL, row.value)
        return row


class Settings(Enum):
    @property
    def cog(self) -> str:
        return cast(str, sys.modules[self.__class__.__module__].__package__).split(".")[-1]

    @property
    def fullname(self) -> str:
        return self.cog + "." + self.name

    @property
    def default(self) -> Value:
        return cast(Value, self.value)

    @property
    def type(self) -> Type[Value]:
        return type(cast(Value, self.default))

    async def get(self) -> Value:
        """Get the value of this setting."""

        return cast(Value, await SettingsModel.get(self.type, self.fullname, self.default))

    async def set(self, value: Value) -> Value:
        """Set the value of this setting."""

        await SettingsModel.set(self.type, self.fullname, value)
        return value

    async def reset(self) -> Value:
        """Reset the value of this setting to its default value."""

        return cast(Value, await self.set(self.default))


class RoleSettings:
    @staticmethod
    async def get(name: str) -> int:
        """Get the value of this role setting."""

        return cast(int, await SettingsModel.get(int, f"role:{name}", -1))

    @staticmethod
    async def set(name: str, role_id: int) -> int:
        """Set the value of this role setting."""

        await SettingsModel.set(int, f"role:{name}", role_id)
        return role_id

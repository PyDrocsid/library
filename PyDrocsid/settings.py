from __future__ import annotations

from aenum import NoAliasEnum
from typing import Union, Optional, Type, TypeVar

from sqlalchemy import Column, String

from PyDrocsid.async_thread import LockDeco
from PyDrocsid.database import db
from PyDrocsid.environment import CACHE_TTL
from PyDrocsid.redis import redis

T = TypeVar("T")


class SettingsModel(db.Base):
    __tablename__ = "settings"

    key: Union[Column, str] = Column(String(64), primary_key=True, unique=True)
    value: Union[Column, str] = Column(String(256))

    @staticmethod
    async def _create(key: str, value: Union[str, int, float, bool]) -> SettingsModel:
        if isinstance(value, bool):
            value = int(value)

        row = SettingsModel(key=key, value=str(value))
        await db.add(row)
        return row

    @staticmethod
    @LockDeco
    async def get(dtype: Type[T], key: str, default: Optional[T] = None) -> Optional[T]:
        if await redis.exists(rkey := f"settings:{key}"):
            out: str = await redis.get(rkey)
        else:
            if (row := await db.get(SettingsModel, key=key)) is None:
                if default is None:
                    return None
                row = await SettingsModel._create(key, default)
            out: str = row.value
            await redis.setex(rkey, CACHE_TTL, out)

        if dtype == bool:
            out: int = int(out)
        return dtype(out)

    @staticmethod
    @LockDeco
    async def set(dtype: Type[T], key: str, value: T) -> SettingsModel:
        rkey = f"settings:{key}"
        if (row := await db.get(SettingsModel, key=key)) is None:
            row = await SettingsModel._create(key, value)
            await redis.setex(rkey, CACHE_TTL, row.value)
            return row

        if dtype == bool:
            value = int(value)
        row.value = str(value)
        await redis.setex(rkey, CACHE_TTL, row.value)
        return row


class Settings(NoAliasEnum):
    @property
    def cog(self) -> str:
        return self.__class__.__name__.lower().removesuffix("settings")

    @property
    def fullname(self) -> str:
        return self.cog + "." + self.name

    @property
    def default(self) -> T:
        return self.value

    @property
    def type(self) -> Type[T]:
        return type(self.default)

    async def get(self) -> T:
        return await SettingsModel.get(self.type, self.fullname, self.default)

    async def set(self, value: T) -> T:
        await SettingsModel.set(self.type, self.fullname, value)
        return value

    async def reset(self) -> T:
        return await self.set(self.default)


class RoleSettings:
    @staticmethod
    async def get(name: str) -> int:
        return await SettingsModel.get(int, f"role:{name}", -1)

    @staticmethod
    async def set(name: str, role_id: int) -> int:
        await SettingsModel.set(int, f"role:{name}", role_id)
        return role_id

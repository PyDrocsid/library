from asyncio import Event
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import partial
from typing import Any, AsyncIterator, NamedTuple, Type, TypeVar, cast

from sqlalchemy import Column, DateTime, Table, TypeDecorator
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.future import select as sa_select
from sqlalchemy.orm import DeclarativeMeta, registry, selectinload
from sqlalchemy.sql import Executable
from sqlalchemy.sql.expression import Delete
from sqlalchemy.sql.expression import delete as sa_delete
from sqlalchemy.sql.expression import exists as sa_exists
from sqlalchemy.sql.functions import count
from sqlalchemy.sql.selectable import Exists, Select

from ..environment import (
    DB_DATABASE,
    DB_DRIVER,
    DB_HOST,
    DB_PASSWORD,
    DB_PORT,
    DB_USERNAME,
    MAX_OVERFLOW,
    POOL_RECYCLE,
    POOL_SIZE,
    SQL_SHOW_STATEMENTS,
)
from ..logger import get_logger


T = TypeVar("T")

logger = get_logger(__name__)


class Session(NamedTuple):
    session: AsyncSession
    close_event: Event


_sessions: ContextVar[list[Session]] = ContextVar("sessions", default=[])


def select(entity: Any, *args: Column[Any]) -> Select:
    """Shortcut for :meth:`sqlalchemy.future.select`"""

    if not args:
        return sa_select(entity)

    options = []
    for arg in args:
        if isinstance(arg, (tuple, list)):
            head, *tail = arg
            opt = selectinload(head)
            for x in tail:
                opt = opt.selectinload(x)
            options.append(opt)
        else:
            options.append(selectinload(arg))

    return sa_select(entity).options(*options)


def filter_by(cls: Any, *args: Column[Any], **kwargs: Any) -> Select:
    """Shortcut for :meth:`sqlalchemy.future.Select.filter_by`"""

    return select(cls, *args).filter_by(**kwargs)


def exists(statement: Executable, *entities: Column[Any], **kwargs: Any) -> Exists:
    """Shortcut for :meth:`sqlalchemy.future.select`"""

    return sa_exists(statement, *entities, **kwargs)


def delete(table: Any) -> Delete:
    """Shortcut for :meth:`sqlalchemy.sql.expression.delete`"""

    return sa_delete(table)


class UTCDateTime(TypeDecorator[Any]):  # noqa
    impl = DateTime

    cache_ok = True

    def process_bind_param(self, value: Any, _: Any) -> Any:
        return value

    def process_result_value(self, value: datetime | None, _: Any) -> datetime | None:
        if value is None:
            return None

        return value.replace(tzinfo=timezone.utc)


class Base(metaclass=DeclarativeMeta):
    __table__: Table

    __abstract__ = True
    registry = registry()
    metadata = registry.metadata

    __table_args__ = {"mysql_collate": "utf8mb4_bin"}

    def __init__(self, **kwargs: Any) -> None:
        self.registry.constructor(self, **kwargs)


class DB:
    def __init__(
        self,
        driver: str,
        host: str,
        port: int,
        database: str,
        username: str,
        password: str,
        pool_recycle: int = 300,
        pool_size: int = 20,
        max_overflow: int = 20,
        echo: bool = False,
    ):
        """
        :param driver: name of the sql connection driver
        :param host: host of the sql server
        :param port: port of the sql server
        :param database: name of the database
        :param username: name of the sql user
        :param password: password of the sql user
        :param echo: whether sql queries should be logged
        """

        self.engine: AsyncEngine = create_async_engine(
            URL.create(
                drivername=driver, username=username, password=password, host=host, port=port, database=database
            ),
            pool_pre_ping=True,
            pool_recycle=pool_recycle,
            pool_size=pool_size,
            max_overflow=max_overflow,
            echo=echo,
        )

    async def create_tables(self) -> None:
        """Create all tables defined in enabled cog packages."""

        from PyDrocsid.config import get_subclasses_in_enabled_packages

        logger.debug("creating tables")
        tables = [cls.__table__ for cls in get_subclasses_in_enabled_packages(Base)]
        async with self.engine.begin() as conn:
            await conn.run_sync(partial(Base.metadata.create_all, tables=tables))

    async def add(self, obj: T) -> T:
        """
        Add a new row to the database

        :param obj: the row to insert
        :return: the same row
        """

        self.session.add(obj)
        return obj

    async def delete(self, obj: T) -> T:
        """
        Remove a row from the database

        :param obj: the row to remove
        :return: the same row
        """

        await self.session.delete(obj)
        return obj

    async def exec(self, statement: Executable) -> Any:
        """Execute an sql statement and return the result."""

        return await self.session.execute(statement)

    async def stream(self, statement: Executable) -> AsyncIterator[Any]:
        """Execute an sql statement and stream the result."""

        return cast(AsyncIterator[Any], (await self.session.stream(statement)).scalars())

    async def all(self, statement: Executable) -> list[Any]:
        """Execute an sql statement and return all results as a list."""

        return [x async for x in await self.stream(statement)]

    async def first(self, statement: Executable) -> Any | None:
        """Execute an sql statement and return the first result."""

        return (await self.exec(statement)).scalar()

    async def exists(self, statement: Executable, *args: Column[Any], **kwargs: Any) -> bool:
        """Execute an sql statement and return whether it returned at least one row."""

        return cast(bool, await self.first(exists(statement, *args, **kwargs).select()))

    async def count(self, statement: Executable, *args: Column[Any]) -> int:
        """Execute an sql statement and return the number of returned rows."""

        return cast(int, await self.first(select(count()).select_from(statement, *args)))

    async def get(self, cls: Type[T], *args: Column[Any], **kwargs: Any) -> T | None:
        """Shortcut for first(filter_by(...))"""

        return await self.first(filter_by(cls, *args, **kwargs))

    async def commit(self) -> None:
        """Shortcut for :meth:`sqlalchemy.ext.asyncio.AsyncSession.commit`"""

        if sessions := _sessions.get():
            await sessions[-1].session.commit()

    async def close(self) -> None:
        """Close the current session"""

        if sessions := _sessions.get():
            session, close_event = sessions.pop()
            _sessions.set(sessions)
            await session.close()
            close_event.set()

    def create_session(self) -> AsyncSession:
        """Create a new async session and store it in the context variable."""

        session = Session(AsyncSession(self.engine, expire_on_commit=False), Event())
        _sessions.set(_sessions.get() + [session])
        return session.session

    @property
    def session(self) -> AsyncSession:
        """Get the session object for the current task"""

        if not (sessions := _sessions.get()):
            raise RuntimeError("No session available")

        return sessions[-1].session

    async def wait_for_close_event(self) -> None:
        if sessions := _sessions.get():
            await sessions[-1].close_event.wait()


def get_database() -> DB:
    """
    Create a database connection object using the environment variables

    :return: The DB object
    """

    return DB(
        driver=DB_DRIVER,
        host=DB_HOST,
        port=DB_PORT,
        database=DB_DATABASE,
        username=DB_USERNAME,
        password=DB_PASSWORD,
        pool_recycle=POOL_RECYCLE,
        pool_size=POOL_SIZE,
        max_overflow=MAX_OVERFLOW,
        echo=SQL_SHOW_STATEMENTS,
    )

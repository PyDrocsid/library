from contextlib import asynccontextmanager
from contextvars import ContextVar
from functools import wraps
from typing import TypeVar, Optional, Type

# noinspection PyProtectedMember
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, AsyncEngine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.future import select as sa_select, Select
from sqlalchemy.sql import Executable
from sqlalchemy.sql.expression import exists as sa_exists, delete as sa_delete, Delete
from sqlalchemy.sql.functions import count
from sqlalchemy.sql.selectable import Exists

from PyDrocsid.logger import get_logger
from PyDrocsid.environment import (
    DB_DRIVER,
    DB_HOST,
    DB_PORT,
    DB_DATABASE,
    DB_USERNAME,
    DB_PASSWORD,
    SQL_SHOW_STATEMENTS,
)

T = TypeVar("T")

logger = get_logger(__name__)


def select(*entities, **kwargs) -> Select:
    """Shortcut for :meth:`sqlalchemy.future.select`"""

    return sa_select(*entities, **kwargs)


def filter_by(cls, **kwargs) -> Select:
    return select(cls).filter_by(**kwargs)


def exists(*entities, **kwargs) -> Exists:
    """Shortcut for :meth:`sqlalchemy.future.select`"""

    return sa_exists(*entities, **kwargs)


def delete(table) -> Delete:
    return sa_delete(table)


class DB:
    """
    Database connection

    Attributes
    ----------
    engine: :class:`sqlalchemy.engine.Engine`
    Base: :class:`sqlalchemy.ext.declarative.DeclarativeMeta`
    """

    def __init__(
        self,
        driver: str,
        host: str,
        port: int,
        database: str,
        username: str,
        password: str,
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
                drivername=driver,
                username=username,
                password=password,
                host=host,
                port=port,
                database=database,
            ),
            pool_pre_ping=True,
            pool_recycle=300,
            pool_size=10,
            max_overflow=20,
            echo=echo,
        )

        self.Base = declarative_base()

        self._session: ContextVar[Optional[AsyncSession]] = ContextVar("session", default=None)

    async def create_tables(self):
        logger.debug("creating tables")
        async with self.engine.begin() as conn:
            await conn.run_sync(self.Base.metadata.create_all)

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

    async def exec(self, statement: Executable, *args, **kwargs):
        return await self.session.execute(statement, *args, **kwargs)

    async def stream(self, statement: Executable, *args, **kwargs):
        return (await self.session.stream(statement, *args, **kwargs)).scalars()

    async def all(self, statement: Executable, *args, **kwargs) -> list[T]:
        return [x async for x in await self.stream(statement, *args, **kwargs)]

    async def first(self, *args, **kwargs):
        return (await self.exec(*args, **kwargs)).scalar()

    async def exists(self, *args, **kwargs):
        return await self.first(exists(*args, **kwargs).select())

    async def count(self, *args, **kwargs):
        return await self.first(select(count()).select_from(*args, **kwargs))

    async def get(self, cls: Type[T], **kwargs) -> Optional[T]:
        return await self.first(filter_by(cls, **kwargs))

    async def commit(self):
        """Shortcut for :meth:`sqlalchemy.ext.asyncio.AsyncSession.commit`"""

        if self._session.get():
            await self.session.commit()

    async def close(self):
        """Close the current session"""

        if self._session.get():
            await self.session.close()

    def create_session(self) -> AsyncSession:
        self._session.set(session := AsyncSession(self.engine))
        return session

    @property
    def session(self) -> AsyncSession:
        """Get the session object for the current thread"""

        return self._session.get()


@asynccontextmanager
async def db_context():
    db.create_session()
    try:
        yield
    finally:
        await db.commit()
        await db.close()


def db_wrapper(f):
    @wraps(f)
    async def inner(*args, **kwargs):
        async with db_context():
            return await f(*args, **kwargs)

    return inner


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
        echo=SQL_SHOW_STATEMENTS,
    )


db: DB = get_database()

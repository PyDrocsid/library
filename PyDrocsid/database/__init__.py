from contextlib import asynccontextmanager
from functools import wraps
from typing import AsyncIterator, Awaitable, Callable, ParamSpec, TypeVar

from .database import Base, UTCDateTime, delete, exists, filter_by, get_database, select


T = TypeVar("T")
P = ParamSpec("P")


@asynccontextmanager
async def db_context() -> AsyncIterator[None]:
    """Async context manager for database sessions."""

    db.create_session()
    try:
        yield
    finally:
        await db.commit()
        await db.close()


def db_wrapper(f: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
    """Decorator which wraps an async function in a database context."""

    @wraps(f)
    async def inner(*args: P.args, **kwargs: P.kwargs) -> T:
        async with db_context():
            return await f(*args, **kwargs)

    return inner


# global database connection object
db = get_database()


__all__ = ["db_context", "db_wrapper", "select", "filter_by", "exists", "delete", "db", "Base", "UTCDateTime"]

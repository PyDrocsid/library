from asyncio import Event, Lock, Semaphore, create_task, gather, get_event_loop
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
from typing import Any, Awaitable, Callable, Coroutine, ParamSpec, TypeVar, cast


T = TypeVar("T")
P = ParamSpec("P")

executor = ThreadPoolExecutor()


def run_in_thread(func: Callable[..., T]) -> Callable[..., Awaitable[T]]:
    @wraps(func)
    async def inner(*args: Any, **kwargs: Any) -> T:
        return await get_event_loop().run_in_executor(executor, lambda: func(*args, **kwargs))

    return inner


async def semaphore_gather(n: int, *tasks: Awaitable[T]) -> list[T]:
    """
    Like asyncio.gather, but limited to n concurrent tasks.

    :param n: the maximum number of concurrent tasks
    :param tasks: the coroutines to run
    :return: a list containing the results of all coroutines
    """

    semaphore = Semaphore(n)

    async def inner(t: Awaitable[T]) -> T:
        async with semaphore:
            return await t

    return list(await gather(*map(inner, tasks)))


def lock_deco(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
    lock = Lock()

    @wraps(func)
    async def inner(*args: Any, **kwargs: Any) -> T:
        async with lock:
            return await func(*args, **kwargs)

    return inner


def run_as_task(func: Callable[..., Coroutine[Any, Any, None]]) -> Callable[..., Awaitable[None]]:
    """
    Decorator for async functions.
    Instead of calling the decorated function directly, this will create a task for it and return immediately.
    """

    @wraps(func)
    async def inner(*args: Any, **kwargs: Any) -> None:
        create_task(func(*args, **kwargs))

    return inner


class GatherAnyError(Exception):
    def __init__(self, idx: int, exception: Exception):
        self.idx: int = idx
        self.exception: Exception = exception


async def gather_any(*coroutines: Awaitable[T]) -> tuple[int, T]:
    """
    Like asyncio.gather, but returns after the first coroutine is done.

    :param coroutines: the coroutines to run
    :return: a tuple containing the index of the coroutine that has finished and its result
    """

    event = Event()
    result: list[tuple[int, bool, T | Exception]] = []

    async def inner(i: int, coro: Awaitable[T]) -> None:
        # noinspection PyBroadException
        try:
            result.append((i, True, await coro))
        except Exception as e:
            result.append((i, False, e))
        event.set()

    tasks = [create_task(inner(i, c)) for i, c in enumerate(coroutines)]
    await event.wait()

    for task in tasks:
        if not task.done():
            task.cancel()

    idx, ok, value = result[0]
    if not ok:
        raise GatherAnyError(idx, cast(Exception, value))

    return idx, cast(T, value)

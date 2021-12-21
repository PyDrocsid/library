import threading
from asyncio import Semaphore, Lock, Event, get_running_loop, AbstractEventLoop, gather, create_task

from functools import partial, update_wrapper, wraps
from typing import Callable, TypeVar, Optional, Coroutine, Awaitable

T = TypeVar("T")


class Thread(threading.Thread):
    def __init__(self, func: Callable[..., T], loop: AbstractEventLoop):
        super().__init__()

        self._return: Optional[T] = None
        self._func: Callable[..., T] = func
        self._event = Event()
        self._loop: AbstractEventLoop = loop

    async def wait(self):
        """Wait for function to finish and return the result."""

        await self._event.wait()
        return self._return

    def run(self):
        """Run the function and set the event after completion."""

        try:
            self._return = True, self._func()
        except Exception as e:  # skipcq: PYL-W0703
            self._return = False, e
        self._loop.call_soon_threadsafe(self._event.set)


async def run_in_thread(func, *args, **kwargs):
    """
    Run a synchronous function asynchronously using threading.

    :param func: the synchronous function
    :param args: positional arguments to pass to the function
    :param kwargs: keyword arguments to pass to the function
    :return: the return value of func(*args, **kwargs)
    """

    thread = Thread(partial(func, *args, **kwargs), get_running_loop())
    thread.start()
    ok, result = await thread.wait()
    if not ok:
        raise result

    return result


async def semaphore_gather(n: int, *tasks: Coroutine) -> list:
    """
    Like asyncio.gather, but limited to n concurrent tasks.

    :param n: the maximum number of concurrent tasks
    :param tasks: the coroutines to run
    :return: a list containing the results of all coroutines
    """

    semaphore = Semaphore(n)

    async def inner(t):
        async with semaphore:
            return await t

    return list(await gather(*map(inner, tasks)))


class LockDeco:
    """Decorator for synchronisation of async functions"""

    def __init__(self, func):
        self.lock = Lock()
        self.func = func
        update_wrapper(self, func)

    async def __call__(self, *args, **kwargs):
        async with self.lock:
            return await self.func(*args, **kwargs)


def run_as_task(func):
    """
    Decorator for async functions.
    Instead of calling the decorated function directly, this will create a task for it and return immediately.
    """

    @wraps(func)
    async def inner(*args, **kwargs):
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
    result: list[tuple[int, bool, T]] = []

    async def inner(i: int, coro: Awaitable[T]):
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
        raise GatherAnyError(idx, value)

    return idx, value

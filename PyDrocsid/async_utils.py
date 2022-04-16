"""This module provides various utilities for working with asynchronous functions."""

from asyncio import Event, Lock, Semaphore, create_task, gather, get_event_loop
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
from typing import Any, Awaitable, Callable, ParamSpec, TypeVar, cast


T = TypeVar("T")
P = ParamSpec("P")

executor = ThreadPoolExecutor()


def run_in_thread(func: Callable[..., T]) -> Callable[..., Awaitable[T]]:
    """Convert a synchronous function to an asynchronous one by running it in a thread.

    Example:
        ```pycon
        >>> @run_in_thread
        ... def test(x):
        ...     return x + 1
        ...
        >>> await test(1)
        2
        ```

    Args:
        func: The synchronous function.

    Returns:
        The converted asynchronous function.
    """

    @wraps(func)
    async def inner(*args: Any, **kwargs: Any) -> T:
        return await get_event_loop().run_in_executor(executor, lambda: func(*args, **kwargs))

    return inner


async def semaphore_gather(max_concurrency: int, *coroutines: Awaitable[T]) -> list[T]:
    """Run a list of coroutines in parallel (like [`asyncio.gather`][]), while limiting the number of concurrent tasks.

    Example:
        ```pycon
        >>> import asyncio
        >>>
        >>> async def test(n):
        ...     print(f"{n} started")
        ...     await asyncio.sleep(n)
        ...     print(f"{n} done")
        ...     return n
        ...
        >>> await semaphore_gather(2, test(1), test(2), test(3))
        1 started
        2 started
        1 done
        3 started
        2 done
        3 done
        [1, 2, 3]
        ```

    Args:
        max_concurrency: The maximum number of concurrent tasks.
        *coroutines: The coroutines to run.

    Returns:
        A list containing the results of all coroutines.
    """

    semaphore = Semaphore(max_concurrency)

    async def inner(t: Awaitable[T]) -> T:
        async with semaphore:
            return await t

    return list(await gather(*map(inner, coroutines)))


def lock_deco(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
    """Decorate an async function to allow only one concurrent execution.

    Example:
        ```pycon
        >>> import asyncio
        >>>
        >>> @lock_deco
        >>> async def test():
        ...     print("test started")
        ...     await asyncio.sleep(1)
        ...     print("test done")
        ...     return 42
        ...
        >>> await asyncio.gather(test(), test())
        test started
        test done
        test started
        test done
        [42, 42]
        ```

    Args:
        func: The function to decorate.

    Returns:
        The decorated function.
    """

    lock = Lock()

    @wraps(func)
    async def inner(*args: Any, **kwargs: Any) -> T:
        async with lock:
            return await func(*args, **kwargs)

    return inner


def run_as_task(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[None]]:
    """Decorate an async function to run it as a task and return immediately.

    Example:
        ```pycon
        >>> import asyncio
        >>>
        >>> @run_as_task
        ... async def test():
        ...     await asyncio.sleep(1)
        ...     print("test done")
        ...
        >>> async def main():
        ...     await test()  # returns immediately
        ...     print("main done")
        ...
        >>> await main()
        main done
        test done
        ```

    !!! Warning
        The return value of the original function is ignored and impossible to retrieve.

    Args:
        func: The function to run as a task.

    Returns:
        An async function that runs `func` as a task and immediately returns `None`.
    """

    @wraps(func)
    async def inner(*args: Any, **kwargs: Any) -> None:
        create_task(func(*args, **kwargs))

    return inner


class GatherAnyError(Exception):
    """Raised by [`gather_any`][PyDrocsid.async_utils.gather_any] if any of the coroutines raised an exception.

    Attributes:
        idx (int): The index of the coroutine that raised the exception.
        exception (Exception): The exception that was raised.
    """

    idx: int
    exception: Exception

    def __init__(self, idx: int, exception: Exception):
        """
        Args:
            idx: The index of the coroutine that raised the exception.
            exception: The exception that was raised.
        """

        self.idx = idx
        self.exception = exception


async def gather_any(*coroutines: Awaitable[T]) -> tuple[int, T]:
    """Run a list of coroutines in parallel (like [`asyncio.gather`][]) until the first one finishes.

    Once the first coroutine is done, the rest of the coroutines are cancelled.
    If the coroutine raises an exception, a [`GatherAnyError`][PyDrocsid.async_utils.GatherAnyError] is raised.

    Example:
        ```pycon
        >>> import asyncio
        >>>
        >>> async def test(n):
        ...     print(f"{n} started")
        ...     await asyncio.sleep(n)
        ...     print(f"{n} done")
        ...     return f"coro {n}"
        ...
        >>> await gather_any(test(1), test(2), test(3))
        1 started
        2 started
        3 started
        1 done
        (0, 'coro 1')
        ```

    Args:
        *coroutines: The coroutines to run.

    Returns:
        A tuple containing the index of the coroutine that finished first and its result.

    Raises:
        GatherAnyError: If any of the coroutines raised an exception.
    """

    event = Event()
    result: list[tuple[int, bool, T | Exception]] = []

    async def inner(i: int, coro: Awaitable[T]) -> None:
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

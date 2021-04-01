import asyncio
import threading
from asyncio import Semaphore, Lock

from functools import partial, update_wrapper, wraps


class Thread(threading.Thread):
    def __init__(self, func, loop):
        super().__init__()
        self._return = None
        self._func = func
        self._event = asyncio.Event()
        self._loop = loop

    async def wait(self):
        await self._event.wait()
        return self._return

    def run(self):
        try:
            self._return = True, self._func()
        except Exception as e:  # skipcq: PYL-W0703
            self._return = False, e
        self._loop.call_soon_threadsafe(self._event.set)


async def run_in_thread(func, *args, **kwargs):
    thread = Thread(partial(func, *args, **kwargs), asyncio.get_running_loop())
    thread.start()
    ok, result = await thread.wait()
    if not ok:
        raise result

    return result


async def semaphore_gather(n, *tasks):
    semaphore = Semaphore(n)

    async def inner(t):
        async with semaphore:
            return await t

    return await asyncio.gather(*map(inner, tasks))


class LockDeco:
    def __init__(self, func):
        self.lock = Lock()
        self.func = func
        update_wrapper(self, func)

    async def __call__(self, *args, **kwargs):
        async with self.lock:
            return await self.func(*args, **kwargs)


def run_as_task(func):
    @wraps(func)
    async def inner(*args, **kwargs):
        asyncio.create_task(func(*args, **kwargs))

    return inner

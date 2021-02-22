import asyncio
import threading

from functools import partial


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

from asyncio import Lock
from typing import TypeVar

T = TypeVar("T")


class MultiLock:
    """Container for multiple async locks which automatically deletes unused locks"""

    def __init__(self):
        self.locks: dict[T, Lock] = {}
        self.requests: dict[T, int] = {}

    def __getitem__(self, key: T):
        multilock: MultiLock = self

        class LockContext:
            async def __aenter__(self, *_):
                if key is not None:
                    await multilock.acquire(key)

            async def __aexit__(self, *_):
                if key is not None:
                    multilock.release(key)

        return LockContext()

    async def acquire(self, key: T):
        lock: Lock = self.locks.setdefault(key, Lock())
        self.requests[key] = self.requests.get(key, 0) + 1
        await lock.acquire()

    def release(self, key: T):
        lock: Lock = self.locks[key]
        lock.release()
        self.requests[key] -= 1
        if not self.requests[key]:
            self.locks.pop(key)
            self.requests.pop(key)

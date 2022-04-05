from __future__ import annotations

from asyncio import Lock
from typing import Any, Generic, TypeVar


T = TypeVar("T")


class _LockContext(Generic[T]):
    def __init__(self, multilock: MultiLock[T], key: T):
        self.multilock = multilock
        self.key = key

    async def __aenter__(self, *_: Any) -> None:
        if self.key is not None:
            await self.multilock.acquire(self.key)

    async def __aexit__(self, *_: Any) -> None:
        if self.key is not None:
            self.multilock.release(self.key)


class MultiLock(Generic[T]):
    """Container for multiple async locks which automatically deletes unused locks"""

    def __init__(self) -> None:
        self.locks: dict[T, Lock] = {}
        self.requests: dict[T, int] = {}

    def __getitem__(self, key: T) -> _LockContext[T]:
        return _LockContext(self, key)

    async def acquire(self, key: T) -> None:
        lock: Lock = self.locks.setdefault(key, Lock())
        self.requests[key] = self.requests.get(key, 0) + 1
        await lock.acquire()

    def release(self, key: T) -> None:
        lock: Lock = self.locks[key]
        lock.release()
        self.requests[key] -= 1
        if not self.requests[key]:
            self.locks.pop(key)
            self.requests.pop(key)

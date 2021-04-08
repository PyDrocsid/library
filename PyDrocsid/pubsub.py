import asyncio
import sys
from typing import Awaitable, Callable

from PyDrocsid.config import Config


class PubSubChannel:
    def __init__(self):
        self._subscriptions: list[Callable[..., Awaitable]] = []

    async def publish(self, *args, **kwargs) -> list:
        result = await asyncio.gather(*[sub(*args, **kwargs) for sub in self._subscriptions])
        return [r for r in result if r is not None]

    __call__ = publish

    @property
    def subscribe(self):
        channel: PubSubChannel = self

        class Subscription:
            def __init__(self, func):
                channel._subscriptions.append(self)
                self._func = func
                self._cls = None

            async def __call__(self, *args, **kwargs):
                if not self._cls.instance:
                    return

                if sys.modules[self._cls.__module__].__package__ in Config.ENABLED_COG_PACKAGES:
                    return await self._func(self._cls.instance, *args, **kwargs)

            def __set_name__(self, owner, name):
                self._cls = owner

        return Subscription

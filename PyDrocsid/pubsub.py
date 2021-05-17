import asyncio
import sys
from typing import Awaitable, Callable

from PyDrocsid.config import Config


class PubSubChannel:
    """Publish-Subscribe channel for inter cog communication"""

    def __init__(self):
        self._subscriptions: list[Callable[..., Awaitable]] = []

    async def publish(self, *args, **kwargs) -> list:
        """
        Publish a message to this channel. This will call all subscriptions and return
        a list of their return values (if they don't return None).
        """

        result: tuple = await asyncio.gather(*[sub(*args, **kwargs) for sub in self._subscriptions])
        return [r for r in result if r is not None]

    # calling the PubSubChannel object directly (like a function) also publishes a message
    __call__ = publish

    @property
    def subscribe(self):
        """
        Decorator for async functions to register them as subscriptions of this channel.
        Can only be used on methods of Cog classes.
        """

        channel: PubSubChannel = self

        class Subscription:
            def __init__(self, func):
                channel._subscriptions.append(self)
                self._func = func  # callback function
                self._cls = None  # cog class

            async def __call__(self, *args, **kwargs):
                # ignore unused cogs
                if not self._cls.instance:
                    return

                # ignore disabled cogs
                if sys.modules[self._cls.__module__].__package__ in Config.ENABLED_COG_PACKAGES:
                    return await self._func(self._cls.instance, *args, **kwargs)

            def __set_name__(self, owner, name):
                # get the cog class the decorated function is defined in
                self._cls = owner

        return Subscription

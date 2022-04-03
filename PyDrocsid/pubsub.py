from __future__ import annotations

import asyncio
import sys
from typing import Awaitable, Callable, Generic, ParamSpec, Type, TypeVar

from PyDrocsid.cog import Cog
from PyDrocsid.config import Config
from PyDrocsid.database import db_context


PubSubArgs = ParamSpec("PubSubArgs")
PubSubResult = TypeVar("PubSubResult")


class Subscription(Generic[PubSubArgs, PubSubResult]):
    channel: PubSubChannel[PubSubArgs, PubSubResult]

    # TODO use Concatenate once mypy supports it
    def __init__(self, func: Callable[..., Awaitable[PubSubResult | None]]) -> None:
        self._func = func  # callback function
        self._cls: Type[Cog] | None = None  # cog class

        self.channel.register(self)

    async def __call__(self, *args: PubSubArgs.args, **kwargs: PubSubArgs.kwargs) -> PubSubResult | None:
        # ignore unused cogs
        if not self._cls or not self._cls.instance:
            return None

        # ignore disabled cogs
        if sys.modules[self._cls.__module__].__package__ not in Config.ENABLED_COG_PACKAGES:
            return None

        async with db_context():
            return await self._func(self._cls.instance, *args, **kwargs)

    def __set_name__(self, owner: Type[Cog], name: str) -> None:
        # get the cog class the decorated function is defined in
        self._cls = owner


class PubSubChannel(Generic[PubSubArgs, PubSubResult]):
    """Publish-Subscribe channel for inter cog communication"""

    def __init__(self) -> None:
        self._subscriptions: list[Callable[PubSubArgs, Awaitable[PubSubResult | None]]] = []

    async def publish(self, *args: PubSubArgs.args, **kwargs: PubSubArgs.kwargs) -> list[PubSubResult]:
        """
        Publish a message to this channel. This will call all subscriptions and return
        a list of their return values (if they don't return None).
        """

        result = await asyncio.gather(*[sub(*args, **kwargs) for sub in self._subscriptions])
        return [r for r in result if r is not None]

    # calling the PubSubChannel object directly (like a function) also publishes a message
    __call__ = publish

    @property
    def subscribe(self) -> Type[Subscription[PubSubArgs, PubSubResult]]:
        """
        Decorator for async functions to register them as subscriptions of this channel.
        Can only be used on methods of Cog classes.
        """

        class Sub(Subscription[PubSubArgs, PubSubResult]):  # type: ignore
            channel = self

        return Sub

    def register(self, subscription: Subscription[PubSubArgs, PubSubResult]) -> None:
        self._subscriptions.append(subscription)

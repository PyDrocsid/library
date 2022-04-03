from __future__ import annotations

import re
import sys
from datetime import datetime
from typing import Any, Awaitable, Callable, Type, cast
from urllib.parse import urljoin

from discord import Guild, Invite, Member, Message, PartialEmoji, RawMessageDeleteEvent, Role, Thread, VoiceState
from discord.abc import Messageable, User
from discord.ext.commands.bot import Bot
from discord.ext.commands.cog import Cog as DiscordCog
from discord.ext.commands.context import Context
from discord.ext.commands.core import Command
from discord.ext.commands.errors import CommandError

from PyDrocsid.config import Config
from PyDrocsid.environment import DISABLED_COGS
from PyDrocsid.events import event_handlers, register_events
from PyDrocsid.logger import get_logger


logger = get_logger(__name__)


class Cog(DiscordCog):
    CONTRIBUTORS: list[tuple[int, str]]
    DEPENDENCIES: list[Type[Cog]] = []

    instance: Cog | None = None
    bot: Bot

    def __new__(cls, *args: Any, **kwargs: Any) -> Cog:
        """Make sure there exists only one instance of a cog."""

        if cls.instance is None:
            cls.instance = super().__new__(cls, *args, **kwargs)

            # set instance attribute of this and potential base classes
            c: Type[Cog]
            for c in cls.mro():
                if c is Cog:
                    break

                c.instance = c.instance or cls.instance

        return cls.instance

    @staticmethod
    def prepare() -> bool:
        """
        Prepare a cog and return whether the cog can be added to the bot.
        If this method returns False, the cog will be disabled.
        """

        return True

    # Event Handlers

    async def on_ready(self) -> None:
        pass

    async def on_typing(self, channel: Messageable, user: User | Member, when: datetime) -> None:
        pass

    async def on_self_message(self, message: Message) -> None:
        pass

    async def on_message(self, message: Message) -> None:
        pass

    async def on_bot_ping(self, message: Message) -> None:
        pass

    async def on_message_delete(self, message: Message) -> None:
        pass

    async def on_raw_message_delete(self, event: RawMessageDeleteEvent) -> None:
        pass

    async def on_message_edit(self, before: Message, after: Message) -> None:
        pass

    async def on_raw_message_edit(self, channel: Messageable, message: Message) -> None:
        pass

    async def on_raw_reaction_add(self, message: Message, emoji: PartialEmoji, user: User | Member) -> None:
        pass

    async def on_raw_reaction_remove(self, message: Message, emoji: PartialEmoji, user: User | Member) -> None:
        pass

    async def on_raw_reaction_clear(self, message: Message) -> None:
        pass

    async def on_raw_reaction_clear_emoji(self, message: Message, emoji: PartialEmoji) -> None:
        pass

    async def on_member_join(self, member: Member) -> None:
        pass

    async def on_member_remove(self, member: Member) -> None:
        pass

    async def on_member_nick_update(self, before: str, after: str) -> None:
        pass

    async def on_member_role_add(self, after: Member, role: Role) -> None:
        pass

    async def on_member_role_remove(self, after: Member, role: Role) -> None:
        pass

    async def on_user_update(self, before: User, after: User) -> None:
        pass

    async def on_voice_state_update(self, member: Member, before: VoiceState, after: VoiceState) -> None:
        pass

    async def on_member_ban(self, guild: Guild, user: User | Member) -> None:
        pass

    async def on_member_unban(self, guild: Guild, user: User) -> None:
        pass

    async def on_invite_create(self, invite: Invite) -> None:
        pass

    async def on_invite_delete(self, invite: Invite) -> None:
        pass

    async def on_command_error(self, ctx: Context[Bot], error: CommandError) -> None:
        pass

    async def on_thread_join(self, thread: Thread) -> None:
        pass


def check_dependencies(cogs: list[Cog]) -> set[Type[Cog]]:
    """
    Make sure all cog dependencies are met by recursively disabling cogs with unsatisfied dependencies.

    :param cogs: list of available cogs
    :return: set of disabled cog classes
    """

    # set of available cogs
    available: set[Type[Cog]] = {type(cog) for cog in cogs}

    # reverse dependency graph
    # required_by maps cog x to a list of cogs that depend on x
    required_by: dict[Type[Cog], list[Cog]] = {}
    for cog in cogs:
        for dep in cog.DEPENDENCIES:
            required_by.setdefault(dep, []).append(cog)

    # set of disabled cogs
    disabled: set[Type[Cog]] = set()

    # list of unsatisfied dependencies
    not_available: list[Type[Cog]] = [dependency for dependency in required_by if dependency not in available]

    # remove all unsatisfied dependencies by disabling all cogs that depend on them
    while not_available:
        # get a dependency and remove it from the list
        dependency: Type[Cog] = not_available.pop()

        # continue if no cog depends on it
        if dependency not in required_by:
            continue

        # iterate over list of cogs that depend on this dependency
        for cog in required_by[dependency]:
            # skip already disabled cogs
            if type(cog) in disabled:
                continue

            # disable cog
            logger.warning(
                "Cog '%s' has been disabled because the dependency '%s' is missing.",
                cog.__class__.__name__,
                dependency.__name__,
            )
            disabled.add(type(cog))

            # add cog to list of unsatisfied dependency, as this cog is no longer available
            # but may still be required by other cogs
            not_available.append(type(cog))

    return disabled


def register_cogs(bot: Bot, *cogs: Cog) -> None:
    """Add cogs to the bot."""

    register_events(bot)

    for cog in cogs:
        cog.bot = bot

        # iterate over attributes of cog to find event handlers
        for e in dir(Cog):
            func: Callable[..., Awaitable[None]] = getattr(cog, e)

            # event handlers must differ from the default handler defined in Cog
            if e.startswith("on_") and callable(func) and getattr(type(cog), e) is not getattr(Cog, e):
                # register the event handler
                event_handlers.setdefault(e[3:], []).append(func)

        bot.add_cog(cog)

        # load metadata from cog and its base classes
        cls: Type[Cog]
        for cls in cog.__class__.mro():
            if cls is Cog:
                break

            Config.CONTRIBUTORS.update(cls.CONTRIBUTORS)
            Config.ENABLED_COG_PACKAGES.add(cast(str, sys.modules[cls.__module__].__package__))


def load_cogs(bot: Bot, *cogs: Cog) -> None:
    """Load and prepare cogs, resolve dependencies and add cogs to the bot."""

    disabled_cogs: list[Cog] = []
    enabled_cogs: list[Cog] = []

    # divide cogs into lists of enabled and disabled cogs
    for cog in cogs:
        if cog.__class__.__name__.lower() in DISABLED_COGS or not cog.prepare():
            disabled_cogs.append(cog)
            continue

        enabled_cogs.append(cog)

    # disable cogs due to unsatisfied dependencies
    disabled: set[Type[Cog]] = check_dependencies(enabled_cogs)
    disabled_cogs += [cog for cog in enabled_cogs if type(cog) in disabled]
    enabled_cogs = [cog for cog in enabled_cogs if type(cog) not in disabled]

    # register remaining cogs
    register_cogs(bot, *enabled_cogs)

    if bot.cogs:
        logger.info("\033[1m\033[32m%s Cog%s enabled:\033[0m", len(bot.cogs), "s" * (len(bot.cogs) > 1))
        for _cog in bot.cogs.values():
            commands = ", ".join(cmd.name for cmd in cast(list[Command[Cog, Any, Any]], _cog.get_commands()))
            logger.info(" + %s %s", _cog.__class__.__name__, commands and f"({commands})")

    if disabled_cogs:
        logger.info("\033[1m\033[31m%s Cog%s disabled:\033[0m", len(disabled_cogs), "s" * (len(disabled_cogs) > 1))
        for name in disabled_cogs:
            logger.info(" - %s", name.__class__.__name__)


def get_documentation(cog: Cog | Type[Cog]) -> str | None:
    if isinstance(cog, Cog):
        cog = type(cog)

    for cls in cog.mro():
        if match := re.match(r"^cogs\.[a-zA-Z\d\-_]+\.([a-zA-Z\d\-_]+)\.([a-zA-Z\d\-_]+)\.cog$", cls.__module__):
            return urljoin(Config.DOCUMENTATION_URL, f"cogs/{match.group(1)}/{match.group(2)}/")

    return None

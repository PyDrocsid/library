import re
from datetime import datetime
from functools import partial
from typing import Any, Awaitable, Callable, Coroutine, Iterable, ParamSpec, TypeVar, cast

from discord import (
    ClientUser,
    Guild,
    Invite,
    Member,
    Message,
    NotFound,
    PartialEmoji,
    RawMessageDeleteEvent,
    RawMessageUpdateEvent,
    RawReactionActionEvent,
    RawReactionClearEmojiEvent,
    RawReactionClearEvent,
    Role,
    TextChannel,
    Thread,
    User,
    VoiceState,
)
from discord.abc import Messageable
from discord.ext.commands.bot import Bot
from discord.ext.commands.context import Context
from discord.ext.commands.errors import CommandError

from PyDrocsid.command_edit import handle_delete, handle_edit
from PyDrocsid.database import db_wrapper
from PyDrocsid.multilock import MultiLock


T = TypeVar("T")
P = ParamSpec("P")


class StopEventHandling(Exception):  # noqa: N818
    """Raise this exception to prevent remaining event handlers from handling the current event."""

    pass


ReactionEventData = tuple[Message, PartialEmoji, User | Member]


async def extract_from_raw_reaction_event(bot: Bot, event: RawReactionActionEvent) -> ReactionEventData | None:
    """
    Extract message, emoji and user from any RawReactionActionEvent.

    :param bot: the bot instance
    :param event: the RawReactionActionEvent
    :return: a (message, emoji, user) tuple or None, if any of these entities does not exist
    """

    channel = cast(Messageable | None, bot.get_channel(event.channel_id))
    if channel is None:
        return None

    user: User | Member | None
    if isinstance(channel, TextChannel):
        # guild channel
        user = channel.guild.get_member(event.user_id)
    else:
        # direct message
        user = bot.get_user(event.user_id)

    if user is None:
        return None

    try:
        message = await channel.fetch_message(event.message_id)
    except NotFound:
        return None

    return message, event.emoji, user


class Events:
    """
    Collection of all registrable event handlers
    For a more detailed documentation on these events, please refer to
    https://discordpy.readthedocs.io/en/latest/ext/commands/api.html#event-reference
    """

    @staticmethod
    async def on_ready(_: Bot) -> None:
        await call_event_handlers("ready")

    @staticmethod
    async def on_typing(_: Bot, channel: Messageable, user: User | Member, when: datetime) -> None:
        await call_event_handlers("typing", channel, user, when, identifier=user.id)

    @staticmethod
    async def on_message(bot: Bot, message: Message) -> None:
        if message.author == bot.user:
            await call_event_handlers("self_message", message, identifier=message.id)
            return

        if not await call_event_handlers("message", message, identifier=message.id):
            return

        # detect whether the message contains just a mention of the bot
        # and call the bot_ping event
        if match := re.match(r"^<@[&!]?(\d+)>$", message.content.strip()):
            mentions = {cast(ClientUser, bot.user).id}

            # find managed role of this bot
            if message.guild is not None:
                for role in message.guild.me.roles:  # type: Role
                    if role.managed:
                        mentions.add(role.id)

            # call bot_ping if bot has been mentioned
            if int(match.group(1)) in mentions:
                await call_event_handlers("bot_ping", message, identifier=message.id)
                return

        await bot.process_commands(message)

    @staticmethod
    async def on_message_delete(bot: Bot, message: Message) -> None:
        await call_event_handlers("message_delete", message, identifier=message.id)

        # delete bot responses if message contained a command
        await handle_delete(bot, message.channel.id, message.id)

    @staticmethod
    async def on_raw_message_delete(bot: Bot, event: RawMessageDeleteEvent) -> None:
        if event.cached_message is not None:
            return

        await call_event_handlers("raw_message_delete", event, identifier=event.message_id)

        # delete bot responses if message contained a command
        await handle_delete(bot, event.channel_id, event.message_id)

    @staticmethod
    async def on_message_edit(bot: Bot, before: Message, after: Message) -> None:
        if before.content != after.content:
            await handle_edit(bot, after)

        await call_event_handlers("message_edit", before, after, identifier=after.id)

        if before.content != after.content and not after.author.bot:
            await bot.process_commands(after)

    @staticmethod
    async def on_raw_message_edit(bot: Bot, event: RawMessageUpdateEvent) -> None:
        if event.cached_message is not None:
            return

        prepared = []

        async def prepare() -> tuple[Messageable, Message] | None:
            """Extract channel and message from event"""

            channel = cast(Messageable | None, bot.get_channel(event.channel_id))
            if channel is None:
                return None

            try:
                message: Message = await channel.fetch_message(event.message_id)
            except NotFound:
                return None

            # delete bot responses if old message contained a command
            await handle_edit(bot, message)
            prepared.append(message)
            return channel, message

        await call_event_handlers("raw_message_edit", identifier=event.message_id, prepare=prepare)

        if not prepared:
            return

        msg = prepared.pop()
        if not msg.author.bot:
            # execute command if new message contains one
            await bot.process_commands(msg)

    @staticmethod
    async def on_raw_reaction_add(bot: Bot, event: RawReactionActionEvent) -> None:
        async def prepare() -> ReactionEventData | None:
            return await extract_from_raw_reaction_event(bot, event)

        await call_event_handlers("raw_reaction_add", identifier=event.message_id, prepare=prepare)

    @staticmethod
    async def on_raw_reaction_remove(bot: Bot, event: RawReactionActionEvent) -> None:
        async def prepare() -> ReactionEventData | None:
            return await extract_from_raw_reaction_event(bot, event)

        await call_event_handlers("raw_reaction_remove", identifier=event.message_id, prepare=prepare)

    @staticmethod
    async def on_raw_reaction_clear(bot: Bot, event: RawReactionClearEvent) -> None:
        async def prepare() -> tuple[Message] | None:
            """Extract message from event."""

            channel = cast(Messageable | None, bot.get_channel(event.channel_id))
            if channel is None:
                return None

            try:
                return (await channel.fetch_message(event.message_id),)
            except NotFound:
                return None

        await call_event_handlers("raw_reaction_clear", identifier=event.message_id, prepare=prepare)

    @staticmethod
    async def on_raw_reaction_clear_emoji(bot: Bot, event: RawReactionClearEmojiEvent) -> None:
        async def prepare() -> tuple[Message, PartialEmoji] | None:
            """Extract message and emoji from event."""

            channel = cast(Messageable | None, bot.get_channel(event.channel_id))
            if channel is None:
                return None

            try:
                return await channel.fetch_message(event.message_id), event.emoji
            except NotFound:
                return None

        await call_event_handlers("raw_reaction_clear_emoji", identifier=event.message_id, prepare=prepare)

    @staticmethod
    async def on_member_join(_: Bot, member: Member) -> None:
        await call_event_handlers("member_join", member, identifier=member.id)

    @staticmethod
    async def on_member_remove(_: Bot, member: Member) -> None:
        await call_event_handlers("member_remove", member, identifier=member.id)

    @staticmethod
    async def on_member_update(_: Bot, before: Member, after: Member) -> None:
        # check if nickname has been updated
        if before.nick != after.nick:
            await call_event_handlers("member_nick_update", before, after, identifier=before.id)

        # check if roles have been added or removed
        roles_before = set(before.roles)
        roles_after = set(after.roles)
        for role in roles_before:
            if role not in roles_after:
                await call_event_handlers("member_role_remove", after, role, identifier=before.id)
        for role in roles_after:
            if role not in roles_before:
                await call_event_handlers("member_role_add", after, role, identifier=before.id)

    @staticmethod
    async def on_user_update(_: Bot, before: User, after: User) -> None:
        await call_event_handlers("user_update", before, after, identifier=before.id)

    @staticmethod
    async def on_voice_state_update(_: Bot, member: Member, before: VoiceState, after: VoiceState) -> None:
        await call_event_handlers("voice_state_update", member, before, after, identifier=member.id)

    @staticmethod
    async def on_member_ban(_: Bot, guild: Guild, user: User | Member) -> None:
        await call_event_handlers("member_ban", guild, user, identifier=user.id)

    @staticmethod
    async def on_member_unban(_: Bot, guild: Guild, user: User) -> None:
        await call_event_handlers("member_unban", guild, user, identifier=user.id)

    @staticmethod
    async def on_invite_create(_: Bot, invite: Invite) -> None:
        await call_event_handlers("invite_create", invite, identifier=invite.code)

    @staticmethod
    async def on_invite_delete(_: Bot, invite: Invite) -> None:
        await call_event_handlers("invite_delete", invite, identifier=invite.code)

    @staticmethod
    async def on_command_error(_: Bot, ctx: Context[Bot], error: CommandError) -> None:
        await call_event_handlers("command_error", ctx, error, identifier=ctx.message.id)

    @staticmethod
    async def on_thread_join(_: Bot, thread: Thread) -> None:
        await call_event_handlers("thread_join", thread, identifier=thread.id)


event_handlers: dict[str, list[Callable[..., Awaitable[None]]]] = {}
handler_lock = MultiLock[Any]()

AsyncFunc = TypeVar("AsyncFunc", bound=Callable[..., Awaitable[None]])


def listener(func: AsyncFunc) -> AsyncFunc:
    """Decorator for registering a new event handler."""

    name: str = func.__name__
    if not name.startswith("on_"):
        raise Exception("Invalid listener name")
    event_handlers.setdefault(name[3:], []).append(func)
    return func


async def call_event_handlers(
    event: str, *args: Any, identifier: Any = None, prepare: Callable[[], Awaitable[Iterable[Any] | None]] | None = None
) -> bool:
    """
    Call handlers for a given event.

    :param event: the name of the event
    :param args: positional arguments to pass to the event handler
    :param identifier: synchronisation identifier of this event (two different events with the same
                       identifier cannot be handled simultaneously)
    :param prepare: async function that is called before handling this event. If this function returns
                    None, the event is ignored. Otherwise the iterable this function must return
                    is passed to the event handlers as a list of positional arguments.
    :return: True if all handlers for this event have been called without raising StopEventHandling, otherwise False
    """

    identifier = (event, identifier) if identifier is not None else None
    async with handler_lock[identifier]:
        if prepare is not None:
            if (prep_args := await prepare()) is None:
                return False

            args = tuple(prep_args)

        for handler in event_handlers.get(event, []):
            try:
                await handler(*args)
            except StopEventHandling:
                return False
            except PermissionError as e:
                if event == "permission_error":
                    raise

                await call_event_handlers("permission_error", *e.args, identifier=("permission_error", identifier))

        return True


def register_events(bot: Bot) -> None:
    """Register all events defined in Events class"""

    for e in dir(Events):
        # TODO use ParamSpec once mypy supports it
        func: Callable[..., Awaitable[None]] = getattr(Events, e)
        if e.startswith("on_") and callable(func):
            # always wrap event handlers in database sessions and pass the bot instance as first argument
            handler: Callable[..., Awaitable[None]] = partial(db_wrapper(func), bot)
            handler.__name__ = e

            # TODO use ParamSpec once mypy supports it
            bot.event(cast(Callable[..., Coroutine[None, None, None]], handler))

from __future__ import annotations

from typing import Any, Callable, TypeVar

from discord import (
    ButtonStyle,
    Embed,
    Forbidden,
    Interaction,
    InteractionResponse,
    Member,
    Message,
    TextChannel,
    Thread,
    User,
    ui,
)
from discord.abc import Messageable
from discord.ext.commands.bot import Bot
from discord.ext.commands.context import Context
from discord.ext.commands.core import Command
from discord.ext.commands.errors import CommandError

from PyDrocsid.cog import Cog
from PyDrocsid.command_edit import link_response
from PyDrocsid.emojis import name_to_emoji
from PyDrocsid.environment import MENTION_AUTHOR, REPLY
from PyDrocsid.events import call_event_handlers
from PyDrocsid.material_colors import MaterialColors
from PyDrocsid.permission import BasePermission
from PyDrocsid.translations import t
from PyDrocsid.util import check_message_send_permissions


t = t.g


class UserCommandError(CommandError):
    def __init__(self, user: User | Member, message: str | None = None, *args: Any):
        super().__init__(message, *args)
        self.user = user


Func = TypeVar("Func", bound=Any)


def command_emoji(emoji: str) -> Callable[[Func], Func]:
    def deco(f: Func) -> Func:
        f.emoji = emoji
        return f

    return deco


def no_documentation(f: Func) -> Func:
    f.no_documentation = True
    return f


def docs(text: str) -> Callable[[Func], Func]:
    """Decorator for setting the docstring of a function."""

    def deco(f: Func) -> Func:
        f.__doc__ = text
        return f

    return deco


def optional_permissions(*permissions: BasePermission) -> Callable[[Func], Func]:
    """Decorator for setting optional permissions of a command."""

    def deco(f: Func) -> Func:
        f.optional_permissions = list(permissions)
        return f

    return deco


def get_optional_permissions(command: Command[Cog, Any, Any]) -> list[BasePermission]:
    """Get the optional permissions of a given command, set by the optional_permissions decorator."""

    return getattr(command.callback, "optional_permissions", [])


def make_error(message: str, user: User | Member | None = None) -> Embed:
    """
    Create an error embed with an optional author.

    :param message: the error message
    :param user: an optional user
    :return: the error embed
    """

    embed = Embed(title=t.error, colour=MaterialColors.error, description=str(message))

    if user:
        embed.set_author(name=str(user), icon_url=user.display_avatar.url)

    return embed


async def can_run_command(command: Command[Cog, Any, Any], ctx: Context[Bot]) -> bool:
    """Return whether a command can be executed in a given context."""

    try:
        return await command.can_run(ctx)
    except CommandError:
        return False


async def reply(
    ctx: Message | Messageable | InteractionResponse, *args: Any, no_reply: bool = False, **kwargs: Any
) -> Message:
    """
    Reply to a message and link response to this message.

    :param ctx: the context/message/messageable to reply to
    :param args: positional arguments to pass to ctx.send/ctx.reply
    :param no_reply: whether to use ctx.send instead of ctx.reply
    :param kwargs: keyword arguments to pass to ctx.send/ctx.reply
    :return: the message that was sent
    """

    if isinstance(ctx, InteractionResponse):
        interaction = await ctx.send_message(*args, **kwargs, ephemeral=True)
        return await interaction.original_message()

    if isinstance(channel := ctx.channel if isinstance(ctx, (Message, Context)) else ctx, TextChannel):
        try:
            check_message_send_permissions(
                channel, check_file=bool(kwargs.get("file")), check_embed=bool(kwargs.get("embed"))
            )
        except CommandError as e:
            raise PermissionError(channel.guild, e.args[0])

    msg: Message
    if REPLY and isinstance(ctx, (Context, Message)) and not no_reply:
        msg = await ctx.reply(*args, **kwargs, mention_author=MENTION_AUTHOR)
    elif isinstance(ctx, Message):
        msg = await ctx.channel.send(*args, **kwargs)
    else:
        msg = await ctx.send(*args, **kwargs)

    if isinstance(ctx, (Context, Message)):
        await link_response(ctx, msg)

    return msg


async def add_reactions(ctx: Context[Any] | Message, *emojis: str) -> None:
    """
    Add reactions to a given message.

    :param ctx: the message or context
    :param emojis: emoji names to react with
    """

    message: Message = ctx if isinstance(ctx, Message) else ctx.message

    try:
        for emoji in emojis:
            await message.add_reaction(name_to_emoji[emoji])
    except Forbidden:
        if not isinstance(message.channel, (TextChannel, Thread)):
            return

        await call_event_handlers("permission_error", ctx.guild, t.could_not_add_reaction(message.channel.mention))


class ConfirmationButton(ui.Button[ui.View]):
    def __init__(self, confirmation: Confirmation, label: str, style: ButtonStyle, disabled: bool, result: bool):
        super().__init__(label=label, style=style, disabled=disabled)

        self._confirmation = confirmation
        self._result = result

    async def callback(self, _: Any) -> None:
        await self._confirmation.callback(self._result)


class Confirmation(ui.View):
    def __init__(
        self,
        timeout: int = 20,
        danger: bool = False,
        user: User | Member | None = None,
        delete_after_confirm: int | None = 5,
        delete_after_cancel: int | None = None,
    ):
        super().__init__(timeout=timeout)

        self._danger = danger
        self._user = user
        self._delete_after_confirm = delete_after_confirm
        self._delete_after_cancel = delete_after_cancel
        self._message: Message | InteractionResponse | None = None
        self._result: bool | None = None

    async def run(
        self, channel: Message | Messageable | InteractionResponse, text: str | None = None, **kwargs: Any
    ) -> bool:
        if text:
            kwargs["embed"] = Embed(title=t.confirmation, description=text)

        if not self._user and isinstance(channel, (Message, Context)):
            self._user = channel.author
        if not self._user:
            raise ValueError("Confirmation must have a user")

        self._update_buttons()
        await self._reply(channel, **kwargs)
        await self.wait()
        self._result = result = bool(self._result)

        await self._update()

        if not isinstance(self._message, Message):
            return result

        if result and self._delete_after_confirm is not None:
            await self._message.delete(delay=self._delete_after_confirm)
        elif not result and self._delete_after_cancel is not None:
            await self._message.delete(delay=self._delete_after_cancel)

        return result

    def _update_buttons(self) -> None:
        done = self._result is not None
        buttons = [
            ConfirmationButton(
                confirmation=self,
                label=t.confirmed if self._result is True else t.confirm,
                style=ButtonStyle.danger if self._danger else ButtonStyle.success,
                disabled=done,
                result=True,
            ),
            ConfirmationButton(
                confirmation=self,
                label=t.canceled if self._result is False else t.cancel,
                style=ButtonStyle.secondary if self._danger else ButtonStyle.danger,
                disabled=done,
                result=False,
            ),
        ]

        self.clear_items()
        for button in buttons:
            self.add_item(button)

    async def _reply(self, channel: Message | Messageable | InteractionResponse, **kwargs: Any) -> Message | None:
        msg = await reply(channel, view=self, **kwargs)
        self._message = channel if isinstance(channel, InteractionResponse) else msg
        return msg

    async def _update(self) -> None:
        self._update_buttons()
        if isinstance(self._message, Message):
            await self._message.edit(view=self)
        elif isinstance(self._message, InteractionResponse):
            await self._message.edit_message(view=self)

    async def callback(self, result: bool) -> None:
        self._result = result
        self.stop()

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user == self._user:
            return True

        await interaction.response.send_message("Please do not press this button again!", ephemeral=True)
        return False

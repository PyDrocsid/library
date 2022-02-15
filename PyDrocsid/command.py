import asyncio
import time
from contextlib import asynccontextmanager
from typing import Union, cast

from PyDrocsid.async_thread import gather_any
from discord import (
    User,
    Member,
    Embed,
    Message,
    Forbidden,
    TextChannel,
    ButtonStyle,
    ui,
    NotFound,
    InteractionResponse,
    Interaction,
)
from discord.abc import Messageable
from discord.ext.commands import Command, Context, CommandError
from discord.ui import View, Button

from PyDrocsid.command_edit import link_response
from PyDrocsid.emojis import name_to_emoji
from PyDrocsid.environment import REPLY, MENTION_AUTHOR
from PyDrocsid.events import call_event_handlers
from PyDrocsid.material_colors import MaterialColors
from PyDrocsid.permission import BasePermission
from PyDrocsid.translations import t
from PyDrocsid.util import check_message_send_permissions

t = t.g


class UserCommandError(CommandError):
    def __init__(self, user: Union[Member, User], message=None, *args):
        super().__init__(message, *args)
        self.user = user


def command_emoji(emoji: str):
    def deco(f):
        f.emoji = emoji
        return f

    return deco


def no_documentation(f):
    f.no_documentation = True
    return f


def docs(text: str):
    """Decorator for setting the docstring of a function."""

    def deco(f):
        f.__doc__ = text
        return f

    return deco


def optional_permissions(*permissions: BasePermission):
    """Decorator for setting optional permissions of a command."""

    def deco(f):
        f.optional_permissions = list(permissions)
        return f

    return deco


def get_optional_permissions(command: Command) -> list[BasePermission]:
    """Get the optional permissions of a given command, set by the optional_permissions decorator."""

    return getattr(command.callback, "optional_permissions", [])


def make_error(message: str, user: Union[Member, User, None] = None) -> Embed:
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


async def can_run_command(command: Command, ctx: Context) -> bool:
    """Return whether a command can be executed in a given context."""

    try:
        return await command.can_run(ctx)
    except CommandError:
        return False


async def reply(
    ctx: Context | Message | Messageable | InteractionResponse,
    *args,
    no_reply: bool = False,
    **kwargs,
) -> Message | None:
    """
    Reply to a message and link response to this message.

    :param ctx: the context/message/messageable to reply to
    :param args: positional arguments to pass to ctx.send/ctx.reply
    :param no_reply: whether to use ctx.send instead of ctx.reply
    :param kwargs: keyword arguments to pass to ctx.send/ctx.reply
    :return: the message that was sent
    """

    if isinstance(ctx, InteractionResponse):
        await ctx.send_message(*args, **kwargs, ephemeral=True)
        return None

    if isinstance(channel := ctx.channel if isinstance(ctx, (Message, Context)) else ctx, TextChannel):
        try:
            check_message_send_permissions(
                channel,
                check_file=bool(kwargs.get("file")),
                check_embed=bool(kwargs.get("embed")),
            )
        except CommandError as e:
            raise PermissionError(channel.guild, e.args[0])

    if REPLY and isinstance(ctx, (Context, Message)) and not no_reply:
        msg = await ctx.reply(*args, **kwargs, mention_author=MENTION_AUTHOR)
    else:
        msg = await (ctx.channel if isinstance(ctx, Message) else ctx).send(*args, **kwargs)

    if isinstance(ctx, (Context, Message)):
        await link_response(ctx, msg)

    return msg


async def add_reactions(ctx: Union[Context, Message], *emojis: str):
    """
    Add reactions to a given message.

    :param ctx: the message or context
    :param emojis: emoji names to react with
    """

    message: Message = ctx if isinstance(ctx, Message) else ctx.message

    for emoji in emojis:
        try:
            await message.add_reaction(name_to_emoji[emoji])
        except Forbidden:
            await call_event_handlers("permission_error", ctx.guild, t.could_not_add_reaction(message.channel.mention))
            break


class Confirm(View):
    def __init__(self, user: Member | User, danger: bool, timeout: int, countdown: bool):
        super().__init__(timeout=timeout)

        self.user = user
        self.result = None
        self.countdown = countdown
        if countdown:
            self.set_countdown(timeout)

        if danger:
            self.children: list[Button]
            self.children[0].style = ButtonStyle.danger
            self.children[1].style = ButtonStyle.secondary

    def set_countdown(self, value: int):
        button = cast(Button, self.children[1])
        button.label = t.cancel + f" ({value})"

    async def run(self, message: Message) -> bool | None:
        async def countdown():
            timeout = cast(int, self.timeout)
            ts = time.time() + timeout
            while (delta := ts - time.time()) > 0:
                await asyncio.sleep(delta % 1)
                if delta < 1:
                    break
                self.set_countdown(int(delta))
                await gather_any(asyncio.sleep(1), message.edit(view=self))

            self.stop()

        if self.countdown:
            task = asyncio.create_task(countdown())
            await self.wait()
            task.cancel()
        else:
            await self.wait()

        if not self.result:
            cast(Button, self.children[1]).label = t.canceled

        for item in self.children:
            item.disabled = True

        try:
            await message.edit(view=self)
        except NotFound:
            return None

        return self.result

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user == self.user:
            return True

        await interaction.response.send_message("Please do not press this button again!", ephemeral=True)
        return False

    @ui.button(label=t.confirm, style=ButtonStyle.success)
    async def confirm(self, button: Button, _):
        self.result = True
        self.stop()
        button.label = t.confirmed
        cast(Button, self.children[1]).label = t.cancel

    @ui.button(label=t.cancel, style=ButtonStyle.danger)
    async def cancel(self, button: Button, _):
        self.result = False
        self.stop()
        button.label = t.canceled


@asynccontextmanager
async def confirm(ctx: Context, embed: Embed, danger: bool = False, timeout: int = 20, countdown: bool = False):
    """
    Send an embed, add confirmation reactions (:white_check_mark: and :x:) and wait for a reaction of the author.
    Yield True or False, depending on whether the author reacted with :white_check_mark: or :x:.
    Update the message if the embed has been modified and remove all reactions.
    """

    # send embed and add reactions
    view = Confirm(ctx.author, danger, timeout, countdown)
    message: Message = await reply(ctx, embed=embed, view=view)

    result = await view.run(message)

    if result is None:
        yield False, None
    else:
        yield result, message

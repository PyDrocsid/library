import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from typing import Union

from PyDrocsid.permission import BasePermission
from discord import User, Member, Embed, Message, Forbidden
from discord.abc import Messageable
from discord.ext.commands import Command, Context, CommandError

from PyDrocsid.async_thread import gather_any
from PyDrocsid.command_edit import link_response
from PyDrocsid.environment import REPLY, MENTION_AUTHOR
from PyDrocsid.material_colors import MaterialColors
from PyDrocsid.translations import t
from PyDrocsid.emojis import name_to_emoji

t = t.g


class UserCommandError(CommandError):
    def __init__(self, user: Union[Member, User], message=None, *args):
        super().__init__(message, *args)
        self.user = user


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
        embed.set_author(name=str(user), icon_url=user.avatar_url)

    return embed


async def can_run_command(command: Command, ctx: Context) -> bool:
    """Return whether a command can be executed in a given context."""

    try:
        return await command.can_run(ctx)
    except CommandError:
        return False


async def reply(ctx: Union[Context, Message, Messageable], *args, no_reply: bool = False, **kwargs) -> Message:
    """
    Reply to a message and link response to this message.

    :param ctx: the context/message/messageable to reply to
    :param args: positional arguments to pass to ctx.send/ctx.reply
    :param no_reply: whether to use ctx.send instead of ctx.reply
    :param kwargs: keyword arguments to pass to ctx.send/ctx.reply
    :return: the message that was sent
    """

    if REPLY and isinstance(ctx, (Context, Message)) and not no_reply:
        msg = await ctx.reply(*args, **kwargs, mention_author=MENTION_AUTHOR)
    else:
        msg = await (ctx.channel if isinstance(ctx, Message) else ctx).send(*args, **kwargs)

    if isinstance(ctx, (Context, Message)):
        await link_response(ctx, msg)

    return msg


@asynccontextmanager
async def confirm(ctx: Context, embed: Embed, timeout: int = 300):
    """
    Send an embed, add confirmation reactions (:white_check_mark: and :x:) and wait for a reaction of the author.
    Yield True or False, depending on whether the author reacted with :white_check_mark: or :x:.
    Update the message if the embed has been modified and remove all reactions.
    """

    # create a copy of the embed so that we can check later if it has been edited
    _embed: dict = deepcopy(embed.to_dict())

    # send embed and add reactions
    message: Message = await reply(ctx, embed=embed)
    await message.add_reaction(yes := name_to_emoji["white_check_mark"])
    await message.add_reaction(no := name_to_emoji["x"])

    # wait for either a confirmation reaction, or the deletion of the message, or the expiration of the timeout
    i, result = await gather_any(
        ctx.bot.wait_for(
            "reaction_add",
            check=lambda r, u: r.message == message and u == ctx.author and str(r) in [yes, no],
        ),
        ctx.bot.wait_for("message_delete", check=lambda msg: msg == message),
        asyncio.sleep(timeout),
    )

    if i == 0:  # confirmation reaction
        reaction, _ = result
        yield str(reaction) == yes
    else:  # message deleted or timeout expired
        yield False

    if i == 1:  # message deleted
        return

    # edit message if embed has been modified
    if embed.to_dict() != _embed:
        await message.edit(embed=embed)

    # remove reactions
    try:
        await message.clear_reactions()
    except Forbidden:
        await message.remove_reaction(yes, ctx.bot.user)
        await message.remove_reaction(no, ctx.bot.user)

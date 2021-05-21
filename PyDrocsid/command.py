import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from typing import Union

from discord import User, Member, Embed, Message, Forbidden
from discord.abc import Messageable
from discord.ext.commands import Command, Context, CommandError

from PyDrocsid.async_thread import gather_any
from PyDrocsid.command_edit import link_response
from PyDrocsid.environment import REPLY, MENTION_AUTHOR
from PyDrocsid.material_colors import MaterialColors
from PyDrocsid.translations import t
from library.PyDrocsid.emojis import name_to_emoji

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
    _embed: dict = deepcopy(embed.to_dict())
    message: Message = await reply(ctx, embed=embed)
    await message.add_reaction(yes := name_to_emoji["white_check_mark"])
    await message.add_reaction(no := name_to_emoji["x"])

    def check(r, u):
        return r.message == message and u == ctx.author and str(r) in [yes, no]

    i, result = await gather_any(
        ctx.bot.wait_for("reaction_add", check=check),
        ctx.bot.wait_for("message_delete", check=lambda msg: msg == message),
        asyncio.sleep(timeout),
    )

    if i == 0:
        reaction, _ = result
        yield str(reaction) == yes
    else:
        yield False
    if i == 1:
        return

    if embed.to_dict() != _embed:
        await message.edit(embed=embed)

    try:
        await message.clear_reactions()
    except Forbidden:
        await message.remove_reaction(yes, ctx.bot.user)
        await message.remove_reaction(no, ctx.bot.user)

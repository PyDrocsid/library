import io
import json
import re
from asyncio import create_task, gather
from copy import deepcopy
from socket import gethostbyname, socket, AF_INET, SOCK_STREAM, timeout, SHUT_RD
from time import time
from typing import Optional, List, Tuple, Union

from PyDrocsid.events import listener
from discord import Embed, Message, File, Attachment, TextChannel, Member, User, PartialEmoji, Forbidden, Role, Guild
from discord.abc import Messageable
from discord.ext.commands import Command, Context, CommandError, Bot, BadArgument, ColorConverter

from PyDrocsid.command_edit import link_response
from PyDrocsid.config import Config
from PyDrocsid.emojis import name_to_emoji
from PyDrocsid.environment import REPLY, MENTION_AUTHOR, PAGINATION_TTL, DISABLE_PAGINATION
from PyDrocsid.material_colors import MaterialColors
from PyDrocsid.permission import BasePermission
from PyDrocsid.redis import redis
from PyDrocsid.settings import Settings
from PyDrocsid.translations import t

t = t.g


class GlobalSettings(Settings):
    prefix = "."


def docs(text: str):
    """Decorator for setting the docstring of a function."""

    def deco(f):
        f.__doc__ = text
        return f

    return deco


async def get_prefix() -> str:
    """Get bot prefix."""

    return await GlobalSettings.prefix.get()


async def set_prefix(new_prefix: str):
    """Set bot prefix."""

    await GlobalSettings.prefix.set(new_prefix)


async def is_teamler(member: Member) -> bool:
    """Return whether a given member is a team member."""

    return await Config.TEAMLER_LEVEL.check_permissions(member)


class Color(ColorConverter):
    """Color converter which also supports hex codes."""

    async def convert(self, ctx, argument: str) -> Optional[int]:
        try:
            return await super().convert(ctx, argument)
        except BadArgument:
            pass

        if not re.match(r"^[0-9a-fA-F]{6}$", argument):
            raise BadArgument(t.invalid_color)
        return int(argument, 16)


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


async def check_wastebasket(
    message: Message,
    member: Member,
    emoji: PartialEmoji,
    footer: str,
    permission: BasePermission,
) -> Optional[int]:
    """
    Check if a user has reacted with :wastebasket: on an embed originally sent by the bot and if the user
    is allowed to delete or collapse this embed.

    :param message: the message the user has reacted on
    :param member: the user who added the reaction
    :param emoji: the emoji the user reacted with
    :param footer: the embed footer to search for
    :param permission: the permission required for deletion
    :return: the id of the user who originally requested this embed if the reacting user is allowed
             to delete this embed, otherwise None
    """

    if emoji.name != name_to_emoji["wastebasket"] or member.bot:
        return None

    # search all embeds for given footer
    for embed in message.embeds:
        if embed.footer.text == Embed.Empty:
            continue

        pattern = re.escape(footer).replace("\\{\\}", "{}").format(r".*?#\d{4}", r"(\d+)")  # noqa: P103
        if (match := re.match("^" + pattern + "$", embed.footer.text)) is None:
            continue

        author_id = int(match.group(1))  # id of user who originally requested this embed

        if author_id == member.id or await permission.check_permissions(member):
            # user is authorized to delete this embed
            return author_id

        # user is not authorized -> remove reaction
        try:
            await message.remove_reaction(emoji, member)
        except Forbidden:
            pass
        return None

    return None


def measure_latency() -> Optional[float]:
    """Measure latency to discord.com."""

    host = gethostbyname("discord.com")
    s = socket(AF_INET, SOCK_STREAM)
    s.settimeout(5)

    now = time()

    try:
        s.connect((host, 443))
        s.shutdown(SHUT_RD)
    except (timeout, OSError):
        return None

    return time() - now


def calculate_edit_distance(a: str, b: str) -> int:
    """Calculate edit distance (Levenshtein distance) between two strings."""

    # dp[i][j] contains edit distance between a[:i] and b[:j]
    dp: list[list[int]] = [[max(i, j) for j in range(len(b) + 1)] for i in range(len(a) + 1)]
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            dp[i][j] = min(dp[i - 1][j - 1] + (a[i - 1] != b[j - 1]), dp[i - 1][j] + 1, dp[i][j - 1] + 1)
    return dp[len(a)][len(b)]


def split_lines(text: str, max_size: int, *, first_max_size: Optional[int] = None) -> List[str]:
    """
    Split a string into a list of substrings such that each substring contains no more than max_size characters.
    To achieve this, this function first tries to split the string at line breaks. Substrings which are still too
    long are split at spaces and (only if necessary) between any two characters.

    :param text: the string
    :param max_size: maximum number of characters allowed in each substring
    :param first_max_size: optional override for max_size of first substring
    :return: list of substrings
    """

    # strip any leading or trailing spaces and newlines
    text: str = text.strip(" \n")

    # max size of current substring
    ms: int = first_max_size or max_size

    # list of substrings
    out: list[str] = []

    # current position in string
    i = 0
    while i + ms < len(text):
        # try to find a line break within the next ms + 1 characters
        j = text.rfind("\n", i, i + ms + 1)
        if j == -1:  # no line break could be found
            # try to find a space within the next ms + 1 characters
            j = text.rfind(" ", i, i + ms + 1)

        if j == -1:  # no line break or space could be found
            # split string after exactly ms characters
            j = i + ms
            out.append(text[i:j])
            i = j
        else:
            # split string after line break or space
            out.append(text[i:j])
            i = j + 1  # line break or space should not be include in next substring

        ms = max_size

    # strip leading or trailing spaces and newlines from substring and remove empty strings
    return [y for x in out + [text[i:]] if (y := x.strip(" \n"))]


async def send_long_embed(
    channel: Messageable,
    embed: Embed,
    *,
    repeat_title: bool = False,
    repeat_name: bool = False,
    paginate: bool = False,
    max_fields: int = 25,
) -> List[Message]:
    """
    Split and send a long embed in multiple messages.

    :param channel: the channel into which the messages should be sent
    :param embed: the embed to send
    :param repeat_title: whether to repeat the embed title in every embed
    :param repeat_name: whether to repeat field names in every embed
    :param paginate: whether to use pagination instead of multiple messages
    :param max_fields: the maximum number of fields an embed is allowed to have
    :return: list of all messages that have been sent
    """

    if DISABLE_PAGINATION:
        paginate = False
        max_fields = 25

    # enforce repeat_title and repeat_name when using pagination
    if paginate:
        repeat_title = True
        repeat_name = True

    # always limit max_fields to 25
    max_fields = min(max_fields, 25)

    embeds: list[Embed] = []

    def add_embed(e: Embed):
        """Copy and add an embed to the list of embeds."""

        embeds.append(Embed.from_dict(deepcopy(e.to_dict())))

    fields = embed.fields.copy()
    cur = embed.copy()
    cur.clear_fields()

    # split embed description
    *parts, last = split_lines(embed.description or "", 2048) or [""]
    for part in parts:
        cur.description = part
        add_embed(cur)
        if not repeat_title:
            cur.title = ""
            cur.remove_author()
    cur.description = last

    # add embed fields
    for field in fields:
        name: str = field.name
        value: str = field.value
        inline: bool = field.inline

        # if repeat_name is True, the text must be put into a field, which cannot contain more than 1024 characters
        # otherwise the text can be put into the embed description, which can contain 2048 characters
        max_size = 1024 if repeat_name else 2048

        # if name is not empty or the current embed already contains other fields or a description, the first part
        # of the value of this field cannot be put into the embed description. in this case must be put into an embed
        # field which is limited to 1024 characters
        # in total the embed cannot contain more than 6000 characters
        first_max_size = min(1024 if name or cur.fields or cur.description else max_size, 6000 - len(cur))

        # split field value
        *parts, last = split_lines(value, max_size, first_max_size=first_max_size)

        # create a new embed if there is not enough space for the first part of the field value
        if len(cur.fields) >= max_fields or len(cur) + len(name or "** **") + len(parts[0] if parts else last) > 6000:
            add_embed(cur)
            if not repeat_title:
                cur.title = ""
                cur.remove_author()
            cur.description = ""
            cur.clear_fields()

        # create embeds for field value substrings
        for part in parts:
            if name or cur.fields or cur.description:
                cur.add_field(name=name or "** **", value=part, inline=False)
            else:
                cur.description = part
            add_embed(cur)
            if not repeat_title:
                cur.title = ""
                cur.remove_author()
            if not repeat_name:
                name = ""
            cur.description = ""
            cur.clear_fields()

        # add last substring
        if name or cur.fields or cur.description:
            cur.add_field(name=name or "** **", value=last, inline=inline and not parts)
        else:
            cur.description = last

    add_embed(cur)

    # don't use pagination if there is only one embed
    if not paginate or len(embeds) <= 1:
        return [await reply(channel, embed=e) for e in embeds]

    # add page numbers to embed titles
    for i, embed in enumerate(embeds):
        embed.title += f" ({i+1}/{len(embeds)})"

    # send first embed and create pagination
    message = await reply(channel, embed=embeds[0])
    await create_pagination(message, embeds)
    return [message]


async def create_pagination(message: Message, embeds: list[Embed]):
    """
    Create embed pagination on a message.

    :param message: the message which should be paginated
    :param embeds: a list of embeds
    """

    key = f"pagination:channel={message.channel.id},msg={message.id}:"

    # save index, length and embeds in redis
    p = redis.pipeline()
    p.setex(key + "index", PAGINATION_TTL, 0)
    p.setex(key + "len", PAGINATION_TTL, len(embeds))
    for embed in embeds:
        p.rpush(key + "embeds", json.dumps(embed.to_dict()))
    p.expire(key + "embeds", PAGINATION_TTL)
    await p.execute()

    # add navigation reactions
    if len(embeds) > 2:
        await message.add_reaction(name_to_emoji["previous_track"])
    await message.add_reaction(name_to_emoji["arrow_backward"])
    await message.add_reaction(name_to_emoji["arrow_forward"])
    if len(embeds) > 2:
        await message.add_reaction(name_to_emoji["next_track"])


@listener
async def on_raw_reaction_add(message: Message, emoji: PartialEmoji, user: Union[User, Member]):
    """Event handler for pagination"""

    if user.bot:
        return

    key = f"pagination:channel={message.channel.id},msg={message.id}:"

    # return if cooldown is active
    if await redis.exists(key + "cooldown"):
        create_task(message.remove_reaction(emoji, user))
        return

    # return if this is no pagination message
    if not (idx := await redis.get(key + "index")) or not (length := await redis.get(key + "len")):
        return

    # enable 1 second cooldown
    await redis.setex(key + "cooldown", 1, 1)

    idx, length = int(idx), int(length)

    # determine new index
    if str(emoji) == name_to_emoji["previous_track"]:
        idx = None if idx <= 0 else 0
    elif str(emoji) == name_to_emoji["arrow_backward"]:
        idx = None if idx <= 0 else idx - 1
    elif str(emoji) == name_to_emoji["arrow_forward"]:
        idx = None if idx >= length - 1 else idx + 1
    elif str(emoji) == name_to_emoji["next_track"]:
        idx = None if idx >= length - 1 else length - 1
    else:
        return

    create_task(message.remove_reaction(emoji, user))
    if idx is None:  # click on reaction has no effect as the requested page is already visible
        return

    if not (embed_json := await redis.lrange(key + "embeds", idx, idx)):
        return

    # update index and reset redis expiration
    p = redis.pipeline()
    p.setex(key + "index", PAGINATION_TTL, idx)
    p.expire(key + "len", PAGINATION_TTL)
    p.expire(key + "embeds", PAGINATION_TTL)

    # update embed
    embed = Embed.from_dict(json.loads(embed_json[0]))
    await gather(p.execute(), message.edit(embed=embed))


async def attachment_to_file(attachment: Attachment) -> File:
    """Convert an attachment to a file"""

    file = io.BytesIO()
    await attachment.save(file)
    return File(file, filename=attachment.filename, spoiler=attachment.is_spoiler())


async def read_normal_message(bot: Bot, channel: TextChannel, author: Member) -> Tuple[str, List[File]]:
    """Read a message and return content and attachments."""

    msg: Message = await bot.wait_for("message", check=lambda m: m.channel == channel and m.author == author)
    return msg.content, [await attachment_to_file(attachment) for attachment in msg.attachments]


async def read_complete_message(message: Message) -> Tuple[str, List[File], Optional[Embed]]:
    """Extract content, attachments and embed from a given message."""

    for embed in message.embeds:
        if embed.type == "rich":
            break
    else:
        embed = None

    return message.content, [await attachment_to_file(attachment) for attachment in message.attachments], embed


async def send_editable_log(
    channel: Messageable,
    title: str,
    description: str,
    name: str,
    value: str,
    *,
    colour: Optional[int] = None,
    inline: bool = False,
    force_resend: bool = False,
    force_new_embed: bool = False,
    force_new_field: bool = False,
):
    """
    Send a log embed into a given channel which can be updated later.

    :param channel: the channel into which the messages should be sent
    :param title: the embed title
    :param description: the embed description
    :param name: the field name
    :param value: the field value
    :param colour: the embed color
    :param inline: inline parameter of embed field
    :param force_resend: whether to force a resend of the embed instead of editing it
    :param force_new_embed: whether to always send a new embed instead of extending the previous embed
    :param force_new_field: whether to always create a new field instead of editing the last field
    """

    messages: List[Message] = await channel.history(limit=1).flatten()
    if messages and messages[0].embeds and not force_new_embed:  # can extend last embed
        embed: Embed = messages[0].embeds[0]

        # if name or description don't match, a new embed must be created
        if embed.title == title and embed.description == description:

            if embed.fields and embed.fields[-1].name == name and not force_new_field:
                # can edit last field
                embed.set_field_at(index=-1, name=name, value=value, inline=inline)
            elif len(embed.fields) < 25:
                # can't edit last field -> create a new one
                embed.add_field(name=name, value=value, inline=inline)
            else:
                # can't edit last field, can't create a new one -> create a new embed
                force_new_embed = True

            if colour is not None:
                embed.colour = colour

            # update embed
            if not force_new_embed:
                if force_resend:
                    await messages[0].delete()
                    await channel.send(embed=embed)
                    return
                await messages[0].edit(embed=embed)
                return

    # create and send a new embed
    embed = Embed(title=title, description=description, colour=colour if colour is not None else 0x008080)
    embed.add_field(name=name, value=value, inline=inline)
    await channel.send(embed=embed)


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


def check_role_assignable(role: Role):
    """Check whether the bot could assign and unassign a given role."""

    guild: Guild = role.guild
    me: Member = guild.me

    if not me.guild_permissions.manage_roles:
        raise CommandError(t.role_assignment_error.no_permissions)
    if role > me.top_role:
        raise CommandError(t.role_assignment_error.higher(role, me.top_role))
    if role == me.top_role:
        raise CommandError(t.role_assignment_error.highest(role))
    if role.managed or role == guild.default_role:
        raise CommandError(t.role_assignment_error.managed_role(role))

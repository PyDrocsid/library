import io
import re
from socket import AF_INET, SHUT_RD, SOCK_STREAM, gethostbyname, socket, timeout
from time import time
from typing import Any, cast

from discord import (
    Attachment,
    Colour,
    Embed,
    File,
    Forbidden,
    Guild,
    Member,
    Message,
    PartialEmoji,
    Permissions,
    Role,
    TextChannel,
)
from discord.abc import Messageable, Snowflake
from discord.ext.commands.bot import Bot
from discord.ext.commands.errors import CommandError

from PyDrocsid.config import Config
from PyDrocsid.emojis import name_to_emoji
from PyDrocsid.permission import BasePermission
from PyDrocsid.translations import t


t = t.g


async def is_teamler(member: Member) -> bool:
    """Return whether a given member is a team member."""

    return await Config.TEAMLER_LEVEL.check_permissions(member)


async def check_wastebasket(
    message: Message, member: Member, emoji: PartialEmoji, footer: str, permission: BasePermission
) -> int | None:
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
        if (match := re.match("^" + pattern + "$", cast(str, embed.footer.text))) is None:
            continue

        author_id = int(match.group(1))  # id of user who originally requested this embed

        if author_id == member.id or await permission.check_permissions(member):
            # user is authorized to delete this embed
            return author_id

        # user is not authorized -> remove reaction
        try:
            await message.remove_reaction(emoji, cast(Snowflake, member))
        except Forbidden:
            pass
        return None

    return None


def measure_latency() -> float | None:
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


async def attachment_to_file(attachment: Attachment) -> File:
    """Convert an attachment to a file"""

    file = io.BytesIO()
    await attachment.save(file)
    return File(file, filename=attachment.filename, spoiler=attachment.is_spoiler())


async def read_normal_message(bot: Bot, channel: TextChannel, author: Member) -> tuple[str, list[File]]:
    """Read a message and return content and attachments."""

    def predicate(m: Message) -> bool:
        return m.author == author and m.channel == channel

    msg: Message = await bot.wait_for("message", check=predicate)
    return msg.content, [await attachment_to_file(attachment) for attachment in msg.attachments]


async def read_complete_message(message: Message) -> tuple[str, list[File], Embed | None]:
    """Extract content, attachments and embed from a given message."""

    embed: Embed | None
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
    colour: int | None = None,
    inline: bool = False,
    force_resend: bool = False,
    force_new_embed: bool = False,
    force_new_field: bool = False,
    **kwargs: Any,
) -> Message:
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

    messages: list[Message] = await channel.history(limit=1).flatten()
    if messages and messages[0].embeds and not force_new_embed:  # can extend last embed
        embed: Embed = messages[0].embeds[0]

        # if name or description don't match, a new embed must be created
        if (embed.title or "") == title and (embed.description or "") == description:

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
                embed.colour = Colour(colour)

            # update embed
            if not force_new_embed:
                if force_resend:
                    await messages[0].delete()
                    return await channel.send(embed=embed, **kwargs)
                await messages[0].edit(embed=embed, **kwargs)
                return messages[0]

    # create and send a new embed
    embed = Embed(title=title, description=description, colour=colour if colour is not None else 0x008080)
    embed.add_field(name=name, value=value, inline=inline)
    return await channel.send(embed=embed)


def check_role_assignable(role: Role) -> None:
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


def check_message_send_permissions(
    channel: TextChannel, check_send: bool = True, check_file: bool = False, check_embed: bool = False
) -> None:
    permissions: Permissions = channel.permissions_for(channel.guild.me)
    if not permissions.view_channel:
        raise CommandError(t.message_send_permission_error.cannot_view_channel(channel.mention))
    if check_send and not permissions.send_messages:
        raise CommandError(t.message_send_permission_error.could_not_send_message(channel.mention))
    if check_file and not permissions.attach_files:
        raise CommandError(t.message_send_permission_error.could_not_send_file(channel.mention))
    if check_embed and not permissions.embed_links:
        raise CommandError(t.message_send_permission_error.could_not_send_embed(channel.mention))

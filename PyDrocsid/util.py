import io
import re
from socket import gethostbyname, socket, AF_INET, SOCK_STREAM, timeout, SHUT_RD
from time import time
from typing import Optional, List, Tuple, Union

from discord import Embed, Message, File, Attachment, TextChannel, Member, User, PartialEmoji, Forbidden, Role, Guild
from discord.abc import Messageable
from discord.ext.commands import Command, Context, CommandError, Bot, BadArgument, ColorConverter

from PyDrocsid.command_edit import link_response
from PyDrocsid.config import Config
from PyDrocsid.emojis import name_to_emoji
from PyDrocsid.environment import REPLY, MENTION_AUTHOR
from PyDrocsid.material_colors import MaterialColors
from PyDrocsid.permission import BasePermission
from PyDrocsid.settings import Settings
from PyDrocsid.translations import t

t = t.g


class GlobalSettings(Settings):
    prefix = "."


def docs(text: str):
    def deco(f):
        f.__doc__ = text
        return f

    return deco


async def get_prefix() -> str:
    return await GlobalSettings.prefix.get()


async def set_prefix(new_prefix: str):
    await GlobalSettings.prefix.set(new_prefix)


async def is_teamler(member: Member) -> bool:
    return await Config.TEAMLER_LEVEL.check_permissions(member)


class Color(ColorConverter):
    async def convert(self, ctx, argument: str) -> Optional[int]:
        try:
            return await super().convert(ctx, argument)
        except BadArgument:
            pass

        if not re.match(r"^[0-9a-fA-F]{6}$", argument):
            raise BadArgument(t.invalid_color)
        return int(argument, 16)


def make_error(message, user: Union[Member, User, None] = None) -> Embed:
    embed = Embed(title=t.error, colour=MaterialColors.error, description=str(message))

    if user:
        embed.set_author(
            name=str(user),
            icon_url=user.avatar_url_as(format=("gif" if user.is_avatar_animated() else "png")),
        )

    return embed


async def can_run_command(command: Command, ctx: Context) -> bool:
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
    if emoji.name != name_to_emoji["wastebasket"]:
        return None

    for embed in message.embeds:
        if embed.footer.text == Embed.Empty:
            continue

        pattern = re.escape(footer).replace("\\{\\}", "{}").format(r".*?#\d{4}", r"(\d+)")  # noqa: P103
        if (match := re.match("^" + pattern + "$", embed.footer.text)) is None:
            continue

        author_id = int(match.group(1))
        if not (author_id == member.id or await permission.check_permissions(member)):
            try:
                await message.remove_reaction(emoji, member)
            except Forbidden:
                pass
            return None

        return author_id

    return None


def measure_latency() -> Optional[float]:
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
    dp = [[max(i, j) for j in range(len(b) + 1)] for i in range(len(a) + 1)]
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            dp[i][j] = min(dp[i - 1][j - 1] + (a[i - 1] != b[j - 1]), dp[i - 1][j] + 1, dp[i][j - 1] + 1)
    return dp[len(a)][len(b)]


def split_lines(text: str, max_size: int, *, first_max_size: Optional[int] = None) -> List[str]:
    out = []
    cur = ""
    for line in text.splitlines():
        ms = max_size if out or first_max_size is None else first_max_size
        ext = "\n" * bool(cur) + line
        if len(cur) + len(ext) > ms and cur:
            out.append(cur)
            cur = line
        else:
            cur += ext
    if cur:
        out.append(cur)
    return out


async def send_long_embed(
    channel: Messageable,
    embed: Embed,
    *,
    repeat_title: bool = False,
    repeat_name: bool = False,
) -> List[Message]:
    messages = []
    fields = embed.fields.copy()
    cur = embed.copy()
    cur.clear_fields()
    *parts, last = split_lines(embed.description or "", 2048) or [""]
    for part in parts:
        cur.description = part
        messages.append(await reply(channel, embed=cur))
        if not repeat_title:
            cur.title = ""
            cur.remove_author()
    cur.description = last
    for field in fields:
        name: str = field.name
        value: str = field.value
        inline: bool = field.inline
        first_max_size = min(1024 if name or cur.fields or cur.description else 2048, 6000 - len(cur))
        *parts, last = split_lines(value, 2048, first_max_size=first_max_size)
        if len(cur.fields) >= 25 or len(cur) + len(name or "** **") + len(parts[0] if parts else last) > 6000:
            messages.append(await reply(channel, embed=cur))
            if not repeat_title:
                cur.title = ""
                cur.remove_author()
            cur.description = ""
            cur.clear_fields()

        for part in parts:
            if name or cur.fields or cur.description:
                cur.add_field(name=name or "** **", value=part, inline=False)
            else:
                cur.description = part
            messages.append(await reply(channel, embed=cur))
            if not repeat_title:
                cur.title = ""
                cur.remove_author()
            if not repeat_name:
                name = ""
            cur.description = ""
            cur.clear_fields()
        if name or cur.fields or cur.description:
            cur.add_field(name=name or "** **", value=last, inline=inline and not parts)
        else:
            cur.description = last
    messages.append(await reply(channel, embed=cur))
    return messages


async def attachment_to_file(attachment: Attachment) -> File:
    file = io.BytesIO()
    await attachment.save(file)
    return File(file, filename=attachment.filename, spoiler=attachment.is_spoiler())


async def read_normal_message(bot: Bot, channel: TextChannel, author: Member) -> Tuple[str, List[File]]:
    msg: Message = await bot.wait_for("message", check=lambda m: m.channel == channel and m.author == author)
    return msg.content, [await attachment_to_file(attachment) for attachment in msg.attachments]


async def read_complete_message(message: Message) -> Tuple[str, List[File], Optional[Embed]]:
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
    messages: List[Message] = await channel.history(limit=1).flatten()
    if messages and messages[0].embeds and not force_new_embed:
        embed: Embed = messages[0].embeds[0]
        if embed.title == title and embed.description == description:
            if embed.fields and embed.fields[-1].name == name and not force_new_field:
                embed.set_field_at(index=-1, name=name, value=value, inline=inline)
            elif len(embed.fields) < 25:
                embed.add_field(name=name, value=value, inline=inline)
            else:
                force_new_embed = True

            if colour is not None:
                embed.colour = colour

            if not force_new_embed:
                if force_resend:
                    await messages[0].delete()
                    await channel.send(embed=embed)
                    return
                await messages[0].edit(embed=embed)
                return

    embed = Embed(title=title, description=description, colour=colour if colour is not None else 0x008080)
    embed.add_field(name=name, value=value, inline=inline)
    await channel.send(embed=embed)


async def reply(ctx: Union[Context, Message, Messageable], *args, no_reply: bool = False, **kwargs) -> Message:
    if REPLY and isinstance(ctx, (Context, Message)) and not no_reply:
        msg = await ctx.reply(*args, **kwargs, mention_author=MENTION_AUTHOR)
    else:
        msg = await (ctx.channel if isinstance(ctx, Message) else ctx).send(*args, **kwargs)

    if isinstance(ctx, (Context, Message)):
        await link_response(ctx, msg)

    return msg


def check_role_assignable(role: Role):
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

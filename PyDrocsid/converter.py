import re
from typing import cast

from discord import PartialEmoji, Member, User, Guild, NotFound, HTTPException, Colour
from discord.ext.commands.context import Context
from discord.ext.commands.converter import PartialEmojiConverter, ColorConverter, Converter
from discord.ext.commands.errors import BadArgument

from PyDrocsid.emojis import emoji_to_name
from PyDrocsid.translations import t

t = t.g


class EmojiConverter(PartialEmojiConverter):  # type: ignore
    """Emoji converter which also supports unicode emojis."""

    async def convert(self, ctx: Context, argument: str) -> PartialEmoji:
        try:
            return cast(PartialEmoji, await super().convert(ctx, argument))
        except BadArgument:
            pass

        if argument not in emoji_to_name:
            raise BadArgument

        connection = ctx.bot._connection  # noqa
        return PartialEmoji.with_state(connection, animated=False, name=argument, id=None)


class Color(ColorConverter):  # type: ignore
    """Color converter which also supports hex codes."""

    async def convert(self, ctx: Context, argument: str) -> int:
        try:
            return cast(Colour, (await super().convert(ctx, argument))).value
        except BadArgument:
            pass

        if not re.match(r"^[0-9a-fA-F]{6}$", argument):
            raise BadArgument(t.invalid_color)
        return int(argument, 16)


class UserMemberConverter(Converter):  # type: ignore
    """Return a member or user object depending on whether the user is currently a guild member."""

    async def convert(self, ctx: Context, argument: str) -> User | Member:
        guild: Guild = ctx.bot.guilds[0]

        if not (match := re.match(r"^(<@!?)?([0-9]{15,20})(?(1)>)$", argument)):
            raise BadArgument(t.user_not_found)

        # find user/member by id
        user_id: int = int(match.group(2))
        if member := guild.get_member(user_id):
            return member
        try:
            return cast(User, await ctx.bot.fetch_user(user_id))
        except (NotFound, HTTPException):
            raise BadArgument(t.user_not_found)

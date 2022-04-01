import re
from typing import Optional, Union

from discord import Guild, HTTPException, Member, NotFound, PartialEmoji, User
from discord.ext.commands import BadArgument, ColorConverter, Converter, PartialEmojiConverter

from PyDrocsid.emojis import emoji_to_name
from PyDrocsid.translations import t


t = t.g


class EmojiConverter(PartialEmojiConverter):
    """Emoji converter which also supports unicode emojis."""

    async def convert(self, ctx, argument):
        try:
            return await super().convert(ctx, argument)
        except BadArgument:
            pass

        if argument in emoji_to_name:
            return PartialEmoji.with_state(ctx.bot._connection, animated=False, name=argument, id=None)

        raise BadArgument(f'Emoji "{argument}" not found.')


class Color(ColorConverter):
    """Color converter which also supports hex codes."""

    async def convert(self, ctx, argument: str) -> Optional[int]:
        try:
            return (await super().convert(ctx, argument)).value
        except BadArgument:
            pass

        if not re.match(r"^[0-9a-fA-F]{6}$", argument):
            raise BadArgument(t.invalid_color)
        return int(argument, 16)


class UserMemberConverter(Converter):
    """Return a member or user object depending on whether the user is currently a guild member."""

    async def convert(self, ctx, argument: str) -> Union[Member, User]:
        guild: Guild = ctx.bot.guilds[0]

        if not (match := re.match(r"^(<@!?)?([0-9]{15,20})(?(1)>)$", argument)):
            raise BadArgument(t.user_not_found)

        # find user/member by id
        user_id: int = int(match.group(2))
        if member := guild.get_member(user_id):
            return member
        try:
            return await ctx.bot.fetch_user(user_id)
        except (NotFound, HTTPException):
            raise BadArgument(t.user_not_found)

import re
from datetime import timedelta

from discord import Guild, HTTPException, Member, NotFound, PartialEmoji, User
from discord.ext.commands import Bot
from discord.ext.commands.context import Context
from discord.ext.commands.converter import ColorConverter, Converter, PartialEmojiConverter
from discord.ext.commands.errors import BadArgument

from PyDrocsid.emojis import emoji_to_name
from PyDrocsid.translations import t


t = t.g


class EmojiConverter(PartialEmojiConverter):
    """Emoji converter which also supports unicode emojis."""

    async def convert(self, ctx: Context[Bot], argument: str) -> PartialEmoji:
        try:
            return await super().convert(ctx, argument)
        except BadArgument:
            pass

        if argument not in emoji_to_name:
            raise BadArgument

        connection = ctx.bot._connection  # noqa
        return PartialEmoji.with_state(connection, animated=False, name=argument, id=None)


class Color(Converter[int]):
    """Color converter which also supports hex codes."""

    async def convert(self, ctx: Context[Bot], argument: str) -> int:
        try:
            return (await ColorConverter().convert(ctx, argument)).value
        except BadArgument:
            pass

        if not re.match(r"^[0-9a-fA-F]{6}$", argument):
            raise BadArgument(t.invalid_color)
        return int(argument, 16)


class UserMemberConverter(Converter[User | Member]):
    """Return a member or user object depending on whether the user is currently a guild member."""

    async def convert(self, ctx: Context[Bot], argument: str) -> User | Member:
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


class DurationConverter(Converter[int | None]):
    """
    Converter for retrieving minutes from a string containing different time units.
    """

    async def convert(self, ctx: Context[Bot], argument: str) -> int | None:
        """
        Extracts information about years, months, weeks, days, hours and minutes from a string
        and returns the total amount of time in minutes.
        :param ctx: the context the converter was called in
        :param argument: the string with the different time units or a variation of 'inf' for an infinite time span
        :returns: the total amount of time in minutes as an int or None if the time span is infinite
        """

        if argument.lower() in ("inf", "perm", "permanent", "-1", "∞"):
            return None
        if (match := re.match(r"^(\d+y)?(\d+m)?(\d+w)?(\d+d)?(\d+H)?(\d+M)?$", argument)) is None:
            raise BadArgument(t.duration_suffixes)

        years, months, weeks, days, hours, minutes = [
            0 if (value := match.group(i)) is None else int(value[:-1]) for i in range(1, 7)
        ]

        days += years * 365
        days += months * 30

        days_test = int(days + (weeks * 7) + (hours / 24) + ((minutes / 60) / 24))

        if days_test >= timedelta.max.days:
            raise BadArgument(t.invalid_duration_inf)

        td = timedelta(weeks=weeks, days=days, hours=hours, minutes=minutes)
        duration = int(td.total_seconds() / 60)

        if duration <= 0:
            raise BadArgument(t.invalid_duration)
        return duration

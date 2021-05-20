import re
from typing import Optional

from discord import PartialEmoji
from discord.ext.commands import PartialEmojiConverter, BadArgument, ColorConverter

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
            # noinspection PyProtectedMember
            # skipcq: PYL-W0212
            return PartialEmoji.with_state(ctx.bot._connection, animated=False, name=argument, id=None)

        raise BadArgument(f'Emoji "{argument}" not found.')


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

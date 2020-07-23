from discord import PartialEmoji
from discord.ext.commands import PartialEmojiConverter, BadArgument


class EmojiConverter(PartialEmojiConverter):
    async def convert(self, ctx, argument):
        try:
            return await super().convert(ctx, argument)
        except BadArgument:
            pass

        # noinspection PyProtectedMember
        # skipcq: PYL-W0212
        return PartialEmoji.with_state(ctx.bot._connection, animated=False, name=argument, id=None)

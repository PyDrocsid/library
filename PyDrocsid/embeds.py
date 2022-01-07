from copy import deepcopy
from typing import List, Optional

from discord import Embed, Message, User, InteractionResponse
from discord.abc import Messageable
from discord.embeds import EmptyEmbed

from PyDrocsid.command import reply
from PyDrocsid.environment import DISABLE_PAGINATION
from PyDrocsid.pagination import create_pagination

# an "empty" markdown string (e.g. for empty field names in embeds)
EMPTY_MARKDOWN = "_ _"


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


class EmbedLimits:
    # https://discord.com/developers/docs/resources/channel#embed-limits
    TITLE = 256
    DESCRIPTION = 2048
    URL = 2048
    THUMBNAIL_URL = 2048
    IMAGE_URL = 2048
    FIELDS = 25
    FIELD_NAME = 256
    FIELD_VALUE = 1024
    FOOTER_TEXT = 2048
    FOOTER_ICON_URL = 2048
    AUTHOR_NAME = 256
    AUTHOR_URL = 2048
    AUTHOR_ICON_URL = 2048
    TOTAL = 6000


async def send_long_embed(
    channel: Messageable | Message | InteractionResponse,
    embed: Embed,
    *,
    content: Optional[str] = None,
    repeat_title: bool = False,
    repeat_thumbnail: bool = False,
    repeat_name: bool = False,
    repeat_image: bool = False,
    repeat_footer: bool = False,
    paginate: bool = False,
    pagination_user: Optional[User] = None,
    max_fields: int = 25,
    **kwargs,
) -> List[Message]:
    """
    Split and send a long embed in multiple messages.

    :param channel: the channel into which the messages should be sent
    :param embed: the embed to send
    :param content: the content of the first message
    :param repeat_title: whether to repeat the embed title in every embed
    :param repeat_thumbnail: whether to repeat the thumbnail image in every embed
    :param repeat_name: whether to repeat field names in every embed
    :param repeat_image: whether to repeat the image in every embed
    :param repeat_footer: whether to repeat the footer in every embed
    :param paginate: whether to use pagination instead of multiple messages
    :param pagination_user: the user who should be able to control the pagination
    :param max_fields: the maximum number of fields an embed is allowed to have
    :return: list of all messages that have been sent
    """

    if DISABLE_PAGINATION:
        paginate = False
        max_fields = EmbedLimits.FIELDS

    # enforce repeat_title, repeat_name and repeat_footer when using pagination
    if paginate:
        repeat_title = True
        repeat_name = True
        repeat_footer = True

    # always limit max_fields to 25
    max_fields = min(max_fields, EmbedLimits.FIELDS)

    # the maximum possible size of an embed
    max_total: int = EmbedLimits.TOTAL - 20 * paginate

    # pre checks
    if len(embed.title) > EmbedLimits.TITLE - 20 * paginate:
        raise ValueError("Embed title is too long.")
    if len(embed.url) > EmbedLimits.URL:
        raise ValueError("Embed url is too long.")
    if embed.thumbnail and len(embed.thumbnail.url) > EmbedLimits.THUMBNAIL_URL:
        raise ValueError("Thumbnail url is too long.")
    if embed.image and len(embed.image.url) > EmbedLimits.IMAGE_URL:
        raise ValueError("Image url is too long.")
    if embed.footer:
        if len(embed.footer.text) > EmbedLimits.FOOTER_TEXT:
            raise ValueError("Footer text is too long.")
        if len(embed.footer.icon_url) > EmbedLimits.FOOTER_ICON_URL:
            raise ValueError("Footer icon_url is too long.")
    if embed.author:
        if len(embed.author.name) > EmbedLimits.AUTHOR_NAME:
            raise ValueError("Author name is too long.")
        if len(embed.author.url) > EmbedLimits.AUTHOR_URL:
            raise ValueError("Author url is too long.")
        if len(embed.author.icon_url) > EmbedLimits.AUTHOR_ICON_URL:
            raise ValueError("Author icon_url is too long.")
    for i, field in enumerate(embed.fields):
        if len(field.name) > EmbedLimits.FIELD_NAME:
            raise ValueError(f"Name of field at position {i} is too long.")

    embeds: list[Embed] = []

    def add_embed(e: Embed):
        """Copy and add an embed to the list of embeds."""

        embeds.append(Embed.from_dict(deepcopy(e.to_dict())))

    def clear_embed(*, clear_completely: bool = False):
        if not repeat_title:
            cur.title = ""
            cur.remove_author()
        if not repeat_thumbnail:
            cur.set_thumbnail(url=EmptyEmbed)

        if clear_completely:
            cur.description = ""
            cur.clear_fields()

    # clear and backup embed fields, footer and image
    fields = embed.fields.copy()
    footer = embed.footer
    image = embed.image
    cur = embed.copy()
    cur.clear_fields()
    if not repeat_footer and footer:
        delattr(cur, "_footer")
    if not repeat_image:
        cur.set_image(url=EmptyEmbed)

    *parts, last = split_lines(embed.description or "", EmbedLimits.DESCRIPTION) or [""]
    for part in parts:
        cur.description = part
        add_embed(cur)
        clear_embed()

    cur.description = last

    # add embed fields
    for field in fields:
        parts = split_lines(field.value, EmbedLimits.FIELD_VALUE)
        inline = bool(field.inline) and len(parts) == 1

        if not field.name:
            field.name = EMPTY_MARKDOWN

        field_length: int = len(field.name) + sum(map(len, parts)) + len(EMPTY_MARKDOWN) * (len(parts) - 1)

        # check whether field fits in just one embed
        total_size_one_embed = field_length
        total_size_one_embed += len(cur.title)
        if cur.author:
            total_size_one_embed += len(cur.author.name)
        if cur.footer:
            total_size_one_embed += len(cur.footer.text)

        if len(parts) <= max_fields and total_size_one_embed <= max_total:

            if len(parts) + len(cur.fields) > max_fields or field_length + len(cur) > max_total:
                # field does not fit into current embed
                # -> create new embed
                add_embed(cur)
                clear_embed(clear_completely=True)

            # add field to current embed
            for i, part in enumerate(parts):
                cur.add_field(name=[field.name, EMPTY_MARKDOWN][i > 0], value=part, inline=inline)

        else:

            # add field parts individually
            for i, part in enumerate(parts):
                name: str = [field.name, EMPTY_MARKDOWN][i > 0]

                # check whether embed is full
                if len(cur.fields) >= max_fields or len(cur) + len(name) + len(part) > max_total:
                    # create new embed
                    add_embed(cur)
                    clear_embed(clear_completely=True)
                    if repeat_name:
                        name = field.name

                # add field part
                cur.add_field(name=name, value=part, inline=inline)

    # add footer to last embed (if previously removed)
    if not repeat_footer and footer:
        if len(cur) + len(footer.text) > max_total:
            add_embed(cur)
            clear_embed(clear_completely=True)

        cur.set_footer(text=footer.text, icon_url=footer.icon_url)

    # add image to last embed (if previously removed)
    if not repeat_image and image:
        cur.set_image(url=image.url)

    add_embed(cur)

    # don't use pagination if there is only one embed
    if not paginate or len(embeds) <= 1:
        return [
            await reply(channel, embed=e, content=content if not i else None, **kwargs) for i, e in enumerate(embeds)
        ]

    # create pagination
    if not pagination_user and hasattr(channel, "author"):
        pagination_user = channel.author
    return [await create_pagination(channel, pagination_user, embeds, **kwargs)]

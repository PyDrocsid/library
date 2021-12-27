from typing import Optional

from discord import Embed, User, Message, ButtonStyle
from discord.abc import Messageable
from discord.ext.pages import Paginator

from PyDrocsid.command import reply
from PyDrocsid.emojis import name_to_emoji


async def create_pagination(channel: Messageable, user: Optional[User], embeds: list[Embed], **kwargs) -> Message:
    """
    Create embed pagination on a message.

    :param channel: the channel to send the message to
    :param user: the user who should be able to control the pagination
    :param embeds: a list of embeds
    """

    paginator = Paginator(embeds, author_check=bool(user))
    paginator.user = user

    msg = await reply(channel, embed=(paginator.pages[0]), view=paginator, **kwargs)
    paginator.message = msg

    return msg

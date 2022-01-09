from typing import Optional

import discord
from discord import Embed, User, Message
from discord.abc import Messageable
from discord.ext.pages import Paginator, PaginatorButton

from PyDrocsid.command import reply
from PyDrocsid.environment import PAGINATION_TTL


class CustomPaginator(Paginator):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if await super().interaction_check(interaction):
            return True

        paginator = CustomPaginator(self.pages, author_check=False)
        paginator.current_page = self.current_page
        for button in self.children:
            if not isinstance(button, PaginatorButton) or button.custom_id != interaction.data["custom_id"]:
                continue

            if button.button_type == "first":
                paginator.current_page = 0
            elif button.button_type == "prev":
                paginator.current_page -= 1
            elif button.button_type == "next":
                paginator.current_page += 1
            elif button.button_type == "last":
                paginator.current_page = paginator.page_count
            break

        paginator.update_buttons()
        paginator.message = await interaction.response.send_message(
            embed=paginator.pages[paginator.current_page],
            view=paginator,
            ephemeral=True,
        )
        return False

    def update_buttons(self) -> dict:
        out = super().update_buttons()

        self.children[0].disabled = self.children[1].disabled
        self.children[4].disabled = self.children[3].disabled

        return out


async def create_pagination(channel: Messageable, user: Optional[User], embeds: list[Embed], **kwargs) -> Message:
    """
    Create embed pagination on a message.

    :param channel: the channel to send the message to
    :param user: the user who should be able to control the pagination
    :param embeds: a list of embeds
    """

    paginator = CustomPaginator(embeds, timeout=PAGINATION_TTL)
    paginator.user = user

    msg = await reply(channel, embed=(paginator.pages[0]), view=paginator, **kwargs)
    paginator.message = msg

    return msg

from __future__ import annotations

from typing import Any

from discord import ButtonStyle, Embed, Interaction, InteractionResponse, Member, Message, User, ui
from discord.abc import Messageable

from PyDrocsid.command import reply
from PyDrocsid.environment import PAGINATION_TTL


class PaginatorButton(ui.Button[ui.View]):
    def __init__(self, paginator: Paginator, label: str, style: ButtonStyle, page: int):
        super().__init__(
            label=label, style=style, disabled=page == paginator.page or page not in range(len(paginator.pages))
        )

        self.paginator = paginator
        self.page = page

    async def callback(self, interaction: Interaction) -> None:
        await self.paginator.goto_page(self.page)


class Paginator(ui.View):
    def __init__(self, pages: list[Embed], *, timeout: float, page: int = 0, user: User | Member | None = None):
        super().__init__(timeout=timeout)

        self._timeout = timeout
        self.pages = pages
        self.page = page
        self.user = user
        self.message: Message | None = None
        self.buttons: list[PaginatorButton] = []

    def _update_buttons(self) -> None:
        self.buttons = [
            PaginatorButton(self, "<<", ButtonStyle.blurple, 0),
            PaginatorButton(self, "<", ButtonStyle.red, self.page - 1),
            PaginatorButton(self, f"{self.page + 1}/{len(self.pages)}", ButtonStyle.grey, -1),
            PaginatorButton(self, ">", ButtonStyle.green, self.page + 1),
            PaginatorButton(self, ">>", ButtonStyle.blurple, len(self.pages) - 1),
        ]

        self.clear_items()
        for button in self.buttons:
            if self.is_finished():
                button.disabled = True
            self.add_item(button)

    async def reply(self, channel: Message | Messageable | InteractionResponse, **kwargs: Any) -> Message:
        self._update_buttons()
        self.message = await reply(channel, embed=self.pages[self.page], view=self, **kwargs)
        return self.message

    async def _update(self) -> None:
        self.page = min(max(self.page, 0), len(self.pages) - 1)
        self._update_buttons()
        if isinstance(self.message, Message):
            await self.message.edit(embed=self.pages[self.page], view=self)

    async def goto_page(self, page: int) -> None:
        self.page = page
        await self._update()

    async def on_timeout(self) -> None:
        await self._update()

    async def interaction_check(self, interaction: Interaction) -> bool:
        if not self.user or self.user == interaction.user:
            return True

        paginator = Paginator(self.pages, timeout=self._timeout, user=interaction.user)
        for button in self.buttons:
            if interaction.data and button.custom_id == interaction.data.get("custom_id"):
                await paginator.goto_page(button.page)
                break

        await paginator.reply(interaction.response)  # noqa
        return False


async def create_pagination(
    channel: Message | Messageable | InteractionResponse, user: User | Member | None, embeds: list[Embed], **kwargs: Any
) -> Message:
    """
    Create embed pagination on a message.

    :param channel: the channel to send the message to
    :param user: the user who should be able to control the pagination
    :param embeds: a list of embeds
    """

    paginator = Paginator(embeds, timeout=PAGINATION_TTL, user=user)
    return await paginator.reply(channel, **kwargs)

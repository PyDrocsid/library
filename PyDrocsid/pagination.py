from typing import Optional, Union, List, Dict

import discord
from discord import Embed, User, Message, ApplicationContext
from discord.abc import Messageable
from discord.ext.commands import Context

from PyDrocsid.command import reply
from PyDrocsid.environment import PAGINATION_TTL


class PaginatorButton(discord.ui.Button):
    def __init__(self, label, emoji, style, disabled, button_type, paginator):
        super().__init__(label=label, emoji=emoji, style=style, disabled=disabled, row=0)
        self.label = label
        self.emoji = emoji
        self.style = style
        self.disabled = disabled
        self.button_type = button_type
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        if self.button_type == "first":
            self.paginator.current_page = 0
        elif self.button_type == "prev":
            self.paginator.current_page -= 1
        elif self.button_type == "next":
            self.paginator.current_page += 1
        elif self.button_type == "last":
            self.paginator.current_page = self.paginator.page_count
        await self.paginator.goto_page(interaction=interaction, page_number=self.paginator.current_page)


class Paginator(discord.ui.View):
    def __init__(
        self,
        pages: Union[List[str], List[discord.Embed]],
        show_disabled=True,
        show_indicator=True,
        author_check=True,
        disable_on_timeout=True,
        custom_view: Optional[discord.ui.View] = None,
        timeout: Optional[float] = 180.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.timeout = timeout
        self.pages = pages
        self.current_page = 0
        self.page_count = len(self.pages) - 1
        self.show_disabled = show_disabled
        self.show_indicator = show_indicator
        self.disable_on_timeout = disable_on_timeout
        self.custom_view = custom_view
        self.message: Union[discord.Message, discord.WebhookMessage, None] = None
        self.buttons = {
            "first": {
                "object": PaginatorButton(
                    label="<<",
                    style=discord.ButtonStyle.blurple,
                    emoji=None,
                    disabled=True,
                    button_type="first",
                    paginator=self,
                ),
                "hidden": True,
            },
            "prev": {
                "object": PaginatorButton(
                    label="<",
                    style=discord.ButtonStyle.red,
                    emoji=None,
                    disabled=True,
                    button_type="prev",
                    paginator=self,
                ),
                "hidden": True,
            },
            "page_indicator": {
                "object": discord.ui.Button(
                    label=f"{self.current_page + 1}/{self.page_count + 1}",
                    style=discord.ButtonStyle.gray,
                    disabled=True,
                    row=0,
                ),
                "hidden": False,
            },
            "next": {
                "object": PaginatorButton(
                    label=">",
                    style=discord.ButtonStyle.green,
                    emoji=None,
                    disabled=True,
                    button_type="next",
                    paginator=self,
                ),
                "hidden": True,
            },
            "last": {
                "object": PaginatorButton(
                    label=">>",
                    style=discord.ButtonStyle.blurple,
                    emoji=None,
                    disabled=True,
                    button_type="last",
                    paginator=self,
                ),
                "hidden": True,
            },
        }
        self.update_buttons()

        self.usercheck = author_check
        self.user = None

    async def on_timeout(self) -> None:
        if self.disable_on_timeout:
            for item in self.children:
                item.disabled = True
            await self.message.edit(view=self)

    async def goto_page(self, interaction: discord.Interaction, page_number=0) -> None:
        self.update_buttons()
        page = self.pages[page_number]
        await interaction.response.edit_message(
            content=page if isinstance(page, str) else None,
            embed=page if isinstance(page, discord.Embed) else None,
            view=self,
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.usercheck:
            return self.user == interaction.user
        return True

    def customize_button(
        self,
        button_name: str = None,
        button_label: str = None,
        button_emoji=None,
        button_style: discord.ButtonStyle = discord.ButtonStyle.gray,
    ) -> PaginatorButton:
        if button_name not in self.buttons.keys():
            raise ValueError(f"no button named {button_name} was found in this view.")
        button: PaginatorButton = self.buttons[button_name]["object"]
        button.label = button_label
        button.emoji = button_emoji
        button.style = button_style
        return button

    def update_buttons(self) -> Dict:
        for key, button in self.buttons.items():
            if key == "first":
                button["hidden"] = self.current_page <= 0
            elif key == "last":
                button["hidden"] = self.current_page >= self.page_count
            elif key == "next":
                button["hidden"] = self.current_page >= self.page_count
            elif key == "prev":
                button["hidden"] = self.current_page <= 0
        self.clear_items()
        if self.show_indicator:
            self.buttons["page_indicator"]["object"].label = f"{self.current_page + 1}/{self.page_count + 1}"
        for key, button in self.buttons.items():
            if key != "page_indicator":
                if button["hidden"]:
                    button["object"].disabled = True
                    if self.show_disabled:
                        self.add_item(button["object"])
                else:
                    button["object"].disabled = False
                    self.add_item(button["object"])
            elif self.show_indicator:
                self.add_item(button["object"])

        if self.custom_view:
            for item in self.custom_view.children:
                self.add_item(item)

        return self.buttons

    async def send(
        self,
        ctx: Union[ApplicationContext, Context],
        ephemeral: bool = False,
    ) -> Union[discord.Message, discord.WebhookMessage]:
        page = self.pages[0]

        self.user = ctx.author

        if isinstance(ctx, ApplicationContext):
            msg = await ctx.respond(
                content=page if isinstance(page, str) else None,
                embed=page if isinstance(page, discord.Embed) else None,
                view=self,
                ephemeral=ephemeral,
            )

        else:
            msg = await ctx.send(
                content=page if isinstance(page, str) else None,
                embed=page if isinstance(page, discord.Embed) else None,
                view=self,
            )
        if isinstance(msg, (discord.WebhookMessage, discord.Message)):
            self.message = msg
        elif isinstance(msg, discord.Interaction):
            self.message = await msg.original_message()

        return self.message

    async def respond(self, interaction: discord.Interaction, ephemeral: bool = False):
        page = self.pages[0]
        self.user = interaction.user

        if interaction.response.is_done():
            msg = await interaction.followup.send(
                content=page if isinstance(page, str) else None,
                embed=page if isinstance(page, discord.Embed) else None,
                view=self,
                ephemeral=ephemeral,
            )

        else:
            msg = await interaction.response.send_message(
                content=page if isinstance(page, str) else None,
                embed=page if isinstance(page, discord.Embed) else None,
                view=self,
                ephemeral=ephemeral,
            )
        if isinstance(msg, (discord.WebhookMessage, discord.Message)):
            self.message = msg
        elif isinstance(msg, discord.Interaction):
            self.message = await msg.original_message()
        return self.message

    async def update(
        self,
        interaction: discord.Interaction,
        pages: List[Union[str, discord.Embed]],
        show_disabled: Optional[bool] = None,
        show_indicator: Optional[bool] = None,
        author_check: Optional[bool] = None,
        disable_on_timeout: Optional[bool] = None,
        custom_view: Optional[discord.ui.View] = None,
        timeout: Optional[float] = None,
    ):
        self.pages = pages
        self.page_count = len(self.pages) - 1
        self.current_page = 0
        self.show_disabled = show_disabled if show_disabled else self.show_disabled
        self.show_indicator = show_indicator if show_indicator else self.show_indicator
        self.usercheck = author_check if author_check else self.usercheck
        self.disable_on_timeout = disable_on_timeout if disable_on_timeout else self.disable_on_timeout
        self.custom_view = custom_view if custom_view else self.custom_view
        self.timeout = timeout if timeout else self.timeout

        await self.goto_page(interaction, self.current_page)


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

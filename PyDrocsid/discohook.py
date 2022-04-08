from __future__ import annotations

import base64
import hashlib
import json
from typing import Any, NamedTuple, cast

from aiohttp import ClientSession
from discord import Embed, Message

from PyDrocsid.redis import redis


class DiscoHookError(Exception):
    pass


class MessageContent(NamedTuple):
    content: str
    embeds: list[Embed]

    @staticmethod
    def from_message(message: Message) -> MessageContent:
        return MessageContent(content=message.content or "", embeds=message.embeds)

    def to_dict(self) -> dict[str, Any]:
        return {"data": {"content": self.content, "embeds": [e.to_dict() for e in self.embeds]}}


async def create_discohook_link(*messages: Message | MessageContent) -> str:
    if not messages:
        raise ValueError("No messages provided")

    _messages = [(MessageContent.from_message(msg) if isinstance(msg, Message) else msg).to_dict() for msg in messages]
    data = json.dumps({"messages": _messages})

    if out := await redis.get(key := f"discohook:link:{hashlib.sha256(data.encode()).hexdigest()[:16]}"):
        return cast(str, out)

    url = "https://discohook.org/?data=" + base64.urlsafe_b64encode(data.encode()).decode().rstrip("=")
    async with ClientSession() as session, session.post(
        "https://share.discohook.app/create", json={"url": url}
    ) as response:
        link: str | None = (await response.json()).get("url")
        if not response.ok or not link:
            raise DiscoHookError("Failed to create link")

    await redis.setex(key, 60 * 60 * 24 * 7, link)

    return link


async def load_discohook_link(link: str) -> list[MessageContent]:
    raise NotImplementedError

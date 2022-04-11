from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from typing import Any, NamedTuple, cast

from discord import Embed, Message
from httpx import AsyncClient

from PyDrocsid.redis import redis


TTL = 60 * 60 * 24 * 7  # 1 week

DISCOHOOK_EMPTY_MESSAGE = (
    "[https://discohook.org/]"
    "(https://discohook.org/?data=eyJtZXNzYWdlcyI6W3siZGF0YSI6eyJjb250ZW50IjpudWxsLCJlbWJlZHMiOm51bGx9fV19)"
)


class DiscoHookError(Exception):
    pass


def _load_embed(data: dict[str, Any]) -> Embed:
    if isinstance(timestamp := data.get("timestamp"), str):
        data["timestamp"] = timestamp.rstrip("Z")

    color = data.pop("color", None)
    if not Embed.from_dict(data):
        # empty embeds are not allowed
        data["description"] = "** **"
    if color is not None:
        data["color"] = color

    for field in data.get("fields") or []:
        if not field.get("name"):
            field["name"] = "** **"
        if not field.get("value"):
            field["value"] = "** **"

    return Embed.from_dict(data)


class MessageContent(NamedTuple):
    content: str
    embeds: list[Embed]

    @classmethod
    def from_message(cls, message: Message) -> MessageContent:
        return cls(content=message.content or "", embeds=message.embeds)

    def to_dict(self) -> dict[str, Any]:
        return {"data": {"content": self.content, "embeds": [e.to_dict() for e in self.embeds]}}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MessageContent:
        content = data.get("content") or ""
        embeds = [*map(_load_embed, data.get("embeds") or [])]
        return cls(content, embeds)

    @property
    def is_empty(self) -> bool:
        return not self.content and not self.embeds


async def create_discohook_link(*messages: Message | MessageContent) -> str:
    if not messages:
        raise ValueError("No messages provided")

    _messages = [(MessageContent.from_message(msg) if isinstance(msg, Message) else msg).to_dict() for msg in messages]
    data = json.dumps({"messages": _messages})

    if out := await redis.get(key := f"discohook:link:{hashlib.sha256(data.encode()).hexdigest()[:16]}"):
        return cast(str, out)

    url = f"https://discohook.org/?data={base64.urlsafe_b64encode(data.encode()).decode().rstrip('=')}"
    client: AsyncClient
    async with AsyncClient() as client:
        response = await client.post("https://share.discohook.app/create", json={"url": url})
        if response.is_error or not isinstance(link := response.json().get("url"), str):
            raise DiscoHookError("Failed to create link")

    await redis.setex(key, TTL, link)
    await redis.setex(f"discohook:data:{hashlib.sha256(link.encode()).hexdigest()[:16]}", TTL, data)

    return link


async def _load_discohook_data(link: str) -> Any:
    if out := await redis.get(key := f"discohook:data:{hashlib.sha256(link.encode()).hexdigest()[:16]}"):
        return json.loads(out)

    client: AsyncClient
    async with AsyncClient() as client:
        response = await client.head(link, follow_redirects=True)
        if response.is_error:
            raise DiscoHookError("Invalid link")

        url = str(response.url)

    if not (match := re.match(r"^https://discohook.org/\?data=([a-zA-Z\d\-_]+)$", url)):
        raise DiscoHookError("Invalid link")

    try:
        data = json.loads(base64.urlsafe_b64decode(match[1] + "=="))
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError):
        raise DiscoHookError("Invalid link")

    await redis.setex(key, TTL, json_data := json.dumps(data))
    await redis.setex(f"discohook:link:{hashlib.sha256(json_data.encode()).hexdigest()[:16]}", TTL, url)

    return data


async def load_discohook_link(link: str) -> list[MessageContent]:
    data = await _load_discohook_data(link)
    if not isinstance(data, dict) or not isinstance(messages := data.get("messages"), list):
        raise DiscoHookError("Invalid link")

    out: list[MessageContent] = []
    for msg in messages:
        if not isinstance(msg, dict) or not isinstance(msg_data := msg.get("data"), dict):
            raise DiscoHookError("Invalid link")
        out.append(MessageContent.from_dict(msg_data))
    return out

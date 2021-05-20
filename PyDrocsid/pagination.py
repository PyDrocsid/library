import json
from asyncio import create_task, gather
from typing import Union

from discord import Message, Embed, PartialEmoji, User, Member

from PyDrocsid.emojis import name_to_emoji
from PyDrocsid.environment import PAGINATION_TTL
from PyDrocsid.events import listener
from PyDrocsid.redis import redis


async def create_pagination(message: Message, embeds: list[Embed]):
    """
    Create embed pagination on a message.

    :param message: the message which should be paginated
    :param embeds: a list of embeds
    """

    key = f"pagination:channel={message.channel.id},msg={message.id}:"

    # save index, length and embeds in redis
    p = redis.pipeline()
    p.setex(key + "index", PAGINATION_TTL, 0)
    p.setex(key + "len", PAGINATION_TTL, len(embeds))
    for embed in embeds:
        p.rpush(key + "embeds", json.dumps(embed.to_dict()))
    p.expire(key + "embeds", PAGINATION_TTL)
    await p.execute()

    # add navigation reactions
    if len(embeds) > 2:
        await message.add_reaction(name_to_emoji["previous_track"])
    await message.add_reaction(name_to_emoji["arrow_backward"])
    await message.add_reaction(name_to_emoji["arrow_forward"])
    if len(embeds) > 2:
        await message.add_reaction(name_to_emoji["next_track"])


@listener
async def on_raw_reaction_add(message: Message, emoji: PartialEmoji, user: Union[User, Member]):
    """Event handler for pagination"""

    if user.bot:
        return

    key = f"pagination:channel={message.channel.id},msg={message.id}:"

    # return if cooldown is active
    if await redis.exists(key + "cooldown"):
        create_task(message.remove_reaction(emoji, user))
        return

    # return if this is no pagination message
    if not (idx := await redis.get(key + "index")) or not (length := await redis.get(key + "len")):
        return

    # enable 1 second cooldown
    await redis.setex(key + "cooldown", 1, 1)

    idx, length = int(idx), int(length)

    # determine new index
    if str(emoji) == name_to_emoji["previous_track"]:
        idx = None if idx <= 0 else 0
    elif str(emoji) == name_to_emoji["arrow_backward"]:
        idx = None if idx <= 0 else idx - 1
    elif str(emoji) == name_to_emoji["arrow_forward"]:
        idx = None if idx >= length - 1 else idx + 1
    elif str(emoji) == name_to_emoji["next_track"]:
        idx = None if idx >= length - 1 else length - 1
    else:
        return

    create_task(message.remove_reaction(emoji, user))
    if idx is None:  # click on reaction has no effect as the requested page is already visible
        return

    if not (embed_json := await redis.lrange(key + "embeds", idx, idx)):
        return

    # update index and reset redis expiration
    p = redis.pipeline()
    p.setex(key + "index", PAGINATION_TTL, idx)
    p.expire(key + "len", PAGINATION_TTL)
    p.expire(key + "embeds", PAGINATION_TTL)

    # update embed
    embed = Embed.from_dict(json.loads(embed_json[0]))
    await gather(p.execute(), message.edit(embed=embed))

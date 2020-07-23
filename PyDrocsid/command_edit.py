from typing import Dict, List

from discord import Message, NotFound
from discord.ext.commands import Bot

error_cache: Dict[Message, List[Message]] = {}
error_queue: List[Message] = []


async def handle_command_edit(bot: Bot, message: Message):
    if message not in error_cache:
        return

    for msg in error_cache.pop(message):
        try:
            await msg.delete()
        except NotFound:
            pass
    await bot.process_commands(message)


def add_to_error_cache(message: Message, response: List[Message]):
    error_cache[message] = response
    error_queue.append(message)

    while len(error_queue) > 1000:
        msg = error_queue.pop(0)
        if msg in error_cache:
            error_cache.pop(msg)

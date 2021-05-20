from PyDrocsid.settings import Settings


class PrefixSettings(Settings):
    prefix = "."


async def get_prefix() -> str:
    """Get bot prefix."""

    return await PrefixSettings.prefix.get()


async def set_prefix(new_prefix: str):
    """Set bot prefix."""

    await PrefixSettings.prefix.set(new_prefix)

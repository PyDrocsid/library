import sys
from collections import Counter
from functools import partial
from os import getenv
from pathlib import Path
from subprocess import getoutput  # noqa: S404
from typing import Type, Union, TypeVar

import yaml
from discord import Member, User

from PyDrocsid.permission import BasePermissionLevel, PermissionLevel
from PyDrocsid.settings import RoleSettings
from PyDrocsid.translations import Translations

T = TypeVar("T")


# noinspection SpellCheckingInspection
class Contributor:
    """Collection of all contributors. Each contributor is a (discord_id, github_id) tuple."""

    Defelo = (370876111992913922, "MDQ6VXNlcjQxNzQ3NjA1")
    TNT2k = (212866839083089921, "MDQ6VXNlcjQ0MzQ5NzUw")
    wolflu = (339062431131369472, "MDQ6VXNlcjYwMDQ4NTY1")
    MaxiHuHe04 = (302365095688798209, "MDQ6VXNlcjEyOTEzNTE4")
    ce_phox = (306774624090456075, "MDQ6VXNlcjQwNTE2OTkx")
    DELTA = (158634035180994560, "MDQ6VXNlcjU4OTA2NDM3")


class Config:
    """Global bot configuration"""

    # bot information
    NAME: str
    VERSION: str

    # repository information
    REPO_OWNER: str
    REPO_NAME: str
    REPO_LINK: str
    REPO_ICON: str

    # pydrocsid information
    DOCUMENTATION_URL: str
    DISCORD_INVITE: str

    # developers
    AUTHOR: Contributor
    CONTRIBUTORS: Counter[Contributor] = Counter(
        {
            Contributor.Defelo: 1000,
            Contributor.TNT2k: 100,
            Contributor.wolflu: 50,
            Contributor.MaxiHuHe04: 10,
            Contributor.ce_phox: 10,
            Contributor.DELTA: 10,
        },
    )

    ROLES: dict[str, tuple[str, bool]]

    # permissions and permission levels
    PERMISSION_LEVELS: Type[BasePermissionLevel]
    DEFAULT_PERMISSION_LEVEL: BasePermissionLevel
    DEFAULT_PERMISSION_OVERRIDES: dict[str, dict[str, BasePermissionLevel]] = {}
    TEAMLER_LEVEL: BasePermissionLevel

    ENABLED_COG_PACKAGES: set[str] = {"PyDrocsid"}


def get_subclasses_in_enabled_packages(base: Type[T]) -> list[Type[T]]:
    """Get all subclasses of a given base class that are defined in an enabled cog package."""

    return [
        cls for cls in base.__subclasses__() if sys.modules[cls.__module__].__package__ in Config.ENABLED_COG_PACKAGES
    ]


def load_version():
    """Get bot version either from the VERSION file or from git describe and store it in the bot config."""

    Config.VERSION = getoutput("cat VERSION 2>/dev/null || git describe --tags --always").lstrip("v")


def load_repo(config):
    """Load repository configuration."""

    Config.REPO_OWNER = config["repo"]["owner"]
    Config.REPO_NAME = config["repo"]["name"]
    Config.REPO_LINK = f"https://github.com/{Config.REPO_OWNER}/{Config.REPO_NAME}"
    Config.REPO_ICON = config["repo"]["icon"]


def load_pydrocsid_info(config):
    """Load pydrocsid information."""

    Config.DOCUMENTATION_URL = config["pydrocsid"]["documentation_url"]
    Config.DISCORD_INVITE = config["pydrocsid"]["discord_invite"]


def load_language(config):
    """Load language configuration."""

    if (lang := getenv("LANGUAGE", config["default_language"])) not in config["languages"]:
        raise ValueError(f"unknown language: {lang}")
    Translations.LANGUAGE = lang


async def _get_permission_level(
    permission_levels: dict[str, PermissionLevel],
    cls,
    member: Union[Member, User],
) -> BasePermissionLevel:
    """Get the permission level of a given member."""

    if not isinstance(member, Member):
        return cls.PUBLIC

    roles = {role.id for role in member.roles}

    async def has_role(role_name):
        return await RoleSettings.get(role_name) in roles

    for k, v in permission_levels.items():
        # check for required guild permissions
        if any(getattr(member.guild_permissions, p) for p in v.guild_permissions):
            return getattr(cls, k.upper())

        # check for required roles
        for r in v.roles:
            if await has_role(r):
                return getattr(cls, k.upper())

    return cls.PUBLIC


def load_permission_levels(config):
    """Load permission level configuration."""

    permission_levels: dict[str, PermissionLevel] = {"public": PermissionLevel(0, ["public", "p"], "Public", [], [])}

    # get custom permission levels from config
    for k, v in config["permission_levels"].items():
        if v["level"] <= 0:
            raise ValueError(f"Invalid permission level: {v['level']} ({k})")

        permission_levels[k] = PermissionLevel(
            v["level"],
            v["aliases"],
            v["name"],
            v["if"].get("permissions", []),
            v["if"].get("roles", []),
        )

    # add owner permission level
    owner_level = max([pl.level for pl in permission_levels.values()], default=0) + 1
    permission_levels["owner"] = PermissionLevel(owner_level, ["owner"], "Owner", [], [])

    # sort permission levels in descending order
    permission_levels = {
        k.upper(): v for k, v in sorted(permission_levels.items(), key=lambda pl: pl[1].level, reverse=True)
    }

    # generate PermissionLevel enum
    Config.PERMISSION_LEVELS = BasePermissionLevel("PermissionLevel", permission_levels)
    Config.PERMISSION_LEVELS._get_permission_level = classmethod(
        partial(_get_permission_level, permission_levels),
    )

    Config.DEFAULT_PERMISSION_LEVEL = getattr(Config.PERMISSION_LEVELS, config["default_permission_level"].upper())
    Config.TEAMLER_LEVEL = getattr(Config.PERMISSION_LEVELS, config["teamler_level"].upper())

    # load default permission level overrides
    for cog, overrides in config.get("default_permission_overrides", {}).items():
        for permission, level in overrides.items():
            Config.DEFAULT_PERMISSION_OVERRIDES.setdefault(cog.lower(), {}).setdefault(
                permission.lower(),
                getattr(Config.PERMISSION_LEVELS, level.upper()),
            )


def load_config_file(path: Path):
    """Load bot configuration from a config file."""

    with path.open() as file:
        config = yaml.safe_load(file)

    Config.NAME = config["name"]
    Config.AUTHOR = getattr(Contributor, config["author"])
    Config.ROLES = {k: (v["name"], v["check_assignable"]) for k, v in config["roles"].items()}

    load_repo(config)
    load_pydrocsid_info(config)
    load_language(config)
    load_permission_levels(config)

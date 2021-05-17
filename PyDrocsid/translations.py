from __future__ import annotations

from collections import namedtuple
from pathlib import Path
from typing import Any

import yaml

from PyDrocsid.logger import get_logger

logger = get_logger(__name__)


def merge(base: dict, src: dict):
    """
    Merge two dictionaries recursively by copying/merging the key-value pairs from src into base.

    :param base: the base dictionary
    :param src: the source dictionary to read from
    """

    for k, v in src.items():
        if k in base and isinstance(v, dict) and isinstance(base[k], dict):
            # recurse if value in both src and base is a dictionary
            merge(base[k], v)
        else:
            base[k] = v


class _FormatString(str):
    """String which can be called directly for formatting"""

    __call__ = str.format


class _PluralDict(dict):
    """Dictionary for pluralization containing multiple _FormatStrings"""

    def __call__(self, *args, **kwargs) -> str:
        """Choose and format the pluralized string."""

        # get count parameter from kwargs
        cnt = None
        if "cnt" in kwargs:
            cnt = kwargs["cnt"]
        elif "count" in kwargs:
            cnt = kwargs["count"]

        # choose pluralized string
        if cnt == 1:
            translation = self.one
        elif cnt == 0 and "zero" in self:  # zero is optional
            translation = self.zero
        else:
            translation = self.many

        # format and return string
        return translation(*args, **kwargs)

    def __getattribute__(self, item: str):
        """Use __getattr__ for non-protected attributes."""

        if item.startswith("_"):
            return super().__getattribute__(item)
        return self.__getattr__(item)

    def __getattr__(self, item):
        """Return a nested item and wrap it in a _FormatString or _PluralDict"""

        value = self[item] if item in self else self._fallback[item]

        if isinstance(value, str):
            value = _FormatString(value)
        elif isinstance(value, dict):
            value = _PluralDict(value)
            value._fallback = self._fallback[item]

        return value


Source = namedtuple("Source", ["priority", "path"])


class _Namespace:
    """Translation namespace containing translations for main and fallback language"""

    def __init__(self):
        # list of source directories for translation files
        self._sources: list[Source] = []

        # map languages to translation dictionaries
        self._translations: dict[str, dict[str, Any]] = {}

    def _add_source(self, prio: int, source: Path):
        """
        Add a new translation source.

        :param prio: priority of translation source (higher priority overrides lower priority)
        :param source: path to the directory containing the translation files
        """

        self._sources.append(Source(prio, source))
        self._translations.clear()

    def _get_language(self, lang: str) -> dict[str, Any]:
        """Return (and load if necessary) the translation dictionary of a given language."""

        if lang not in self._translations:
            self._translations[lang] = {}

            # load translations from sources and merge them
            for _, source in sorted(self._sources):
                path = source.joinpath(f"{lang}.yml")
                if not path.exists():
                    continue

                with path.open() as file:
                    merge(self._translations[lang], yaml.safe_load(file) or {})

        return self._translations[lang]

    def _get_translation(self, key: str) -> Any:
        """Return an item from the translation dictionary."""

        translations: dict[str, Any] = self._get_language(Translations.LANGUAGE)

        if key not in translations:
            translations = self._get_language(Translations.FALLBACK)

        return translations[key]

    def __getattr__(self, item: str) -> Any:
        """Return an item and wrap it in a _FormatString or _PluralDict"""

        value = self._get_translation(item)

        if isinstance(value, str):
            value = _FormatString(value)
        elif isinstance(value, dict):
            value = _PluralDict(value)
            value._fallback = self._get_language(Translations.FALLBACK)[item]

        return value


class Translations:
    """Container of multiple translation namespaces"""

    LANGUAGE: str
    FALLBACK: str = "en"

    def __init__(self):
        self._namespaces: dict[str, _Namespace] = {}

    def register_namespace(self, name: str, path: Path, prio: int = 0):
        """Register a new source for a translation namespace."""

        if name not in self._namespaces:
            logger.debug("creating new translation namespace '%s'", name)
            self._namespaces[name] = _Namespace()
        else:
            logger.debug("extending translation namespace '%s'", name)

        # noinspection PyProtectedMember
        self._namespaces[name]._add_source(prio, path)

    def __getattr__(self, item: str):
        """Return a translation namespace"""

        return self._namespaces[item]


def load_translations(path: Path, prio: int = 0):
    """Recursively load all translations in a given directory and register the appropriate namespaces."""

    # skip hidden directories
    if path.name.startswith("."):
        return

    # check if current directory contains a translations subdirectory
    if (p := path.joinpath("translations")).is_dir():
        # register translations directory and return
        t.register_namespace(path.name, p, prio=prio)
        return

    # recurse into subdirectories
    for p in path.iterdir():
        if p.is_dir() and not p.name.startswith("_"):
            load_translations(p, prio)


# create a global translations container
t = Translations()

# register a namespace for global translations
t.register_namespace("g", Path(__file__).parent.joinpath("translations"))

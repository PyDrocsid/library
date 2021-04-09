from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from PyDrocsid.logger import get_logger

logger = get_logger(__name__)


def merge(base: dict, src: dict):
    for k, v in src.items():
        if k not in base or not isinstance(v, dict) or not isinstance(base[k], dict):
            base[k] = v
        else:
            merge(base[k], v)


class _FormatString(str):
    __call__ = str.format


class _PluralDict(dict):
    def __call__(self, *args, **kwargs) -> str:
        cnt = None
        if "cnt" in kwargs:
            cnt = kwargs["cnt"]
        elif "count" in kwargs:
            cnt = kwargs["count"]

        if cnt == 1:
            translation = self.one
        elif cnt == 0 and "zero" in self:
            translation = self.zero
        else:
            translation = self.many

        return translation(*args, **kwargs)

    def __getattr__(self, item):
        value = self[item] if item in self else self._fallback[item]

        if isinstance(value, str):
            value = _FormatString(value)
        elif isinstance(value, dict):
            value = _PluralDict(value)
            value._fallback = self._fallback[item]

        return value


class _Namespace:
    def __init__(self):
        self._sources: list[tuple[int, Path]] = []
        self._translations: dict[str, Any] = {}

    def _add_source(self, prio: int, source: Path):
        self._sources.append((prio, source))
        self._translations.clear()

    def _get_language(self, lang: str) -> dict[str, Any]:
        if lang not in self._translations:
            self._translations[lang] = {}

            for _, source in sorted(self._sources):
                path = source.joinpath(f"{lang}.yml")
                if not path.exists():
                    continue

                with path.open() as file:
                    merge(self._translations[lang], yaml.safe_load(file) or {})

        return self._translations[lang]

    def _get_translation(self, key: str) -> Any:
        translations: dict[str, Any] = self._get_language(Translations.LANGUAGE)

        if key not in translations:
            translations = self._get_language(Translations.FALLBACK)

        return translations[key]

    def __getattr__(self, item: str) -> Any:
        value = self._get_translation(item)

        if isinstance(value, str):
            value = _FormatString(value)
        elif isinstance(value, dict):
            value = _PluralDict(value)
            value._fallback = self._get_language(Translations.FALLBACK)[item]

        return value


class Translations:
    LANGUAGE: str
    FALLBACK: str = "en"

    def __init__(self):
        self._namespaces: dict[str, _Namespace] = {}

    def register_namespace(self, name: str, path: Path, prio: int = 0):
        if name not in self._namespaces:
            logger.debug("creating new translation namespace '%s'", name)
            self._namespaces[name] = _Namespace()
        else:
            logger.debug("extending translation namespace '%s'", name)

        # noinspection PyProtectedMember
        self._namespaces[name]._add_source(prio, path)

    def __getattr__(self, item: str):
        return self._namespaces[item]


def load_translations(path: Path, prio: int = 0):
    if path.name.startswith("."):
        return

    if (p := path.joinpath("translations")).is_dir():
        t.register_namespace(path.name, p, prio=prio)
        return

    for p in path.iterdir():
        if p.is_dir() and not p.name.startswith("_"):
            load_translations(p, prio)


t = Translations()
t.register_namespace("g", Path(__file__).parent.joinpath("translations"))

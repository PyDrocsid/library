import json
import os
from typing import Dict


def _invert_dict(d: dict[str, str]) -> dict[str, list[str]]:
    """Invert a dictionary such that every value is mapped to a list of its keys."""

    out: dict[str, list[str]] = {}
    for k, v in d.items():
        out.setdefault(v, []).append(k)

    return out


with open(os.path.join(os.path.dirname(__file__), "emoji_map.json"), encoding="utf-8") as map_file:
    # maps emoji names to their unicode characters
    name_to_emoji: Dict[str, str] = json.load(map_file)

    # maps emoji unicode characters to their names
    emoji_to_name: Dict[str, list[str]] = _invert_dict(name_to_emoji)

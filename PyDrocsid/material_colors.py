import os
from typing import Union

import yaml


class NestedInt(int):
    """Combination of integer and read only dictionary."""

    _values = {}

    def __new__(cls, x, values):
        obj = super(NestedInt, cls).__new__(cls, x)
        obj._values = values
        return obj

    def __getitem__(self, key):
        return self._values[key]

    def __iter__(self):
        return self._values.__iter__()

    def items(self):
        return self._values.items()

    def __copy__(self):
        return int(self)

    def __deepcopy__(self, *_):
        return int(self)


with open(os.path.join(os.path.dirname(__file__), "material_colors.yml"), encoding="utf-8") as file:
    _color_data: dict[str, dict[Union[int, str], int]] = yaml.safe_load(file)


def _load_color(name: str) -> NestedInt:
    data = _color_data[name]
    return NestedInt(data[500], data)


class MaterialColors:
    """List of all material colors"""

    red = _load_color("red")
    pink = _load_color("pink")
    purple = _load_color("purple")
    deeppurple = _load_color("deeppurple")
    indigo = _load_color("indigo")
    blue = _load_color("blue")
    lightblue = _load_color("lightblue")
    cyan = _load_color("cyan")
    teal = _load_color("teal")
    green = _load_color("green")
    lightgreen = _load_color("lightgreen")
    lime = _load_color("lime")
    yellow = _load_color("yellow")
    amber = _load_color("amber")
    orange = _load_color("orange")
    deeporange = _load_color("deeporange")
    brown = _load_color("brown")
    grey = _load_color("grey")
    bluegrey = _load_color("bluegrey")

    default = teal
    error = red
    warning = yellow[700]

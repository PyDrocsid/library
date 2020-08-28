import os
import json

with open(os.path.join(os.path.dirname(__file__), "emoji_map.json"), encoding="utf-8") as map_file:
    emoji_map = json.load(map_file)

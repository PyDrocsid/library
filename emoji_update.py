import json
import re
import sys
from html.parser import HTMLParser
from json import JSONDecodeError
from pathlib import Path
from typing import Any, cast
from urllib.request import Request, urlopen


EMOJI_JSON_REGEX = re.compile(r'{("\w+":\[({"names":.+"surrogates":.+},)*{"names":.+"surrogates":.+}])+}')


def get(url: str) -> str:
    return cast(bytes, urlopen(Request(url, data=None, headers={"User-Agent": ""})).read()).decode("utf8")  # noqa: S310


def convert_emoji_map(categories: dict[Any, Any]) -> dict[Any, Any]:
    return {
        **{
            name: emoji["surrogates"]
            for category in categories.values()
            for emoji in category
            for name in emoji["names"]
        },
        **{
            name: child["surrogates"]
            for category in categories.values()
            for emoji in category
            if "diversityChildren" in emoji
            for child in emoji["diversityChildren"]
            for name in child["names"]
        },
    }


class DiscordLoginPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()

        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "script":
            return

        for name, value in attrs:
            if name != "src":
                continue

            if value and value.startswith("/assets/") and value.endswith(".js"):
                self.urls.append(f"https://discord.com{value}")

    def error(self, message: str) -> None:
        print(f"Error while parsing the Discord login page: {message}")


if __name__ == "__main__":
    login_page = get("https://discord.com/login")
    parser = DiscordLoginPageParser()
    parser.feed(login_page)

    emoji_json: Any | None = None

    for script_url in reversed(parser.urls):
        json_match = EMOJI_JSON_REGEX.search(get(script_url))
        if json_match:
            try:
                emoji_json = json.loads(json_match.group(0))
                break
            except JSONDecodeError as e:
                print(
                    f"Error while decoding emoji JSON from {script_url} "
                    f"(position {json_match.start(0)}-{json_match.end(0)}): {e}"
                )

    if not emoji_json:
        print("Emoji map could not be found")
        sys.exit(1)

    result = convert_emoji_map(emoji_json)
    print(f"Found {len(result)} emojis including variations")

    with Path(__file__).parent.joinpath("PyDrocsid/emoji_map.json").open("w") as file:
        json.dump(result, file)

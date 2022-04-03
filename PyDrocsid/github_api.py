from collections import namedtuple
from typing import Any, cast

from aiohttp import ClientSession

from PyDrocsid.environment import GITHUB_TOKEN


GitHubUser = namedtuple("GitHubUser", ["id", "name", "profile"])

API_URL = "https://api.github.com/graphql"


async def graphql(query: str, **kwargs: Any) -> dict[Any, Any] | None:
    """Send a query to the github graphql api and return the result."""

    headers = {"Authorization": f"bearer {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}
    async with ClientSession() as session:
        async with session.post(API_URL, headers=headers, json={"query": query, "variables": kwargs}) as response:
            if response.status != 200:
                return None

            return cast(dict[Any, Any], (await response.json())["data"])


async def get_users(ids: list[str]) -> dict[str, GitHubUser] | None:
    """Get a list of github users by their ids."""

    result = await graphql("query($ids:[ID!]!){nodes(ids:$ids){...on User{id,login,url}}}", ids=ids)
    if not result:
        return None

    return {user["id"]: GitHubUser(user["id"], user["login"], user["url"]) for user in result["nodes"]}


async def get_repo_description(owner: str, name: str) -> str | None:
    """Get the description of a github repository."""

    result = await graphql(
        "query($owner:String!,$name:String!){repository(owner:$owner,name:$name){description}}", owner=owner, name=name
    )
    if not result:
        return None

    return cast(str | None, result["repository"]["description"])

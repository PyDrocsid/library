from os import environ, getenv


def get_bool(key: str, default: bool) -> bool:
    """Get a boolean from an environment variable."""

    return getenv(key, str(default)).lower() in ("true", "t", "yes", "y", "1")


TOKEN: str = environ["TOKEN"]  # bot token
LOG_LEVEL: str = getenv("LOG_LEVEL", "INFO")

# database configuration
DB_DRIVER: str = getenv("DB_DRIVER", "mysql+aiomysql")
DB_HOST: str = getenv("DB_HOST", "localhost")
DB_PORT: int = int(getenv("DB_PORT", "3306"))
DB_DATABASE: str = getenv("DB_DATABASE", "bot")
DB_USERNAME: str = getenv("DB_USERNAME", "bot")
DB_PASSWORD: str = getenv("DB_PASSWORD", "bot")
POOL_RECYCLE: int = int(getenv("POOL_RECYCLE", 300))
POOL_SIZE: int = int(getenv("POOL_SIZE", 20))
MAX_OVERFLOW: int = int(getenv("MAX_OVERFLOW", 20))
SQL_SHOW_STATEMENTS: bool = get_bool("SQL_SHOW_STATEMENTS", False)

SENTRY_DSN: str = getenv("SENTRY_DSN")  # sentry data source name
GITHUB_TOKEN: str = getenv("GITHUB_TOKEN")  # github personal access token

OWNER_ID: int = int(getenv("OWNER_ID", 0))

DISABLED_COGS: set[str] = set(map(str.lower, getenv("DISABLED_COGS", "").split(",")))

# redis configuration
REDIS_HOST: str = environ["REDIS_HOST"]
REDIS_PORT: int = int(getenv("REDIS_PORT", "6379"))
REDIS_DB: int = int(getenv("REDIS_DB", "0"))

CACHE_TTL: int = int(getenv("CACHE_TTL", 8 * 60 * 60))
RESPONSE_LINK_TTL: int = int(getenv("RESPONSE_LINK_TTL", 2 * 60 * 60))
PAGINATION_TTL: int = int(getenv("PAGINATION_TTL", 2 * 60 * 60))

# configuration for reply feature
REPLY: bool = get_bool("REPLY", True)
MENTION_AUTHOR: bool = get_bool("MENTION_AUTHOR", True)

DISABLE_PAGINATION: bool = get_bool("DISABLE_PAGINATION", False)

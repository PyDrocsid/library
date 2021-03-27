from os import environ, getenv


def get_bool(key: str, default: bool) -> bool:
    return getenv(key, str(default)).lower() in ("true", "t", "yes", "y", "1")


TOKEN: str = environ["TOKEN"]
LOG_LEVEL: str = getenv("LOG_LEVEL", "INFO")

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

SENTRY_DSN: str = getenv("SENTRY_DSN")
GITHUB_TOKEN: str = getenv("GITHUB_TOKEN")

REDIS_HOST: str = environ["REDIS_HOST"]
REDIS_PORT: int = int(getenv("REDIS_PORT", "6379"))
REDIS_DB: int = int(getenv("REDIS_DB", "0"))

CACHE_TTL: int = int(getenv("CACHE_TTL", 8 * 60 * 60))
RESPONSE_LINK_TTL: int = int(getenv("RESPONSE_LINK_TTL", 2 * 60 * 60))

REPLY: bool = get_bool("REPLY", False)
MENTION_AUTHOR: bool = get_bool("MENTION_AUTHOR", False)

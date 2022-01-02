import logging
import sys

import sentry_sdk
from sentry_sdk.integrations.aiohttp import AioHttpIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from uvicorn.config import LOGGING_CONFIG
from uvicorn.logging import DefaultFormatter

from PyDrocsid.environment import LOG_LEVEL


def setup_sentry(dsn: str, name: str, version: str):
    """Initialize sentry connection."""

    sentry_sdk.init(
        dsn=dsn,
        attach_stacktrace=True,
        shutdown_timeout=5,
        integrations=[
            AioHttpIntegration(),
            SqlalchemyIntegration(),
            LoggingIntegration(
                level=logging.DEBUG,
                event_level=logging.WARNING,
            ),
        ],
        release=f"{name}@{version}",
    )


logging_formatter = DefaultFormatter(fmt := "[%(asctime)s] %(levelprefix)s %(message)s")
LOGGING_CONFIG["formatters"]["default"]["fmt"] = fmt
LOGGING_CONFIG["formatters"]["access"][
    "fmt"
] = '[%(asctime)s] %(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s'

logging_handler = logging.StreamHandler(sys.stdout)
logging_handler.setFormatter(logging_formatter)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with a given name."""

    logger: logging.Logger = logging.getLogger(name)
    logger.addHandler(logging_handler)
    logger.setLevel(LOG_LEVEL.upper())

    return logger

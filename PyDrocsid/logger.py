import logging
import sentry_sdk

logging_handler = logging.StreamHandler()
logging_formatter = logging.Formatter('{asctime} - {levelname} - {name} - {message}', style='{')


class Message:
    def __init__(self, fmt: str, args: tuple):
        self._fmt = fmt
        self._args = args

    def __str__(self):
        return self._fmt.format(*self._args)


class LoggingAdapter(logging.LoggerAdapter):
    def __init__(self, logger, extra=None):
        super().__init__(logger, extra or {})

    def log(self, level: int, msg: str, *args, error=None, **kwargs):  # skipcq: PYL-W0221
        if self.isEnabledFor(level):
            msg, kwargs = self.process(msg, kwargs)
            self.logger._log(level, Message(msg, args), (), {})  # skipcq: PYL-W0212


def get_logger(name, handler=logging_handler, formatter=logging_formatter, level=logging.INFO):
    logger = LoggingAdapter(logging.getLogger(name))
    handler.setFormatter(formatter)
    logger.logger.addHandler(handler)
    logger.setLevel(level)
    return logger

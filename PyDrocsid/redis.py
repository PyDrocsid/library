from aioredis import Redis, from_url

from PyDrocsid.environment import REDIS_DB, REDIS_HOST, REDIS_PORT

# global redis connection
redis: Redis = from_url(f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}", encoding="utf-8", decode_responses=True)

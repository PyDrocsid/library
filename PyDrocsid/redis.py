from aioredis import from_url, Redis

from PyDrocsid.environment import REDIS_HOST, REDIS_PORT, REDIS_DB

# global redis connection
redis: Redis = from_url(f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}", encoding="utf-8", decode_responses=True)

from asyncio import get_event_loop

from aioredis import create_redis_pool, Redis

from PyDrocsid.environment import REDIS_HOST, REDIS_PORT, REDIS_DB

loop = get_event_loop()
redis: Redis = loop.run_until_complete(
    create_redis_pool(f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}", encoding="utf-8", loop=loop),
)

import redis.asyncio as aioredis
from typing import Optional


class RedisClient:
    def __init__(self, host: str = "localhost", port: int = 6379):
        self._host = host
        self._port = port
        self._conn: Optional[aioredis.Redis] = None

    async def connect(self):
        if not self._conn:
            self._conn = aioredis.Redis(
                host=self._host,
                port=self._port,
            )

    async def close(self):
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def set(self, key: str, value: str):
        if not self._conn:
            await self.connect()
        await self._conn.set(key, value)

    async def get(self, key: str):
        if not self._conn:
            await self.connect()
        return await self._conn.get(key)

    async def hset(self, name: str, key: str, value: str):
        if not self._conn:
            await self.connect()
        await self._conn.hset(name, key, value)

    async def hgetall(self, name: str):
        if not self._conn:
            await self.connect()
        return await self._conn.hgetall(name)

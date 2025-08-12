import asyncpg
from typing import Optional, Any, List, Dict


class AsyncPostgresClient:
    def __init__(self, user: str, password: str, database: str, host: str = "localhost", port: int = 5432):
        self._user = user
        self._password = password
        self._database = database
        self._host = host
        self._port = port
        self._conn: Optional[asyncpg.Connection] = None

    async def connect(self):
        if not self._conn:
            self._conn = await asyncpg.connect(
                user=self._user,
                password=self._password,
                database=self._database,
                host=self._host,
                port=self._port
            )

    async def close(self):
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def execute(self, query: str, *args: Any):
        if not self._conn:
            await self.connect()
        await self._conn.execute(query, *args)

    async def fetch(self, query: str, *args: Any) -> List[Dict[str, Any]]:
        if not self._conn:
            await self.connect()
        rows = await self._conn.fetch(query, *args)
        return [dict(row) for row in rows]

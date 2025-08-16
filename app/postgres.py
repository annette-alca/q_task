import asyncpg
from typing import Optional, Any, List, Dict, TypeVar, Generic
from pydantic import BaseModel

T = TypeVar('T', bound=BaseModel)

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

    async def fetchrow(self, query: str, *args: Any) -> Optional[Dict[str, Any]]:
        if not self._conn:
            await self.connect()
        row = await self._conn.fetchrow(query, *args)
        return dict(row) if row else None

    async def fetchval(self, query: str, *args: Any):
        if not self._conn:
            await self.connect()
        return await self._conn.fetchval(query, *args)

    async def fetch_model(self, model_class: type[T], query: str, *args: Any) -> Optional[T]:
        """Fetch a single row and return as a Pydantic model"""
        row = await self.fetchrow(query, *args)
        if row:
            return model_class(**row)
        return None

    async def fetch_models(self, model_class: type[T], query: str, *args: Any) -> List[T]:
        """Fetch multiple rows and return as a list of Pydantic models"""
        rows = await self.fetch(query, *args)
        return [model_class(**row) for row in rows]

    async def insert_model(self, model: BaseModel, table: str) -> int:
        """Insert a Pydantic model into a table and return the ID"""
        fields = model.dict(exclude_unset=True, exclude={'id'})
        field_names = list(fields.keys())
        placeholders = [f"${i+1}" for i in range(len(field_names))]
        
        query = f"""
            INSERT INTO {table} ({', '.join(field_names)})
            VALUES ({', '.join(placeholders)})
            RETURNING id
        """
        return await self.fetchval(query, *fields.values())

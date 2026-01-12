from scurrypy import Client

import asyncpg

class PostgresDB:
    def __init__(self, client: Client, user: str, database: str, password: str):
        self.bot = client

        from urllib.parse import quote

        self.dsn = f"postgresql://{user}:{quote(password)}@localhost:5432/{database}"
        self.pool: asyncpg.Pool = None
    
        client.add_startup_hook(self.start_db)
        client.add_shutdown_hook(self.close_db)

    async def start_db(self):
        self.pool = await asyncpg.create_pool(self.dsn)
    
    async def close_db(self):
        await self.pool.close()

    async def get_connection(self) -> asyncpg.Connection:
        return await self.pool.acquire()

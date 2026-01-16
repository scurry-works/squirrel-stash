import asyncpg
from dataclasses import dataclass

LB_SIZE = 3

@dataclass
class LeaderboardEntry:
    rank: int
    user_id: int
    best_score: int

class Leaderboard:
    async def fetch(self, conn: asyncpg.Connection, guild_id: int):
        q = await conn.fetch(
            """
                WITH leaderboard AS (
                SELECT
                    user_id,
                    GREATEST(highscore, score) AS best_score,
                    ROW_NUMBER() OVER (ORDER BY GREATEST(highscore, score) DESC) AS rank
                FROM player
                WHERE guild_id = $1
                )
                SELECT rank, user_id, best_score
                FROM leaderboard
                LIMIT $2
            """, guild_id, LB_SIZE)
        
        return [LeaderboardEntry(rank, user_id, best_score) for rank, user_id, best_score in q]
    
    async def fetch_local_player(self, conn: asyncpg.Connection, guild_id: int, user_id: int):
        leaderboard = await conn.fetchrow(
            """
                WITH leaderboard AS (
                SELECT
                    user_id,
                    GREATEST(highscore, score) AS best_score,
                    ROW_NUMBER() OVER (ORDER BY GREATEST(highscore, score) DESC) AS rank
                FROM player
                WHERE guild_id = $1
                )
                SELECT rank, user_id, best_score
                FROM leaderboard
                WHERE user_id = $2
            """,
            guild_id, user_id
        )

        if not leaderboard:
            return False
                
        return LeaderboardEntry(*leaderboard)

    async def fetch_global_player(self, conn: asyncpg.Connection, user_id: int):
        leaderboard = await conn.fetchrow(
            """
                WITH leaderboard AS (
                SELECT
                    user_id,
                    GREATEST(highscore, score) AS best_score,
                    ROW_NUMBER() OVER (ORDER BY GREATEST(highscore, score) DESC) AS rank
                FROM player
                )
                SELECT rank, user_id, best_score
                FROM leaderboard
                WHERE user_id = $1;
            """,
            user_id
        )

        if not leaderboard:
            return False
                
        return LeaderboardEntry(*leaderboard)

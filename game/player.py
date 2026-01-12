import asyncpg
from dataclasses import dataclass, field

from .card import Card

MAX_HEALTH = 5
OPTIONS_SIZE = 3

"""
create table player(
    user_id bigint,
    session_id text,
    hp int,
    score int,
    highscore int,
    guild_id bigint,
    hand text[],
    options text[]
);
"""

@dataclass
class Player:
    user_id: int

    session_id: str = None
    hp: int = MAX_HEALTH
    score: int = 0
    highscore: int = 0
    guild_id: int = 0

    hand: list[str | Card] = field(default_factory=list)
    options: list[str | Card] = field(default_factory=list)

    async def fetch(self, conn: asyncpg.Connection):
        record = await conn.fetchrow(f"select * from player where user_id = {self.user_id}")

        if not record:
            options = [Card.random().to_str() for _ in range(OPTIONS_SIZE)]

            await conn.execute("insert into player values ($1, 0, $2, 0, 0, 0, '{}', $3::text[])", self.user_id, MAX_HEALTH, options)
            record = await conn.fetchrow("select * from player where user_id = $1", self.user_id)
        
        record = dict(record)

        self.session_id = record.get('session_id')
        self.hp = record.get('hp')
        self.score = record.get('score')
        self.highscore = record.get('highscore')
        self.guild_id = record.get('guild_id')

        self.hand = [Card.to_card(c) for c in record.get('hand', [])]
        self.options = [Card.to_card(c) for c in record.get('options')]

        return self

    async def save(self, conn: asyncpg.Connection):
        new_hand = [c.to_str() for c in self.hand]
        new_options = [c.to_str() for c in self.options]

        await conn.execute("update player set session_id = $1, hp = $2, score = $3, highscore = $4, hand = $5::text[], options = $6::text[], guild_id = $7 where user_id = $8",
            self.session_id, self.hp, self.score, self.highscore, new_hand, new_options, self.guild_id, self.user_id)
    
    def matches(self):
        cards = {}

        for c in self.hand:
            cards[c.rank] = cards.setdefault(c.rank, 0) +1
        
        return {r: n for r, n in cards.items() if n > 1}
    
    def has_rank(self, rank: str):
        return rank in [c.rank for c in self.hand]
    
    def pop_match(self, rank: str):
        removed_cards = []
        for _ in range(2):
            card = next(c for c in self.hand if c.rank == rank)
            self.hand.remove(card)
            removed_cards.append(card)
        return removed_cards
        
    def pop_rank(self, rank: str):
        card = next((c for c in self.hand if c.rank == rank))
        
        self.hand.remove(card)

        return card
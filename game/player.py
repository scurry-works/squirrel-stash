import asyncpg
import random
from dataclasses import dataclass, field

from .card import Card, RANKS, SUITS, FACES
from .cards import Cards
from .select_event import SelectEvent

MAX_HEALTH = 3
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
            options = [
                Card.random_rank().to_str() 
                for _ in range(OPTIONS_SIZE)
            ]

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

    def add_card(self, card: Card):
        new_hand = self.hand + [card]

        e = SelectEvent(
            is_match=Cards.has_rank(self.hand, card), 
            is_stash=Cards.sum_cards(new_hand) == 21
        )

        if e.is_stash:
            e.points = 100

            if Cards.all_one_suit(new_hand):
                e.points = 500
                e.suit = card.emoji_name

            self.hand.clear()

        elif e.is_match:
            matching_card = Cards.get_next_card(self.hand, card)

            e.points = 2 * card.value
            if Cards.all_one_suit([matching_card, card]):
                e.points *= 3
                e.suit = card.emoji_name

            self.hand.remove(matching_card)
        else:
            self.hand.append(card)
        
        self.score += e.points
        
        return e

    def new_options(self):
        ranks = random.sample(population=RANKS if len(self.hand) == 0 else RANKS + FACES, k=OPTIONS_SIZE)
        suits = random.choices(population=SUITS, k=OPTIONS_SIZE)

        new_options = [Card(s, r) for s, r in zip(suits, ranks)]

        if random.randint(0, 100) > 80:
            new_options[random.randint(0, OPTIONS_SIZE -1)] = Card('HP', '+1')

        self.options = new_options

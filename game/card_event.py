from dataclasses import dataclass

from .card import Card
from .cards import Cards

@dataclass
class CardEvent:
    points: int = 0
    stash_suit: str = None
    match_suit: str = None
    is_match: bool = False
    is_stash: bool = False

    def check_21(self, cards: list[Card], card: Card):
        p_cards = cards + [card] if card else cards

        self.is_stash = Cards.sum_cards(p_cards) == 21

        if self.is_stash:
            self.stash_suit = Cards.all_one_suit(p_cards)
            self.points += 500 if self.stash_suit else 100

            cards.clear()
        
        return cards

    def check_match(self, cards: list[Card], card: Card):
        self.is_match = card.rank in [c.rank for c in cards]

        add_pts = 0

        if self.is_match:
            matching_card = Cards.get_next_card(cards, card)

            add_pts = 2 * card.value
            self.match_suit = Cards.all_one_suit([matching_card, card])

            if self.match_suit:
                add_pts *= 2

            cards.remove(matching_card)

        self.points += add_pts

        return cards

from .card import Card

class Cards:
    @staticmethod
    def sum_cards(cards: list[Card]):
        from functools import reduce
        return reduce(lambda x, y: x + y, [c.value for c in cards], 0)

    @staticmethod
    def all_one_suit(cards: list[Card]):
        return cards[0].emoji_name if len(set([c.suit for c in cards])) == 1 else None
    
    @staticmethod
    def get_next_card(cards: list[Card], card: Card):
        return next(c for c in cards if c.rank == card.rank)
    
    @staticmethod
    def get_highest_card(cards: list[Card]):
        highest_rank = max([c.value for c in cards])
        return next(c for c in cards if c.value == highest_rank)

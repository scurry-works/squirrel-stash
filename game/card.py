from dataclasses import dataclass

STANDARD_RANKS = ['A', '2', '3', '4', '5', '6', '7', '8', '9', 'B', 'P', 'W']
STANDARD_SUITS = ['GL', 'SP', 'DG', 'LA']

@dataclass
class Card:
    suit: str
    rank: str

    @property
    def value(self):
        if self.rank in ['B', 'P', 'W']:
            return 10
        elif self.rank == 'A':
            return 1
        else:
            return int(self.rank)
        
    @property
    def emoji_name(self):
        
        # NOTE: Suit can only be these 5 values!
        match self.suit:
            case 'GL':
                return 'acorn'
            case 'SP':
                return 'flaming_acorn'
            case 'DG':
                return 'frozen_acorn'
            case 'LA':
                return 'corrupt_acorn'
            case 'HP':
                return 'heart'
    
    @staticmethod
    def random():
        import random

        return Card(random.choice(STANDARD_SUITS), random.choice(STANDARD_RANKS))
    
    @staticmethod
    def to_card(card_fmt: str):
        suit, rank = card_fmt.split('.')

        return Card(suit, rank)

    def to_str(self):
        return f"{self.suit}.{self.rank}"  

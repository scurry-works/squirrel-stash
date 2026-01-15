import random
from dataclasses import dataclass

RANKS = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10']
FACES = ['B', 'P', 'W']
SUITS = ['GL', 'SP', 'DG', 'LA']

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
        return Card(random.choice(SUITS), random.choice(RANKS + FACES))
    
    @staticmethod
    def random_rank():
        return Card(random.choice(SUITS), random.choice(RANKS))
    
    @staticmethod
    def to_card(card_fmt: str):
        suit, rank = card_fmt.split('.')

        return Card(suit, rank)

    def to_str(self):
        return f"{self.suit}.{self.rank}"  

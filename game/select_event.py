from dataclasses import dataclass

@dataclass
class SelectEvent:
    points: int = 0
    suit: str = None
    is_match: bool = False
    is_stash: bool = False

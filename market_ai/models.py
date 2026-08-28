from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class Quote:
    event_id: str
    home: str
    away: str
    minute: Optional[int]
    score: str
    bookmaker: str
    market: str
    selection: str
    line: Optional[float]
    odds: float
    ts: float
    source: str

    @property
    def key(self):
        return (self.event_id, self.market, self.selection, self.line, self.bookmaker)

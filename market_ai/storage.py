import sqlite3
from .models import Quote

SCHEMA = '''
CREATE TABLE IF NOT EXISTS quotes(event_id TEXT,home TEXT,away TEXT,minute INTEGER,score TEXT,bookmaker TEXT,market TEXT,selection TEXT,line REAL,odds REAL,ts REAL,source TEXT);
CREATE INDEX IF NOT EXISTS idx_quotes_lookup ON quotes(event_id,market,selection,line,ts);
CREATE TABLE IF NOT EXISTS alerts(alert_key TEXT PRIMARY KEY, sent_at REAL, score REAL);
'''

class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)
        self.db.commit()
    def add(self, quotes):
        self.db.executemany('INSERT INTO quotes VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',[(q.event_id,q.home,q.away,q.minute,q.score,q.bookmaker,q.market,q.selection,q.line,q.odds,q.ts,q.source) for q in quotes])
        self.db.commit()
    def history(self, q, since):
        return self.db.execute('SELECT bookmaker,odds,ts FROM quotes WHERE event_id=? AND market=? AND selection=? AND line IS ? AND ts>=? ORDER BY ts', (q.event_id,q.market,q.selection,q.line,since)).fetchall()
    def can_alert(self, key, now, cooldown):
        row=self.db.execute('SELECT sent_at FROM alerts WHERE alert_key=?',(key,)).fetchone()
        return not row or now-row[0]>=cooldown
    def mark_alert(self,key,now,score):
        self.db.execute('INSERT OR REPLACE INTO alerts VALUES(?,?,?)',(key,now,score)); self.db.commit()

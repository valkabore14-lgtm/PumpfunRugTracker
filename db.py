import sqlite3
from datetime import datetime, timezone

def utcnow():
    return datetime.now(timezone.utc)

class DB:
    def __init__(self, path="db.sqlite"):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init()

    def _init(self):
        cur = self.conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS wallets (
            address TEXT PRIMARY KEY,
            is_seed INTEGER NOT NULL,
            parent TEXT,
            hop INTEGER NOT NULL,
            expires_at TEXT
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            src TEXT NOT NULL,
            dst TEXT NOT NULL,
            lamports INTEGER NOT NULL,
            signature TEXT,
            created_at TEXT NOT NULL
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS seen_creates (
            signature TEXT PRIMARY KEY,
            mint TEXT,
            creator TEXT,
            created_at TEXT NOT NULL
        )
        """)
        self.conn.commit()

    def upsert_seed(self, address: str):
        cur = self.conn.cursor()
        cur.execute("""
        INSERT INTO wallets(address, is_seed, parent, hop, expires_at)
        VALUES(?, 1, NULL, 0, NULL)
        ON CONFLICT(address) DO UPDATE SET is_seed=1, hop=0, parent=NULL, expires_at=NULL
        """, (address,))
        self.conn.commit()

    def cleanup_expired(self):
        cur = self.conn.cursor()
        now = utcnow().isoformat()
        cur.execute("DELETE FROM wallets WHERE is_seed=0 AND expires_at IS NOT NULL AND expires_at < ?", (now,))
        self.conn.commit()

    def is_watched(self, address: str) -> bool:
        self.cleanup_expired()
        cur = self.conn.cursor()
        r = cur.execute("SELECT 1 FROM wallets WHERE address=?", (address,)).fetchone()
        return r is not None

    def get_wallet(self, address: str):
        self.cleanup_expired()
        cur = self.conn.cursor()
        return cur.execute("SELECT * FROM wallets WHERE address=?", (address,)).fetchone()

    def add_descendant(self, src: str, dst: str, hop: int, expires_at_iso: str):
        cur = self.conn.cursor()
        cur.execute("""
        INSERT INTO wallets(address, is_seed, parent, hop, expires_at)
        VALUES(?, 0, ?, ?, ?)
        ON CONFLICT(address) DO UPDATE SET
            parent=excluded.parent,
            hop=MIN(wallets.hop, excluded.hop),
            expires_at=MAX(wallets.expires_at, excluded.expires_at)
        """, (dst, src, hop, expires_at_iso))
        self.conn.commit()

    def add_edge(self, src: str, dst: str, lamports: int, signature: str):
        cur = self.conn.cursor()
        cur.execute("""
        INSERT INTO edges(src, dst, lamports, signature, created_at)
        VALUES(?,?,?,?,?)
        """, (src, dst, lamports, signature, utcnow().isoformat()))
        self.conn.commit()

    def mark_seen_create(self, signature: str, mint: str, creator: str):
        cur = self.conn.cursor()
        cur.execute("""
        INSERT OR IGNORE INTO seen_creates(signature, mint, creator, created_at)
        VALUES(?,?,?,?)
        """, (signature, mint, creator, utcnow().isoformat()))
        self.conn.commit()

    def already_seen_create(self, signature: str) -> bool:
        cur = self.conn.cursor()
        r = cur.execute("SELECT 1 FROM seen_creates WHERE signature=?", (signature,)).fetchone()
        return r is not None

    def trace_to_seed(self, address: str, max_steps=20):
        path = [address]
        cur = self.conn.cursor()
        steps = 0
        while steps < max_steps:
            row = cur.execute("SELECT * FROM wallets WHERE address=?", (path[-1],)).fetchone()
            if not row:
                break
            if row["is_seed"] == 1:
                return path
            parent = row["parent"]
            if not parent:
                break
            path.append(parent)
            steps += 1
        return path

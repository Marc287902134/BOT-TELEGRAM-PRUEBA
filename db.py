import sqlite3, json, os
from datetime import datetime, timezone
from .config import settings

def connect():
    os.makedirs(os.path.dirname(settings.database_path) or ".", exist_ok=True)
    con = sqlite3.connect(settings.database_path)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with connect() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS memory (
            user_id INTEGER PRIMARY KEY, messages TEXT NOT NULL DEFAULT '[]')''')
        c.execute('''CREATE TABLE IF NOT EXISTS pending (
            id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, action TEXT NOT NULL,
            created_at TEXT NOT NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS event_state (
            object_type TEXT PRIMARY KEY, last_seen TEXT NOT NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
            action TEXT, details TEXT, created_at TEXT)''')

def get_memory(user_id):
    with connect() as c:
        row = c.execute("SELECT messages FROM memory WHERE user_id=?", (user_id,)).fetchone()
    return json.loads(row["messages"]) if row else []

def save_memory(user_id, messages):
    messages = messages[-16:]
    with connect() as c:
        c.execute("INSERT INTO memory(user_id,messages) VALUES(?,?) "
                  "ON CONFLICT(user_id) DO UPDATE SET messages=excluded.messages",
                  (user_id, json.dumps(messages, ensure_ascii=False)))

def save_pending(pid, user_id, action):
    with connect() as c:
        c.execute("INSERT OR REPLACE INTO pending VALUES(?,?,?,?)",
                  (pid, user_id, json.dumps(action, ensure_ascii=False),
                   datetime.now(timezone.utc).isoformat()))

def get_pending(pid, user_id):
    with connect() as c:
        row = c.execute("SELECT action FROM pending WHERE id=? AND user_id=?", (pid,user_id)).fetchone()
    return json.loads(row["action"]) if row else None

def delete_pending(pid):
    with connect() as c:
        c.execute("DELETE FROM pending WHERE id=?", (pid,))

def audit(user_id, action, details):
    with connect() as c:
        c.execute("INSERT INTO audit(user_id,action,details,created_at) VALUES(?,?,?,?)",
                  (user_id, action, json.dumps(details, ensure_ascii=False),
                   datetime.now(timezone.utc).isoformat()))

def get_event_state(obj):
    with connect() as c:
        row = c.execute("SELECT last_seen FROM event_state WHERE object_type=?", (obj,)).fetchone()
    return row["last_seen"] if row else None

def set_event_state(obj, stamp):
    with connect() as c:
        c.execute("INSERT INTO event_state VALUES(?,?) ON CONFLICT(object_type) "
                  "DO UPDATE SET last_seen=excluded.last_seen", (obj, stamp))

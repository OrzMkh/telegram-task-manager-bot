import os
import sqlite3
from contextlib import contextmanager

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    HAS_POSTGRES = True
except ImportError:
    HAS_POSTGRES = False

class PostgresCursorWrapper:
    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, query, params=None):
        query = query.replace("?", "%s")
        if "INSERT OR IGNORE" in query:
            query = query.replace("INSERT OR IGNORE", "INSERT")
        query = query.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
        query = query.replace("AUTOINCREMENT", "")
        query = query.replace("REAL DEFAULT 0", "DOUBLE PRECISION DEFAULT 0")
        if "LIKE '%' ||" in query:
            query = query.replace("LIKE '%' ||", "ILIKE '%' ||")
            
        if params is not None:
            self._cursor.execute(query, params)
        else:
            self._cursor.execute(query)
            
    def executemany(self, query, seq):
        query = query.replace("?", "%s")
        if "INSERT OR IGNORE" in query:
            query = query.replace("INSERT OR IGNORE", "INSERT")
        self._cursor.executemany(query, seq)
        
    def fetchone(self):
        res = self._cursor.fetchone()
        return dict(res) if res else None
        
    def fetchall(self):
        res = self._cursor.fetchall()
        return [dict(r) for r in res] if res else []
        
    @property
    def lastrowid(self):
        try:
            self._cursor.execute("SELECT lastval() AS id")
            row = self._cursor.fetchone()
            return row["id"] if row else None
        except Exception:
            return None

class PostgresConnectionWrapper:
    def __init__(self, conn):
        self._conn = conn
        
    def cursor(self):
        return PostgresCursorWrapper(self._conn.cursor())
        
    def commit(self):
        self._conn.commit()
        
    def close(self):
        self._conn.close()
        
    @property
    def row_factory(self):
        return None
        
    @row_factory.setter
    def row_factory(self, val):
        pass

_orig_sqlite3_connect = sqlite3.connect

def connect_wrapper(db_path, *args, **kwargs):
    db_url = os.getenv("DATABASE_URL")
    if db_url and HAS_POSTGRES:
        conn = psycopg2.connect(db_url)
        return PostgresConnectionWrapper(conn)
    else:
        return _orig_sqlite3_connect(db_path, *args, **kwargs)

sqlite3.connect = connect_wrapper

@contextmanager
def get_connection(db_path="tasks.db"):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()



def init_db(db_path="tasks.db"):
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_text TEXT NOT NULL,
                assignee TEXT NOT NULL,
                author TEXT NOT NULL,
                sla_deadline TEXT NOT NULL,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Active',
                reminder_sent INTEGER DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bike_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                report_date TEXT NOT NULL,
                issued TEXT NOT NULL,
                returned TEXT NOT NULL,
                total_in_trip TEXT NOT NULL,
                new_bikes TEXT NOT NULL,
                old_bikes TEXT NOT NULL,
                broken_bikes TEXT NOT NULL,
                return_reasons TEXT NOT NULL,
                comment TEXT,
                created_at TEXT NOT NULL
            )
        """)
        # Ensure rating and dispute columns exist
        cols_to_check = [
            ("priority", "TEXT DEFAULT 'Medium'"),
            ("city", "TEXT DEFAULT 'Ташкент'"),
            ("rating", "INTEGER DEFAULT 0"),
            ("rating_comment", "TEXT"),
            ("initial_rating", "INTEGER DEFAULT 0"),
            ("final_rating", "INTEGER DEFAULT 0"),
            ("is_disputed", "INTEGER DEFAULT 0")
        ]
        cursor.execute("PRAGMA table_info(tasks)")
        existing_cols = [row[1] for row in cursor.fetchall()]
        for col_name, col_type in cols_to_check:
            if col_name not in existing_cols:
                try:
                    cursor.execute(f"ALTER TABLE tasks ADD COLUMN {col_name} {col_type}")
                except Exception:
                    pass
        conn.commit()

def add_task(task_text: str, assignee: str, author: str, sla_deadline: str, created_at: str, db_path="tasks.db") -> dict:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO tasks (task_text, assignee, author, sla_deadline, created_at, status, reminder_sent)
            VALUES (?, ?, ?, ?, ?, 'Active', 0)
        """, (task_text, assignee, author, sla_deadline, created_at))
        conn.commit()
        task_id = cursor.lastrowid
        return {
            "id": task_id,
            "task_text": task_text,
            "assignee": assignee,
            "author": author,
            "sla_deadline": sla_deadline,
            "created_at": created_at,
            "status": "Active",
            "reminder_sent": 0
        }

def get_task(task_id: int, db_path="tasks.db") -> dict | None:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_all_tasks(db_path="tasks.db", status: str = None) -> list[dict]:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        if status:
            cursor.execute("SELECT * FROM tasks WHERE status = ? ORDER BY id DESC", (status,))
        else:
            cursor.execute("SELECT * FROM tasks ORDER BY id DESC")
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

def get_user_tasks(username_or_query: str, status: str = "Active", db_path="tasks.db") -> list[dict]:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        clean = (username_or_query or "").lower().replace("@", "").strip()
        if not clean:
            if status:
                cursor.execute("SELECT * FROM tasks WHERE status = ? ORDER BY id DESC", (status,))
            else:
                cursor.execute("SELECT * FROM tasks ORDER BY id DESC")
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

        search_pattern = f"%{clean}%"
        if status:
            cursor.execute("""
                SELECT * FROM tasks 
                WHERE status = ? 
                  AND (
                      LOWER(assignee) LIKE ? 
                      OR LOWER(assignee) LIKE '%команда%' 
                      OR LOWER(assignee) LIKE '%всей команде%'
                  )
                ORDER BY id DESC
            """, (status, search_pattern))
        else:
            cursor.execute("""
                SELECT * FROM tasks 
                WHERE (
                    LOWER(assignee) LIKE ? 
                    OR LOWER(assignee) LIKE '%команда%' 
                    OR LOWER(assignee) LIKE '%всей команде%'
                )
                ORDER BY id DESC
            """, (search_pattern,))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


def update_task_status(task_id: int, status: str, db_path="tasks.db") -> bool:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE tasks SET status = ? WHERE id = ?", (status, task_id))
        conn.commit()
        return cursor.rowcount > 0

def delete_task(task_id: int, db_path="tasks.db") -> bool:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE tasks SET status = 'Deleted' WHERE id = ?", (task_id,))
        conn.commit()
        return cursor.rowcount > 0

def mark_reminder_sent(task_id: int, db_path="tasks.db") -> bool:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE tasks SET reminder_sent = 1 WHERE id = ?", (task_id,))
        conn.commit()
        return cursor.rowcount > 0

def add_bike_report(report_data: dict, db_path="tasks.db") -> dict:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO bike_reports (
                user_id, username, report_date, issued, returned, total_in_trip,
                new_bikes, old_bikes, broken_bikes, return_reasons, comment, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            report_data.get("user_id"),
            report_data.get("username"),
            report_data.get("report_date"),
            report_data.get("issued"),
            report_data.get("returned"),
            report_data.get("total_in_trip"),
            report_data.get("new_bikes"),
            report_data.get("old_bikes"),
            report_data.get("broken_bikes"),
            report_data.get("return_reasons"),
            report_data.get("comment", ""),
            report_data.get("created_at")
        ))
        conn.commit()
        report_id = cursor.lastrowid
        res = dict(report_data)
        res["id"] = report_id
        return res

def get_bike_reports(limit: int = 50, db_path="tasks.db") -> list[dict]:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM bike_reports ORDER BY id DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


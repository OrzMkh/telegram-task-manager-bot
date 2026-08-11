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
        if HAS_POSTGRES:
            return PostgresCursorWrapper(self._conn.cursor(cursor_factory=RealDictCursor))
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
        # Recurring tasks table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS recurring_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                assignee TEXT NOT NULL,
                author TEXT NOT NULL DEFAULT 'Руководитель',
                frequency TEXT NOT NULL,
                day_of_week TEXT NOT NULL,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Active',
                last_evaluated_at TEXT,
                last_rating INTEGER DEFAULT 0,
                last_rating_comment TEXT,
                message_link TEXT DEFAULT ''
            )
        """)
        # Recurring task evaluations history
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS recurring_task_evaluations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recurring_task_id INTEGER,
                assignee TEXT NOT NULL,
                period_month TEXT NOT NULL,
                rating INTEGER NOT NULL,
                comment TEXT,
                evaluated_at TEXT NOT NULL
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
            ("is_disputed", "INTEGER DEFAULT 0"),
            ("message_link", "TEXT DEFAULT ''")
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

def add_recurring_task(title: str, assignee: str, author: str, frequency: str, day_of_week: str, created_at: str, message_link: str = "", db_path="tasks.db") -> dict:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO recurring_tasks (title, assignee, author, frequency, day_of_week, created_at, status, message_link)
            VALUES (?, ?, ?, ?, ?, ?, 'Active', ?)
        """, (title, assignee, author, frequency, day_of_week, created_at, message_link))
        conn.commit()
        task_id = cursor.lastrowid
        return {
            "id": task_id,
            "title": title,
            "assignee": assignee,
            "author": author,
            "frequency": frequency,
            "day_of_week": day_of_week,
            "created_at": created_at,
            "status": "Active",
            "message_link": message_link,
            "last_rating": 0
        }

def get_all_recurring_tasks(db_path="tasks.db", status: str = "Active") -> list[dict]:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        if status:
            cursor.execute("SELECT * FROM recurring_tasks WHERE status = ? ORDER BY id DESC", (status,))
        else:
            cursor.execute("SELECT * FROM recurring_tasks ORDER BY id DESC")
        rows = cursor.fetchall()
        return [dict(r) for r in rows] if rows else []

def get_recurring_task(task_id: int, db_path="tasks.db") -> dict | None:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM recurring_tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def delete_recurring_task(task_id: int, db_path="tasks.db") -> bool:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE recurring_tasks SET status = 'Deleted' WHERE id = ?", (task_id,))
        conn.commit()
        return True

def rate_recurring_task(task_id: int, rating: int, comment: str = "", evaluated_at: str = "", db_path="tasks.db") -> dict | None:
    if not evaluated_at:
        from config import get_now
        evaluated_at = get_now().strftime("%Y-%m-%d %H:%M:%S")
    
    period_month = evaluated_at[:7] # e.g. '2026-08'

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM recurring_tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        if not row:
            return None
        task = dict(row)
        assignee = task.get("assignee", "")

        # Update current task state
        cursor.execute("""
            UPDATE recurring_tasks 
            SET last_rating = ?, last_rating_comment = ?, last_evaluated_at = ?
            WHERE id = ?
        """, (rating, comment, evaluated_at, task_id))

        # Insert into evaluations history
        cursor.execute("""
            INSERT INTO recurring_task_evaluations (recurring_task_id, assignee, period_month, rating, comment, evaluated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (task_id, assignee, period_month, rating, comment, evaluated_at))
        conn.commit()

        task["last_rating"] = rating
        task["last_rating_comment"] = comment
        task["last_evaluated_at"] = evaluated_at
        return task

def get_recurring_evaluations(month: str = None, db_path="tasks.db") -> list[dict]:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        if month:
            cursor.execute("SELECT * FROM recurring_task_evaluations WHERE period_month = ? ORDER BY id DESC", (month,))
        else:
            cursor.execute("SELECT * FROM recurring_task_evaluations ORDER BY id DESC")
        rows = cursor.fetchall()
        return [dict(r) for r in rows] if rows else []


def add_task(task_text: str, assignee: str, author: str, sla_deadline: str, created_at: str, message_link: str = "", db_path="tasks.db") -> dict:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO tasks (task_text, assignee, author, sla_deadline, created_at, status, reminder_sent, message_link)
            VALUES (?, ?, ?, ?, ?, 'Active', 0, ?)
        """, (task_text, assignee, author, sla_deadline, created_at, message_link))
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
            "reminder_sent": 0,
            "message_link": message_link
        }


def get_task(task_id: int, db_path="tasks.db") -> dict | None:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_all_tasks(db_path="tasks.db", status: str = None, sheets_sync = None) -> list[dict]:
    tasks = []
    if sheets_sync and hasattr(sheets_sync, "get_all_tasks"):
        try:
            tasks = sheets_sync.get_all_tasks()
        except Exception:
            tasks = []

    if not tasks:
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tasks ORDER BY id DESC")
            rows = cursor.fetchall()
            tasks = [dict(r) for r in rows] if rows else []

    if status:
        target_st = status.strip().lower()
        if target_st in ("active", "активные", "активна", "активно", "в работе"):
            # Active means anything not completed or deleted (includes Active, Expired, Disputed, В работе)
            return [
                t for t in tasks 
                if str(t.get("status", "")).strip().lower() not in (
                    "completed", "done", "deleted", "выполнено", "выполнена", "удалена", "завершена"
                )
            ]
        else:
            return [t for t in tasks if str(t.get("status", "")).strip().lower() == target_st]
    return tasks

def get_user_tasks(username_or_query: str, status: str = "Active", db_path="tasks.db", sheets_sync = None) -> list[dict]:
    all_tasks = get_all_tasks(db_path=db_path, status=status, sheets_sync=sheets_sync)
    if not username_or_query:
        return all_tasks


    query_str = (username_or_query or "").lower().strip()
    tokens = [t.replace("@", "").strip() for t in query_str.split() if t.replace("@", "").strip()]
    if not tokens:
        return all_tasks

    # Team leads mapping for known aliases
    alias_map = {
        "axi0603": ["axi0603", "мужохид", "мужахид", "мужохиджон", "мужахиджон", "axadov"],
        "isslamov": ["isslamov", "ильяс", "ильясбек", "иляс"],
        "silent_trickster": ["silent_trickster", "silenttrickster", "жахангир", "джахангир", "jahangir"],
        "orzmkh": ["orzmkh", "орзу", "орзубек"]
    }

    all_search_terms = set(tokens)
    for tok in tokens:
        tok_clean = tok.replace("_", "")
        all_search_terms.add(tok_clean)
        for key, aliases in alias_map.items():
            if tok == key or tok_clean == key.replace("_", "") or tok in aliases:
                all_search_terms.update(aliases)
                all_search_terms.add(key)
                all_search_terms.add(key.replace("_", ""))

    team_keywords = ["команда", "команде", "команду", "всем", "вся команда", "всей команде", "все"]

    matched = []
    for t in all_tasks:
        assignee_raw = str(t.get("assignee", "")).lower()
        assignee_clean = assignee_raw.replace("@", "").replace("_", "")

        is_match = False
        for term in all_search_terms:
            term_clean = term.replace("@", "").replace("_", "")
            if term_clean and (term_clean in assignee_clean or term in assignee_raw):
                is_match = True
                break

        if not is_match:
            for kw in team_keywords:
                if kw in assignee_raw:
                    is_match = True
                    break

        if is_match:
            matched.append(t)

    return matched



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


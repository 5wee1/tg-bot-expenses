import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta

from config import DB_PATH

DEFAULT_EXPENSE_CATEGORIES = [
    ("🍔", "Еда"),
    ("🚕", "Транспорт"),
    ("🏠", "Дом"),
    ("👕", "Одежда"),
    ("🎮", "Развлечения"),
    ("💊", "Здоровье"),
    ("📱", "Связь"),
    ("🎁", "Подарки"),
    ("✈️", "Путешествия"),
    ("📚", "Образование"),
]

DEFAULT_INCOME_CATEGORIES = [
    ("💼", "Зарплата"),
    ("💰", "Подработка"),
    ("🎁", "Подарок"),
    ("📈", "Инвестиции"),
    ("💵", "Кэшбэк"),
    ("🏦", "Проценты"),
    ("💸", "Возврат"),
    ("🏆", "Премия"),
    ("🔄", "Продажа"),
    ("❓", "Другое"),
]


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                type TEXT NOT NULL CHECK (type IN ('expense', 'income')),
                emoji TEXT NOT NULL,
                name TEXT NOT NULL,
                is_default INTEGER NOT NULL DEFAULT 0
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                category_id INTEGER NOT NULL,
                type TEXT NOT NULL CHECK (type IN ('expense', 'income')),
                amount REAL NOT NULL,
                comment TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (category_id) REFERENCES categories (id)
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_tx_user ON transactions(user_id, created_at)")
        c.execute("""
            CREATE TABLE IF NOT EXISTS pro_users (
                user_id INTEGER PRIMARY KEY,
                purchased_at TEXT NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS autocategory (
                user_id INTEGER NOT NULL,
                comment_key TEXT NOT NULL,
                category_id INTEGER NOT NULL,
                hits INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, comment_key)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS budgets (
                user_id INTEGER NOT NULL,
                category_id INTEGER NOT NULL,
                monthly_limit REAL NOT NULL,
                PRIMARY KEY (user_id, category_id)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS recurring (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                category_id INTEGER NOT NULL,
                type TEXT NOT NULL CHECK (type IN ('expense', 'income')),
                amount REAL NOT NULL,
                comment TEXT,
                day_of_month INTEGER NOT NULL CHECK (day_of_month BETWEEN 1 AND 28),
                last_triggered TEXT
            )
        """)

        c.execute("SELECT COUNT(*) FROM categories WHERE is_default = 1")
        if c.fetchone()[0] == 0:
            for emoji, name in DEFAULT_EXPENSE_CATEGORIES:
                c.execute(
                    "INSERT INTO categories (user_id, type, emoji, name, is_default) VALUES (NULL, 'expense', ?, ?, 1)",
                    (emoji, name),
                )
            for emoji, name in DEFAULT_INCOME_CATEGORIES:
                c.execute(
                    "INSERT INTO categories (user_id, type, emoji, name, is_default) VALUES (NULL, 'income', ?, ?, 1)",
                    (emoji, name),
                )


# ---------- Categories ----------

def get_categories(user_id: int, type_: str):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT id, emoji, name, is_default
            FROM categories
            WHERE type = ? AND (is_default = 1 OR user_id = ?)
            ORDER BY is_default DESC, id ASC
            """,
            (type_, user_id),
        )
        return [dict(r) for r in c.fetchall()]


def get_user_categories(user_id: int):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            "SELECT id, emoji, name, type FROM categories WHERE user_id = ? AND is_default = 0 ORDER BY type, id",
            (user_id,),
        )
        return [dict(r) for r in c.fetchall()]


def get_category(category_id: int):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM categories WHERE id = ?", (category_id,))
        row = c.fetchone()
        return dict(row) if row else None


def add_category(user_id: int, type_: str, emoji: str, name: str) -> int:
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO categories (user_id, type, emoji, name, is_default) VALUES (?, ?, ?, ?, 0)",
            (user_id, type_, emoji, name),
        )
        return c.lastrowid


def delete_category(user_id: int, category_id: int) -> bool:
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            "DELETE FROM categories WHERE id = ? AND user_id = ? AND is_default = 0",
            (category_id, user_id),
        )
        return c.rowcount > 0


# ---------- Transactions ----------

def add_transaction(user_id: int, category_id: int, type_: str, amount: float, comment: str) -> int:
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO transactions (user_id, category_id, type, amount, comment, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, category_id, type_, amount, comment, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        return c.lastrowid


def delete_transaction(user_id: int, transaction_id: int) -> bool:
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM transactions WHERE id = ? AND user_id = ?", (transaction_id, user_id))
        return c.rowcount > 0


def get_stats(user_id: int, period: str):
    now = datetime.now()
    if period == "today":
        since = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        since = now - timedelta(days=7)
    elif period == "month":
        since = now - timedelta(days=30)
    else:
        since = None

    with get_conn() as conn:
        c = conn.cursor()
        query = """
            SELECT t.type, c.emoji, c.name, SUM(t.amount) AS total, COUNT(*) AS cnt
            FROM transactions t JOIN categories c ON t.category_id = c.id
            WHERE t.user_id = ?{where}
            GROUP BY t.type, c.id ORDER BY t.type, total DESC
        """
        if since is not None:
            c.execute(query.format(where=" AND t.created_at >= ?"), (user_id, since.strftime("%Y-%m-%d %H:%M:%S")))
        else:
            c.execute(query.format(where=""), (user_id,))
        return [dict(r) for r in c.fetchall()]


def get_recent(user_id: int, limit: int = 10):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT t.id, t.type, t.amount, t.comment, t.created_at, c.emoji, c.name
            FROM transactions t JOIN categories c ON t.category_id = c.id
            WHERE t.user_id = ? ORDER BY t.id DESC LIMIT ?
            """,
            (user_id, limit),
        )
        return [dict(r) for r in c.fetchall()]


def get_all_transactions(user_id: int):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT t.created_at, t.type, c.emoji, c.name, t.amount, t.comment
            FROM transactions t JOIN categories c ON t.category_id = c.id
            WHERE t.user_id = ? ORDER BY t.created_at DESC
            """,
            (user_id,),
        )
        return [dict(r) for r in c.fetchall()]


# ---------- Pro ----------

def is_pro(user_id: int) -> bool:
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT 1 FROM pro_users WHERE user_id = ?", (user_id,))
        return c.fetchone() is not None


def add_pro_user(user_id: int):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            "INSERT OR IGNORE INTO pro_users (user_id, purchased_at) VALUES (?, ?)",
            (user_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )


# ---------- Autocategory ----------

def get_auto_category(user_id: int, comment: str, tx_type: str):
    key = comment.lower().strip()
    if not key:
        return None
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT a.category_id FROM autocategory a
            JOIN categories cat ON a.category_id = cat.id
            WHERE a.user_id = ? AND a.comment_key = ? AND cat.type = ? AND a.hits >= 3
            """,
            (user_id, key, tx_type),
        )
        row = c.fetchone()
        return row[0] if row else None


def update_autocategory(user_id: int, comment: str, category_id: int):
    key = comment.lower().strip()
    if not key:
        return
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            "SELECT category_id FROM autocategory WHERE user_id = ? AND comment_key = ?", (user_id, key)
        )
        row = c.fetchone()
        if row:
            if row[0] == category_id:
                c.execute("UPDATE autocategory SET hits = hits + 1 WHERE user_id = ? AND comment_key = ?", (user_id, key))
            else:
                c.execute(
                    "UPDATE autocategory SET category_id = ?, hits = 1 WHERE user_id = ? AND comment_key = ?",
                    (category_id, user_id, key),
                )
        else:
            c.execute(
                "INSERT INTO autocategory (user_id, comment_key, category_id, hits) VALUES (?,?,?,1)",
                (user_id, key, category_id),
            )


def reset_autocategory(user_id: int, comment: str):
    key = comment.lower().strip()
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM autocategory WHERE user_id = ? AND comment_key = ?", (user_id, key))


# ---------- Budgets ----------

def set_budget(user_id: int, category_id: int, monthly_limit: float):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO budgets (user_id, category_id, monthly_limit) VALUES (?,?,?) "
            "ON CONFLICT(user_id, category_id) DO UPDATE SET monthly_limit = excluded.monthly_limit",
            (user_id, category_id, monthly_limit),
        )


def delete_budget(user_id: int, category_id: int):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM budgets WHERE user_id = ? AND category_id = ?", (user_id, category_id))


def get_budgets(user_id: int):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT b.category_id, c.emoji, c.name, b.monthly_limit,
                   COALESCE((
                       SELECT SUM(t.amount) FROM transactions t
                       WHERE t.user_id = b.user_id AND t.category_id = b.category_id
                       AND t.type = 'expense'
                       AND strftime('%Y-%m', t.created_at) = strftime('%Y-%m', 'now', 'localtime')
                   ), 0) AS spent
            FROM budgets b JOIN categories c ON b.category_id = c.id
            WHERE b.user_id = ? ORDER BY c.name
            """,
            (user_id,),
        )
        return [dict(r) for r in c.fetchall()]


def check_budget_status(user_id: int, category_id: int):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT b.monthly_limit,
                   COALESCE((
                       SELECT SUM(t.amount) FROM transactions t
                       WHERE t.user_id = b.user_id AND t.category_id = b.category_id
                       AND t.type = 'expense'
                       AND strftime('%Y-%m', t.created_at) = strftime('%Y-%m', 'now', 'localtime')
                   ), 0) AS spent
            FROM budgets b WHERE b.user_id = ? AND b.category_id = ?
            """,
            (user_id, category_id),
        )
        row = c.fetchone()
        return dict(row) if row else None


# ---------- Recurring ----------

def add_recurring(user_id: int, category_id: int, type_: str, amount: float, comment: str, day: int) -> int:
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO recurring (user_id, category_id, type, amount, comment, day_of_month) VALUES (?,?,?,?,?,?)",
            (user_id, category_id, type_, amount, comment, day),
        )
        return c.lastrowid


def get_recurring(user_id: int):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT r.id, r.type, r.amount, r.comment, r.day_of_month, c.emoji, c.name AS cat_name
            FROM recurring r JOIN categories c ON r.category_id = c.id
            WHERE r.user_id = ? ORDER BY r.day_of_month
            """,
            (user_id,),
        )
        return [dict(r) for r in c.fetchall()]


def get_recurring_item(item_id: int):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT r.*, c.emoji, c.name AS cat_name
            FROM recurring r JOIN categories c ON r.category_id = c.id
            WHERE r.id = ?
            """,
            (item_id,),
        )
        row = c.fetchone()
        return dict(row) if row else None


def delete_recurring(user_id: int, item_id: int) -> bool:
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM recurring WHERE id = ? AND user_id = ?", (item_id, user_id))
        return c.rowcount > 0


def get_due_recurring():
    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")
    month_start = today.strftime("%Y-%m")
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT r.*, c.emoji, c.name AS cat_name
            FROM recurring r JOIN categories c ON r.category_id = c.id
            WHERE r.day_of_month = ?
            AND (r.last_triggered IS NULL OR strftime('%Y-%m', r.last_triggered) < ?)
            ORDER BY r.user_id
            """,
            (today.day, month_start),
        )
        return [dict(r) for r in c.fetchall()]


def mark_recurring_triggered(item_id: int):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            "UPDATE recurring SET last_triggered = ? WHERE id = ?",
            (datetime.now().strftime("%Y-%m-%d"), item_id),
        )

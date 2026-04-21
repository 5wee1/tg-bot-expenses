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
            """
            SELECT id, emoji, name, type
            FROM categories
            WHERE user_id = ? AND is_default = 0
            ORDER BY type, id
            """,
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
        c.execute(
            "DELETE FROM transactions WHERE id = ? AND user_id = ?",
            (transaction_id, user_id),
        )
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
        if since is not None:
            c.execute(
                """
                SELECT t.type, c.emoji, c.name, SUM(t.amount) AS total, COUNT(*) AS cnt
                FROM transactions t
                JOIN categories c ON t.category_id = c.id
                WHERE t.user_id = ? AND t.created_at >= ?
                GROUP BY t.type, c.id
                ORDER BY t.type, total DESC
                """,
                (user_id, since.strftime("%Y-%m-%d %H:%M:%S")),
            )
        else:
            c.execute(
                """
                SELECT t.type, c.emoji, c.name, SUM(t.amount) AS total, COUNT(*) AS cnt
                FROM transactions t
                JOIN categories c ON t.category_id = c.id
                WHERE t.user_id = ?
                GROUP BY t.type, c.id
                ORDER BY t.type, total DESC
                """,
                (user_id,),
            )
        return [dict(r) for r in c.fetchall()]


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


def get_recent(user_id: int, limit: int = 10):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT t.id, t.type, t.amount, t.comment, t.created_at, c.emoji, c.name
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE t.user_id = ?
            ORDER BY t.id DESC
            LIMIT ?
            """,
            (user_id, limit),
        )
        return [dict(r) for r in c.fetchall()]

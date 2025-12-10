# database.py
import sqlite3

conn = sqlite3.connect("users.db")
cursor = conn.cursor()

# Таблица пользователей: credits = сколько генераций осталось
cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        credits INTEGER NOT NULL DEFAULT 0
    )
    """
)

# Таблица платежей: чтобы не начислять повторно по одному invoice_id
cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS payments (
        payment_id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        confirmed INTEGER NOT NULL DEFAULT 1
    )
    """
)

conn.commit()

FREE_CREDITS_ON_FIRST_SEEN = 3  # первые 3 бесплатно (один раз на пользователя)


def _ensure_user_with_free_credits(user_id: int) -> None:
    """
    Создаёт пользователя с FREE_CREDITS_ON_FIRST_SEEN при первом обращении.
    Если пользователь уже есть — ничего не меняем.
    """
    cursor.execute(
        "INSERT OR IGNORE INTO users (user_id, credits) VALUES (?, ?)",
        (user_id, FREE_CREDITS_ON_FIRST_SEEN),
    )
    conn.commit()


def get_credits(user_id: int) -> int:
    _ensure_user_with_free_credits(user_id)
    cursor.execute("SELECT credits FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    return int(row[0]) if row else 0


def has_credits(user_id: int) -> bool:
    """Есть ли хотя бы 1 генерация в остатке (с учётом бесплатных при первом заходе)."""
    return get_credits(user_id) > 0


def consume_credit(user_id: int, n: int = 1) -> bool:
    """
    Списывает n генераций, если хватает. Возвращает True/False.
    Использовать ТОЛЬКО ПОСЛЕ успешной генерации/редактирования.
    """
    _ensure_user_with_free_credits(user_id)
    cursor.execute("SELECT credits FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    credits = int(row[0]) if row else 0
    if credits < n:
        return False
    cursor.execute("UPDATE users SET credits = credits - ? WHERE user_id = ?", (n, user_id))
    conn.commit()
    return True


def add_uses(user_id: int, count: int) -> None:
    """Начислить пользователю N генераций (например, после оплаты)."""
    _ensure_user_with_free_credits(user_id)
    cursor.execute("UPDATE users SET credits = credits + ? WHERE user_id = ?", (count, user_id))
    conn.commit()


def is_payment_recorded(payment_id: str) -> bool:
    cursor.execute("SELECT 1 FROM payments WHERE payment_id = ?", (payment_id,))
    return cursor.fetchone() is not None


def record_payment(payment_id: str, user_id: int, amount: float) -> None:
    cursor.execute(
        "INSERT OR IGNORE INTO payments (payment_id, user_id, amount, confirmed) VALUES (?, ?, ?, 1)",
        (payment_id, user_id, amount),
    )
    conn.commit()
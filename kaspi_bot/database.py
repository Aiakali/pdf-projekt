"""
Работа с базой данных SQLite.
Хранит информацию о заказах, PDF-файлах и администраторе бота.
"""

import sqlite3
from datetime import date, datetime, timedelta
import secrets
from config import DB_PATH


def _connect():
    """Создать подключение к БД."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Инициализация таблиц базы данных."""
    conn = _connect()
    c = conn.cursor()

    # Таблица заказов
    c.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id    TEXT PRIMARY KEY,
            order_code  TEXT,
            customer    TEXT DEFAULT '',
            total_price REAL DEFAULT 0,
            status      TEXT DEFAULT 'NEW',
            kaspi_status TEXT DEFAULT '',
            pdf_path    TEXT,
            created_at  TEXT,
            processed_at TEXT,
            sent_at     TEXT
        )
    """)

    # Миграция: добавить kaspi_status если его нет
    try:
        c.execute("ALTER TABLE orders ADD COLUMN kaspi_status TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass  # колонка уже существует

    # Таблица администратора (кто управляет ботом)
    c.execute("""
        CREATE TABLE IF NOT EXISTS admin (
            chat_id       INTEGER PRIMARY KEY,
            username      TEXT,
            first_name    TEXT,
            registered_at TEXT
        )
    """)

    # Таблица логов отправок
    c.execute("""
        CREATE TABLE IF NOT EXISTS send_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            merged_path TEXT,
            order_count INTEGER,
            sent_at     TEXT
        )
    """)

    # Таблица отправок по админам (кто уже скачал)
    c.execute("""
        CREATE TABLE IF NOT EXISTS admin_sends (
            order_id    TEXT NOT NULL,
            admin_id    INTEGER NOT NULL,
            sent_at     TEXT,
            PRIMARY KEY (order_id, admin_id)
        )
    """)

    # Таблица ежедневной статистики (не зависит от /clean)
    c.execute("""
        CREATE TABLE IF NOT EXISTS stats_daily (
            day         TEXT PRIMARY KEY,
            orders      INTEGER DEFAULT 0,
            total_sum   REAL DEFAULT 0,
            pdf_count   INTEGER DEFAULT 0,
            sent_count  INTEGER DEFAULT 0
        )
    """)

    # Таблица веб-сессий (вход через Telegram)
    c.execute("""
        CREATE TABLE IF NOT EXISTS web_sessions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            code        TEXT NOT NULL,
            chat_id     INTEGER NOT NULL,
            created_at  TEXT NOT NULL,
            expires_at  TEXT NOT NULL,
            used        INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()


# ========== Администраторы ==========

MAX_ADMINS = 2


# ========== Веб-авторизация ==========

def create_web_login_code(chat_id: int) -> str:
    """Создать 6-значный код для входа в веб-панель, действует 5 минут."""
    code = str(secrets.randbelow(900000) + 100000)
    now = datetime.now()
    expires = now + timedelta(minutes=5)
    conn = _connect()
    # Удалить старые коды этого пользователя
    conn.execute("DELETE FROM web_sessions WHERE chat_id = ?", (chat_id,))
    conn.execute(
        "INSERT INTO web_sessions (code, chat_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (code, chat_id, now.isoformat(), expires.isoformat()),
    )
    conn.commit()
    conn.close()
    return code




def get_admin_chat_id() -> int | None:
    """Получить chat_id первого администратора."""
    conn = _connect()
    row = conn.execute("SELECT chat_id FROM admin LIMIT 1").fetchone()
    conn.close()
    return row["chat_id"] if row else None


def get_all_admin_ids() -> list[int]:
    """Получить список chat_id всех администраторов."""
    conn = _connect()
    rows = conn.execute("SELECT chat_id FROM admin").fetchall()
    conn.close()
    return [r["chat_id"] for r in rows]


def get_admin_count() -> int:
    """Количество зарегистрированных администраторов."""
    conn = _connect()
    count = conn.execute("SELECT COUNT(*) as c FROM admin").fetchone()["c"]
    conn.close()
    return count


def set_admin(chat_id: int, username: str = "", first_name: str = ""):
    """Сохранить администратора бота."""
    conn = _connect()
    conn.execute(
        "INSERT OR REPLACE INTO admin (chat_id, username, first_name, registered_at) VALUES (?, ?, ?, ?)",
        (chat_id, username, first_name, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def is_admin(chat_id: int) -> bool:
    """Проверить, является ли пользователь администратором."""
    admin_ids = get_all_admin_ids()
    if not admin_ids:
        return True  # Если админов нет, разрешаем первого
    return chat_id in admin_ids


# ========== Заказы ==========

def order_exists(order_id: str) -> bool:
    """Проверить, существует ли заказ в БД."""
    conn = _connect()
    row = conn.execute("SELECT 1 FROM orders WHERE order_id = ?", (order_id,)).fetchone()
    conn.close()
    return row is not None


def get_order_status(order_id: str) -> str | None:
    """Получить текущий статус заказа из БД."""
    conn = _connect()
    row = conn.execute("SELECT status FROM orders WHERE order_id = ?", (order_id,)).fetchone()
    conn.close()
    return row["status"] if row else None


def save_order(
    order_id: str,
    order_code: str,
    status: str,
    customer: str = "",
    total_price: float = 0,
    pdf_path: str | None = None,
):
    """Сохранить или обновить заказ."""
    conn = _connect()
    now = datetime.now().isoformat()
    conn.execute(
        """INSERT INTO orders (order_id, order_code, customer, total_price, status, pdf_path, created_at, processed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(order_id) DO UPDATE SET
               status = excluded.status,
               pdf_path = COALESCE(excluded.pdf_path, orders.pdf_path),
               processed_at = excluded.processed_at
        """,
        (order_id, order_code, customer, total_price, status, pdf_path, now, now),
    )
    conn.commit()
    conn.close()


def update_order_pdf(order_id: str, pdf_path: str):
    """Обновить путь к PDF и статус."""
    conn = _connect()
    conn.execute(
        "UPDATE orders SET pdf_path = ?, status = 'PDF_READY', processed_at = ? WHERE order_id = ?",
        (pdf_path, datetime.now().isoformat(), order_id),
    )
    conn.commit()
    conn.close()


def update_order_status(order_id: str, status: str):
    """Обновить статус заказа."""
    conn = _connect()
    conn.execute(
        "UPDATE orders SET status = ?, processed_at = ? WHERE order_id = ?",
        (status, datetime.now().isoformat(), order_id),
    )
    conn.commit()
    conn.close()


def archive_previous_window() -> int:
    """Перевести заказы предыдущего бизнес-окна (PDF_READY) в SENT.

    Заказы, созданные до начала текущего окна (15:00) и ещё в PDF_READY,
    автоматически помечаются как SENT — они уже реально переданы.
    """
    from config import BUSINESS_DAY_CUTOFF_HOUR
    from datetime import timezone, timedelta
    tz_almaty = timezone(timedelta(hours=5))
    now = datetime.now(tz=tz_almaty)
    cutoff = now.replace(hour=BUSINESS_DAY_CUTOFF_HOUR, minute=0, second=0, microsecond=0)
    if now >= cutoff:
        window_start = cutoff
    else:
        window_start = cutoff - timedelta(days=1)
    # window_start — начало текущего окна. Всё что создано ДО него — предыдущее окно.
    window_start_str = window_start.astimezone().strftime('%Y-%m-%dT%H:%M:%S')
    conn = _connect()
    now_str = datetime.now().isoformat()
    cursor = conn.execute(
        "UPDATE orders SET status = 'SENT', sent_at = ?, processed_at = ? "
        "WHERE status = 'PDF_READY' AND created_at < ?",
        (now_str, now_str, window_start_str),
    )
    count = cursor.rowcount
    conn.commit()
    conn.close()
    return count


def get_unsent_orders(admin_id: int | None = None) -> list[dict]:
    """Получить заказы с PDF, которые ещё не были отправлены этому админу."""
    conn = _connect()
    if admin_id is not None:
        rows = conn.execute(
            "SELECT o.order_id, o.order_code, o.customer, o.total_price, o.pdf_path "
            "FROM orders o "
            "WHERE o.pdf_path IS NOT NULL "
            "  AND o.status NOT IN ('COMPLETED', 'CANCELLED', 'RETURNED') "
            "  AND o.order_id NOT IN ("
            "    SELECT order_id FROM admin_sends WHERE admin_id = ?"
            "  ) "
            "ORDER BY o.created_at ASC",
            (admin_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT order_id, order_code, customer, total_price, pdf_path FROM orders "
            "WHERE pdf_path IS NOT NULL AND sent_at IS NULL "
            "ORDER BY created_at ASC"
        ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def mark_orders_sent_for_admin(order_ids: list[str], admin_id: int):
    """Отметить заказы как отправленные конкретному админу."""
    conn = _connect()
    now = datetime.now().isoformat()
    for oid in order_ids:
        conn.execute(
            "INSERT OR IGNORE INTO admin_sends (order_id, admin_id, sent_at) VALUES (?, ?, ?)",
            (oid, admin_id, now),
        )
    # Проверяем: если ВСЕ админы получили эти заказы — помечаем глобально как SENT
    admin_count = get_admin_count()
    if admin_count > 0:
        for oid in order_ids:
            received = conn.execute(
                "SELECT COUNT(DISTINCT admin_id) as c FROM admin_sends WHERE order_id = ?",
                (oid,),
            ).fetchone()["c"]
            if received >= admin_count:
                conn.execute(
                    "UPDATE orders SET sent_at = ?, status = 'SENT' WHERE order_id = ?",
                    (now, oid),
                )
    conn.commit()
    conn.close()


def mark_orders_sent(order_ids: list[str]):
    """Отметить заказы как отправленные (глобально, для обратной совместимости)."""
    conn = _connect()
    now = datetime.now().isoformat()
    for oid in order_ids:
        conn.execute("UPDATE orders SET sent_at = ?, status = 'SENT' WHERE order_id = ?", (now, oid))
    conn.commit()
    conn.close()


def log_send(merged_path: str, order_count: int):
    """Записать лог отправки."""
    conn = _connect()
    conn.execute(
        "INSERT INTO send_log (merged_path, order_count, sent_at) VALUES (?, ?, ?)",
        (merged_path, order_count, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def get_orders_needing_waybill() -> list[dict]:
    """Получить заказы в передаче, для которых ещё нет PDF."""
    conn = _connect()
    rows = conn.execute(
        "SELECT order_id, order_code FROM orders "
        "WHERE status IN ('ASSEMBLE', 'DELIVERY', 'KASPI_DELIVERY') AND pdf_path IS NULL"
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_active_orders() -> list[dict]:
    """Получить все активные заказы (не завершенные, не отмененные)."""
    conn = _connect()
    rows = conn.execute(
        "SELECT order_id, order_code, status, kaspi_status FROM orders "
        "WHERE status NOT IN ('CANCELLED', 'COMPLETED', 'SENT', 'RETURNED')"
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def update_kaspi_status(order_id: str, kaspi_status: str, internal_status: str | None = None):
    """Обновить реальный статус Kaspi и опционально внутренний."""
    conn = _connect()
    now = datetime.now().isoformat()
    if internal_status:
        conn.execute(
            "UPDATE orders SET kaspi_status = ?, status = ?, processed_at = ? WHERE order_id = ?",
            (kaspi_status, internal_status, now, order_id),
        )
    else:
        conn.execute(
            "UPDATE orders SET kaspi_status = ?, processed_at = ? WHERE order_id = ?",
            (kaspi_status, now, order_id),
        )
    conn.commit()
    conn.close()


# ========== Статистика ==========

def get_today_stats() -> dict:
    """Получить статистику за сегодня."""
    today = date.today().isoformat()
    conn = _connect()

    total = conn.execute(
        "SELECT COUNT(*) as c FROM orders WHERE created_at LIKE ?", (f"{today}%",)
    ).fetchone()["c"]

    ready = conn.execute(
        "SELECT COUNT(*) as c FROM orders WHERE pdf_path IS NOT NULL AND sent_at IS NULL"
    ).fetchone()["c"]

    sent = conn.execute(
        "SELECT COUNT(*) as c FROM orders WHERE created_at LIKE ? AND sent_at IS NOT NULL", (f"{today}%",)
    ).fetchone()["c"]

    no_pdf = conn.execute(
        "SELECT COUNT(*) as c FROM orders WHERE pdf_path IS NULL AND sent_at IS NULL"
    ).fetchone()["c"]

    conn.close()
    return {"total": total, "ready": ready, "sent": sent, "no_pdf": no_pdf}


def get_full_stats() -> dict:
    """Получить полную статистику системы."""
    today = date.today().isoformat()
    conn = _connect()

    active = conn.execute(
        "SELECT COUNT(*) as c FROM orders "
        "WHERE status NOT IN ('CANCELLED', 'COMPLETED', 'SENT', 'RETURNED')"
    ).fetchone()["c"]

    ready = conn.execute(
        "SELECT COUNT(*) as c FROM orders WHERE pdf_path IS NOT NULL AND sent_at IS NULL"
    ).fetchone()["c"]

    waiting_pdf = conn.execute(
        "SELECT COUNT(*) as c FROM orders "
        "WHERE pdf_path IS NULL AND sent_at IS NULL "
        "AND status NOT IN ('CANCELLED', 'COMPLETED', 'RETURNED')"
    ).fetchone()["c"]

    sent_total = conn.execute(
        "SELECT COUNT(*) as c FROM orders WHERE sent_at IS NOT NULL"
    ).fetchone()["c"]

    today_new = conn.execute(
        "SELECT COUNT(*) as c FROM orders WHERE created_at LIKE ?", (f"{today}%",)
    ).fetchone()["c"]

    today_pdf = conn.execute(
        "SELECT COUNT(*) as c FROM orders "
        "WHERE pdf_path IS NOT NULL AND processed_at LIKE ?", (f"{today}%",)
    ).fetchone()["c"]

    conn.close()
    return {
        "active": active,
        "ready": ready,
        "waiting_pdf": waiting_pdf,
        "sent_total": sent_total,
        "today_new": today_new,
        "today_pdf": today_pdf,
    }


def save_daily_stats():
    """Сохранить/обновить статистику за сегодня в stats_daily."""
    today = date.today().isoformat()
    conn = _connect()
    orders = conn.execute(
        "SELECT COUNT(*) as c FROM orders WHERE created_at LIKE ?", (f"{today}%",)
    ).fetchone()["c"]
    total_sum = conn.execute(
        "SELECT COALESCE(SUM(total_price), 0) as s FROM orders WHERE created_at LIKE ?", (f"{today}%",)
    ).fetchone()["s"]
    pdf_count = conn.execute(
        "SELECT COUNT(*) as c FROM orders WHERE pdf_path IS NOT NULL AND created_at LIKE ?", (f"{today}%",)
    ).fetchone()["c"]
    sent_count = conn.execute(
        "SELECT COUNT(*) as c FROM orders WHERE sent_at IS NOT NULL AND created_at LIKE ?", (f"{today}%",)
    ).fetchone()["c"]
    conn.execute(
        "INSERT INTO stats_daily (day, orders, total_sum, pdf_count, sent_count) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(day) DO UPDATE SET orders=excluded.orders, total_sum=excluded.total_sum, "
        "pdf_count=excluded.pdf_count, sent_count=excluded.sent_count",
        (today, orders, total_sum, pdf_count, sent_count),
    )
    conn.commit()
    conn.close()


def get_period_stats(days: int = 7) -> dict:
    """Получить агрегированную статистику из stats_daily за последние N дней."""
    cutoff = (date.today() - timedelta(days=days - 1)).isoformat()
    conn = _connect()
    row = conn.execute(
        "SELECT COUNT(*) as days, COALESCE(SUM(orders), 0) as orders, "
        "COALESCE(SUM(total_sum), 0) as total_sum, COALESCE(SUM(pdf_count), 0) as pdf_count, "
        "COALESCE(SUM(sent_count), 0) as sent_count "
        "FROM stats_daily WHERE day >= ?",
        (cutoff,),
    ).fetchone()
    conn.close()
    total_orders = row["orders"]
    return {
        "days": row["days"],
        "orders": total_orders,
        "total_sum": row["total_sum"],
        "pdf_count": row["pdf_count"],
        "sent_count": row["sent_count"],
        "avg_check": round(row["total_sum"] / total_orders, 0) if total_orders > 0 else 0,
    }


def delete_old_orders(days: int = 7) -> dict:
    """Удалить завершённые/отменённые заказы старше N дней. Вернуть кол-во и пути PDF."""
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    conn = _connect()

    rows = conn.execute(
        "SELECT order_id, pdf_path FROM orders "
        "WHERE status IN ('COMPLETED', 'SENT', 'CANCELLED', 'RETURNED') "
        "AND processed_at < ?",
        (cutoff,),
    ).fetchall()

    pdf_paths = [r["pdf_path"] for r in rows if r["pdf_path"]]
    count = len(rows)

    if count > 0:
        conn.execute(
            "DELETE FROM orders "
            "WHERE status IN ('COMPLETED', 'SENT', 'CANCELLED', 'RETURNED') "
            "AND processed_at < ?",
            (cutoff,),
        )
        conn.commit()

    conn.close()
    return {"deleted": count, "pdf_paths": pdf_paths}

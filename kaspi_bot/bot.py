"""
Telegram бот.

Команды:
  /start   - Регистрация и приветствие
  /status  - Статус заказов за сегодня
  /collect - Собрать все накладные в один PDF и отправить
  /force   - Принудительно запустить цикл проверки заказов
    /netcheck - Проверка сети до Kaspi API
  /help    - Показать список команд
"""

import logging
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import FSInputFile, Message

from config import TELEGRAM_BOT_TOKEN
from database import (
    create_web_login_code,
    delete_old_orders,
    get_admin_chat_id,
    get_admin_count,
    get_all_admin_ids,
    get_full_stats,
    get_period_stats,
    get_today_stats,
    get_unsent_orders,
    is_admin,
    log_send,
    mark_orders_sent,
    mark_orders_sent_for_admin,
    set_admin,
    MAX_ADMINS,
)
from kaspi_client import network_check
from pdf_manager import get_merged_file_size, merge_pdfs
from scheduler import run_full_cycle

logger = logging.getLogger("kaspi_bot.bot")

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
router = Router()


# ==================== Проверка доступа ====================

def _check_admin(message: Message) -> bool:
    """Проверить, является ли отправитель администратором."""
    return is_admin(message.from_user.id)


async def _ensure_admin(message: Message) -> bool:
    """Проверить доступ и при отказе отправить понятный ответ."""
    if _check_admin(message):
        return True
    await message.answer("У тебя нет доступа к этому боту.")
    logger.warning("Доступ запрещен для user_id=%s", message.from_user.id)
    return False


# ==================== Команды ====================

@router.message(Command("start"))
async def cmd_start(message: Message):
    """Регистрация администратора и приветствие."""
    user = message.from_user
    admin_ids = get_all_admin_ids()
    admin_count = len(admin_ids)

    if user.id in admin_ids:
        # Уже зарегистрирован
        await message.answer(
            f"С возвращением, {user.first_name}!\n\n"
            f"Бот работает. Нажми /status чтобы проверить заказы.\n"
            f"Все команды: /help"
        )
    elif admin_count < MAX_ADMINS:
        # Есть место для нового админа
        set_admin(
            chat_id=user.id,
            username=user.username or "",
            first_name=user.first_name or "",
        )
        await message.answer(
            f"Привет, {user.first_name}!\n\n"
            f"Ты зарегистрирован как администратор бота ({admin_count + 1}/{MAX_ADMINS}).\n"
            f"Твой ID: {user.id}\n\n"
            f"Бот автоматически:\n"
            f"  - Принимает новые заказы Kaspi\n"
            f"  - Переводит их в статус передачи\n"
            f"  - Скачивает накладные PDF\n\n"
            f"Когда нужно распечатать -- нажми /collect\n\n"
            f"Все команды: /help"
        )
        logger.info("Администратор зарегистрирован: %s (ID: %d) [%d/%d]", user.username, user.id, admin_count + 1, MAX_ADMINS)
    else:
        # Лимит админов достигнут
        await message.answer("У тебя нет доступа к этому боту.")
        logger.warning("Отказ регистрации: лимит админов (%d/%d), user_id=%s", admin_count, MAX_ADMINS, user.id)


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Показать список команд."""
    if not await _ensure_admin(message):
        return

    await message.answer(
        "Доступные команды:\n\n"
        "/status  - Статус заказов\n"
        "/stats   - Статистика за период\n"
        "/collect - Собрать и отправить накладные\n"
        "/force   - Принудительно проверить новые заказы\n"
        "/web     - Войти в веб-панель\n"
        "/clean   - Удалить старые заказы\n"
        "/admins  - Показать текущих админов\n"
        "/netcheck - Проверить доступ к Kaspi API\n"
        "/help    - Эта подсказка"
    )


@router.message(Command("web"))
async def cmd_web(message: Message):
    """Сгенерировать код входа для веб-панели."""
    if not await _ensure_admin(message):
        return

    code = create_web_login_code(message.from_user.id)
    await message.answer(
        f"🔑 Код для входа в веб-панель:\n\n"
        f"<code>{code}</code>\n\n"
        f"Введи этот код на странице входа.\n"
        f"Код действителен 5 минут.",
        parse_mode="HTML",
    )


@router.message(Command("admins"))
async def cmd_admins(message: Message):
    """Показать список текущих администраторов."""
    if not await _ensure_admin(message):
        return
    if not await _ensure_admin(message):
        return

    admin_ids = get_all_admin_ids()
    if not admin_ids:
        await message.answer("Нет зарегистрированных админов.")
        return

    conn = __import__("database")._connect()
    rows = conn.execute(
        "SELECT chat_id, username, first_name, registered_at FROM admin ORDER BY registered_at"
    ).fetchall()
    conn.close()

    lines = [f"👥 Админы ({len(rows)}/{MAX_ADMINS}):\n"]
    for i, r in enumerate(rows, 1):
        name = r["first_name"] or "—"
        uname = f"@{r['username']}" if r["username"] else "—"
        lines.append(f"{i}. {name} ({uname}) — id: {r['chat_id']}")

    await message.answer("\n".join(lines))


@router.message(Command("netcheck"))
async def cmd_netcheck(message: Message):
    """Проверить сетевую доступность Kaspi с сервера."""
    if not await _ensure_admin(message):
        return

    await message.answer("Проверяю сеть до Kaspi...")
    result = await network_check()

    await message.answer(
        "Сетевой отчёт Kaspi:\n\n"
        f"DNS: {result['dns']}\n"
        f"TCP 443: {result['tcp443']}\n"
        f"HTTP kaspi.kz: {result['http_home']}\n"
        f"HTTP API /orders: {result['http_api']}\n"
        f"Proxy: {result['proxy']}"
    )


@router.message(Command("status"))
async def cmd_status(message: Message):
    """Показать статистику заказов."""
    if not await _ensure_admin(message):
        return

    stats = get_full_stats()

    text = (
        f"📊 Статус системы:\n\n"
        f"Активных заказов: {stats['active']}\n"
        f"PDF готово к сборке: {stats['ready']}\n"
        f"Ожидают накладную: {stats['waiting_pdf']}\n"
        f"Отправлено (всего): {stats['sent_total']}\n"
        f"\nЗа сегодня:\n"
        f"Новых: {stats['today_new']} | PDF скачано: {stats['today_pdf']}"
    )

    if stats['ready'] > 0:
        text += f"\n\nНажми /collect чтобы собрать и получить."

    await message.answer(text)


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    """Показать статистику за период. /stats [дней]"""
    if not await _ensure_admin(message):
        return

    parts = message.text.strip().split()
    days = 7
    if len(parts) > 1:
        try:
            days = max(1, min(365, int(parts[1])))
        except ValueError:
            await message.answer("Использование: /stats [дней]\nПример: /stats 30")
            return

    s = get_period_stats(days)

    def fmt_sum(val):
        return f"{val:,.0f}".replace(",", " ")

    await message.answer(
        f"📊 Статистика за {days} дн. ({s['days']} дн. с данными):\n\n"
        f"Заказов: {s['orders']}\n"
        f"Сумма: {fmt_sum(s['total_sum'])} ₸\n"
        f"Средний чек: {fmt_sum(s['avg_check'])} ₸\n"
        f"PDF скачано: {s['pdf_count']}\n"
        f"Отправлено: {s['sent_count']}"
    )


@router.message(Command("collect"))
async def cmd_collect(message: Message):
    """Собрать все накладные в один PDF и отправить."""
    if not await _ensure_admin(message):
        return

    logger.info("Команда /collect от user_id=%s", message.from_user.id)

    admin_id = message.from_user.id
    unsent = get_unsent_orders(admin_id=admin_id)

    if not unsent:
        await message.answer(
            "Нет новых накладных для сборки.\n\n"
            "Возможные причины:\n"
            "- Все накладные уже были отправлены\n"
            "- Новые заказы ещё обрабатываются (подожди 2 минуты)\n\n"
            "Нажми /force чтобы проверить заказы прямо сейчас."
        )
        return

    await message.answer(f"Собираю {len(unsent)} накладных...")

    # Список путей к PDF
    pdf_paths = [order["pdf_path"] for order in unsent if order.get("pdf_path")]

    if not pdf_paths:
        await message.answer("Ошибка: PDF файлы не найдены на диске.")
        return

    # Объединяем все PDF в один
    merged_path, merged_ids = merge_pdfs(pdf_paths)

    if not merged_path:
        await message.answer("Ошибка при объединении PDF файлов. Проверь логи.")
        return

    # Фильтруем заказы до только реально объединённых
    actually_sent = [o for o in unsent if o["pdf_path"] in merged_ids]

    # Размер файла
    size_mb = get_merged_file_size(merged_path)

    # Telegram ограничивает файлы до 50 MB
    if size_mb > 49:
        await message.answer(
            f"Файл слишком большой ({size_mb:.1f} МБ). "
            f"Telegram ограничивает файлы до 50 МБ. "
            f"Попробуй собирать чаще."
        )
        return

    # Формируем описание
    order_codes = [o["order_code"] for o in actually_sent]
    caption = f"Накладные ({len(actually_sent)} шт.):\n" + ", ".join(order_codes[:20])
    if len(order_codes) > 20:
        caption += f"\n...и ещё {len(order_codes) - 20}"

    # Отправляем файл
    try:
        document = FSInputFile(merged_path, filename=f"nakladnye_{len(actually_sent)}_sht.pdf")
        await message.answer_document(document=document, caption=caption)

        # Отмечаем только реально отправленные заказы
        order_ids = [o["order_id"] for o in actually_sent]
        mark_orders_sent_for_admin(order_ids, admin_id)
        log_send(merged_path, len(actually_sent))

        skipped = len(unsent) - len(actually_sent)
        text = f"Готово! {len(actually_sent)} накладных отправлено.\n"
        text += f"Размер файла: {size_mb:.1f} МБ"
        if skipped > 0:
            text += f"\nПропущено (файл не найден): {skipped}"
        await message.answer(text)
        logger.info("Отправлено %d накладных, размер %.1f МБ", len(actually_sent), size_mb)

    except Exception as e:
        logger.error("Ошибка отправки файла: %s", e)
        await message.answer(f"Ошибка при отправке файла: {e}")


@router.message(Command("force"))
async def cmd_force(message: Message):
    """Принудительно запустить цикл проверки заказов."""
    if not await _ensure_admin(message):
        return

    await message.answer("Запускаю проверку заказов...")

    stats = await run_full_cycle()

    await message.answer(
        f"Проверка завершена:\n\n"
        f"Синхронизировано: {stats.get('synced', 0)}\n"
        f"Принято новых: {stats['accepted']}\n"
        f"Переведено в передачу: {stats['moved']}\n"
        f"Скачано накладных: {stats['downloaded']}\n\n"
        f"Нажми /collect чтобы собрать накладные."
    )


@router.message(F.text.regexp(r"^/clean\d*$"))
async def cmd_clean(message: Message):
    """Удалить завершённые/отменённые заказы старше N дней."""
    if not await _ensure_admin(message):
        return

    # Парсим количество дней из команды (по умолчанию 7)
    # Поддержка: /clean, /clean7, /clean30
    cmd_text = message.text.strip().split()[0]  # "/clean" или "/clean30"
    suffix = cmd_text.replace("/clean", "").replace("@testpdf1_bot", "")
    days = 7
    if suffix:
        try:
            days = max(1, int(suffix))
        except ValueError:
            await message.answer("Использование: /clean[дней]\nПример: /clean30")
            return

    result = delete_old_orders(days)
    deleted = result["deleted"]
    pdf_paths = result["pdf_paths"]

    # Удаляем PDF файлы с диска
    files_removed = 0
    for p in pdf_paths:
        path = Path(p)
        if path.exists():
            path.unlink()
            files_removed += 1

    if deleted == 0:
        await message.answer(f"Нет завершённых заказов старше {days} дней.")
    else:
        await message.answer(
            f"🧹 Очищено:\n"
            f"Удалено записей из БД: {deleted}\n"
            f"Удалено PDF файлов: {files_removed}\n"
            f"(старше {days} дней)"
        )
        logger.info("Очистка: %d записей, %d PDF файлов (старше %d дней)", deleted, files_removed, days)


@router.message(F.text)
async def handle_text(message: Message):
    """Обработка текстовых сообщений (ключевые слова)."""
    if not await _ensure_admin(message):
        return

    text = message.text.lower().strip()

    if text in ("собрать документы", "собрать", "collect"):
        await cmd_collect(message)
    elif text in ("статус", "status"):
        await cmd_status(message)
    elif text in ("статистика", "stats"):
        await cmd_stats(message)
    elif text in ("проверить", "force", "check"):
        await cmd_force(message)
    elif text in ("очистка", "clean", "очистить"):
        await cmd_clean(message)
    elif text in ("веб", "web", "панель"):
        await cmd_web(message)
    else:
        await message.answer(
            "Не понял команду. Доступные:\n"
            "/collect - собрать накладные\n"
            "/status - статус заказов\n"
            "/force - проверить заказы\n"
            "/netcheck - проверка сети до Kaspi\n"
            "/help - помощь"
        )


# ==================== Уведомления ====================

async def notify_admin(text: str):
    """Отправить уведомление всем администраторам."""
    admin_ids = get_all_admin_ids()
    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, text)
        except Exception as e:
            logger.error("Не удалось отправить уведомление админу %s: %s", admin_id, e)


def setup_bot():
    """Подключить роутер к диспетчеру."""
    dp.include_router(router)
    return dp, bot

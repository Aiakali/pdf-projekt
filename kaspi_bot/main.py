"""
Kaspi Waybill Bot -- Главный файл запуска.

Запускает одновременно:
- Telegram бота (приём команд)
- Планировщик (автоматическая проверка заказов каждые N секунд)
"""

import asyncio
import logging
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler

from aiogram.exceptions import TelegramUnauthorizedError
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import (
    CHECK_INTERVAL,
    LOG_PATH,
    KASPI_API_TOKEN,
    TELEGRAM_BOT_TOKEN,
    KASPI_DRY_RUN,
    KASPI_SYNC_ENABLED,
    AUTO_NOTIFY_ENABLED,
    AUTO_NOTIFY_ON_DRY_RUN,
    NEW_ORDER_NOTIFY_ENABLED,
)
from database import init_db, get_unsent_orders
from bot import setup_bot, notify_admin
from scheduler import run_full_cycle

try:
    import sdnotify
    _notifier = sdnotify.SystemdNotifier()
except ImportError:
    _notifier = None

# ==================== Логирование ====================

def setup_logging():
    """Настройка логирования в файл и консоль."""
    formatter = logging.Formatter(
        "%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # В файл (ротация: 5 МБ × 3 файла)
    file_handler = RotatingFileHandler(
        str(LOG_PATH), maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    # В консоль
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Тишина для библиотек
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("aiogram").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)


logger = logging.getLogger("kaspi_bot.main")


# ==================== Задача планировщика ====================

async def scheduled_check():
    """Задача, выполняемая по расписанию."""
    try:
        stats = await run_full_cycle()

        # Watchdog ping
        if _notifier:
            _notifier.notify("WATCHDOG=1")

        # Уведомление о скачанных PDF
        if stats.get("downloaded", 0) > 0:
            unsent = get_unsent_orders()
            ready_count = len(unsent)
            text = (
                f"📄 Скачано накладных: {stats['downloaded']}\n"
                f"Готово к сборке: {ready_count}\n"
                f"Нажми /collect чтобы забрать."
            )
            await notify_admin(text)

        # Отдельное полезное уведомление: только о новых заказах
        if NEW_ORDER_NOTIFY_ENABLED and stats.get("accepted", 0) > 0:
            accepted = stats["accepted"]
            suffix = "" if accepted == 1 else "а(ов)"
            text = (
                "Новый заказ\n"
                if accepted == 1
                else f"Новые заказы: {accepted}"
            )
            text += f"\nПринято автоматически: {accepted} заказ{suffix}."
            text += "\nОткрой Kaspi и проверь детали, затем нажми /collect при готовности."
            await notify_admin(text)

        # Уведомляем админа только если это явно включено
        if not AUTO_NOTIFY_ENABLED:
            return

        if KASPI_DRY_RUN and not AUTO_NOTIFY_ON_DRY_RUN:
            return

        # Уведомляем админа если есть новые заказы
        total = stats["accepted"] + stats["moved"] + stats["downloaded"]
        if total > 0:
            parts = []
            if stats["accepted"] > 0:
                parts.append(f"Принято: {stats['accepted']}")
            if stats["moved"] > 0:
                parts.append(f"В передачу: {stats['moved']}")
            if stats["downloaded"] > 0:
                parts.append(f"Накладных: {stats['downloaded']}")

            text = "Автообработка:\n" + "\n".join(parts)
            text += "\n\nНажми /collect когда будешь готов."
            await notify_admin(text)

    except Exception as e:
        logger.error("Ошибка в планировщике: %s", e)


# ==================== Запуск ====================

async def main():
    """Главная функция запуска."""
    setup_logging()

    logger.info("=" * 50)
    logger.info("Kaspi Waybill Bot запускается...")
    logger.info("=" * 50)

    # Проверка конфигурации
    if not KASPI_API_TOKEN:
        logger.error("KASPI_API_TOKEN не задан! Проверь файл .env")
        sys.exit(1)

    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN не задан! Проверь файл .env")
        sys.exit(1)

    # Инициализация базы данных
    init_db()
    logger.info("База данных инициализирована")

    # Настройка бота
    dp, bot = setup_bot()
    logger.info("Telegram бот настроен")

    # Проверяем валидность токена ДО запуска планировщика
    try:
        bot_info = await bot.me()
        logger.info("Telegram токен валиден (бот: @%s)", bot_info.username)
    except TelegramUnauthorizedError:
        logger.error(
            "TELEGRAM_BOT_TOKEN невалиден! Telegram отвечает 'Unauthorized'.\n"
            "Получи новый токен через @BotFather и обнови .env файл."
        )
        await bot.session.close()
        sys.exit(1)
    except Exception as e:
        logger.error("Не удалось подключиться к Telegram: %s", e)
        await bot.session.close()
        sys.exit(1)

    from aiogram.types import BotCommand
    await bot.set_my_commands([
        BotCommand(command="start", description="Регистрация администратора"),
        BotCommand(command="web", description="Войти в веб-панель"),
        BotCommand(command="status", description="Статус заказов"),
        BotCommand(command="stats", description="Статистика за период"),
        BotCommand(command="collect", description="Собрать и отправить накладные"),
        BotCommand(command="force", description="Проверить новые заказы"),
        BotCommand(command="clean", description="Удалить старые заказы"),
        BotCommand(command="admins", description="Текущие админы"),
        BotCommand(command="netcheck", description="Проверка сети до Kaspi"),
        BotCommand(command="help", description="Список команд"),
    ])
    logger.info("Команды бота зарегистрированы в Telegram")

    # Настройка планировщика (только после успешной проверки токена)
    scheduler = AsyncIOScheduler()
    if KASPI_SYNC_ENABLED:
        scheduler.add_job(
            scheduled_check,
            "interval",
            seconds=CHECK_INTERVAL,
            id="kaspi_check",
            max_instances=1,
            next_run_time=datetime.now(),
        )
        scheduler.start()
        logger.info(
            "Планировщик запущен (интервал: %d сек, dry-run: %s)",
            CHECK_INTERVAL,
            "ON" if KASPI_DRY_RUN else "OFF",
        )
    else:
        logger.info("Kaspi синк отключен (KASPI_SYNC_ENABLED=false)")

    # Запуск бота (бесконечный цикл)
    logger.info("Бот запущен и ожидает команды...")

    # Сообщаем systemd что сервис готов
    if _notifier:
        _notifier.notify("READY=1")

    try:
        await dp.start_polling(bot)
    except TelegramUnauthorizedError:
        logger.error(
            "Telegram токен стал невалидным во время работы!\n"
            "Возможно, токен был отозван через @BotFather."
        )
    finally:
        if KASPI_SYNC_ENABLED:
            scheduler.shutdown()
        await bot.session.close()
        logger.info("Бот остановлен")


if __name__ == "__main__":
    asyncio.run(main())

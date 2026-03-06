"""
Планировщик задач.

Каждые N секунд проверяет Kaspi API:
0. Синхронизирует статусы активных заказов с Kaspi
1. Принимает новые заказы (APPROVED_BY_BANK -> ACCEPTED_BY_MERCHANT)
2. Формирует передачу (ACCEPTED_BY_MERCHANT -> ASSEMBLE)
3. Скачивает накладные PDF для заказов Kaspi Доставки
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta

from kaspi_client import (
    accept_order,
    get_order_by_code,
    get_orders_by_state,
    get_orders_by_status,
    get_waybill_pdf,
    move_to_delivery,
    parse_order,
)
from database import (
    archive_previous_window,
    get_active_orders,
    get_order_status,
    get_orders_needing_waybill,
    order_exists,
    save_daily_stats,
    save_order,
    update_kaspi_status,
    update_order_pdf,
    update_order_status,
)
from pdf_manager import save_pdf

logger = logging.getLogger("kaspi_bot.scheduler")


async def sync_order_statuses():
    """
    Шаг 0: Синхронизировать статусы активных заказов в БД с Kaspi.

    Проверяет каждый активный заказ по его коду и обновляет kaspi_status.
    Если заказ CANCELLED/COMPLETED — помечает в БД тоже.
    """
    logger.info("Шаг 0: Синхронизация статусов с Kaspi...")
    try:
        active_orders = get_active_orders()
        if not active_orders:
            return 0

        synced = 0
        for order in active_orders:
            order_code = order["order_code"]
            order_id = order["order_id"]

            kaspi_order = await get_order_by_code(order_code)
            if not kaspi_order:
                continue

            parsed = parse_order(kaspi_order)
            kaspi_status = parsed["status"]

            # Обновляем kaspi_status всегда
            if kaspi_status in ("CANCELLED", "CANCELLING"):
                update_kaspi_status(order_id, kaspi_status, internal_status="CANCELLED")
                synced += 1
                logger.info("Заказ %s отменён в Kaspi", order_code)
            elif kaspi_status in ("COMPLETED", "RETURNED"):
                update_kaspi_status(order_id, kaspi_status, internal_status=kaspi_status)
                synced += 1
                logger.info("Заказ %s завершён в Kaspi (%s)", order_code, kaspi_status)
            else:
                update_kaspi_status(order_id, kaspi_status)

            await asyncio.sleep(0.3)

        if synced > 0:
            logger.info("Синхронизировано статусов: %d", synced)
        return synced

    except Exception as e:
        logger.error("Ошибка при синхронизации статусов: %s", e, exc_info=True)
        return 0


async def process_new_orders():
    """
    Шаг 1: Автоматически принять все новые заказы.

    APPROVED_BY_BANK -> ACCEPTED_BY_MERCHANT
    """
    logger.info("Шаг 1: Проверка новых заказов (APPROVED_BY_BANK)...")
    try:
        orders = await get_orders_by_status("APPROVED_BY_BANK")
        if not orders:
            return 0

        accepted = 0
        for order_data in orders:
            order = parse_order(order_data)
            order_id = order["order_id"]

            # Уже известный заказ не считаем новым
            if order_exists(order_id):
                continue

            # Проверяем реальный статус — API может вернуть уже обработанные заказы
            if order["status"] != "APPROVED_BY_BANK":
                continue

            # Принимаем заказ через Kaspi API
            success = await accept_order(order_id, order["order_code"])
            if success:
                # Сохраняем в БД
                save_order(
                    order_id=order_id,
                    order_code=order["order_code"],
                    status="ACCEPTED",
                    customer=order["customer"],
                    total_price=order["total_price"],
                )
                accepted += 1
                logger.info(
                    "Новый заказ принят: %s (%s) - %s",
                    order["order_code"], order["customer"], order["total_price"],
                )

            # Небольшая задержка между запросами
            await asyncio.sleep(0.5)

        if accepted > 0:
            logger.info("Принято новых заказов: %d", accepted)
        return accepted

    except Exception as e:
        logger.error("Ошибка при обработке новых заказов: %s", e, exc_info=True)
        return 0


async def process_accepted_orders():
    """
    Шаг 2: Перевести принятые заказы в передачу.

    ACCEPTED_BY_MERCHANT -> ASSEMBLE
    """
    logger.info("Шаг 2: Проверка принятых заказов (ACCEPTED_BY_MERCHANT)...")
    try:
        orders = await get_orders_by_status("ACCEPTED_BY_MERCHANT")
        if not orders:
            return 0

        moved = 0
        for order_data in orders:
            order = parse_order(order_data)
            order_id = order["order_id"]

            # Пропускаем уже обработанные
            current_status = get_order_status(order_id)
            if current_status in {"ASSEMBLE", "DELIVERY", "KASPI_DELIVERY", "PDF_READY", "SENT"}:
                continue

            # Проверяем реальный статус в Kaspi
            if order["status"] != "ACCEPTED_BY_MERCHANT":
                continue

            # Пропускаем уже скомплектованные (assembled=True)
            if order.get("assembled"):
                continue

            success = await move_to_delivery(order_id, order["order_code"])
            if success:
                # Обновляем или создаём запись в БД
                if order_exists(order_id):
                    update_order_status(order_id, "ASSEMBLE")
                else:
                    save_order(
                        order_id=order_id,
                        order_code=order["order_code"],
                        status="ASSEMBLE",
                        customer=order["customer"],
                        total_price=order["total_price"],
                    )
                moved += 1
                logger.info(
                    "Заказ переведён в передачу: %s (%s)",
                    order["order_code"], order["customer"],
                )

            await asyncio.sleep(0.5)

        if moved > 0:
            logger.info("Переведено в передачу: %d", moved)
        return moved

    except Exception as e:
        logger.error("Ошибка при переводе заказов в передачу: %s", e, exc_info=True)
        return 0


async def download_waybills():
    """
    Шаг 3: Скачать накладные для заказов Kaspi Доставки.

    Получаем заказы с state=KASPI_DELIVERY (у них есть kaspiDelivery.waybill),
    сопоставляем с БД и скачиваем PDF.
    """
    logger.info("Шаг 3: Скачивание накладных для заказов Kaspi Доставки...")
    try:
        downloaded = 0

        # Получаем заказы со state=KASPI_DELIVERY (за сегодня)
        api_orders = await get_orders_by_state("KASPI_DELIVERY", days_back=1)
        waybill_links = {}
        for order_data in api_orders:
            order = parse_order(order_data)
            order_id = order["order_id"]

            # Пропускаем отменённые/завершённые в Kaspi
            if order["status"] in ("CANCELLING", "CANCELLED", "COMPLETED", "RETURNED"):
                continue

            waybill_links[order_id] = order.get("waybill")

            # Проверяем статус в БД
            current_status = get_order_status(order_id)

            # Уже обработанный заказ — не трогаем
            if current_status in ("SENT", "PDF_READY", "COMPLETED", "CANCELLED", "RETURNED"):
                continue

            # Заказ есть в БД — обновляем статус если нужно
            if current_status is not None:
                if current_status not in ("KASPI_DELIVERY", "DELIVERY"):
                    update_order_status(order_id, "KASPI_DELIVERY")
                continue

            # Заказа нет в БД — создаём только если в текущем бизнес-окне
            creation_ts = order.get("creation_date")
            if isinstance(creation_ts, (int, float)) and creation_ts > 0:
                from config import BUSINESS_DAY_CUTOFF_HOUR
                tz_almaty = timezone(timedelta(hours=5))
                order_time = datetime.fromtimestamp(
                    creation_ts / 1000, tz=tz_almaty
                )
                now = datetime.now(tz=tz_almaty)
                today_cutoff = now.replace(hour=BUSINESS_DAY_CUTOFF_HOUR, minute=0, second=0, microsecond=0)
                if now >= today_cutoff:
                    window_start = today_cutoff
                else:
                    window_start = today_cutoff - timedelta(days=1)
                if order_time < window_start:
                    continue
            else:
                # Нет даты создания — пропускаем (не можем проверить)
                continue

            save_order(
                order_id=order_id,
                order_code=order["order_code"],
                status="KASPI_DELIVERY",
                customer=order["customer"],
                total_price=order["total_price"],
            )

        # Скачиваем PDF для заказов без накладной
        orders_need_pdf = get_orders_needing_waybill()
        if not orders_need_pdf:
            return 0

        for order in orders_need_pdf:
            order_id = order["order_id"]
            order_code = order["order_code"]
            waybill_url = waybill_links.get(order_id)

            if not (isinstance(waybill_url, str) and waybill_url.startswith(("http://", "https://"))):
                logger.info(
                    "Накладная ещё не готова в Kaspi: %s (%s)",
                    order_code, order_id,
                )
                continue

            pdf_bytes = await get_waybill_pdf(order_id, waybill_url)
            if pdf_bytes:
                pdf_path = save_pdf(order_id, order_code, pdf_bytes)
                update_order_pdf(order_id, pdf_path)
                downloaded += 1
                logger.info("Накладная скачана: %s", order_code)

            await asyncio.sleep(0.5)

        if downloaded > 0:
            logger.info("Скачано накладных: %d", downloaded)
        return downloaded

    except Exception as e:
        logger.error("Ошибка при скачивании накладных: %s", e, exc_info=True)
        return 0


async def run_full_cycle() -> dict:
    """
    Запустить полный цикл обработки заказов.

    Возвращает статистику: сколько заказов синхронизировано, принято, переведено, скачано.
    """
    logger.info("--- Начало цикла обработки ---")

    # Авто-архивация: заказы предыдущего окна (до 15:00) -> SENT
    archived = archive_previous_window()
    if archived > 0:
        logger.info("Авто-архивация: %d заказов предыдущего окна -> SENT", archived)

    synced = await sync_order_statuses()
    await asyncio.sleep(1)

    accepted = await process_new_orders()
    await asyncio.sleep(1)

    moved = await process_accepted_orders()
    await asyncio.sleep(1)

    downloaded = await download_waybills()

    stats = {"archived": archived, "synced": synced, "accepted": accepted, "moved": moved, "downloaded": downloaded}
    logger.info("--- Цикл завершён: %s ---", stats)

    # Сохраняем ежедневную статистику
    try:
        save_daily_stats()
    except Exception as e:
        logger.warning("Ошибка сохранения stats_daily: %s", e)

    return stats

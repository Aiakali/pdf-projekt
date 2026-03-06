"""
Клиент для Kaspi Merchant API.

Документация: https://guide.kaspi.kz/partner/ru/shop/api/orders/
Базовый URL: https://kaspi.kz/shop/api/v2
Авторизация: заголовок X-Auth-Token
Формат: JSON:API (application/vnd.api+json)

Цепочка статусов заказа (Kaspi Доставка):
  APPROVED_BY_BANK  -> Новый заказ (оплачен покупателем)
  ACCEPTED_BY_MERCHANT -> Принят продавцом (упаковка)
  GIVEN_TO_DELIVERY -> Передан курьеру (можно скачать накладную)
  SIGN_REQUIRED -> Требует подписи
  COMPLETED -> Завершён
  CANCELLED -> Отменён
"""

import asyncio
import logging
import socket
import time
from datetime import datetime, timedelta, timezone

import httpx

from config import (
    KASPI_API_TOKEN,
    KASPI_BASE_URL,
    KASPI_DRY_RUN,
    KASPI_HTTP_TIMEOUT,
    KASPI_PROXY_URL,
    KASPI_SSL_VERIFY,
    KASPI_USER_AGENT,
)

logger = logging.getLogger("kaspi_bot.kaspi")
api_logger = logging.getLogger("kaspi_bot.api")

# Часовой пояс Алматы (UTC+5)
TZ_ALMATY = timezone(timedelta(hours=5))

# Заголовки для всех запросов
HEADERS = {
    "X-Auth-Token": KASPI_API_TOKEN,
    "Content-Type": "application/vnd.api+json",
    "Accept": "application/vnd.api+json",
    "User-Agent": KASPI_USER_AGENT,
}


def _build_http_client() -> httpx.AsyncClient:
    """Создать HTTP-клиент с учетом прокси и SSL настроек."""
    kwargs = {
        "timeout": KASPI_HTTP_TIMEOUT,
        "verify": KASPI_SSL_VERIFY,
    }
    if KASPI_PROXY_URL:
        kwargs["proxy"] = KASPI_PROXY_URL
    return httpx.AsyncClient(**kwargs)


def _get_today_range() -> tuple[int, int]:
    """Вернуть timestamp текущего бизнес-окна Kaspi (мс, Алматы).

    До 15:00 — окно вчера 15:00 → сегодня 15:00 (заказы ещё копятся).
    После 15:00 — окно сегодня 15:00 → завтра 15:00 (новое окно).
    """
    from config import BUSINESS_DAY_CUTOFF_HOUR
    now = datetime.now(TZ_ALMATY)
    today_cutoff = now.replace(hour=BUSINESS_DAY_CUTOFF_HOUR, minute=0, second=0, microsecond=0)
    if now >= today_cutoff:
        start = today_cutoff
        end = today_cutoff + timedelta(days=1) - timedelta(milliseconds=1)
    else:
        start = today_cutoff - timedelta(days=1)
        end = today_cutoff - timedelta(milliseconds=1)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def _get_multi_day_range(days_back: int = 3) -> tuple[int, int]:
    """Вернуть timestamp за последние N бизнес-окон (мс, Алматы)."""
    from config import BUSINESS_DAY_CUTOFF_HOUR
    now = datetime.now(TZ_ALMATY)
    today_cutoff = now.replace(hour=BUSINESS_DAY_CUTOFF_HOUR, minute=0, second=0, microsecond=0)
    if now >= today_cutoff:
        end = today_cutoff + timedelta(days=1) - timedelta(milliseconds=1)
        start = today_cutoff - timedelta(days=days_back)
    else:
        end = today_cutoff - timedelta(milliseconds=1)
        start = today_cutoff - timedelta(days=days_back + 1)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


async def get_orders_by_status(status: str) -> list[dict]:
    """
    Получить список заказов по статусу за сегодня.

    Статусы: APPROVED_BY_BANK, ACCEPTED_BY_MERCHANT,
             GIVEN_TO_DELIVERY, SIGN_REQUIRED, COMPLETED, CANCELLED
    """
    ts_start, ts_end = _get_today_range()

    params = {
        "page[number]": 0,
        "page[size]": 100,
        "filter[orders][status]": status,
        "filter[orders][creationDate][$ge]": ts_start,
        "filter[orders][creationDate][$le]": ts_end,
    }

    all_orders = []

    async with _build_http_client() as client:
        while True:
            t0 = time.monotonic()
            url = f"{KASPI_BASE_URL}/orders"
            resp = None
            for attempt in range(3):
                try:
                    resp = await client.get(url, headers=HEADERS, params=params)
                    if resp.status_code < 500:
                        break
                    api_logger.warning("GET /orders | status=%s page:%d | HTTP %d | retry %d", status, params["page[number]"], resp.status_code, attempt + 1)
                except asyncio.CancelledError:
                    logger.warning("Запрос к Kaspi API отменён (CancelledError)")
                    return all_orders
                except (httpx.TimeoutException, httpx.ConnectError) as e:
                    api_logger.warning("GET /orders | status=%s | attempt %d | %s", status, attempt + 1, type(e).__name__)
                    resp = None
                if attempt < 2:
                    await asyncio.sleep(1 * (attempt + 1))

            if resp is None or resp.status_code != 200:
                if resp is not None:
                    logger.error("Kaspi API /orders ошибка: %s %s", resp.status_code, resp.text[:300])
                break

            elapsed = int((time.monotonic() - t0) * 1000)
            orders_in_page = len(resp.json().get("data", []))
            api_logger.info(
                "GET /orders | filter=status:%s page:%d | HTTP %d | %d заказов | %dms",
                status, params["page[number]"], resp.status_code, orders_in_page, elapsed,
            )

            data = resp.json()
            orders = data.get("data", [])

            if not orders:
                break

            all_orders.extend(orders)

            # Следующая страница
            next_link = data.get("links", {}).get("next")
            if not next_link:
                break
            params["page[number]"] += 1

    logger.info("Получено %d заказов со статусом %s", len(all_orders), status)
    return all_orders


def parse_order(order_data: dict) -> dict:
    """Извлечь ключевые поля из JSON:API ресурса заказа."""
    attrs = order_data.get("attributes", {})
    kaspi_delivery = attrs.get("kaspiDelivery") or {}
    return {
        "order_id": order_data.get("id", ""),
        "order_code": attrs.get("code", ""),
        "status": attrs.get("status", ""),
        "state": attrs.get("state", ""),
        "total_price": attrs.get("totalPrice", 0),
        "creation_date": attrs.get("creationDate", ""),
        "delivery_mode": attrs.get("deliveryMode", ""),
        "waybill": kaspi_delivery.get("waybill") or attrs.get("waybill"),
        "assembled": attrs.get("assembled", False),
        "customer": _extract_customer(attrs),
    }


def _extract_customer(attrs: dict) -> str:
    """Извлечь имя покупателя из атрибутов заказа."""
    customer = attrs.get("customer", {})
    if isinstance(customer, dict):
        first = customer.get("firstName", "")
        last = customer.get("lastName", "")
        return f"{first} {last}".strip()
    return str(customer) if customer else ""


async def _update_order_status(
    order_id: str,
    order_code: str,
    status: str,
    extra_attributes: dict | None = None,
    extra_headers: dict | None = None,
) -> bool:
    """Изменить статус заказа через POST /orders согласно API.txt."""
    attributes = {
        "status": status,
    }
    if order_code:
        attributes["code"] = order_code
    if extra_attributes:
        attributes.update(extra_attributes)

    body = {
        "data": {
            "type": "orders",
            "id": order_id,
            "attributes": attributes,
        }
    }

    if KASPI_DRY_RUN:
        api_logger.info("POST /orders [DRY-RUN] | %s -> %s", order_id, status)
        return True

    request_headers = dict(HEADERS)
    if extra_headers:
        request_headers.update(extra_headers)

    async with _build_http_client() as client:
        t0 = time.monotonic()
        url = f"{KASPI_BASE_URL}/orders"
        resp = None
        for attempt in range(3):
            try:
                resp = await client.post(url, headers=request_headers, json=body)
                if resp.status_code < 500:
                    break
                api_logger.warning("POST /orders | %s -> %s | HTTP %d | retry %d", order_id, status, resp.status_code, attempt + 1)
            except asyncio.CancelledError:
                logger.warning("[CancelledError] Запрос смены статуса заказа %s отменён", order_id)
                return False
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                api_logger.warning("POST /orders | %s -> %s | attempt %d | %s", order_id, status, attempt + 1, type(e).__name__)
                resp = None
            if attempt < 2:
                await asyncio.sleep(1 * (attempt + 1))

    if resp is None:
        return False

    elapsed = int((time.monotonic() - t0) * 1000)
    api_logger.info(
        "POST /orders | %s -> %s | HTTP %d | %dms | body=%s",
        order_code or order_id, status, resp.status_code, elapsed, resp.text[:200],
    )

    if resp.status_code in (200, 201, 202, 204):
        logger.info("Заказ %s переведён в статус %s", order_id, status)
        return True

    logger.error(
        "Не удалось изменить статус заказа %s -> %s: %s %s",
        order_id, status, resp.status_code, resp.text[:400],
    )
    return False


async def accept_order(order_id: str, order_code: str) -> bool:
    """
    Принять заказ: APPROVED_BY_BANK -> ACCEPTED_BY_MERCHANT.

    POST /orders
    Body: {"data": {"type": "orders", "id": order_id,
           "attributes": {"code": "...", "status": "ACCEPTED_BY_MERCHANT"}}}
    """
    return await _update_order_status(order_id, order_code, "ACCEPTED_BY_MERCHANT")


async def move_to_delivery(order_id: str, order_code: str, number_of_space: int = 1) -> bool:
    """
    Сформировать накладную для передачи: ACCEPTED_BY_MERCHANT -> ASSEMBLE.

    POST /orders
    Body: {"data": {"type": "orders", "id": order_id,
           "attributes": {"code": "...", "status": "ASSEMBLE", "numberOfSpace": "1"}}}
    """
    return await _update_order_status(
        order_id,
        order_code,
        "ASSEMBLE",
        extra_attributes={"numberOfSpace": str(max(1, number_of_space))},
    )


async def get_waybill_pdf(order_id: str, waybill_url: str | None = None) -> bytes | None:
    """
    Скачать накладную (waybill) в PDF.

    Скачивание накладной только по прямой ссылке waybill из заказа.
    Retry: до 3 попыток при сетевых ошибках / HTTP 5xx.
    """
    if not (isinstance(waybill_url, str) and waybill_url.startswith(("http://", "https://"))):
        logger.info("Для заказа %s ещё нет валидной ссылки waybill", order_id)
        return None

    retry_delays = [1, 3, 5]

    async with _build_http_client() as client:
        for attempt in range(len(retry_delays) + 1):
            t0 = time.monotonic()
            try:
                resp = await client.get(
                    waybill_url,
                    headers={
                        "X-Auth-Token": KASPI_API_TOKEN,
                        "Accept": "application/pdf,application/vnd.api+json",
                        "User-Agent": KASPI_USER_AGENT,
                    },
                )
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                elapsed = int((time.monotonic() - t0) * 1000)
                api_logger.warning(
                    "GET waybill | %s | attempt %d | error: %s | %dms",
                    order_id, attempt + 1, type(e).__name__, elapsed,
                )
                if attempt < len(retry_delays):
                    await asyncio.sleep(retry_delays[attempt])
                    continue
                return None
            except Exception as e:
                logger.warning("Ошибка скачивания накладной для %s: %s", order_id, e)
                return None

            elapsed = int((time.monotonic() - t0) * 1000)

            if resp.status_code == 200 and len(resp.content) > 100:
                api_logger.info(
                    "GET waybill | %s | HTTP 200 | %d байт | %dms",
                    order_id, len(resp.content), elapsed,
                )
                return resp.content

            # Retry на 5xx ошибки сервера
            if resp.status_code >= 500 and attempt < len(retry_delays):
                api_logger.warning(
                    "GET waybill | %s | attempt %d | HTTP %d | retry in %ds",
                    order_id, attempt + 1, resp.status_code, retry_delays[attempt],
                )
                await asyncio.sleep(retry_delays[attempt])
                continue

            # 4xx или исчерпаны попытки
            api_logger.warning(
                "GET waybill | %s | HTTP %d | %d байт | %dms | no retry",
                order_id, resp.status_code, len(resp.content), elapsed,
            )
            return None

    return None


async def get_orders_by_state(state: str, days_back: int = 3) -> list[dict]:
    """
    Получить заказы по state (KASPI_DELIVERY, DELIVERY, NEW и т.д.) за N дней.
    """
    ts_start, ts_end = _get_multi_day_range(days_back)

    params = {
        "page[number]": 0,
        "page[size]": 100,
        "filter[orders][state]": state,
        "filter[orders][creationDate][$ge]": ts_start,
        "filter[orders][creationDate][$le]": ts_end,
    }

    all_orders = []

    async with _build_http_client() as client:
        while True:
            t0 = time.monotonic()
            url = f"{KASPI_BASE_URL}/orders"
            resp = None
            for attempt in range(3):
                try:
                    resp = await client.get(url, headers=HEADERS, params=params)
                    if resp.status_code < 500:
                        break
                    api_logger.warning("GET /orders | state=%s | HTTP %d | retry %d", state, resp.status_code, attempt + 1)
                except asyncio.CancelledError:
                    logger.warning("Запрос к Kaspi API (state=%s) отменён", state)
                    return all_orders
                except (httpx.TimeoutException, httpx.ConnectError) as e:
                    api_logger.warning("GET /orders | state=%s | attempt %d | %s", state, attempt + 1, type(e).__name__)
                    resp = None
                if attempt < 2:
                    await asyncio.sleep(1 * (attempt + 1))

            if resp is None or resp.status_code != 200:
                if resp is not None:
                    logger.error("Kaspi API /orders (state=%s) ошибка: %s %s", state, resp.status_code, resp.text[:300])
                break

            elapsed = int((time.monotonic() - t0) * 1000)
            orders_in_page = len(resp.json().get("data", []))
            api_logger.info(
                "GET /orders | filter=state:%s page:%d | HTTP %d | %d заказов | %dms",
                state, params["page[number]"], resp.status_code, orders_in_page, elapsed,
            )

            data = resp.json()
            orders = data.get("data", [])

            if not orders:
                break

            all_orders.extend(orders)

            next_link = data.get("links", {}).get("next")
            if not next_link:
                break
            params["page[number]"] += 1

    logger.info("Получено %d заказов с state=%s (за %d дней)", len(all_orders), state, days_back)
    return all_orders


async def get_order_by_code(order_code: str) -> dict | None:
    """Получить заказ из Kaspi по коду (order_code)."""
    async with _build_http_client() as client:
        resp = None
        for attempt in range(3):
            try:
                resp = await client.get(
                    f"{KASPI_BASE_URL}/orders",
                    headers=HEADERS,
                    params={"filter[orders][code]": order_code},
                )
                if resp.status_code < 500:
                    break
            except (asyncio.CancelledError, httpx.TimeoutException, httpx.ConnectError) as e:
                logger.warning("Ошибка при запросе заказа %s (attempt %d): %s", order_code, attempt + 1, e)
                resp = None
            if attempt < 2:
                await asyncio.sleep(1 * (attempt + 1))

        if resp is None or resp.status_code != 200:
            return None

        data = resp.json()
        orders = data.get("data", [])
        return orders[0] if orders else None


async def network_check() -> dict:
    """Проверить доступность Kaspi по шагам: DNS -> TCP443 -> HTTP."""
    result = {
        "dns": "unknown",
        "tcp443": "unknown",
        "http_home": "unknown",
        "http_api": "unknown",
        "proxy": KASPI_PROXY_URL or "(not set)",
    }

    try:
        socket.gethostbyname("kaspi.kz")
        result["dns"] = "ok"
    except Exception as exc:
        result["dns"] = f"fail: {type(exc).__name__}"

    try:
        import asyncio

        _reader, writer = await asyncio.wait_for(asyncio.open_connection("kaspi.kz", 443), timeout=8)
        writer.close()
        await writer.wait_closed()
        result["tcp443"] = "ok"
    except Exception as exc:
        result["tcp443"] = f"fail: {type(exc).__name__}"

    try:
        async with _build_http_client() as client:
            response = await client.get(
                "https://kaspi.kz/",
                headers={
                    "User-Agent": KASPI_USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Connection": "close",
                },
            )
            result["http_home"] = str(response.status_code)
    except Exception as exc:
        result["http_home"] = f"fail: {type(exc).__name__}"

    try:
        ts_start, ts_end = _get_today_range()
        async with _build_http_client() as client:
            response = await client.get(
                f"{KASPI_BASE_URL}/orders",
                headers=HEADERS,
                params={
                    "page[number]": 0,
                    "page[size]": 1,
                    "filter[orders][status]": "APPROVED_BY_BANK",
                    "filter[orders][creationDate][$ge]": ts_start,
                    "filter[orders][creationDate][$le]": ts_end,
                },
            )
            result["http_api"] = str(response.status_code)
    except Exception as exc:
        result["http_api"] = f"fail: {type(exc).__name__}"

    return result

"""
Конфигурация проекта.
Загружает настройки из .env файла.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Загружаем .env файл
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
# --- Kaspi API ---
KASPI_API_TOKEN = os.getenv("KASPI_API_TOKEN", "")
KASPI_BASE_URL = os.getenv("KASPI_BASE_URL", "https://kaspi.kz/shop/api/v2")
KASPI_DRY_RUN = os.getenv("KASPI_DRY_RUN", "true").lower() in ("1", "true", "yes", "on")
KASPI_HTTP_TIMEOUT = float(os.getenv("KASPI_HTTP_TIMEOUT", "20"))
KASPI_SYNC_ENABLED = os.getenv("KASPI_SYNC_ENABLED", "false").lower() in ("1", "true", "yes", "on")
KASPI_PROXY_URL = os.getenv("KASPI_PROXY_URL", "").strip()
KASPI_SSL_VERIFY = os.getenv("KASPI_SSL_VERIFY", "true").lower() in ("1", "true", "yes", "on")
KASPI_USER_AGENT = os.getenv(
	"KASPI_USER_AGENT",
	"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
	"Chrome/122.0.0.0 Safari/537.36",
).strip()
AUTO_NOTIFY_ENABLED = os.getenv("AUTO_NOTIFY_ENABLED", "false").lower() in ("1", "true", "yes", "on")
AUTO_NOTIFY_ON_DRY_RUN = os.getenv("AUTO_NOTIFY_ON_DRY_RUN", "false").lower() in ("1", "true", "yes", "on")
NEW_ORDER_NOTIFY_ENABLED = os.getenv("NEW_ORDER_NOTIFY_ENABLED", "true").lower() in ("1", "true", "yes", "on")

# --- Telegram Bot ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# --- Расписание ---
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "120"))  # секунды

# --- Часовой пояс ---
TIMEZONE = "Asia/Almaty"

# --- Бизнес-окно Kaspi ---
# Заказы накапливаются до этого часа, потом отправляются.
# Окно дня: вчера 15:00 → сегодня 15:00
BUSINESS_DAY_CUTOFF_HOUR = 15

# --- Пути к файлам ---
DATA_DIR = BASE_DIR / "data"
PDF_DIR = DATA_DIR / "pdfs"
MERGED_DIR = DATA_DIR / "merged"
DB_PATH = DATA_DIR / "orders.db"
LOG_PATH = DATA_DIR / "bot.log"

# Создаём директории если не существуют
DATA_DIR.mkdir(exist_ok=True)
PDF_DIR.mkdir(exist_ok=True)
MERGED_DIR.mkdir(exist_ok=True)

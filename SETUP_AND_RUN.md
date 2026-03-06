# Проект Kaspi PDF Bot - Запуск и Настройка

## 📋 Описание проекта

Проект состоит из двух частей:
1. **Next.js фронтенд** — веб-приложение (React + Next.js 16)
2. **Telegram бот + Kaspi API интеграция** — Python backend (aiogram + APScheduler)

---

## 🚀 Быстрый старт

### Инструменты (требуется установить один раз)

```bash
# Node.js >= 20.9.0 (для фронтенда)
node --version  
npm --version

# Python 3.12+ (для бота)
python3 --version
```

### Шаг 1: Запуск фронтенда (Next.js)

```bash
# Из корня проекта
npm install
npm run dev
```

**Доступно на:** `http://localhost:3000`

### Шаг 2: Запуск Telegram бота и Kaspi интеграции

```bash
# Активируем виртуальное окружение
source .venv/bin/activate

# Если окружение не создано
python3 -m venv .venv
source .venv/bin/activate
pip install -r kaspi_bot/requirements.txt

# Запускаем бот
python kaspi_bot/main.py
```

**Бот слушает команды через Telegram.** Логи пишутся в `kaspi_bot/data/bot.log`.

---

## ⚙️ Конфигурация

### Telegram бот

Отредактируйте `kaspi_bot/.env`:

```dotenv
# Новый Telegram Bot Token (получить через @BotFather)
TELEGRAM_BOT_TOKEN=<ваш_новый_токен>

# Kaspi Merchant API Token
KASPI_API_TOKEN=<ваш_kaspi_токен>

# Интервал проверки заказов (сек)
CHECK_INTERVAL=120
```

### Переменные окружения для фронтенда

Если требуются — создайте `.env.local` в корне:

```dotenv
NEXT_PUBLIC_API_URL=http://localhost:3001
```

---

## 🤖 Telegram команды бота

После первого сообщения `/start` бот регистрирует администратора.

| Команда | Описание |
|---------|---------|
| `/start` | 🔐 Регистрация администратора (первый юзер) |
| `/status` | 📊 Статус заказов за сегодня |
| `/collect` | 📥 Собрать и отправить все накладные в один PDF |
| `/force` | ⚡ Принудительно проверить заказы сейчас |
| `/help` | ❓ Список команд |

---

## 📊 Структура базы данных

Бот автоматически создаёт SQLite БД в `kaspi_bot/data/orders.db`.

**Схема:**
- `orders` — все заказы (ID, код, статус, цена, дата)
- `pdf_files` — загруженные накладные (путь, размер, дата загрузки)
- `admins` — пользователь с доступом к боту
- `send_log` — история отправленных файлов

---

## 🔄 Как работает автоматизация

**Каждые 120 секунд бот выполняет три шага:**

1. **Шаг 1: Принять новые заказы**
   - Парсит статус `APPROVED_BY_BANK` из Kaspi
   - Переводит в `ACCEPTED_BY_MERCHANT`

2. **Шаг 2: Перевести в передачу**
   - Берет заказы со статусом `ACCEPTED_BY_MERCHANT`
   - Переводит в `GIVEN_TO_DELIVERY` для курьера

3. **Шаг 3: Скачать накладные**
   - Получает PDF накладные для заказов "в передаче"
   - Сохраняет файлы в `kaspi_bot/data/pdfs/`

**После сборки** командой `/collect`:
- Объединяет все PDF в один файл
- Отправляет в Telegram
- Отмечает файлы как отправленные

---

## 📁 Структура файлов

```
/home/xyrel/pdf-projekt/
├── app/                    # Next.js app directory
├── components/             # React компоненты (UI)
├── kaspi_bot/              # Python бот
│   ├── main.py            # Точка входа
│   ├── bot.py             # Telegram команды
│   ├── kaspi_client.py    # API клиент Kaspi
│   ├── scheduler.py       # Планировщик автоматации
│   ├── database.py        # SQLite операции
│   ├── pdf_manager.py     # Работа с PDF
│   ├── config.py          # Конфигурация
│   ├── .env               # Переменные окружения
│   ├── requirements.txt    # Python зависимости
│   └── data/
│       ├── orders.db      # БД заказов
│       ├── pdfs/          # Скачанные накладные
│       ├── merged/        # Собранные PDF
│       └── bot.log        # Логи
├── package.json           # Node.js зависимости
├── tsconfig.json          # TypeScript конфиг
└── .env                   # Telegram токен (бот)
```

---

## 🐛 Известные проблемы и решения

### 1. TelegramConflictError

**Ошибка:** `terminated by other getUpdates request; make sure that only one bot instance is running`

**Причина:** Другой процесс или вебхук использует тот же токен бота.

**Решение:**
- Создать **новый бот** через @BotFather
- Использовать новый токен в `.env`
- Убедиться, что старый процесс убит: `pkill -f kaspi_bot/main.py`

### 2. httpx.ReadTimeout при обращении к Kaspi API

**Ошибка:** `httpx.ReadTimeout` в логах scheduler'а

**Причина:** 
- Kaspi API недоступна из вашей сети
- Очень медленный ответ сервера (может быть географический lag)
- Неверный/истекший API токен

**Решение:**
- Проверить токен в `kaspi_bot/config.py`: `KASPI_API_TOKEN`
- Проверить сетевое соединение: `curl https://kaspi.kz/shop/api/v2/orders`
- Увеличить timeout в `kaspi_bot/kaspi_client.py` (сейчас 60 сек)

### 3. Node.js версия

**Ошибка:** `You are using Node.js 18.x. For Next.js, Node.js version ">=20.9.0" is required.`

**Решение:**
```bash
# Обновить Node.js
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
node --version  # Проверить >= 20.9.0
```

---

## 📝 Разработка и Тестирование

### Запуск в разработке

```bash
# Terminal 1: Фронтенд
npm run dev

# Terminal 2: Бот
source .venv/bin/activate && python kaspi_bot/main.py
```

### Просмотр логов

```bash
# Логи фронтенда — в консоли Terminal 1

# Логи бота
tail -f kaspi_bot/data/bot.log

# Логи БД заказов (для проверки данных)
sqlite3 kaspi_bot/data/orders.db "SELECT * FROM orders;"
```

### Тестирование бота

В Telegram отправьте:
```
/start
/status
/force
```

Проверьте `kaspi_bot/data/bot.log` на ошибки.

---

## 🔒 Безопасность

⚠️ **Важно:**
- Не коммитить `.env` с реальными токенами в git
- Использовать разные токены для разработки и production
- Хранить `kaspi_bot/.env` на отдельном защищённом сервере

---

## 📞 Справка

**Документация:**
- [Next.js](https://nextjs.org/docs)
- [Telegram Bot API (aiogram)](https://aiogram.dev/)
- [Kaspi Merchant API](https://guide.kaspi.kz/partner/ru/shop/api/)
- [APScheduler](https://apscheduler.readthedocs.io/)

---

## 📌 Статус и Заметки

### ✅ Что работает

- ✓ Next.js фронтенд запускается на `localhost:3000`
- ✓ Python виртуальное окружение и зависимости установлены
- ✓ Telegram бот инициализируется и слушает команды
- ✓ Планировщик запускает циклы обновления (каждые 2 минуты)
- ✓ Логирование с полными stack traces

### ⚠️ Что требует внимания

- ⚠️ Kaspi API медленно отвечает или недоступна (ReadTimeout)
- ⚠️ Telegram конфликт с использованным токеном (нужен новый бот)
- ⚠️ Нет тестовых данных для проверки полного цикла

### 🔄 Рекомендуемые действия

1. **Проверить Kaspi API доступность:**
   ```bash
   curl -H "X-Auth-Token: <ваш_токен>" https://kaspi.kz/shop/api/v2/orders?page[size]=1
   ```

2. **Создать новый Telegram бот:**
   - Отправить @BotFather `/newbot`
   - Получить новый токен
   - Обновить `kaspi_bot/.env`

3. **Монитор логов в реальном времени:**
   ```bash
   tail -f kaspi_bot/data/bot.log | grep -E "(ERROR|WARNING|INFO)"
   ```

---

**Последнее обновление:** 04.03.2026 08:10 UTC  
**Версия Next.js:** 16.1.6  
**Версия Python:** 3.12  

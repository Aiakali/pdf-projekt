# Вариант B - Полная интеграция (Готов к тестированию)

## ✅ Что реализовано:

### 1. **Telegram бот с командой `/add_order`**
Позволяет вручную добавлять заказы без Kaspi API.

**Синтаксис:**
```
/add_order <order_id> <order_code> [price] [customer name]
```

**Примеры:**
```
/add_order TEST-001 KZ-001 15000 "Иван Петров"
/add_order TEST-002 KZ-002
```

### 2. **Next.js API для управления заказами**
**Файл:** `app/api/orders/route.js`

**Endpoints:**
- `GET /api/orders` — получить все заказы (JSON)
- `POST /api/orders` — добавить заказ (JSON body)
- `DELETE /api/orders?order_id=<id>` — удалить заказ

**Пример добавления через curl:**
```bash
curl -X POST http://localhost:3000/api/orders \
  -H "Content-Type: application/json" \
  -d '{"order_id":"TEST-004","order_code":"KZ-004","customer":"Алина Сидорова","total_price":28500}'
```

### 3. **Next.js UI страница для управления заказами**
**URL:** `http://localhost:3000/orders`

**Функции:**
- Просмотр всех заказов в таблице (заказ ID, код, статус, клиент, цена)
- Добавление новых заказов через форму
- Удаление заказов с подтверждением
- Синхронизация с БД в реальном времени

### 4. **Тестовые данные**
**Файл:** `kaspi_bot/test_data.py`

**Содержит:**
- 3 готовых тестовых заказа (KZ-001, KZ-002, KZ-003)
- Генератор тестовых PDF файлов (reportlab)
- Запись в SQLite БД

**Уже выполнено:** ✅ 3 заказа с PDF готовы в `kaspi_bot/data/pdfs/`

## 🧪 Как тестировать (после возврата в локальную сеть):

### Шаг 1: Убедитесь, что всё работает
```bash
# До прекращения интернета убедитесь, что это выполнено:
# ✅ Фронтенд запущен: npm run dev
# ✅ Бот запущен: source .venv/bin/activate && python kaspi_bot/main.py
```

### Шаг 2: Откройте Next.js панель
```
http://localhost:3000/orders
```
Должны увидеть 3 тестовых заказа (KZ-001, KZ-002, KZ-003)

### Шаг 3: Протестируйте Telegram команды

**Регистрация (первый запуск):**
```
/start
```
Бот ответит, что вы администратор.

**Добавить ещё один заказ:**
```
/add_order TEST-004 KZ-004 35000 "Марат Ибраев"
```
Бот ответит: "Заказ KZ-004 (TEST-004) добавлен."

**Проверить статистику:**
```
/status
```
Должно показать все заказы за сегодня.

**Собрать и отправить PDF:**
```
/collect
```
Бот объединит все имеющиеся PDF накладные в один файл и отправит вам.

### Шаг 4: Добавьте заказы через API

```bash
# Через curl (при наличии интернета на сервере)
curl -X POST http://localhost:3000/api/orders \
  -H "Content-Type: application/json" \
  -d '{
    "order_id":"API-001",
    "order_code":"KZ-005",
    "customer":"Алион Компания",
    "total_price":50000
  }'

# Или откройте http://localhost:3000/orders и введите данные в форму
```

### Шаг 5: Проверьте БД (дополнительно)

```bash
# Все заказы в БД
source .venv/bin/activate
python3 -c "
import sqlite3
conn = sqlite3.connect('kaspi_bot/data/orders.db')
cur = conn.cursor()
cur.execute('SELECT order_id, order_code, customer, total_price FROM orders')
for row in cur.fetchall():
  print(row)
conn.close()
"
```

## 📊 Структура данных:

### БД (SQLite): `kaspi_bot/data/orders.db`
```
orders таблица:
- order_id: уникальный ID заказа
- order_code: код заказа (KZ-001, и т.д.)
- status: статус (NEW, DELIVERY, COMPLETED, и т.д.)
- customer: ФИ клиента
- total_price: сумма
- pdf_path: путь к PDF накладной
- created_at: дата создания
```

### PDF файлы: `kaspi_bot/data/pdfs/`
Хранятся все загруженные накладные:
```
test_waybill_KZ-001.pdf
test_waybill_KZ-002.pdf
test_waybill_KZ-003.pdf
```

### Собранный PDF: `kaspi_bot/data/merged/`
После `/collect` команды здесь хранится объединённый PDF:
```
merged_<timestamp>.pdf
```

## 🔧 Что можно дополнительно протестировать:

1. **Попытайтесь иправить Kaspi API время от времени** — если ответѓ приходит, заказы будут синхронизироваться автоматически.

2. **Создайте CSV с заказами** — можно добавить импорт CSV в будущей версии.

3. **Посмотрите логи:**
   ```bash
   tail -f kaspi_bot/data/bot.log
   ```

4. **Проверьте размер объединённого PDF:**
   ```bash
   ls -lh kaspi_bot/data/merged/
   ```
   (Telegram ограничивает файлы 50 МБ, система предупредит если больше)

## 📝 Итоговый статус:

| Функция | Статус | 
|---------|--------|
| Фронтенд Next.js | ✅ Работает |
| API GET /api/orders | ✅ Готов к тесту |
| API POST /api/orders | ✅ Готов к тесту |
| API DELETE /api/orders | ✅ Готов к тесту |
| UI страница /orders | ✅ Готов к тесту |
| Bот команда /add_order | ✅ Готов к тесту |
| Bот команда /collect | ✅ Работает |
| Bот команда /status | ✅ Работает  |
| Тестовые данные (3 заказа) | ✅ Созданы |
| Тестовые PDF файлы | ✅ Созданы |
| Kaspi API интеграция | ⏳ Ожидает ответа от Kaspi |

---

**Ваше действие:** Как только вернётесь в локальную сеть, откройте `http://localhost:3000/orders` и следуйте шагам выше. Если найдёте баги — буду готов их исправить! 🚀

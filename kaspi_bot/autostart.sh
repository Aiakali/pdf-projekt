#!/bin/bash
# ============================================
# Скрипт настройки автозагрузки
# Создаёт systemd сервис для автозапуска бота
# ============================================
# Запустить: bash autostart.sh
# ============================================

set -e

SERVICE_NAME="kaspi-bot"
PROJECT_DIR="/home/xyrel/pdf-projekt"
PYTHON_PATH="$PROJECT_DIR/.venv/bin/python3"
MAIN_FILE="$PROJECT_DIR/kaspi_bot/main.py"

echo "========================================"
echo " Настройка автозагрузки: $SERVICE_NAME"
echo "========================================"

# Создаём systemd сервис
sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null << EOF
[Unit]
Description=Kaspi Waybill Telegram Bot
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=xyrel
WorkingDirectory=$PROJECT_DIR
ExecStart=$PYTHON_PATH $MAIN_FILE
Restart=always
RestartSec=10

# Переменные окружения из .env загружаются внутри Python
# Но на всякий случай задаём рабочую директорию
Environment=PYTHONUNBUFFERED=1

# Логи
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

echo "[1/3] Сервис создан"

# Перезагружаем systemd
sudo systemctl daemon-reload
echo "[2/3] systemd обновлён"

# Включаем автозапуск и стартуем
sudo systemctl enable ${SERVICE_NAME}
sudo systemctl start ${SERVICE_NAME}
echo "[3/3] Сервис запущен и добавлен в автозагрузку"

echo ""
echo "========================================"
echo " Готово! Бот работает в фоне."
echo "========================================"
echo ""
echo " Полезные команды:"
echo ""
echo "   Статус бота:"
echo "     sudo systemctl status $SERVICE_NAME"
echo ""
echo "   Логи в реальном времени:"
echo "     sudo journalctl -u $SERVICE_NAME -f"
echo ""
echo "   Перезапуск бота:"
echo "     sudo systemctl restart $SERVICE_NAME"
echo ""
echo "   Остановка бота:"
echo "     sudo systemctl stop $SERVICE_NAME"
echo ""
echo "   Логи приложения:"
echo "     cat $PROJECT_DIR/data/bot.log"
echo ""

#!/bin/bash
# ============================================
# Скрипт установки Kaspi Waybill Bot
# на Ubuntu Server
# ============================================
# Запустить: bash setup.sh
# ============================================

set -e

echo "========================================"
echo " Установка Kaspi Waybill Bot"
echo "========================================"
echo ""

# 1. Обновление системы
echo "[1/5] Обновляю систему..."
sudo apt update -y
sudo apt upgrade -y

# 2. Установка Python 3.11+ и pip
echo "[2/5] Устанавливаю Python..."
sudo apt install -y python3 python3-pip python3-venv

# Проверка версии
python3 --version

# 3. Создание виртуального окружения
echo "[3/5] Создаю виртуальное окружение..."
cd /home/xyrel/pdf-projekt
python3 -m venv venv
source venv/bin/activate

# 4. Установка зависимостей
echo "[4/5] Устанавливаю зависимости Python..."
pip install --upgrade pip
pip install -r requirements.txt

# 5. Тест запуска (проверяем что все импорты работают)
echo "[5/5] Проверяю что всё установилось..."
python3 -c "
import aiogram
import httpx
import apscheduler
import pypdf
import dotenv
print('Все зависимости установлены!')
print(f'  aiogram:     {aiogram.__version__}')
print(f'  httpx:       {httpx.__version__}')
print(f'  pypdf:       {pypdf.__version__}')
"

echo ""
echo "========================================"
echo " Установка завершена!"
echo "========================================"
echo ""
echo " Для запуска вручную:"
echo "   cd /home/xyrel/pdf-projekt"
echo "   source venv/bin/activate"
echo "   python3 main.py"
echo ""
echo " Для автозагрузки запусти:"
echo "   bash autostart.sh"
echo ""

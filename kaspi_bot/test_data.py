#!/usr/bin/env python3
"""
Генератор тестовых данных — добавляет тестовые заказы в БД и создаёт фиктивные PDF.
Используйте перед тестированием `/collect` команды.

Запуск:
    python kaspi_bot/test_data.py
"""

import os
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

from database import save_order, update_order_pdf
from pdf_manager import save_pdf
from config import PDF_DIR

def create_fake_pdf(order_code):
    """Создаёт простой PDF для тестирования."""
    pdf_path = PDF_DIR / f"test_waybill_{order_code}.pdf"
    
    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    c.setFont("Helvetica", 20)
    c.drawString(50, 750, f"Kaspi Тестовая накладная")
    
    c.setFont("Helvetica", 12)
    y = 700
    c.drawString(50, y, f"Код заказа: {order_code}")
    y -= 30
    c.drawString(50, y, f"Дата создания: 2026-03-04")
    y -= 30
    c.drawString(50, y, f"Статус: Готово к отправке")
    y -= 50
    c.drawString(50, y, "Это тестовый PDF для демонстрации функции /collect")
    
    c.save()
    return pdf_path

def add_test_orders():
    """Добавляет 3 тестовых заказа с PDF файлами."""
    test_orders = [
        {"order_id": "TEST-001", "order_code": "KZ-001", "customer": "Иван Петров", "price": 15000},
        {"order_id": "TEST-002", "order_code": "KZ-002", "customer": "Алина Сидорова", "price": 28500},
        {"order_id": "TEST-003", "order_code": "KZ-003", "customer": "Марат Ибраев", "price": 42000},
    ]
    
    print("Создаю тестовые заказы...")
    
    for order in test_orders:
        # Добавляем заказ в БД
        save_order(
            order_id=order["order_id"],
            order_code=order["order_code"],
            status="DELIVERY",
            customer=order["customer"],
            total_price=order["price"]
        )
        
        # Создаём тестовый PDF
        pdf_file = create_fake_pdf(order["order_code"])
        update_order_pdf(order["order_id"], str(pdf_file))
        
        print(f"✅ Заказ {order['order_code']} создан с PDF: {pdf_file}")
    
    print("\n✅ Тестовые данные готовы!")
    print(f"\nТеперь вы можете:")
    print("1. Отправить /collect боту — он соберёт эти PDF в один файл")
    print("2. Посетить http://localhost:3000/orders — увидеть заказы в интерфейсе")
    print("3. Отправить /status боту — увидеть статистику за сегодня")

if __name__ == "__main__":
    # Убедимся, что директория PDF существует
    PDF_DIR.mkdir(exist_ok=True)
    add_test_orders()

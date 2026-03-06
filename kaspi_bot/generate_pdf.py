#!/usr/bin/env python3
"""Generate a simple blank PDF for testing and update DB."""
import sys
from pathlib import Path
from pypdf import PdfWriter

from database import update_order_pdf, order_exists
from config import PDF_DIR


def generate(order_id: str, order_code: str | None = None):
    if not order_exists(order_id):
        print(f"Order {order_id} not found", file=sys.stderr)
        return 2

    if not order_code:
        order_code = order_id

    PDF_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{order_code}_{order_id}.pdf"
    path = PDF_DIR / filename

    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)

    with open(path, 'wb') as f:
        writer.write(f)

    # Update DB
    update_order_pdf(order_id, str(path))
    print(str(path))
    return 0


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: generate_pdf.py <order_id> [order_code]', file=sys.stderr)
        sys.exit(1)
    oid = sys.argv[1]
    ocode = sys.argv[2] if len(sys.argv) >= 3 else None
    sys.exit(generate(oid, ocode))

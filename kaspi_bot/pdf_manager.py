"""
Менеджер PDF файлов.

Отвечает за:
- Сохранение скачанных накладных на диск
- Объединение нескольких PDF в один файл
"""

import logging
from datetime import datetime
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from config import MERGED_DIR, PDF_DIR

logger = logging.getLogger("kaspi_bot.pdf")


def save_pdf(order_id: str, order_code: str, pdf_bytes: bytes) -> str:
    """
    Сохранить PDF на диск.

    Возвращает путь к сохранённому файлу.
    """
    filename = f"{order_code}_{order_id}.pdf"
    filepath = PDF_DIR / filename
    filepath.write_bytes(pdf_bytes)
    logger.info("PDF сохранён: %s (%d байт)", filepath, len(pdf_bytes))
    return str(filepath)


def merge_pdfs(pdf_paths: list[str]) -> tuple[str | None, set[str]]:
    """
    Объединить несколько PDF файлов в один.

    Возвращает (путь к объединённому файлу, множество реально объединённых путей)
    или (None, set()) если нет файлов.
    """
    if not pdf_paths:
        logger.warning("Нет PDF файлов для объединения")
        return None, set()

    # Проверяем что все файлы существуют
    valid_paths = []
    for p in pdf_paths:
        path = Path(p)
        if path.exists() and path.stat().st_size > 0:
            valid_paths.append(path)
        else:
            logger.warning("PDF файл не найден или пуст: %s", p)

    if not valid_paths:
        logger.warning("Ни один PDF файл не доступен для объединения")
        return None, set()

    # Имя файла с датой и временем
    now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    merged_filename = f"nakladnye_{now}.pdf"
    merged_path = MERGED_DIR / merged_filename

    try:
        writer = PdfWriter()
        for path in valid_paths:
            reader = PdfReader(str(path))
            for page in reader.pages:
                writer.add_page(page)
        with open(merged_path, "wb") as output_file:
            writer.write(output_file)

        merged_ids = {str(p) for p in valid_paths}
        logger.info(
            "Объединено %d PDF -> %s (%d байт)",
            len(valid_paths), merged_path, merged_path.stat().st_size,
        )
        return str(merged_path), merged_ids
    except Exception as e:
        logger.error("Ошибка при объединении PDF: %s", e)
        return None, set()


def get_merged_file_size(path: str) -> float:
    """Вернуть размер файла в мегабайтах."""
    p = Path(path)
    if p.exists():
        return p.stat().st_size / (1024 * 1024)
    return 0

import { readFileSync, existsSync } from 'fs';
import { resolve } from 'path';
import Database from 'better-sqlite3';
import { PDFDocument } from 'pdf-lib';

const dbPath = process.cwd() + '/kaspi_bot/data/orders.db';
const dataDir = resolve(process.cwd(), 'kaspi_bot', 'data');

export async function GET() {
  try {
    const db = new Database(dbPath, { readonly: true });

    const rows = db.prepare(
      "SELECT order_id, order_code, pdf_path FROM orders " +
      "WHERE pdf_path IS NOT NULL " +
      "AND status NOT IN ('COMPLETED', 'CANCELLED', 'RETURNED', 'SENT') " +
      "ORDER BY created_at ASC"
    ).all();

    db.close();

    if (!rows || rows.length === 0) {
      return Response.json(
        { ok: false, error: 'Нет накладных для сборки' },
        { status: 404 }
      );
    }

    const merged = await PDFDocument.create();
    let count = 0;

    for (const row of rows) {
      const pdfPath = resolve(row.pdf_path);
      if (!pdfPath.startsWith(dataDir) || !existsSync(pdfPath)) continue;

      try {
        const bytes = readFileSync(pdfPath);
        const doc = await PDFDocument.load(bytes);
        const pages = await merged.copyPages(doc, doc.getPageIndices());
        for (const page of pages) {
          merged.addPage(page);
        }
        count++;
      } catch {
        // Skip corrupted PDFs
      }
    }

    if (count === 0) {
      return Response.json(
        { ok: false, error: 'PDF файлы не найдены на диске' },
        { status: 404 }
      );
    }

    const pdfBytes = await merged.save();

    return new Response(pdfBytes, {
      headers: {
        'Content-Type': 'application/pdf',
        'Content-Disposition': `attachment; filename="nakladnye_${count}_sht.pdf"`,
        'Content-Length': String(pdfBytes.length),
      },
    });
  } catch (err) {
    console.error('API GET /api/orders/collect error', err);
    return Response.json(
      { ok: false, error: 'Internal server error' },
      { status: 500 }
    );
  }
}

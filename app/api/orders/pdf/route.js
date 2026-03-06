import { readFileSync, existsSync } from 'fs';
import { resolve, basename } from 'path';
import Database from 'better-sqlite3';

const dbPath = process.cwd() + '/kaspi_bot/data/orders.db';

export async function GET(req) {
  try {
    const { searchParams } = new URL(req.url);
    const orderId = searchParams.get('order_id');

    if (!orderId || !/^[a-zA-Z0-9_-]{1,64}$/.test(orderId)) {
      return Response.json(
        { ok: false, error: 'order_id query parameter required' },
        { status: 400 }
      );
    }

    const db = new Database(dbPath, { readonly: true });
    const row = db.prepare('SELECT pdf_path FROM orders WHERE order_id = ?').get(orderId);
    db.close();

    if (!row || !row.pdf_path) {
      return Response.json(
        { ok: false, error: 'PDF not found for this order' },
        { status: 404 }
      );
    }

    // Resolve path and validate it's within the data directory
    const pdfPath = resolve(row.pdf_path);
    const dataDir = resolve(process.cwd(), 'kaspi_bot', 'data');

    if (!pdfPath.startsWith(dataDir)) {
      return Response.json(
        { ok: false, error: 'Invalid file path' },
        { status: 403 }
      );
    }

    if (!existsSync(pdfPath)) {
      return Response.json(
        { ok: false, error: 'PDF file not found on disk' },
        { status: 404 }
      );
    }

    const fileBuffer = readFileSync(pdfPath);
    const filename = basename(pdfPath);

    return new Response(fileBuffer, {
      headers: {
        'Content-Type': 'application/pdf',
        'Content-Disposition': `attachment; filename="${filename}"`,
        'Content-Length': String(fileBuffer.length),
      },
    });
  } catch (err) {
    console.error('API GET /api/orders/pdf error', err);
    return Response.json(
      { ok: false, error: 'Internal server error' },
      { status: 500 }
    );
  }
}

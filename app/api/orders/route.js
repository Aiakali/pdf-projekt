import Database from 'better-sqlite3';

const dbPath = process.cwd() + '/kaspi_bot/data/orders.db';

function ensureDb(db) {
  db.prepare(
    `CREATE TABLE IF NOT EXISTS orders (
      order_id    TEXT PRIMARY KEY,
      order_code  TEXT,
      customer    TEXT DEFAULT '',
      total_price REAL DEFAULT 0,
      status      TEXT DEFAULT 'NEW',
      kaspi_status TEXT DEFAULT '',
      pdf_path    TEXT,
      created_at  TEXT,
      processed_at TEXT,
      sent_at     TEXT
    )`
  ).run();
}

export async function GET() {
  try {
    const db = new Database(dbPath);
    ensureDb(db);
    const rows = db.prepare('SELECT * FROM orders ORDER BY created_at DESC').all();
    db.close();
    return Response.json({ ok: true, orders: rows });
  } catch (err) {
    console.error('API /api/orders error', err);
    return Response.json({ ok: false, error: 'Internal server error' }, { status: 500 });
  }
}

const ID_RE = /^[a-zA-Z0-9_-]{1,64}$/;

export async function POST(req) {
  try {
    const body = await req.json();
    const { order_id, order_code, status, customer, total_price } = body;
    
    if (!order_id || !order_code) {
      return Response.json({ ok: false, error: 'order_id and order_code required' }, { status: 400 });
    }
    if (!ID_RE.test(order_id) || !ID_RE.test(order_code)) {
      return Response.json({ ok: false, error: 'Invalid order_id or order_code format' }, { status: 400 });
    }

    const db = new Database(dbPath);
    ensureDb(db);
    const stmt = db.prepare(
      `INSERT OR IGNORE INTO orders (order_id, order_code, status, customer, total_price)
       VALUES (@order_id, @order_code, @status, @customer, @total_price)`
    );
    const safeCustomer = typeof customer === 'string' ? customer.slice(0, 200) : '';
    stmt.run({ order_id, order_code, status: status || 'NEW', customer: safeCustomer, total_price: Number(total_price) || 0 });
    const row = db.prepare('SELECT * FROM orders WHERE order_id = ?').get(order_id);
    db.close();
    
    return Response.json({ ok: true, order: row }, { status: 201 });
  } catch (err) {
    console.error('API POST /api/orders error', err);
    return Response.json({ ok: false, error: 'Internal server error' }, { status: 500 });
  }
}

export async function DELETE(req) {
  try {
    const { searchParams } = new URL(req.url);
    const order_id = searchParams.get('order_id');
    
    if (!order_id) {
      return Response.json({ ok: false, error: 'order_id query required' }, { status: 400 });
    }
    if (!ID_RE.test(order_id)) {
      return Response.json({ ok: false, error: 'Invalid order_id format' }, { status: 400 });
    }

    const db = new Database(dbPath);
    ensureDb(db);
    db.prepare('DELETE FROM orders WHERE order_id = ?').run(order_id);
    db.close();
    
    return Response.json({ ok: true });
  } catch (err) {
    console.error('API DELETE /api/orders error', err);
    return Response.json({ ok: false, error: 'Internal server error' }, { status: 500 });
  }
}

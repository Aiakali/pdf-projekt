import Database from 'better-sqlite3';

const dbPath = process.cwd() + '/kaspi_bot/data/orders.db';

// In-memory rate limiting: IP -> { count, resetAt }
const attempts = new Map();
const MAX_ATTEMPTS = 5;
const WINDOW_MS = 15 * 60 * 1000;

function checkRateLimit(ip) {
  const now = Date.now();
  const entry = attempts.get(ip);
  if (!entry || now > entry.resetAt) {
    attempts.set(ip, { count: 1, resetAt: now + WINDOW_MS });
    return true;
  }
  if (entry.count >= MAX_ATTEMPTS) return false;
  entry.count++;
  return true;
}

export async function POST(req) {
  const ip = req.headers.get('x-forwarded-for') || req.headers.get('x-real-ip') || 'unknown';

  if (!checkRateLimit(ip)) {
    return Response.json(
      { ok: false, error: 'Too many attempts. Try again later.' },
      { status: 429 }
    );
  }

  let body;
  try {
    body = await req.json();
  } catch {
    return Response.json({ ok: false, error: 'Invalid request' }, { status: 400 });
  }

  const code = String(body.code || '').trim();
  if (!code || !/^\d{6}$/.test(code)) {
    return Response.json({ ok: false, error: 'Invalid code' }, { status: 400 });
  }

  try {
    const db = new Database(dbPath);
    const now = new Date().toISOString();

    const row = db.prepare(
      "SELECT id FROM web_sessions WHERE code = ? AND expires_at > ? AND used = 0"
    ).get(code, now);

    if (!row) {
      db.close();
      return Response.json({ ok: false, error: 'Invalid or expired code' }, { status: 401 });
    }

    // Mark code as used
    db.prepare("UPDATE web_sessions SET used = 1 WHERE id = ?").run(row.id);
    // Clean up expired codes
    db.prepare("DELETE FROM web_sessions WHERE expires_at < ?").run(now);
    db.close();

    // Return the API key for session
    const apiKey = process.env.WEB_API_KEY;
    return Response.json({ ok: true, key: apiKey });
  } catch {
    return Response.json({ ok: false, error: 'Internal server error' }, { status: 500 });
  }
}

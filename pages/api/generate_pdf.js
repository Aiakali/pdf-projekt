import { spawnSync } from 'child_process';

const ID_RE = /^[a-zA-Z0-9_-]{1,64}$/;

export default function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).end();

  // Auth check — match middleware behavior for pages/api routes
  const apiKey = process.env.WEB_API_KEY;
  const headerKey = req.headers['x-api-key'];
  const authHeader = req.headers['authorization'];
  const bearerKey = authHeader?.startsWith('Bearer ') ? authHeader.slice(7) : null;
  if (!apiKey || (headerKey !== apiKey && bearerKey !== apiKey)) {
    return res.status(401).json({ ok: false, error: 'Unauthorized' });
  }

  const { order_id, order_code } = req.body || {};
  if (!order_id || !ID_RE.test(order_id)) {
    return res.status(400).json({ ok: false, error: 'Invalid order_id' });
  }
  if (order_code && !ID_RE.test(order_code)) {
    return res.status(400).json({ ok: false, error: 'Invalid order_code' });
  }

  const py = spawnSync('python3', ['kaspi_bot/generate_pdf.py', order_id, order_code || ''], { encoding: 'utf8', timeout: 30000 });

  if (py.error) {
    console.error('generate_pdf.js error', py.error);
    return res.status(500).json({ ok: false, error: 'PDF generation failed' });
  }

  const out = py.stdout && py.stdout.trim();

  if (py.status !== 0) {
    console.error('generate_pdf.js stderr', py.stderr);
    return res.status(500).json({ ok: false, error: 'PDF generation failed' });
  }

  res.status(200).json({ ok: true, path: out });
}

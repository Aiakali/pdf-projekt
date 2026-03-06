import Database from 'better-sqlite3';

const dbPath = process.cwd() + '/kaspi_bot/data/orders.db';

export async function GET(req) {
  try {
    const db = new Database(dbPath, { readonly: true });

    const total = db.prepare('SELECT COUNT(*) as c FROM orders').get().c;

    const active = db.prepare(
      "SELECT COUNT(*) as c FROM orders WHERE status NOT IN ('CANCELLED', 'COMPLETED', 'SENT', 'RETURNED')"
    ).get().c;

    const pdfReady = db.prepare(
      "SELECT COUNT(*) as c FROM orders WHERE pdf_path IS NOT NULL AND sent_at IS NULL"
    ).get().c;

    // Period stats
    const { searchParams } = new URL(req.url);
    const statsFrom = searchParams.get('stats_from');
    const statsTo = searchParams.get('stats_to');
    const statsDays = Math.min(365, Math.max(0, parseInt(searchParams.get('stats_days') || '7', 10)));

    let periodStats = null;
    try {
      if (statsFrom) {
        // Custom date range mode
        const from = statsFrom.replace(/[^0-9-]/g, '');
        const to = (statsTo || '9999-12-31').replace(/[^0-9-]/g, '');
        const row = db.prepare(
          "SELECT COUNT(*) as orders, COALESCE(SUM(total_price),0) as total_sum, " +
          "COUNT(CASE WHEN pdf_path IS NOT NULL THEN 1 END) as pdf_count, " +
          "COUNT(CASE WHEN sent_at IS NOT NULL THEN 1 END) as sent_count " +
          "FROM orders WHERE created_at >= ? AND created_at < ?"
        ).get(from + 'T00:00:00', to + 'T23:59:59');
        periodStats = {
          days: 0,
          label: 'custom',
          orders: row.orders,
          total_sum: row.total_sum,
          pdf_count: row.pdf_count,
          sent_count: row.sent_count,
          avg_check: row.orders > 0 ? Math.round(row.total_sum / row.orders) : 0,
        };
      } else if (statsDays === 0) {
        // Session mode: current 15:00 Almaty business window
        // Server is UTC; Almaty = UTC+5, so 15:00 Almaty = 10:00 UTC
        const ALMATY_OFFSET = 5;
        const now = new Date();
        const almatyH = (now.getUTCHours() + ALMATY_OFFSET) % 24;
        // Calculate today's 10:00 UTC (= 15:00 Almaty)
        const todayCutoffUTC = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), 15 - ALMATY_OFFSET, 0, 0));
        let sessionStart;
        if (now >= todayCutoffUTC) {
          sessionStart = todayCutoffUTC.toISOString().replace('Z','');
        } else {
          const prev = new Date(todayCutoffUTC); prev.setUTCDate(prev.getUTCDate() - 1);
          sessionStart = prev.toISOString().replace('Z','');
        }
        const row = db.prepare(
          "SELECT COUNT(*) as orders, COALESCE(SUM(total_price),0) as total_sum, " +
          "COUNT(CASE WHEN pdf_path IS NOT NULL THEN 1 END) as pdf_count, " +
          "COUNT(CASE WHEN sent_at IS NOT NULL THEN 1 END) as sent_count " +
          "FROM orders WHERE created_at >= ?"
        ).get(sessionStart);
        periodStats = {
          days: 1,
          label: 'session',
          orders: row.orders,
          total_sum: row.total_sum,
          pdf_count: row.pdf_count,
          sent_count: row.sent_count,
          avg_check: row.orders > 0 ? Math.round(row.total_sum / row.orders) : 0,
        };
      } else {
        const cutoff = new Date(Date.now() - (statsDays - 1) * 86400000).toISOString().slice(0, 10);
        const row = db.prepare(
          "SELECT COUNT(*) as days, COALESCE(SUM(orders),0) as orders, " +
          "COALESCE(SUM(total_sum),0) as total_sum, COALESCE(SUM(pdf_count),0) as pdf_count, " +
          "COALESCE(SUM(sent_count),0) as sent_count FROM stats_daily WHERE day >= ?"
        ).get(cutoff);
        const totalOrders = row.orders;
        periodStats = {
          days: row.days,
          orders: totalOrders,
          total_sum: row.total_sum,
          pdf_count: row.pdf_count,
          sent_count: row.sent_count,
          avg_check: totalOrders > 0 ? Math.round(row.total_sum / totalOrders) : 0,
        };
      }
    } catch (_) {
      // stats_daily table might not exist yet
    }

    db.close();

    return Response.json({
      status: 'ok',
      db_orders: total,
      db_active: active,
      pdf_ready: pdfReady,
      period_stats: periodStats,
      timestamp: new Date().toISOString(),
    });
  } catch (err) {
    return Response.json(
      { status: 'error', error: 'Internal server error' },
      { status: 500 }
    );
  }
}

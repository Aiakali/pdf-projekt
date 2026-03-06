'use client';

import { useEffect, useState } from 'react';

const STATUS_LABELS = {
	NEW: 'Новый',
	ACCEPTED: 'Принят',
	ASSEMBLE: 'Упаковка',
	KASPI_DELIVERY: 'Kaspi Доставка',
	DELIVERY: 'Доставка',
	PDF_READY: 'PDF готов',
	SENT: 'Отправлен',
	CANCELLED: 'Отменён',
	COMPLETED: 'Завершён',
	RETURNED: 'Возвращён',
};

const STATUS_BADGE = {
	NEW:            { bg: '#fef3c7', fg: '#92400e', icon: '🆕' },
	ACCEPTED:       { bg: '#dbeafe', fg: '#1e40af', icon: '✅' },
	ASSEMBLE:       { bg: '#e0e7ff', fg: '#3730a3', icon: '📦' },
	KASPI_DELIVERY: { bg: '#fce7f3', fg: '#9d174d', icon: '🚚' },
	DELIVERY:       { bg: '#fce7f3', fg: '#9d174d', icon: '🚚' },
	PDF_READY:      { bg: '#d1fae5', fg: '#065f46', icon: '📄' },
	SENT:           { bg: '#dbeafe', fg: '#1e40af', icon: '📨' },
	CANCELLED:      { bg: '#fee2e2', fg: '#991b1b', icon: '❌' },
	COMPLETED:      { bg: '#f3f4f6', fg: '#374151', icon: '✔' },
	RETURNED:       { bg: '#fee2e2', fg: '#991b1b', icon: '↩' },
};

function statusLabel(status) {
	return STATUS_LABELS[status] || status;
}

function StatusBadge({ status }) {
	const s = STATUS_BADGE[status] || { bg: '#f3f4f6', fg: '#374151', icon: '' };
	return (
		<span style={{
			display: 'inline-flex', alignItems: 'center', gap: '4px',
			padding: '3px 10px', borderRadius: 20, fontSize: 12, fontWeight: 600,
			background: s.bg, color: s.fg, whiteSpace: 'nowrap',
		}}>
			{s.icon} {statusLabel(status)}
		</span>
	);
}

function formatDate(dateStr) {
	if (!dateStr) return '—';
	const d = new Date(dateStr + (dateStr.includes('+') || dateStr.includes('Z') ? '' : 'Z'));
	return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', timeZone: 'Asia/Almaty' })
		+ ' ' + d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Almaty' });
}

function formatPrice(price) {
	if (!price && price !== 0) return '—';
	return Number(price).toLocaleString('ru-RU') + ' ₸';
}

export default function OrdersPage() {
	const [orders, setOrders] = useState([]);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState('');
	const [statusFilter, setStatusFilter] = useState('ACTIVE');
	const [dateFilter, setDateFilter] = useState('');
	const [dateFilterEnd, setDateFilterEnd] = useState('');
	const [lastUpdate, setLastUpdate] = useState(null);
	const [showForm, setShowForm] = useState(false);
	const [apiKey, setApiKey] = useState('');
	const [authOk, setAuthOk] = useState(false);
	const [authLoading, setAuthLoading] = useState(true);
	const [keyInput, setKeyInput] = useState('');
	const [loginMode, setLoginMode] = useState('telegram');
	const [codeInput, setCodeInput] = useState('');
	const [periodStats, setPeriodStats] = useState(null);
	const [statsDays, setStatsDays] = useState(7);
	const [statsFrom, setStatsFrom] = useState('');
	const [statsTo, setStatsTo] = useState('');
	const [form, setForm] = useState({
		order_id: '',
		order_code: '',
		customer: '',
		total_price: '',
	});

	const authHeaders = (extra = {}) => ({ 'x-api-key': apiKey, ...extra });

	// Check saved key on mount
	useEffect(() => {
		const saved = sessionStorage.getItem('web_api_key');
		if (saved) {
			setApiKey(saved);
			// verify key
			fetch('/api/health', { headers: { 'x-api-key': saved } })
				.then(r => { if (r.ok) { setAuthOk(true); setApiKey(saved); } setAuthLoading(false); })
				.catch(() => setAuthLoading(false));
		} else {
			setAuthLoading(false);
		}
	}, []);

	const handleLogin = async (e) => {
		e.preventDefault();
		const key = keyInput.trim();
		if (!key) return;
		try {
			const r = await fetch('/api/health', { headers: { 'x-api-key': key } });
			if (r.ok) {
				sessionStorage.setItem('web_api_key', key);
				setApiKey(key);
				setAuthOk(true);
			} else {
				setError('Неверный ключ доступа');
			}
		} catch { setError('Ошибка соединения'); }
	};

	const handleTelegramLogin = async (e) => {
		e.preventDefault();
		const code = codeInput.trim();
		if (code.length !== 6) return;
		setError('');
		try {
			const r = await fetch('/api/auth/login', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ code }),
			});
			const data = await r.json();
			if (r.ok && data.ok) {
				sessionStorage.setItem('web_api_key', data.key);
				setApiKey(data.key);
				setAuthOk(true);
			} else if (r.status === 429) {
				setError('Слишком много попыток. Подожди 15 минут.');
			} else {
				setError('Неверный или просроченный код');
			}
		} catch { setError('Ошибка соединения'); }
	};

	const loadOrders = async () => {
		setError('');
		try {
			const response = await fetch('/api/orders', { cache: 'no-store', headers: authHeaders() });
			const data = await response.json();
			if (response.status === 401) { setAuthOk(false); sessionStorage.removeItem('web_api_key'); return; }
			if (!response.ok || !data.ok) {
				throw new Error(data.error || 'Не удалось загрузить заказы');
			}
			setOrders(data.orders || []);
			setLastUpdate(new Date());
		} catch (loadError) {
			setError(loadError.message || 'Ошибка загрузки');
		} finally {
			setLoading(false);
		}
	};

	const loadStats = async (days, from, to) => {
		try {
			let url;
			if (days === -1 && from) {
				url = `/api/health?stats_from=${from}` + (to ? `&stats_to=${to}` : '');
			} else {
				url = `/api/health?stats_days=${days}`;
			}
			const r = await fetch(url, { headers: authHeaders() });
			if (r.ok) {
				const d = await r.json();
				if (d.period_stats) setPeriodStats(d.period_stats);
			}
		} catch {}
	};

	useEffect(() => {
		if (!authOk) return;
		loadOrders();
		loadStats(statsDays, statsFrom, statsTo);
		const interval = setInterval(() => { loadOrders(); loadStats(statsDays, statsFrom, statsTo); }, 30000);
		return () => clearInterval(interval);
	}, [authOk, statsDays, statsFrom, statsTo]);

	const addOrder = async (event) => {
		event.preventDefault();
		setError('');
		try {
			const response = await fetch('/api/orders', {
				method: 'POST',
				headers: authHeaders({ 'Content-Type': 'application/json' }),
				body: JSON.stringify({
					order_id: form.order_id.trim(),
					order_code: form.order_code.trim(),
					customer: form.customer.trim(),
					total_price: form.total_price ? Number(form.total_price) : 0,
					status: 'DELIVERY',
				}),
			});
			const data = await response.json();
			if (!response.ok || !data.ok) {
				throw new Error(data.error || 'Не удалось добавить заказ');
			}
			setForm({ order_id: '', order_code: '', customer: '', total_price: '' });
			setShowForm(false);
			await loadOrders();
		} catch (addError) {
			setError(addError.message || 'Ошибка добавления');
		}
	};

	const removeOrder = async (orderId) => {
		if (!confirm(`Удалить заказ ${orderId}?`)) return;
		setError('');
		try {
			const response = await fetch(`/api/orders?order_id=${encodeURIComponent(orderId)}`, { method: 'DELETE', headers: authHeaders() });
			const data = await response.json();
			if (!response.ok || !data.ok) throw new Error(data.error || 'Не удалось удалить');
			await loadOrders();
		} catch (removeError) {
			setError(removeError.message || 'Ошибка удаления');
		}
	};

	const INACTIVE = ['CANCELLED', 'COMPLETED', 'RETURNED', 'SENT'];
	const filtered = orders.filter((o) => {
		if (statusFilter === 'ACTIVE') { if (INACTIVE.includes(o.status)) return false; }
		else if (statusFilter && statusFilter !== 'ALL') { if (o.status !== statusFilter) return false; }
		if (dateFilter && o.created_at) {
			const d = o.created_at.slice(0, 10);
			if (d < dateFilter) return false;
			if (dateFilterEnd && d > dateFilterEnd) return false;
		}
		return true;
	});

	/* Summary counters */
	const counts = {
		active: orders.filter(o => !INACTIVE.includes(o.status)).length,
		pdfReady: orders.filter(o => o.status === 'PDF_READY').length,
		sent: orders.filter(o => o.status === 'SENT').length,
		total: orders.length,
	};

	/* Total sum of filtered orders */
	const filteredSum = filtered.reduce((sum, o) => sum + (Number(o.total_price) || 0), 0);

	return (
		<>
			<style>{`
				/* ---- Animations ---- */
				@keyframes fadeIn {
					from { opacity: 0; }
					to { opacity: 1; }
				}
				@keyframes slideUp {
					from { opacity: 0; transform: translateY(16px); }
					to { opacity: 1; transform: translateY(0); }
				}
				@keyframes slideDown {
					from { opacity: 0; transform: translateY(-10px); }
					to { opacity: 1; transform: translateY(0); }
				}
				@keyframes spin { to { transform: rotate(360deg); } }

				* { box-sizing: border-box; }
				body { margin: 0; background: #f0f2f5; }

				/* ---- Login ---- */
				.login-page {
					min-height: 100vh;
					display: flex;
					align-items: center;
					justify-content: center;
					font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
					background: linear-gradient(135deg, #1a1625 0%, #231c30 40%, #2d1a2a 70%, #331a24 100%);
					position: relative;
					overflow: hidden;
				}
				.login-page::before {
					content: '';
					position: absolute;
					width: 420px; height: 420px;
					background: radial-gradient(circle, rgba(220,38,38,0.13) 0%, transparent 70%);
					top: -120px; right: -120px;
					border-radius: 50%;
					pointer-events: none;
				}
				.login-page::after {
					content: '';
					position: absolute;
					width: 320px; height: 320px;
					background: radial-gradient(circle, rgba(124,58,237,0.09) 0%, transparent 70%);
					bottom: -100px; left: -100px;
					border-radius: 50%;
					pointer-events: none;
				}
				.login-box {
					background: rgba(255,255,255,0.06);
					backdrop-filter: blur(24px);
					-webkit-backdrop-filter: blur(24px);
					border: 1px solid rgba(255,255,255,0.1);
					border-radius: 20px;
					box-shadow: 0 25px 60px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.06);
					padding: 44px 36px;
					max-width: 400px;
					width: 100%;
					text-align: center;
					animation: slideUp 0.6s cubic-bezier(0.16, 1, 0.3, 1);
					position: relative;
					z-index: 1;
				}
				.login-box h2 { margin: 0 0 10px; color: #f87171; font-size: 1.5rem; }
				.login-box p  { margin: 0 0 20px; color: rgba(255,255,255,0.45); font-size: 14px; }
				.login-box input {
					width: 100%; padding: 12px 16px;
					border: 1px solid rgba(255,255,255,0.12);
					border-radius: 10px; font-size: 14px; outline: none;
					background: rgba(255,255,255,0.06);
					color: #fff;
					transition: all 0.2s;
				}
				.login-box input::placeholder { color: rgba(255,255,255,0.28); }
				.login-box input:focus {
					border-color: #f87171;
					box-shadow: 0 0 0 3px rgba(248,113,113,0.15);
					background: rgba(255,255,255,0.09);
				}
				.login-box button {
					margin-top: 16px; width: 100%; padding: 12px; border: none;
					border-radius: 10px;
					background: linear-gradient(135deg, #dc2626, #ef4444);
					color: #fff;
					font-weight: 600; font-size: 14px; cursor: pointer;
					transition: all 0.2s;
					box-shadow: 0 4px 16px rgba(220,38,38,0.3);
				}
				.login-box button:hover {
					background: linear-gradient(135deg, #b91c1c, #dc2626);
					box-shadow: 0 6px 22px rgba(220,38,38,0.4);
					transform: translateY(-1px);
				}
				.login-box button:active { transform: translateY(0); }
				.login-box button:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
				.login-error { color: #f87171; font-size: 13px; margin-top: 12px; }

				/* ---- Page ---- */
				.page {
					min-height: 100vh;
					font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
					color: #1f2937;
					animation: fadeIn 0.3s ease;
				}

				/* ---- Header ---- */
				.header {
					background: linear-gradient(135deg, #1a1625 0%, #231c30 50%, #2d1a2a 100%);
					color: #fff;
					padding: 24px 24px 44px;
					position: relative;
					overflow: hidden;
				}
				.header::before {
					content: '';
					position: absolute;
					top: -50%; right: -20%;
					width: 400px; height: 400px;
					background: radial-gradient(circle, rgba(220,38,38,0.08) 0%, transparent 70%);
					border-radius: 50%;
					pointer-events: none;
				}
				.header::after {
					content: '';
					position: absolute;
					bottom: 0; left: 0; right: 0;
					height: 24px;
					background: #f0f2f5;
					border-radius: 24px 24px 0 0;
				}
				.header-inner {
					max-width: 1200px;
					margin: 0 auto;
					display: flex;
					align-items: center;
					justify-content: space-between;
					flex-wrap: wrap;
					gap: 12px;
					position: relative;
					z-index: 1;
				}
				.header h1 {
					margin: 0;
					font-size: 1.4rem;
					font-weight: 700;
					display: flex;
					align-items: center;
					gap: 10px;
					letter-spacing: -0.3px;
				}
				.header-right {
					display: flex;
					align-items: center;
					gap: 10px;
					flex-wrap: wrap;
				}
				.header-right .update-info {
					font-size: 0.78rem;
					opacity: 0.55;
					font-variant-numeric: tabular-nums;
				}

				/* ---- Summary cards ---- */
				.summary {
					max-width: 1200px;
					margin: -20px auto 0;
					padding: 0 24px;
					display: grid;
					grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
					gap: 14px;
					position: relative;
					z-index: 2;
				}
				.summary-card {
					background: #fff;
					border-radius: 14px;
					padding: 20px 16px;
					text-align: center;
					box-shadow: 0 2px 8px rgba(0,0,0,0.06), 0 0 0 1px rgba(0,0,0,0.03);
					transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
					animation: slideUp 0.5s cubic-bezier(0.16, 1, 0.3, 1) both;
					position: relative;
					overflow: hidden;
				}
				.summary-card::before {
					content: '';
					position: absolute;
					top: 0; left: 0; right: 0;
					height: 3px;
					border-radius: 14px 14px 0 0;
				}
				.summary-card:nth-child(1)::before { background: linear-gradient(90deg, #dc2626, #ef4444); }
				.summary-card:nth-child(2)::before { background: linear-gradient(90deg, #059669, #34d399); }
				.summary-card:nth-child(3)::before { background: linear-gradient(90deg, #2563eb, #60a5fa); }
				.summary-card:nth-child(4)::before { background: linear-gradient(90deg, #7c3aed, #a78bfa); }
				.summary-card:nth-child(1) { animation-delay: 0s; }
				.summary-card:nth-child(2) { animation-delay: 0.06s; }
				.summary-card:nth-child(3) { animation-delay: 0.12s; }
				.summary-card:nth-child(4) { animation-delay: 0.18s; }
				.summary-card:hover {
					transform: translateY(-4px);
					box-shadow: 0 8px 25px rgba(0,0,0,0.1), 0 0 0 1px rgba(0,0,0,0.03);
				}
				.summary-card .num {
					font-size: 2rem;
					font-weight: 800;
					line-height: 1;
					letter-spacing: -1px;
				}
				.summary-card .lbl {
					font-size: 0.74rem;
					color: #6b7280;
					margin-top: 6px;
					font-weight: 500;
					text-transform: uppercase;
					letter-spacing: 0.4px;
				}

				/* ---- Content ---- */
				.content {
					max-width: 1200px;
					margin: 20px auto;
					padding: 0 24px;
				}

				/* ---- Toolbar ---- */
				.toolbar {
					background: #fff;
					border-radius: 14px;
					padding: 14px 18px;
					margin-bottom: 16px;
					box-shadow: 0 2px 8px rgba(0,0,0,0.04), 0 0 0 1px rgba(0,0,0,0.03);
					display: flex;
					align-items: center;
					gap: 14px;
					flex-wrap: wrap;
					animation: slideUp 0.5s cubic-bezier(0.16, 1, 0.3, 1) 0.15s both;
				}
				.toolbar select, .toolbar input[type="date"] {
					padding: 7px 12px;
					border: 1px solid #e5e7eb;
					border-radius: 8px;
					font-size: 13px;
					background: #f9fafb;
					color: #374151;
					outline: none;
					transition: all 0.2s;
				}
				.toolbar select:focus, .toolbar input[type="date"]:focus {
					border-color: #dc2626;
					box-shadow: 0 0 0 2px rgba(220,38,38,0.08);
					background: #fff;
				}
				.toolbar .toolbar-label {
					font-size: 13px;
					color: #9ca3af;
					font-weight: 500;
				}
				.toolbar .count-info {
					margin-left: auto;
					display: inline-flex;
					align-items: center;
					gap: 10px;
					font-size: 13px;
					font-weight: 600;
				}
				.count-orders {
					color: #6b7280;
				}
				.count-sum {
					background: linear-gradient(135deg, #dc2626, #ef4444);
					color: #fff;
					padding: 5px 14px;
					border-radius: 20px;
					font-size: 13px;
					font-weight: 700;
					letter-spacing: 0.3px;
					box-shadow: 0 2px 8px rgba(220,38,38,0.25);
				}

				/* ---- Stats panel ---- */
				.stats-panel {
					background: #fff;
					border-radius: 14px;
					padding: 20px;
					margin-bottom: 16px;
					box-shadow: 0 2px 8px rgba(0,0,0,0.04), 0 0 0 1px rgba(0,0,0,0.03);
					animation: slideUp 0.5s cubic-bezier(0.16, 1, 0.3, 1) 0.2s both;
				}
				.stats-header {
					display: flex;
					align-items: center;
					justify-content: space-between;
					margin-bottom: 16px;
				}
				.stats-header h3 {
					margin: 0;
					font-size: 0.95rem;
					color: #374151;
					font-weight: 600;
				}
				.stats-header select {
					padding: 6px 12px;
					border: 1px solid #e5e7eb;
					border-radius: 8px;
					font-size: 13px;
					outline: none;
					background: #f9fafb;
					color: #374151;
					transition: all 0.2s;
				}
				.stats-header select:focus { border-color: #dc2626; box-shadow: 0 0 0 2px rgba(220,38,38,0.08); }
				.stats-grid {
					display: grid;
					grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
					gap: 12px;
				}
				.stat-item {
					background: #f8fafc;
					border-radius: 12px;
					padding: 16px;
					text-align: center;
					border: 1px solid #f1f5f9;
					transition: all 0.2s;
				}
				.stat-item:hover {
					background: #f1f5f9;
					border-color: #e2e8f0;
				}
				.stat-item .stat-val {
					font-size: 1.5rem;
					font-weight: 700;
					line-height: 1.2;
					letter-spacing: -0.5px;
				}
				.stat-item .stat-lbl {
					font-size: 0.73rem;
					color: #94a3b8;
					margin-top: 4px;
					font-weight: 500;
					text-transform: uppercase;
					letter-spacing: 0.3px;
				}

				/* ---- Buttons ---- */
				.btn {
					display: inline-flex;
					align-items: center;
					gap: 6px;
					padding: 8px 16px;
					border: none;
					border-radius: 10px;
					font-size: 13px;
					font-weight: 500;
					cursor: pointer;
					transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
					text-decoration: none;
					white-space: nowrap;
				}
				.btn:active { transform: scale(0.97); }
				.btn-primary {
					background: linear-gradient(135deg, #dc2626, #ef4444);
					color: #fff;
					box-shadow: 0 2px 8px rgba(220,38,38,0.25);
				}
				.btn-primary:hover {
					box-shadow: 0 4px 16px rgba(220,38,38,0.35);
					transform: translateY(-1px);
				}
				.btn-ghost {
					background: rgba(255,255,255,0.08);
					color: #6b7280;
					border: 1px solid #e5e7eb;
				}
				.btn-ghost:hover {
					background: rgba(0,0,0,0.04);
					border-color: #d1d5db;
				}
				.btn-success {
					background: linear-gradient(135deg, #d1fae5, #a7f3d0);
					color: #065f46;
					border: 1px solid rgba(5,150,105,0.1);
				}
				.btn-success:hover {
					background: linear-gradient(135deg, #a7f3d0, #6ee7b7);
					transform: translateY(-1px);
				}
				.btn-danger {
					background: transparent;
					color: #dc2626;
					border: 1px solid #fecaca;
				}
				.btn-danger:hover {
					background: #fef2f2;
					border-color: #fca5a5;
				}
				.btn-sm {
					padding: 5px 10px;
					font-size: 12px;
				}

				/* ---- Add form ---- */
				.add-panel {
					background: #fff;
					border-radius: 14px;
					padding: 20px;
					margin-bottom: 16px;
					box-shadow: 0 2px 8px rgba(0,0,0,0.04), 0 0 0 1px rgba(0,0,0,0.03);
					animation: slideDown 0.3s ease both;
				}
				.add-panel h3 {
					margin: 0 0 14px;
					font-size: 0.95rem;
					color: #374151;
					font-weight: 600;
				}
				.add-grid {
					display: grid;
					grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
					gap: 10px;
				}
				.add-grid input {
					padding: 9px 14px;
					border: 1px solid #e5e7eb;
					border-radius: 10px;
					font-size: 13px;
					outline: none;
					background: #f9fafb;
					transition: all 0.2s;
				}
				.add-grid input:focus {
					border-color: #dc2626;
					box-shadow: 0 0 0 2px rgba(220,38,38,0.08);
					background: #fff;
				}
				.add-actions {
					margin-top: 14px;
					display: flex;
					gap: 8px;
				}

				/* ---- Error ---- */
				.error-bar {
					background: linear-gradient(135deg, #fef2f2, #fee2e2);
					color: #991b1b;
					padding: 12px 18px;
					border-radius: 12px;
					font-size: 13px;
					margin-bottom: 14px;
					display: flex;
					align-items: center;
					gap: 8px;
					border: 1px solid #fecaca;
					animation: slideDown 0.3s ease;
				}

				/* ---- Table ---- */
				.table-wrap {
					background: #fff;
					border-radius: 14px;
					overflow: hidden;
					box-shadow: 0 2px 8px rgba(0,0,0,0.04), 0 0 0 1px rgba(0,0,0,0.03);
					animation: slideUp 0.5s cubic-bezier(0.16, 1, 0.3, 1) 0.25s both;
				}
				.orders-table {
					width: 100%;
					border-collapse: collapse;
				}
				.orders-table th {
					background: #f8fafc;
					padding: 12px 14px;
					text-align: left;
					font-size: 11px;
					font-weight: 600;
					text-transform: uppercase;
					letter-spacing: 0.5px;
					color: #94a3b8;
					border-bottom: 1px solid #f1f5f9;
				}
				.orders-table td {
					padding: 14px;
					font-size: 13px;
					border-bottom: 1px solid #f8fafc;
					vertical-align: middle;
					transition: background 0.15s;
				}
				.orders-table tbody tr {
					transition: all 0.15s;
				}
				.orders-table tbody tr:hover {
					background: #fafbfe;
				}
				.orders-table tbody tr:last-child td {
					border-bottom: none;
				}
				.order-code {
					font-weight: 600;
					font-variant-numeric: tabular-nums;
					color: #111827;
				}
				.customer-name {
					max-width: 160px;
					overflow: hidden;
					text-overflow: ellipsis;
					white-space: nowrap;
				}
				.price {
					font-variant-numeric: tabular-nums;
					font-weight: 500;
				}
				.empty-state {
					text-align: center;
					padding: 56px 20px;
					color: #94a3b8;
					font-size: 14px;
				}
				.empty-state .empty-icon {
					font-size: 3rem;
					margin-bottom: 12px;
					opacity: 0.6;
				}

				/* ---- Mobile cards ---- */
				.order-cards { display: none; }
				.order-card {
					background: #fff;
					border-radius: 14px;
					padding: 16px;
					margin-bottom: 12px;
					box-shadow: 0 2px 8px rgba(0,0,0,0.04), 0 0 0 1px rgba(0,0,0,0.03);
					transition: all 0.2s;
					animation: slideUp 0.4s cubic-bezier(0.16, 1, 0.3, 1) both;
					border-left: 3px solid #e5e7eb;
				}
				.card-header {
					display: flex;
					justify-content: space-between;
					align-items: center;
					margin-bottom: 12px;
				}
				.card-header .order-code { font-size: 15px; }
				.card-body .card-row {
					display: flex;
					justify-content: space-between;
					padding: 5px 0;
					font-size: 13px;
				}
				.card-body .card-row .label { color: #94a3b8; }
				.card-footer {
					margin-top: 14px;
					display: flex;
					gap: 8px;
				}
				.card-footer > * { flex: 1; text-align: center; justify-content: center; }

				/* ---- Loader ---- */
				.loader {
					display: flex;
					justify-content: center;
					padding: 60px 0;
				}
				.spinner {
					width: 36px; height: 36px;
					border: 3px solid #e5e7eb;
					border-top-color: #dc2626;
					border-radius: 50%;
					animation: spin 0.7s linear infinite;
				}

				/* ---- Responsive ---- */
				@media (max-width: 768px) {
					.header { padding: 16px 16px 40px; }
					.header h1 { font-size: 1.1rem; }
					.summary { padding: 0 12px; margin-top: -20px; grid-template-columns: repeat(2, 1fr); }
					.summary-card { padding: 14px 12px; }
					.summary-card .num { font-size: 1.5rem; }
					.content { padding: 0 12px; margin-top: 14px; }
					.stats-grid { grid-template-columns: repeat(2, 1fr); }
					.stat-item .stat-val { font-size: 1.2rem; }
					.toolbar { padding: 10px 12px; gap: 8px; }
					.table-wrap { display: none; }
					.order-cards { display: block; }
					.add-grid { grid-template-columns: 1fr; }
					.login-box { margin: 0 16px; padding: 36px 24px; }
				}
			`}</style>

			{authLoading ? (
				<div className="login-page"><div className="login-box"><p>Загрузка...</p></div></div>
			) : !authOk ? (
				<div className="login-page">
					<div className="login-box">
						<h2>🔐 Авторизация</h2>
						{loginMode === 'telegram' ? (
							<form onSubmit={handleTelegramLogin}>
								<p style={{ fontSize: 14, color: 'rgba(255,255,255,0.7)', marginBottom: 6 }}>1. Отправь <b style={{ color: '#f87171' }}>/web</b> боту в Telegram</p>
								<p style={{ fontSize: 14, color: 'rgba(255,255,255,0.7)', marginBottom: 16 }}>2. Введи полученный код:</p>
								<input
									type="text"
									inputMode="numeric"
									maxLength={6}
									placeholder="000000"
									value={codeInput}
									onChange={e => setCodeInput(e.target.value.replace(/\D/g, ''))}
									autoFocus
									style={{ textAlign: 'center', fontSize: 28, letterSpacing: 10, fontWeight: 700 }}
								/>
								<button type="submit" disabled={codeInput.length !== 6}>Войти</button>
								<div style={{ marginTop: 16 }}>
									<span style={{ fontSize: 13, color: 'rgba(255,255,255,0.4)', cursor: 'pointer', textDecoration: 'underline' }} onClick={() => { setLoginMode('key'); setError(''); }}>Войти по ключу</span>
								</div>
							</form>
						) : (
							<form onSubmit={handleLogin}>
								<p>Введите ключ доступа к панели</p>
								<input
									type="password"
									placeholder="Ключ доступа"
									value={keyInput}
									onChange={e => setKeyInput(e.target.value)}
									autoFocus
								/>
								<button type="submit">Войти</button>
								<div style={{ marginTop: 16 }}>
									<span style={{ fontSize: 13, color: 'rgba(255,255,255,0.4)', cursor: 'pointer', textDecoration: 'underline' }} onClick={() => { setLoginMode('telegram'); setError(''); }}>Войти через Telegram</span>
								</div>
							</form>
						)}
						{error && <div className="login-error">{error}</div>}
					</div>
				</div>
			) : (

			<div className="page">
				{/* Header */}
				<header className="header">
					<div className="header-inner">
						<h1>📋 Kaspi Заказы</h1>
						<div className="header-right">
							{lastUpdate && (
								<span className="update-info">
									Обновлено: {lastUpdate.toLocaleTimeString('ru-RU')}
								</span>
							)}
							<button className="btn btn-ghost" style={{ color: '#fff', borderColor: 'rgba(255,255,255,0.3)' }} onClick={loadOrders}>
								🔄 Обновить
							</button>
							<a
								href={`/api/orders/collect?key=${encodeURIComponent(apiKey)}`}
								className="btn btn-ghost"
								style={{ color: '#fff', borderColor: 'rgba(255,255,255,0.3)' }}
							>
								📦 Собрать PDF
							</a>
							<button className="btn btn-ghost" style={{ color: '#fff', borderColor: 'rgba(255,255,255,0.3)' }} onClick={() => { sessionStorage.removeItem('web_api_key'); setAuthOk(false); setApiKey(''); setKeyInput(''); }}>
								🚪 Выход
							</button>
						</div>
					</div>
				</header>

				{/* Summary cards */}
				<div className="summary">
					<div className="summary-card">
						<div className="num" style={{ color: '#dc2626' }}>{counts.active}</div>
						<div className="lbl">Активных</div>
					</div>
					<div className="summary-card">
						<div className="num" style={{ color: '#059669' }}>{counts.pdfReady}</div>
						<div className="lbl">PDF готово</div>
					</div>
					<div className="summary-card">
						<div className="num" style={{ color: '#2563eb' }}>{counts.sent}</div>
						<div className="lbl">Отправлено</div>
					</div>
					<div className="summary-card">
						<div className="num" style={{ color: '#6b7280' }}>{counts.total}</div>
						<div className="lbl">Всего</div>
					</div>
				</div>

				<div className="content">
					{/* Toolbar */}
					<div className="toolbar">
						<span className="toolbar-label">Статус:</span>
						<select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
							<option value="ACTIVE">Активные</option>
							<option value="ALL">Все</option>
							<option value="ASSEMBLE">Упаковка</option>
							<option value="KASPI_DELIVERY">Kaspi Доставка</option>
							<option value="PDF_READY">PDF готов</option>
							<option value="SENT">Отправлен</option>
							<option value="CANCELLED">Отменён</option>
							<option value="COMPLETED">Завершён</option>
						</select>
						<span className="toolbar-label">Дата:</span>
						<input type="date" value={dateFilter} onChange={(e) => setDateFilter(e.target.value)} />
						<span className="toolbar-label">—</span>
						<input type="date" value={dateFilterEnd} onChange={(e) => setDateFilterEnd(e.target.value)} />
						{(dateFilter || dateFilterEnd) && (
							<button className="btn btn-ghost btn-sm" onClick={() => { setDateFilter(''); setDateFilterEnd(''); }}>✕</button>
						)}
						<button className="btn btn-ghost btn-sm" onClick={() => setShowForm(!showForm)}>
							{showForm ? '✕ Скрыть' : '＋ Добавить'}
						</button>
						<span className="count-info">
							<span className="count-orders">{filtered.length} из {orders.length}</span>
							<span className="count-sum">💰 {filteredSum.toLocaleString('ru-RU')} ₸</span>
						</span>
					</div>

					{/* Add form (collapsible) */}
					{showForm && (
						<form className="add-panel" onSubmit={addOrder}>
							<h3>Добавить заказ</h3>
							<div className="add-grid">
								<input placeholder="Order ID" value={form.order_id} onChange={(e) => setForm({ ...form, order_id: e.target.value })} required />
								<input placeholder="Код заказа" value={form.order_code} onChange={(e) => setForm({ ...form, order_code: e.target.value })} required />
								<input placeholder="Клиент" value={form.customer} onChange={(e) => setForm({ ...form, customer: e.target.value })} />
								<input placeholder="Сумма" type="number" min="0" value={form.total_price} onChange={(e) => setForm({ ...form, total_price: e.target.value })} />
							</div>
							<div className="add-actions">
								<button type="submit" className="btn btn-primary">Добавить</button>
								<button type="button" className="btn btn-ghost" onClick={() => setShowForm(false)}>Отмена</button>
							</div>
						</form>
					)}

					{/* Period stats */}
					{periodStats && (
						<div className="stats-panel">
							<div className="stats-header">
								<h3>📊 Статистика за период</h3>
								<div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
									<select value={statsDays} onChange={(e) => { const d = Number(e.target.value); setStatsDays(d); if (d !== -1) { setStatsFrom(''); setStatsTo(''); loadStats(d); } }}>
										<option value={0}>День (сеанс 15:00)</option>
										<option value={7}>7 дней</option>
										<option value={14}>14 дней</option>
										<option value={30}>30 дней</option>
										<option value={90}>90 дней</option>
										<option value={-1}>Интервал ↓</option>
									</select>
									{statsDays === -1 && (
										<>
											<input type="date" value={statsFrom} onChange={(e) => setStatsFrom(e.target.value)} style={{ padding: '5px 8px', border: '1px solid #d1d5db', borderRadius: 8, fontSize: 13 }} />
											<span style={{ color: '#9ca3af' }}>—</span>
											<input type="date" value={statsTo} onChange={(e) => setStatsTo(e.target.value)} style={{ padding: '5px 8px', border: '1px solid #d1d5db', borderRadius: 8, fontSize: 13 }} />
										</>
									)}
								</div>
							</div>
							<div className="stats-grid">
								<div className="stat-item">
									<div className="stat-val" style={{ color: '#dc2626' }}>{periodStats.orders}</div>
									<div className="stat-lbl">Заказов</div>
								</div>
								<div className="stat-item">
									<div className="stat-val" style={{ color: '#059669' }}>{periodStats.total_sum.toLocaleString('ru-RU')} ₸</div>
									<div className="stat-lbl">Общая сумма</div>
								</div>
								<div className="stat-item">
									<div className="stat-val" style={{ color: '#7c3aed' }}>{periodStats.avg_check.toLocaleString('ru-RU')} ₸</div>
									<div className="stat-lbl">Средний чек</div>
								</div>
								<div className="stat-item">
									<div className="stat-val" style={{ color: '#2563eb' }}>{periodStats.pdf_count}</div>
									<div className="stat-lbl">PDF создано</div>
								</div>
								<div className="stat-item">
									<div className="stat-val" style={{ color: '#0891b2' }}>{periodStats.sent_count}</div>
									<div className="stat-lbl">Отправлено</div>
								</div>
							</div>
						</div>
					)}

					{/* Error */}
					{error && <div className="error-bar">⚠️ {error}</div>}

					{/* Loading */}
					{loading ? (
						<div className="loader"><div className="spinner" /></div>
					) : filtered.length === 0 ? (
						<div className="table-wrap">
							<div className="empty-state">
								<div className="empty-icon">📭</div>
								<div>Заказов не найдено</div>
							</div>
						</div>
					) : (
						<>
							{/* Desktop table */}
							<div className="table-wrap">
								<table className="orders-table">
									<thead>
										<tr>
											<th>Код заказа</th>
											<th>Статус</th>
											<th>Kaspi</th>
											<th>Клиент</th>
											<th>Сумма</th>
											<th>PDF</th>
											<th>Дата</th>
											<th></th>
										</tr>
									</thead>
									<tbody>
										{filtered.map((order) => (
											<tr key={order.order_id}>
												<td><span className="order-code">{order.order_code}</span></td>
												<td><StatusBadge status={order.status} /></td>
												<td style={{ color: '#6b7280', fontSize: 12 }}>{order.kaspi_status || '—'}</td>
												<td><span className="customer-name">{order.customer || '—'}</span></td>
												<td><span className="price">{formatPrice(order.total_price)}</span></td>
												<td>
													{order.pdf_path ? (
														<a
															href={`/api/orders/pdf?order_id=${encodeURIComponent(order.order_id)}&key=${encodeURIComponent(apiKey)}`}
															target="_blank"
															rel="noopener noreferrer"
															className="btn btn-success btn-sm"
														>
															📥 Скачать
														</a>
													) : (
														<span style={{ color: '#d1d5db' }}>—</span>
													)}
												</td>
												<td style={{ color: '#6b7280', fontSize: 12 }}>{formatDate(order.created_at)}</td>
												<td>
													<button className="btn btn-danger btn-sm" onClick={() => removeOrder(order.order_id)}>
														🗑
													</button>
												</td>
											</tr>
										))}
									</tbody>
								</table>
							</div>

							{/* Mobile cards */}
							<div className="order-cards">
								{filtered.map((order) => (
									<div key={order.order_id} className="order-card">
										<div className="card-header">
											<span className="order-code">{order.order_code}</span>
											<StatusBadge status={order.status} />
										</div>
										<div className="card-body">
											{order.kaspi_status && (
												<div className="card-row">
													<span className="label">Kaspi</span>
													<span>{order.kaspi_status}</span>
												</div>
											)}
											<div className="card-row">
												<span className="label">Клиент</span>
												<span>{order.customer || '—'}</span>
											</div>
											<div className="card-row">
												<span className="label">Сумма</span>
												<span className="price">{formatPrice(order.total_price)}</span>
											</div>
											<div className="card-row">
												<span className="label">Дата</span>
												<span>{formatDate(order.created_at)}</span>
											</div>
										</div>
										<div className="card-footer">
											{order.pdf_path ? (
												<a
													href={`/api/orders/pdf?order_id=${encodeURIComponent(order.order_id)}&key=${encodeURIComponent(apiKey)}`}
													target="_blank"
													rel="noopener noreferrer"
													className="btn btn-success btn-sm"
												>
													📥 Скачать PDF
												</a>
											) : (
												<span className="btn btn-ghost btn-sm" style={{ color: '#d1d5db', cursor: 'default' }}>PDF нет</span>
											)}
											<button className="btn btn-danger btn-sm" onClick={() => removeOrder(order.order_id)}>
												🗑 Удалить
											</button>
										</div>
									</div>
								))}
							</div>
						</>
					)}
				</div>
			</div>

			)}
		</>
	);
}

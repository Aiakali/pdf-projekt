import { NextResponse } from 'next/server';

export function middleware(request) {
  // Auth routes are public (login via Telegram code)
  const { pathname } = new URL(request.url);
  if (pathname.startsWith('/api/auth')) {
    return NextResponse.next();
  }

  const apiKey = process.env.WEB_API_KEY;
  if (!apiKey) {
    return NextResponse.json({ ok: false, error: 'Server misconfigured' }, { status: 500 });
  }

  // Check x-api-key header, Authorization: Bearer, or ?key= query param (for download links)
  const headerKey = request.headers.get('x-api-key');
  const authHeader = request.headers.get('authorization');
  const bearerKey = authHeader?.startsWith('Bearer ') ? authHeader.slice(7) : null;
  const url = new URL(request.url);
  const queryKey = url.searchParams.get('key');

  if (headerKey === apiKey || bearerKey === apiKey || queryKey === apiKey) {
    return NextResponse.next();
  }

  return NextResponse.json({ ok: false, error: 'Unauthorized' }, { status: 401 });
}

export const config = {
  matcher: ['/api/:path*'],
};

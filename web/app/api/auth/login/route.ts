import { NextResponse } from "next/server";
import { backendFetch, COOKIE_OPTS, ACCESS_COOKIE, REFRESH_COOKIE } from "@/lib/backend";

export async function POST(request: Request) {
  const body = await request.json();

  const backendRes = await backendFetch("/auth/login", {
    method: "POST",
    body: JSON.stringify(body),
  });
  const payload = await backendRes.json();

  if (!backendRes.ok || !payload.status) {
    return NextResponse.json(payload, { status: backendRes.status || 401 });
  }

  const { tokens, user } = payload.data;
  const response = NextResponse.json({ status: true, data: { user } });
  response.cookies.set(ACCESS_COOKIE, tokens.access_token, { ...COOKIE_OPTS, maxAge: tokens.expires_in });
  response.cookies.set(REFRESH_COOKIE, tokens.refresh_token, { ...COOKIE_OPTS, maxAge: 60 * 60 * 24 * 30 });
  return response;
}

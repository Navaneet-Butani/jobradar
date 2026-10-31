import { NextResponse } from "next/server";
import { backendFetch, COOKIE_OPTS, ACCESS_COOKIE, REFRESH_COOKIE } from "@/lib/backend";

/**
 * Claim an invite. Unauthenticated by necessity — the person doing this has no
 * account yet, and the token in the URL is the whole credential.
 *
 * Modelled on /api/auth/login: the backend hands back a token pair, and this is
 * the only place that can turn it into httpOnly cookies, so the new user lands
 * signed in instead of being bounced to a login form for the password they
 * typed ten seconds ago.
 */
export async function POST(request: Request, ctx: RouteContext<"/api/invite/[token]">) {
  const { token } = await ctx.params;

  const backendRes = await backendFetch(`/invites/accept/${encodeURIComponent(token)}`, {
    method: "POST",
    body: JSON.stringify(await request.json()),
  });
  const payload = await backendRes.json();

  if (!backendRes.ok || !payload.status) {
    return NextResponse.json(payload, { status: backendRes.status || 400 });
  }

  const { tokens, user } = payload.data;
  const response = NextResponse.json({ status: true, data: { user } });
  response.cookies.set(ACCESS_COOKIE, tokens.access_token, { ...COOKIE_OPTS, maxAge: tokens.expires_in });
  response.cookies.set(REFRESH_COOKIE, tokens.refresh_token, { ...COOKIE_OPTS, maxAge: 60 * 60 * 24 * 30 });
  return response;
}

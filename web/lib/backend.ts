import { cookies } from "next/headers";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000";

export const ACCESS_COOKIE = "jr_at";
export const REFRESH_COOKIE = "jr_rt";

const COOKIE_OPTS = {
  httpOnly: true,
  // COOKIE_SECURE=false lets a production build run over plain http on a LAN.
  secure: process.env.COOKIE_SECURE ? process.env.COOKIE_SECURE === "true" : process.env.NODE_ENV === "production",
  sameSite: "lax" as const,
  path: "/",
};

export type Tokens = {
  access_token: string;
  refresh_token: string;
  expires_in: number;
};

/**
 * Plain call to the FastAPI backend — no auth, no cookies.
 * A FormData body sets its own multipart Content-Type (with the boundary),
 * so we must not pin it to JSON — that's how the resume upload gets through.
 */
export async function backendFetch(path: string, init: RequestInit = {}) {
  const isFormData = init.body instanceof FormData;
  return fetch(`${API_BASE_URL}/api/v1${path}`, {
    ...init,
    headers: { ...(isFormData ? {} : { "Content-Type": "application/json" }), ...init.headers },
    cache: "no-store",
  });
}

async function refreshTokens(refreshToken: string): Promise<Tokens | null> {
  const res = await backendFetch("/auth/refresh", {
    method: "POST",
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!res.ok) return null;
  const body = await res.json();
  if (!body.status) return null;
  return body.data as Tokens;
}

/**
 * Authenticated call to the backend using the caller's session cookies.
 * Retries once with a refreshed access token on 401 — the refresh, if it
 * happens, is returned as `refreshed` so the Route Handler can re-set
 * cookies on its NextResponse (a Server Component can't set cookies, so
 * mid-render refresh there just falls through to the next request).
 */
export async function authedFetch(
  path: string,
  init: RequestInit = {}
): Promise<{ res: Response; refreshed: Tokens | null }> {
  const jar = await cookies();
  const accessToken = jar.get(ACCESS_COOKIE)?.value;
  const refreshToken = jar.get(REFRESH_COOKIE)?.value;

  const unauthenticated = () => ({
    res: new Response(JSON.stringify({ detail: "Not authenticated" }), { status: 401 }),
    refreshed: null,
  });

  /** Refresh, then replay the call with the new token. */
  const refreshAndRetry = async (): Promise<{ res: Response; refreshed: Tokens | null } | null> => {
    if (!refreshToken) return null;
    const refreshed = await refreshTokens(refreshToken);
    if (!refreshed) return null;
    const res = await backendFetch(path, {
      ...init,
      headers: { ...init.headers, Authorization: `Bearer ${refreshed.access_token}` },
    });
    return { res, refreshed };
  };

  // The access cookie's maxAge matches the 30-minute token lifetime, so it
  // disappears on expiry rather than expiring in place. Without this branch a
  // session that sat idle for 30 minutes fails every call with "Not
  // authenticated" while a perfectly good refresh token is still in the jar.
  if (!accessToken) {
    return (await refreshAndRetry()) ?? unauthenticated();
  }

  const res = await backendFetch(path, {
    ...init,
    headers: { ...init.headers, Authorization: `Bearer ${accessToken}` },
  });

  if (res.status !== 401) return { res, refreshed: null };

  return (await refreshAndRetry()) ?? { res, refreshed: null };
}

/** Apply a refreshed token pair to a NextResponse's outgoing cookies. */
export function applyRefreshedTokens(
  response: { cookies: { set: (name: string, value: string, opts: Record<string, unknown>) => void } },
  tokens: Tokens
) {
  response.cookies.set(ACCESS_COOKIE, tokens.access_token, { ...COOKIE_OPTS, maxAge: tokens.expires_in });
  response.cookies.set(REFRESH_COOKIE, tokens.refresh_token, { ...COOKIE_OPTS, maxAge: 60 * 60 * 24 * 30 });
}

export { COOKIE_OPTS };

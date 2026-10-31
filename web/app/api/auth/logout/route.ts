import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { backendFetch, ACCESS_COOKIE, REFRESH_COOKIE } from "@/lib/backend";

function decodeSessionId(accessToken: string): string | null {
  try {
    const payload = JSON.parse(Buffer.from(accessToken.split(".")[1], "base64url").toString("utf-8"));
    return payload.session_id ?? null;
  } catch {
    return null;
  }
}

export async function POST() {
  const jar = await cookies();
  const accessToken = jar.get(ACCESS_COOKIE)?.value;
  const sessionId = accessToken ? decodeSessionId(accessToken) : null;

  if (accessToken && sessionId) {
    await backendFetch(`/auth/logout?session_id=${encodeURIComponent(sessionId)}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${accessToken}` },
    }).catch(() => null);
  }

  const response = NextResponse.json({ status: true });
  response.cookies.delete(ACCESS_COOKIE);
  response.cookies.delete(REFRESH_COOKIE);
  return response;
}

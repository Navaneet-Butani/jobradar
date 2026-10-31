import { NextResponse } from "next/server";
import { authedFetch, applyRefreshedTokens } from "@/lib/backend";

/** Create an invite. Admin-only — the backend enforces that, not this. */
export async function POST(request: Request) {
  const { res, refreshed } = await authedFetch("/invites", {
    method: "POST",
    body: JSON.stringify(await request.json()),
  });
  const body = await res.json();
  const response = NextResponse.json(body, { status: res.status });
  if (refreshed) applyRefreshedTokens(response, refreshed);
  return response;
}

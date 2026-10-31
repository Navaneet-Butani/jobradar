import { NextResponse } from "next/server";
import { authedFetch, applyRefreshedTokens } from "@/lib/backend";

export async function POST(request: Request) {
  const body = await request.text();
  const { res, refreshed } = await authedFetch("/packet", { method: "POST", body });
  const payload = await res.json();
  const response = NextResponse.json(payload, { status: res.status });
  if (refreshed) applyRefreshedTokens(response, refreshed);
  return response;
}

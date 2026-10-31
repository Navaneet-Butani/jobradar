import { NextResponse } from "next/server";
import { authedFetch, applyRefreshedTokens } from "@/lib/backend";

export async function GET(request: Request) {
  const { search } = new URL(request.url);
  const { res, refreshed } = await authedFetch(`/matches${search}`);
  const body = await res.json();
  const response = NextResponse.json(body, { status: res.status });
  if (refreshed) applyRefreshedTokens(response, refreshed);
  return response;
}

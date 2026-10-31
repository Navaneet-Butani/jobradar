import { NextResponse } from "next/server";
import { authedFetch, applyRefreshedTokens } from "@/lib/backend";

export async function GET() {
  const { res, refreshed } = await authedFetch("/profiles");
  const body = await res.json();
  const response = NextResponse.json(body, { status: res.status });
  if (refreshed) applyRefreshedTokens(response, refreshed);
  return response;
}

/** Create the first (or an additional) matching profile. */
export async function POST(request: Request) {
  const { res, refreshed } = await authedFetch("/profiles", {
    method: "POST",
    body: JSON.stringify(await request.json()),
  });
  const body = await res.json();
  const response = NextResponse.json(body, { status: res.status });
  if (refreshed) applyRefreshedTokens(response, refreshed);
  return response;
}

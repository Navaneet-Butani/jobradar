import { NextResponse } from "next/server";
import { authedFetch, applyRefreshedTokens } from "@/lib/backend";

export async function GET() {
  const { res, refreshed } = await authedFetch("/scraping/roles");
  const body = await res.json();
  const response = NextResponse.json(body, { status: res.status });
  if (refreshed) applyRefreshedTokens(response, refreshed);
  return response;
}

export async function PUT(request: Request) {
  const { res, refreshed } = await authedFetch("/scraping/roles", {
    method: "PUT",
    body: JSON.stringify(await request.json()),
  });
  const body = await res.json();
  const response = NextResponse.json(body, { status: res.status });
  if (refreshed) applyRefreshedTokens(response, refreshed);
  return response;
}

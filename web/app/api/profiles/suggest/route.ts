import { NextResponse } from "next/server";
import { authedFetch, applyRefreshedTokens } from "@/lib/backend";

/** Profile fields suggested from the uploaded resume. Nothing is saved. */
export async function POST() {
  const { res, refreshed } = await authedFetch("/profiles/suggest-from-resume", { method: "POST" });
  const body = await res.json();
  const response = NextResponse.json(body, { status: res.status });
  if (refreshed) applyRefreshedTokens(response, refreshed);
  return response;
}

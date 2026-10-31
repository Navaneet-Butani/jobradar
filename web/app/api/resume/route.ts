import { NextResponse } from "next/server";
import { authedFetch, applyRefreshedTokens } from "@/lib/backend";

export async function POST(request: Request) {
  const form = await request.formData();
  const { res, refreshed } = await authedFetch("/resume", { method: "POST", body: form });
  const payload = await res.json();
  const response = NextResponse.json(payload, { status: res.status });
  if (refreshed) applyRefreshedTokens(response, refreshed);
  return response;
}

export async function DELETE() {
  const { res, refreshed } = await authedFetch("/resume", { method: "DELETE" });
  // The backend answers 204 with no body on a successful delete.
  const payload = res.status === 204 ? { status: true, data: null } : await res.json();
  const response = NextResponse.json(payload, { status: res.status === 204 ? 200 : res.status });
  if (refreshed) applyRefreshedTokens(response, refreshed);
  return response;
}

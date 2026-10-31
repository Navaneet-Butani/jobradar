import { NextResponse } from "next/server";
import { authedFetch, applyRefreshedTokens } from "@/lib/backend";

/** Full application update — used for editing the contact name/email by hand. */
export async function PUT(request: Request, ctx: RouteContext<"/api/applications/[id]">) {
  const { id } = await ctx.params;
  const body = await request.text();
  const { res, refreshed } = await authedFetch(`/applications/${id}`, { method: "PUT", body });
  const payload = await res.json();
  const response = NextResponse.json(payload, { status: res.status });
  if (refreshed) applyRefreshedTokens(response, refreshed);
  return response;
}

import { NextResponse } from "next/server";
import { authedFetch, applyRefreshedTokens } from "@/lib/backend";

async function forward(path: string, method: string, body?: BodyInit) {
  const { res, refreshed } = await authedFetch(path, { method, body });
  const payload = await res.json();
  const response = NextResponse.json(payload, { status: res.status });
  if (refreshed) applyRefreshedTokens(response, refreshed);
  return response;
}

/** Activate or deactivate an account. */
export async function PATCH(request: Request, ctx: RouteContext<"/api/invites/[id]">) {
  const { id } = await ctx.params;
  return forward(`/invites/${id}`, "PATCH", await request.text());
}

/** Withdraw an invite nobody has accepted. */
export async function DELETE(_request: Request, ctx: RouteContext<"/api/invites/[id]">) {
  const { id } = await ctx.params;
  return forward(`/invites/${id}`, "DELETE");
}

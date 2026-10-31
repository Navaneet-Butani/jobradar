import { NextResponse } from "next/server";
import { authedFetch, applyRefreshedTokens } from "@/lib/backend";

export async function PATCH(request: Request, ctx: RouteContext<"/api/matches/[jobId]/state">) {
  const { jobId } = await ctx.params;
  const body = await request.text();
  const { res, refreshed } = await authedFetch(`/matches/${jobId}/state`, { method: "PATCH", body });
  const payload = await res.json();
  const response = NextResponse.json(payload, { status: res.status });
  if (refreshed) applyRefreshedTokens(response, refreshed);
  return response;
}

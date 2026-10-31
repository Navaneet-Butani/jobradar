import { NextResponse } from "next/server";
import { authedFetch, applyRefreshedTokens } from "@/lib/backend";

export async function POST(request: Request, { params }: RouteContext<"/api/applications/[id]/draft-followup">) {
  const { id } = await params;
  const { res, refreshed } = await authedFetch(`/applications/${id}/draft-followup`, { method: "POST" });
  const body = await res.json();
  const response = NextResponse.json(body, { status: res.status });
  if (refreshed) applyRefreshedTokens(response, refreshed);
  return response;
}

import { NextResponse } from "next/server";
import { authedFetch, applyRefreshedTokens } from "@/lib/backend";

export async function PATCH(request: Request, { params }: RouteContext<"/api/applications/[id]/status">) {
  const { id } = await params;
  const body = await request.text();
  const { res, refreshed } = await authedFetch(`/applications/${id}/status`, {
    method: "PATCH",
    body,
  });
  const responseBody = await res.json();
  const response = NextResponse.json(responseBody, { status: res.status });
  if (refreshed) applyRefreshedTokens(response, refreshed);
  return response;
}

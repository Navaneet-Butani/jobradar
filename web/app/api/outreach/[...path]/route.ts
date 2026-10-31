import { NextResponse } from "next/server";
import { authedFetch, applyRefreshedTokens } from "@/lib/backend";

/**
 * Catch-all proxy for /api/outreach/* — the outreach surface is a dozen
 * endpoints that all do the same thing (forward with the httpOnly cookie,
 * re-set refreshed tokens), so one handler beats a dozen near-identical files.
 * Multipart (CSV import) and JSON bodies both pass through untouched.
 */
async function proxy(request: Request, path: string[], method: string) {
  const target = `/outreach/${path.join("/")}`;
  const contentType = request.headers.get("content-type") ?? "";

  let body: BodyInit | undefined;
  if (method !== "GET" && method !== "DELETE") {
    body = contentType.includes("multipart/form-data")
      ? await request.formData()
      : await request.text();
  }

  const { res, refreshed } = await authedFetch(target, { method, body });
  const payload = res.status === 204 ? { status: true, data: null } : await res.json();
  const response = NextResponse.json(payload, { status: res.status === 204 ? 200 : res.status });
  if (refreshed) applyRefreshedTokens(response, refreshed);
  return response;
}

export async function GET(request: Request, ctx: RouteContext<"/api/outreach/[...path]">) {
  const { path } = await ctx.params;
  return proxy(request, path, "GET");
}

export async function POST(request: Request, ctx: RouteContext<"/api/outreach/[...path]">) {
  const { path } = await ctx.params;
  return proxy(request, path, "POST");
}

export async function PATCH(request: Request, ctx: RouteContext<"/api/outreach/[...path]">) {
  const { path } = await ctx.params;
  return proxy(request, path, "PATCH");
}

export async function DELETE(request: Request, ctx: RouteContext<"/api/outreach/[...path]">) {
  const { path } = await ctx.params;
  return proxy(request, path, "DELETE");
}

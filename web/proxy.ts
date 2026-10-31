import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Kept as a literal (not imported from lib/backend) so this file, which
// runs on the Edge runtime, doesn't pull in the Node-only cookies()/fetch
// helper module just for one constant.
const ACCESS_COOKIE = "jr_at";
const REFRESH_COOKIE = "jr_rt";

// /invite/<token> is public by necessity: the person opening it has no
// account yet, and the token is the only credential they hold.
const PUBLIC_PATHS = ["/login", "/invite"];

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const isPublic = PUBLIC_PATHS.some((p) => pathname.startsWith(p));
  const hasAccess = Boolean(request.cookies.get(ACCESS_COOKIE)?.value);
  const hasRefresh = Boolean(request.cookies.get(REFRESH_COOKIE)?.value);

  // Deliberately asymmetric, and the asymmetry is the whole point.
  //
  // Letting a request through needs only jr_rt: jr_at is written with maxAge
  // equal to the 30-minute token lifetime, so the browser stops sending it the
  // moment it expires while jr_rt stays valid for 30 days. Requiring jr_at
  // here sent people to /login on the first navigation after half an hour,
  // never giving authedFetch the chance to trade the refresh token for a new
  // pair.
  //
  // Bouncing someone OFF /login needs jr_at specifically. Middleware cannot
  // tell a live refresh token from a dead one, so trusting jr_rt for this
  // branch deadlocks anyone holding a stale cookie: /login sends them to /,
  // session.ts gets a 401 and redirects back to /login, forever
  // (ERR_TOO_MANY_REDIRECTS). With jr_at required, a stale jr_rt simply lands
  // on the login page and signing in replaces both cookies.
  if (!hasAccess && !hasRefresh && !isPublic) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }

  if (hasAccess && pathname === "/login") {
    const url = request.nextUrl.clone();
    url.pathname = "/";
    url.search = "";
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};

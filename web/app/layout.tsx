import type { Metadata } from "next";
import { IBM_Plex_Sans, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";

const plexSans = IBM_Plex_Sans({
  variable: "--font-plex-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

const plexMono = IBM_Plex_Mono({
  variable: "--font-plex-mono",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

export const metadata: Metadata = {
  title: "JobRadar",
  description: "Self-hosted job radar for Indian IT and software roles: ranked, explained, tracked.",
};

/*
  Applies the saved theme before first paint. Without it a user who picked dark
  sees a white flash on every navigation, because the preference lives in
  localStorage and the server cannot know it. Deliberately inline and blocking:
  it is three lines, and deferring it is the whole problem.
*/
const THEME_INIT = `
try {
  var m = localStorage.getItem('jr-theme');
  if (m === 'dark' || m === 'light') document.documentElement.setAttribute('data-theme', m);
} catch (e) {}
`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // suppressHydrationWarning is scoped to this one element on purpose: the
    // script above intentionally sets data-theme before React hydrates, so the
    // server HTML and the client DOM are expected to differ here and nowhere
    // else. Children still hydrate under the normal checks.
    <html
      lang="en"
      className={`${plexSans.variable} ${plexMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT }} />
      </head>
      <body className="min-h-full flex flex-col bg-bg text-ink">{children}</body>
    </html>
  );
}

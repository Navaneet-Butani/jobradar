"use client";

import { useState } from "react";

/*
  Logos come from the source boards (Hirist S3, Instahyre media, Himalayas CDN),
  so a fair number of URLs are dead or hotlink-blocked. A broken <img> renders as
  a torn-page glyph and looks like the app is broken, so any load failure falls
  back to initials on a tinted square — which is also what a company with no logo
  at all gets. Same shape either way, so a list of cards never jitters.

  Deliberately a plain <img>, not next/image: these are hundreds of third-party
  hosts, and remote patterns would have to allow effectively everything.
*/

const SIZES = {
  sm: "h-8 w-8 text-[11px] rounded-md",
  md: "h-10 w-10 text-xs rounded-lg",
  lg: "h-14 w-14 text-base rounded-xl",
} as const;

function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}

export function CompanyLogo({
  name,
  src,
  size = "md",
}: {
  name: string;
  src?: string | null;
  size?: keyof typeof SIZES;
}) {
  const [failed, setFailed] = useState(false);
  const shape = SIZES[size];

  if (!src || failed) {
    return (
      <span
        aria-hidden="true"
        className={`${shape} flex shrink-0 items-center justify-center border border-border bg-bg-sunken font-semibold text-ink-faint`}
      >
        {initials(name)}
      </span>
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt=""
      loading="lazy"
      onError={() => setFailed(true)}
      /* White tile, in both themes, on purpose. Most of these logos are dark
         artwork on a transparent background — on the dark surface they render
         as an empty box. */
      className={`${shape} shrink-0 border border-border bg-white object-contain p-0.5`}
    />
  );
}

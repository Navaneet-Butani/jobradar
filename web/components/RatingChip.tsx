import { Star } from "@phosphor-icons/react/dist/ssr";

/*
  Employer rating as published by the source (AmbitionBox, via Hirist). Shown
  with its review count because 4.8 from 3 reviews and 3.9 from 4,000 are not
  the same claim, and named by source rather than presented as ours.
*/
export function RatingChip({
  rating,
  count,
  source,
  href,
}: {
  rating: number | null | undefined;
  count?: number | null;
  source?: string | null;
  href?: string | null;
}) {
  if (rating == null) return null;

  const label = `${rating.toFixed(1)} out of 5${count ? ` from ${count.toLocaleString("en-IN")} reviews` : ""}${
    source ? ` on ${source}` : ""
  }`;

  const body = (
    <>
      <Star size={12} weight="fill" className="text-score-moderate" />
      <span className="font-mono font-semibold tabular-nums">{rating.toFixed(1)}</span>
      {count ? <span className="text-ink-faint">({count.toLocaleString("en-IN")})</span> : null}
    </>
  );

  const className =
    "inline-flex items-center gap-1 rounded-full bg-bg-sunken px-2 py-0.5 text-[11px] text-ink-soft";

  if (href) {
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        title={label}
        className={`${className} hover:text-accent`}
      >
        {body}
      </a>
    );
  }

  return (
    <span title={label} className={className}>
      {body}
    </span>
  );
}

const LABELS: Record<string, string> = {
  skill_overlap: "Skill overlap",
  title_match: "Title match",
  experience_fit: "Experience fit",
  location_fit: "Location fit",
  freshness: "Freshness",
  salary: "Salary",
  source_quality: "Source quality",
  llm_relevance: "AI relevance",
};

function label(key: string): string {
  return LABELS[key] ?? key.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

export function ScoreBreakdown({ score, reasons }: { score: number; reasons: Record<string, number> }) {
  const entries = Object.entries(reasons).sort((a, b) => b[1] - a[1]);
  const maxAbs = Math.max(1, ...entries.map(([, v]) => Math.abs(v)));

  return (
    <section className="rounded-xl border border-border bg-bg-elevated p-5">
      <div className="flex items-baseline justify-between">
        <h2 className="font-display text-base font-semibold text-ink">Why this score</h2>
        <span className="font-mono text-lg font-semibold tabular-nums text-accent">{Math.round(score)}</span>
      </div>
      <ul className="mt-4 flex flex-col gap-2.5">
        {entries.map(([key, value]) => {
          const negative = value < 0;
          const width = `${Math.min(100, (Math.abs(value) / maxAbs) * 100)}%`;
          return (
            <li key={key} className="flex items-center gap-3 text-sm">
              <span className="w-32 shrink-0 text-ink-soft">{label(key)}</span>
              <span className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-bg-sunken">
                <span
                  className="absolute inset-y-0 left-0 rounded-full"
                  style={{ width, background: negative ? "var(--danger)" : "var(--accent)" }}
                />
              </span>
              <span className="w-10 shrink-0 text-right font-mono tabular-nums text-ink-faint">{Math.round(value)}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

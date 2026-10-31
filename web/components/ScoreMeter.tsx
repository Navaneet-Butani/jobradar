const RADIUS = 20;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

function band(score: number): { color: string; bg: string; label: string } {
  if (score >= 70) return { color: "var(--score-strong)", bg: "var(--score-strong-bg)", label: "Strong" };
  if (score >= 50) return { color: "var(--score-moderate)", bg: "var(--score-moderate-bg)", label: "Moderate" };
  return { color: "var(--score-weak)", bg: "var(--score-weak-bg)", label: "Weak" };
}

/**
 * The signature "signal strength" readout: a radar-sweep arc rather than a plain badge.
 *
 * The band is printed as a word as well as a colour. Strong/moderate/weak here
 * are green/amber/red, which is the one palette a red-green colourblind reader
 * cannot separate, so colour alone would carry the meaning for nobody.
 */
export function ScoreMeter({ score }: { score: number }) {
  const { color, bg, label } = band(score);
  const filled = (Math.max(0, Math.min(100, score)) / 100) * CIRCUMFERENCE;

  return (
    <div
      className="flex shrink-0 flex-col items-center gap-1"
      title={`${label} match, ${Math.round(score)} out of 100`}
    >
      <div className="relative h-14 w-14">
        <svg viewBox="0 0 44 44" className="h-14 w-14 -rotate-90" aria-hidden>
          <circle cx="22" cy="22" r={RADIUS} fill={bg} stroke="var(--border)" strokeWidth="2.5" />
          <circle
            cx="22"
            cy="22"
            r={RADIUS}
            fill="none"
            stroke={color}
            strokeWidth="3"
            strokeLinecap="round"
            strokeDasharray={`${filled} ${CIRCUMFERENCE}`}
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="font-mono text-sm font-semibold tabular-nums text-ink">{Math.round(score)}</span>
        </div>
      </div>
      <span className="text-[11px] font-medium" style={{ color }}>
        {label}
      </span>
      <span className="sr-only">Match score {Math.round(score)} out of 100</span>
    </div>
  );
}

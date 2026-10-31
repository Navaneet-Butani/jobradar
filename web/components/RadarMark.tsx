export function RadarMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" aria-hidden>
      <circle cx="12" cy="12" r="2.25" fill="currentColor" />
      <circle cx="12" cy="12" r="7" stroke="currentColor" strokeWidth="1.6" strokeOpacity="0.55" />
      <circle cx="12" cy="12" r="11" stroke="currentColor" strokeWidth="1.6" strokeOpacity="0.25" />
    </svg>
  );
}

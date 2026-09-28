import { count } from "@/lib/admin-format";

/**
 * Matches per 10-point Opportunity Score bucket: one series, so one hue and
 * no legend. Columns grow from the baseline with a rounded data end; only the
 * tallest carries its value, the rest is in the tooltip and the table below.
 */
export function ScoreHistogram({ buckets }: { buckets: { bucket: number; matches: number }[] }) {
  const byBucket = new Map(buckets.map((b) => [b.bucket, b.matches]));
  const values = Array.from({ length: 10 }, (_, i) => ({ bucket: i * 10, matches: byBucket.get(i * 10) ?? 0 }));
  const max = Math.max(...values.map((v) => v.matches), 0);
  const peak = values.findIndex((v) => v.matches === max);
  return (
    <figure className="rounded-xl bg-card p-4 ring-1 ring-foreground/10">
      <figcaption className="sr-only">Cantidad de matches por rango de Opportunity Score</figcaption>
      <div className="flex h-40 items-end gap-0.5 border-b border-border" role="list">
        {values.map((v, i) => (
          <div
            key={v.bucket}
            role="listitem"
            aria-label={`${v.bucket}–${v.bucket === 90 ? 100 : v.bucket + 9}: ${v.matches} matches`}
            title={`Score ${v.bucket}–${v.bucket === 90 ? 100 : v.bucket + 9}: ${count(v.matches)} matches`}
            className="group relative flex h-full flex-1 cursor-default items-end justify-center"
          >
            {max > 0 && i === peak ? (
              <span
                className="absolute text-xs font-medium text-foreground tabular-nums"
                style={{ bottom: `calc(${(v.matches / max) * 100}% + 4px)` }}
              >
                {count(v.matches)}
              </span>
            ) : null}
            <div
              className="w-full max-w-6 rounded-t-[4px] bg-sky-600 group-hover:bg-sky-700"
              style={{ height: max ? `${(v.matches / max) * 100}%` : 0, minHeight: v.matches ? 2 : 0 }}
            />
          </div>
        ))}
      </div>
      <div className="mt-1 flex gap-0.5 text-[11px] text-muted-foreground tabular-nums">
        {values.map((v) => (
          <span key={v.bucket} className="flex-1 text-center">
            {v.bucket}
          </span>
        ))}
      </div>
    </figure>
  );
}

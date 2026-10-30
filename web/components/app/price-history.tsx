import { dayMonth, money } from "@/lib/format";
import { cn } from "@/lib/utils";

export type PricePoint = { at: string; price: number; currency: string };

/**
 * §31: "Bajó USD 500 desde que la vimos por primera vez", or "Subió…". The
 * listing page shows it when PAR-03's summary (lib/price-track.ts) has
 * nothing to say, so the two never repeat each other.
 */
export function PriceChange({ points }: { points: PricePoint[] }) {
  const first = points[0];
  const last = points[points.length - 1];
  const change = last.price - first.price;
  if (change === 0) return null;
  return (
    <p className="text-[15px]">
      <span className={change < 0 ? "mark" : undefined}>
        {change < 0 ? "Bajó" : "Subió"} {money(Math.abs(change), last.currency)}
      </span>{" "}
      desde que la vimos por primera vez.
    </p>
  );
}

/** §31: every published price we saw, oldest first, in plain words — no chart. */
export function PriceHistory({ points }: { points: PricePoint[] }) {
  return (
    <ul className="mt-2" aria-label="Histórico de precios">
      {points.map((p, i) => (
        <li key={`${p.at}-${i}`} className="flex justify-between gap-3 border-b py-2 text-[15px] last:border-b-0">
          <span className="text-muted-foreground">{i === points.length - 1 ? `${dayMonth(p.at)}, ahora` : dayMonth(p.at)}</span>
          <span className={cn("type-figure", i === points.length - 1 ? "text-base" : "font-semibold text-muted-foreground")}>
            {money(p.price, p.currency)}
          </span>
        </li>
      ))}
    </ul>
  );
}

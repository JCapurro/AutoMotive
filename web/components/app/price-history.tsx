"use client";

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { dayMonth, money } from "@/lib/format";

export type PricePoint = { at: string; price: number; currency: string };

/** §31: the published price over time (one point per observed change). */
export function PriceHistory({ points }: { points: PricePoint[] }) {
  const currency = points[points.length - 1]?.currency ?? "USD";
  const data = points.map((p) => ({ ...p, label: dayMonth(p.at) }));
  return (
    <div className="space-y-3">
      <div className="h-44 w-full" aria-hidden>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" />
            <XAxis dataKey="label" tickLine={false} axisLine={false} fontSize={12} />
            <YAxis
              width={64}
              tickLine={false}
              axisLine={false}
              fontSize={12}
              domain={["auto", "auto"]}
              tickFormatter={(v: number) => money(v, "").trim()}
            />
            <Tooltip
              formatter={(v) => [money(Number(v), currency), "Precio publicado"]}
              labelFormatter={(label) => String(label)}
            />
            <Line type="stepAfter" dataKey="price" stroke="var(--foreground)" strokeWidth={2} dot={{ r: 3 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <ul className="space-y-1 text-sm tabular-nums" aria-label="Histórico de precios">
        {points.map((p, i) => (
          <li key={`${p.at}-${i}`} className="flex justify-between gap-3">
            <span className="text-muted-foreground">{dayMonth(p.at)}</span>
            <span>{money(p.price, p.currency)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

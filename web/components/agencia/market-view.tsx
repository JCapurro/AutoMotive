"use client";

import { ExternalLink } from "lucide-react";
import { useMemo, useState } from "react";

import { cn } from "@/lib/utils";

/** One comparable listing of dealer_market_listings(), already in display form. */
export type MarketListing = {
  id: number;
  title: string;
  year: number | null;
  km: number | null;
  /** Part of the reference the car's price is compared against (dealer_market_listings.in_ref). */
  inRef: boolean;
  priceUsd: number;
  priceShown: string;
  source: string;
  seller: "private" | "dealer" | null;
  location: string | null;
  days: number;
  url: string | null;
};

export type OwnCar = { name: string; year: number | null; priceUsd: number | null; priceShown: string };

const nf = new Intl.NumberFormat("es-AR");
const usd = (v: number) => `USD ${nf.format(Math.round(v))}`;

function quantile(sorted: number[], q: number): number {
  const pos = (sorted.length - 1) * q;
  const lo = Math.floor(pos);
  const hi = Math.ceil(pos);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
}

function Chips<T extends string>({ label, value, options, onChange }: { label: string; value: T; options: { id: T; label: string }[]; onChange: (v: T) => void }) {
  return (
    <div role="group" aria-label={label} className="inline-flex rounded-lg border p-0.5">
      {options.map((o) => (
        <button
          key={o.id}
          type="button"
          aria-pressed={value === o.id}
          onClick={() => onChange(o.id)}
          className={cn("h-7 rounded-md px-2.5 text-xs font-medium whitespace-nowrap", value === o.id ? "bg-foreground text-background" : "text-muted-foreground hover:bg-muted")}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** The market of one car: where its price sits, the spread, and every comparable listing with the car placed among them. */
export function MarketView({ listings, own, refLabel = null }: { listings: MarketListing[]; own: OwnCar; refLabel?: string | null }) {
  // With a reference by km the page opens on it: those are the cars the price is compared against.
  const [group, setGroup] = useState<"ref" | "all">(refLabel ? "ref" : "all");
  const [years, setYears] = useState<"all" | "same">("all");
  const [seller, setSeller] = useState<"all" | "private" | "dealer">("all");

  const rows = useMemo(
    () => listings.filter((l) => (group === "all" || l.inRef) && (years === "all" || l.year === own.year) && (seller === "all" || l.seller === seller)),
    [listings, group, years, seller, own.year],
  );
  const prices = useMemo(() => rows.map((r) => r.priceUsd), [rows]);
  const enough = prices.length >= 5;
  const median = prices.length ? quantile(prices, 0.5) : null;
  const p25 = prices.length ? quantile(prices, 0.25) : null;
  const p75 = prices.length ? quantile(prices, 0.75) : null;
  const cheaper = own.priceUsd == null ? null : prices.filter((p) => p < own.priceUsd!).length;
  const pct = own.priceUsd != null && median ? Math.round((own.priceUsd / median - 1) * 100) : null;

  // Histogram: 12 bins over the spread, widened to hold the car's own price.
  const bins = useMemo(() => {
    if (!prices.length) return null;
    const lo = Math.min(prices[0], own.priceUsd ?? prices[0]);
    const hi = Math.max(prices[prices.length - 1], own.priceUsd ?? 0);
    const width = (hi - lo) / 12 || 1;
    const at = (v: number) => Math.min(11, Math.floor((v - lo) / width));
    const counts = Array.from({ length: 12 }, () => 0);
    for (const p of prices) counts[at(p)]++;
    return { lo, hi, counts, max: Math.max(...counts), own: own.priceUsd == null ? -1 : at(own.priceUsd) };
  }, [prices, own.priceUsd]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        {refLabel ? (
          <Chips label="Comparables" value={group} onChange={setGroup} options={[{ id: "ref", label: refLabel }, { id: "all", label: "Todo el modelo" }]} />
        ) : null}
        <Chips label="Años" value={years} onChange={setYears} options={[{ id: "all", label: "Año ±1" }, { id: "same", label: own.year ? `Solo ${own.year}` : "Mismo año" }]} />
        <Chips label="Vendedor" value={seller} onChange={setSeller} options={[{ id: "all", label: "Todos" }, { id: "private", label: "Particulares" }, { id: "dealer", label: "Agencias" }]} />
        <span className="text-sm text-muted-foreground">{nf.format(rows.length)} {rows.length === 1 ? "aviso" : "avisos"}</span>
      </div>

      {rows.length === 0 ? (
        <p className="rounded-lg bg-muted p-8 text-center text-sm text-muted-foreground">No hay avisos con ese filtro.</p>
      ) : (
        <>
          <dl className="grid grid-cols-2 gap-x-6 border-y py-3 sm:grid-cols-4">
            <Stat label="Tu precio" tone={pct != null && enough && Math.abs(pct) > 10 ? "warn" : undefined}>
              {own.priceUsd != null ? usd(own.priceUsd) : "Sin precio"}
            </Stat>
            <Stat label="Mediana del mercado">{median != null ? usd(median) : "—"}</Stat>
            <Stat label="La mitad pide entre">{p25 != null && p75 != null ? `${nf.format(Math.round(p25))} y ${nf.format(Math.round(p75))}` : "—"}</Stat>
            <Stat label="Más baratos que el tuyo">{cheaper == null ? "—" : `${nf.format(cheaper)} de ${nf.format(rows.length)}`}</Stat>
          </dl>
          {pct != null && enough ? (
            <p className="text-[15px]">
              {Math.abs(pct) <= 10 ? "Estás en precio: " : pct > 0 ? `Estás ${Math.abs(pct)} % arriba: ` : `Estás ${Math.abs(pct)} % abajo: `}
              {cheaper === 0 ? "sos el más barato de esta lista." : cheaper === rows.length ? "sos el más caro de esta lista." : `hay ${nf.format(cheaper!)} más baratos y ${nf.format(rows.length - cheaper!)} más caros o iguales.`}
            </p>
          ) : !enough ? (
            <p className="text-[15px] text-muted-foreground">Con menos de 5 avisos no alcanza para sacar una referencia de precio.</p>
          ) : null}

          {bins ? (
            <figure aria-label="Cuántos avisos hay en cada tramo de precio">
              <div className="flex h-28 items-end gap-1">
                {bins.counts.map((c, i) => (
                  <div key={i} className="flex h-full flex-1 flex-col justify-end">
                    {i === bins.own ? <span className="mb-1 text-center text-[11px] font-semibold text-warn">Vos</span> : null}
                    <div
                      className={cn("rounded-t-sm", i === bins.own ? "bg-warn" : "bg-foreground/20")}
                      style={{ height: `${Math.max(c ? 6 : i === bins.own ? 3 : 0, (c / bins.max) * 80)}%` }}
                      title={`${c} ${c === 1 ? "aviso" : "avisos"}`}
                    />
                  </div>
                ))}
              </div>
              <figcaption className="mt-1 flex justify-between border-t pt-1 text-[11px] text-muted-foreground">
                <span>{usd(bins.lo)}</span>
                <span>Cantidad de avisos por tramo de precio</span>
                <span>{usd(bins.hi)}</span>
              </figcaption>
            </figure>
          ) : null}

          <div className="-mx-4 overflow-x-auto px-4">
            <table className="w-full min-w-[760px] border-t-2 border-foreground text-sm" data-testid="market-table">
              <thead>
                <tr className="text-left text-[11px] tracking-wide text-muted-foreground uppercase">
                  <th className="py-2 pr-3 font-medium">Aviso</th>
                  <th className="px-3 py-2 text-right font-medium">Año</th>
                  <th className="px-3 py-2 text-right font-medium">Km</th>
                  <th className="px-3 py-2 text-right font-medium">Precio</th>
                  <th className="px-3 py-2 font-medium">Dónde</th>
                  <th className="px-3 py-2 font-medium">Vende</th>
                  <th className="px-3 py-2 text-right font-medium">Publicado hace</th>
                  <th className="py-2 pl-3" />
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <Rows key={r.id} showOwn={own.priceUsd != null && cheaper === i} own={own}>
                    <tr className="border-t">
                      <td className="max-w-72 truncate py-2 pr-3">{r.title}</td>
                      <td className="px-3 py-2 text-right">{r.year ?? "—"}</td>
                      <td className="px-3 py-2 text-right whitespace-nowrap">{r.km != null ? nf.format(r.km) : "—"}</td>
                      <td className="type-figure px-3 py-2 text-right whitespace-nowrap">{r.priceShown}</td>
                      <td className="px-3 py-2">
                        {r.source}
                        {r.location ? <span className="block max-w-40 truncate text-xs text-muted-foreground">{r.location}</span> : null}
                      </td>
                      <td className="px-3 py-2 text-muted-foreground">{r.seller === "dealer" ? "Agencia" : r.seller === "private" ? "Particular" : "—"}</td>
                      <td className="px-3 py-2 text-right whitespace-nowrap text-muted-foreground">{r.days <= 0 ? "hoy" : `${r.days} ${r.days === 1 ? "día" : "días"}`}</td>
                      <td className="py-2 pl-3 text-right">
                        {r.url ? (
                          <a href={r.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-xs font-medium whitespace-nowrap underline-offset-2 hover:underline">
                            Ver aviso <ExternalLink className="size-3" aria-hidden />
                          </a>
                        ) : null}
                      </td>
                    </tr>
                  </Rows>
                ))}
                {own.priceUsd != null && cheaper === rows.length ? <OwnRow own={own} /> : null}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

function Rows({ showOwn, own, children }: { showOwn: boolean; own: OwnCar; children: React.ReactNode }) {
  return (
    <>
      {showOwn ? <OwnRow own={own} /> : null}
      {children}
    </>
  );
}

function OwnRow({ own }: { own: OwnCar }) {
  return (
    <tr className="border-t bg-warn-soft font-semibold" data-testid="market-own">
      <td className="py-2 pr-3 pl-2">Tu auto · {own.name}</td>
      <td className="px-3 py-2 text-right">{own.year ?? "—"}</td>
      <td className="px-3 py-2" />
      <td className="type-figure px-3 py-2 text-right whitespace-nowrap">{own.priceShown}</td>
      <td className="px-3 py-2" colSpan={4}>Acá queda tu precio en la lista</td>
    </tr>
  );
}

function Stat({ label, tone, children }: { label: string; tone?: "warn"; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className={cn("type-figure text-xl leading-tight", tone === "warn" && "text-warn")}>{children}</dd>
    </div>
  );
}

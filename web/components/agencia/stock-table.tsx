"use client";

import { AlertTriangle, Check, ImageOff } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { toast } from "sonner";

import { confirmStock, setItemStatus } from "@/app/agencia/actions";
import { askSaleSource } from "@/components/agencia/sale-question";
import { Button } from "@/components/ui/button";
import type { StockFacts } from "@/lib/dealer-insights";
import { cn } from "@/lib/utils";

/** One car of the stock screen (the page builds it from dealer_stock_insights). */
export type StockRow = {
  itemId: number;
  photo: string | null;
  name: string;
  detail: string;
  price: string;
  priceUsd: string | null;
  market: string;
  priceCheck: boolean;
  demand: string;
  days: string;
  status: string;
  origin: string;
  sending: string;
  sends: boolean;
  review: boolean;
  facts: StockFacts;
};

const STATUSES = [
  { id: "available", label: "Disponible" },
  { id: "reserved", label: "Reservado" },
  { id: "sold", label: "Vendido" },
] as const;

const TONE: Record<StockFacts["tone"], string> = {
  fair: "bg-ok/10 text-ok",
  below: "bg-warn-soft text-warn",
  above: "bg-warn-soft text-warn",
  check: "bg-warn text-background",
  none: "bg-muted text-muted-foreground",
};

/** The stock ordered by what to do with each car, first match wins. */
const GROUPS = [
  { id: "check", title: "Revisá el precio", hint: "Lejos del mercado: puede ser un error de carga o una oportunidad de ajustar." },
  { id: "wanted", title: "Los están buscando", hint: "Hay gente en tu zona con una búsqueda que los acepta." },
  { id: "slow", title: "Tardan más que su modelo", hint: "Llevan en stock bastante más de lo que suele tardar ese modelo en venderse." },
  { id: "rest", title: "El resto", hint: "" },
] as const;

function groupOf(r: StockRow): (typeof GROUPS)[number]["id"] {
  if (r.review || r.facts.tone === "check" || r.facts.tone === "above") return "check";
  if (r.facts.demandRank > 0) return "wanted";
  if (r.facts.slow) return "slow";
  return "rest";
}

const usd = (v: number | null) => (v == null ? "—" : `USD ${new Intl.NumberFormat("es-AR").format(Math.round(v))}`);
const days = (n: number) => `${n} ${n === 1 ? "día" : "días"}`;

/** The car's cover photo, or a neutral placeholder: so a row without photos is noticed. */
export function StockPhoto({ url, className }: { url: string | null; className?: string }) {
  return url ? (
    // eslint-disable-next-line @next/next/no-img-element -- the agency's uploads or its portal listing's photo, any host
    <img src={url} alt="" loading="lazy" className={cn("shrink-0 rounded-md bg-muted object-cover", className)} />
  ) : (
    <div className={cn("flex shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground", className)} title="Sin fotos">
      <ImageOff className="size-4" aria-hidden />
    </div>
  );
}

/** The status as buttons on the car itself. */
function StatusButtons({ row, pending, onChange }: { row: StockRow; pending: boolean; onChange: (id: number, s: string) => void }) {
  return (
    <div className="flex items-center gap-2">
      <div role="group" aria-label={`Estado de ${row.name}`} className="inline-flex rounded-lg border p-0.5">
        {STATUSES.map((s) => {
          const on = row.status === s.id;
          return (
            <button
              key={s.id}
              type="button"
              aria-pressed={on}
              disabled={pending || on}
              onClick={() => onChange(row.itemId, s.id)}
              className={cn(
                "h-7 rounded-md px-2 text-xs font-medium whitespace-nowrap transition-colors",
                on ? "bg-foreground text-background" : "text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
            >
              {s.label}
            </button>
          );
        })}
      </div>
      {row.origin !== "sync" && row.status !== "archived" ? (
        <button type="button" disabled={pending} onClick={() => onChange(row.itemId, "archived")} className="text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline">
          Sacar
        </button>
      ) : null}
    </div>
  );
}

/** «27 días» and, under it, «Lo habitual: 25 días» (what the model usually takes to sell): in words, never a bare ratio. */
function DaysCell({ f }: { f: StockFacts }) {
  if (f.daysInStock == null) return <span className="text-muted-foreground">Sin fecha</span>;
  return (
    <>
      <p className={cn("font-semibold whitespace-nowrap", f.slow && "text-warn")}>{f.daysInStock <= 0 ? "Entró hoy" : days(f.daysInStock)}</p>
      {f.modelDays != null ? <p className="text-xs whitespace-nowrap text-muted-foreground">Lo habitual: {days(f.modelDays)}</p> : null}
    </>
  );
}

function Summary({ rows }: { rows: StockRow[] }) {
  const check = rows.filter((r) => r.facts.tone === "check" || r.facts.tone === "above").length;
  const items = [
    { n: check, label: "para revisar el precio", tone: check ? "text-warn" : "" },
    { n: rows.filter((r) => r.facts.tone === "fair").length, label: "en precio", tone: "text-ok" },
    { n: rows.filter((r) => r.facts.demandRank > 0).length, label: "con gente buscándolos en tu zona", tone: "" },
    { n: rows.filter((r) => r.facts.slow).length, label: "tardan más que su modelo", tone: "" },
  ];
  return (
    <dl className="grid grid-cols-2 gap-x-6 border-y py-3 sm:grid-cols-4">
      {items.map((i) => (
        <div key={i.label}>
          <dd className={cn("type-figure text-2xl leading-tight", i.tone)}>{i.n}</dd>
          <dt className="text-xs text-muted-foreground">{i.label}</dt>
        </div>
      ))}
    </dl>
  );
}

export function StockTable({ rows, unconfirmed }: { rows: StockRow[]; unconfirmed: number }) {
  const router = useRouter();
  const [pending, run] = useTransition();
  const [busy, setBusy] = useState<number | "all" | null>(null);

  function changeStatus(itemId: number, status: string) {
    setBusy(itemId);
    run(async () => {
      const result = await setItemStatus(itemId, status).catch(() => ({ error: "No pudimos guardar. Probá de nuevo." }));
      if (result.error) toast.error(result.error);
      else if (status === "sold") askSaleSource({ itemId }, () => router.refresh());
      else toast.success(status === "available" ? "Listo: vuelve a estar disponible" : "Listo: ya no se envía a compradores");
      setBusy(null);
      router.refresh();
    });
  }

  function confirmAll() {
    setBusy("all");
    run(async () => {
      const result = await confirmStock(null).catch(() => ({ error: "No pudimos guardar. Probá de nuevo.", count: 0 }));
      if (result.error) toast.error(result.error);
      else toast.success(result.count ? `Confirmamos ${result.count} ${result.count === 1 ? "auto" : "autos"}` : "No había autos para confirmar");
      setBusy(null);
      router.refresh();
    });
  }

  if (rows.length === 0) return <p className="rounded-lg bg-muted p-8 text-center text-sm text-muted-foreground">No hay autos en esta lista.</p>;

  return (
    <div className="space-y-4">
      <Summary rows={rows} />
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={confirmAll} disabled={pending} className="h-9" data-testid="confirm-stock">
          {busy === "all" ? "Confirmando…" : "Confirmar stock"}
        </Button>
        <p className="text-sm text-muted-foreground">
          {unconfirmed > 0
            ? `${unconfirmed} ${unconfirmed === 1 ? "auto sin confirmar" : "autos sin confirmar"}: confirmá que siguen en venta.`
            : "Confirmá cada semana que tus autos siguen en venta."}
        </p>
      </div>
      <div className="space-y-8" data-testid="stock-table">
        {GROUPS.map((g) => {
          const list = rows.filter((r) => groupOf(r) === g.id).sort((x, y) => y.facts.demandRank - x.facts.demandRank);
          if (!list.length) return null;
          return (
            <section key={g.id}>
              <h2 className="type-heading text-lg">{g.title} <span className="font-normal text-muted-foreground">· {list.length}</span></h2>
              {g.hint ? <p className="text-[13px] text-muted-foreground">{g.hint}</p> : null}
              <div className="-mx-4 mt-2 overflow-x-auto px-4">
                <table className="w-full min-w-[820px] border-t-2 border-foreground text-sm">
                  <thead>
                    <tr className="text-left text-[11px] tracking-wide text-muted-foreground uppercase">
                      <th className="py-2 pr-3 font-medium">Auto</th>
                      <th className="px-3 py-2 text-right font-medium">Tu precio</th>
                      <th className="px-3 py-2 font-medium">Contra el mercado</th>
                      <th className="px-3 py-2 font-medium whitespace-nowrap">Lo buscan</th>
                      <th className="px-3 py-2 font-medium">En stock</th>
                      <th className="py-2 pl-3 font-medium">Estado</th>
                    </tr>
                  </thead>
                  <tbody>
                    {list.map((r) => (
                      <tr key={r.itemId} className="border-t align-middle" data-testid="stock-row">
                        <td className="py-2.5 pr-3">
                          <div className="flex items-center gap-2.5">
                            <StockPhoto url={r.photo} className="h-9 w-12" />
                            <div className="min-w-0">
                              <Link href={`/agencia/stock/${r.itemId}`} className="font-semibold hover:underline">{r.name}</Link>
                              <p className="max-w-44 truncate text-xs text-muted-foreground">
                                {r.review ? (
                                  <Link href={`/agencia/stock/${r.itemId}`} className="font-semibold text-warn underline underline-offset-2">¿Es este aviso tuyo? Revisalo</Link>
                                ) : r.detail}
                              </p>
                            </div>
                          </div>
                        </td>
                        <td className="type-figure px-3 py-2.5 text-right whitespace-nowrap">{r.price}</td>
                        <td className="px-3 py-2.5" data-testid="stock-market">
                          <span className={cn("inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-semibold whitespace-nowrap", TONE[r.facts.tone])}>
                            {r.facts.tone === "check" ? <AlertTriangle className="size-3.5" aria-hidden /> : null}
                            {r.facts.priceLabel}
                          </span>
                          <p className="mt-0.5 text-xs whitespace-nowrap text-muted-foreground">
                            {r.facts.enough ? <>Mediana {usd(r.facts.medianUsd)} · </> : null}
                            {r.facts.n > 0 ? (
                              <Link href={`/agencia/stock/${r.itemId}/mercado`} className="font-medium text-foreground underline underline-offset-2">Ver el mercado</Link>
                            ) : null}
                          </p>
                        </td>
                        <td className="px-3 py-2.5 whitespace-nowrap" data-testid="stock-demand">
                          {r.facts.demandApproved ? (
                            <>
                              <p className="font-semibold">{r.facts.demand.zone} en tu zona</p>
                              <p className="text-xs text-muted-foreground">{r.facts.demand.fits} en todo el país</p>
                            </>
                          ) : <span className="text-xs text-muted-foreground">Cuando aprobemos tu agencia</span>}
                        </td>
                        <td className="px-3 py-2.5"><DaysCell f={r.facts} /></td>
                        <td className="py-2.5 pl-3">
                          <StatusButtons row={r} pending={pending} onChange={changeStatus} />
                          <p className={cn("mt-1 flex max-w-52 items-start gap-1 text-xs leading-snug", r.sends ? "font-medium text-ok" : "text-muted-foreground")} data-testid="stock-sending">
                            {r.sends && busy !== r.itemId ? <Check className="size-3.5" aria-hidden /> : null}
                            {busy === r.itemId ? "Guardando…" : r.sending}
                          </p>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}

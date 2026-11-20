"use client";

import { AlertTriangle, Camera, Check, ImageOff, Loader2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState, useTransition } from "react";
import { toast } from "sonner";

import { addItemPhotos, confirmStock, setItemStatus } from "@/app/agencia/actions";
import { BUCKET, shrink } from "@/components/agencia/photo-uploader";
import { askSaleSource } from "@/components/agencia/sale-question";
import { Button } from "@/components/ui/button";
import { type StockFacts, SUGGESTED_PRICE_NOTE } from "@/lib/dealer-insights";
import { createClient } from "@/lib/supabase/client";
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
  /** «Sugerido USD 18.500»: from published prices (the car's page says why). */
  suggested?: string | null;
  /** Private: only the owning agency's page passes it. */
  margin?: string | null;
  marginNegative?: boolean;
  /** «Más km que los parecidos»: the first possible explanation of a price off the market (the car's page has them all). */
  why?: string | null;
  /** «Sin km: comparación floja»: the reference could not take the km (dealer-insights.ts marketBasisNote). */
  basisNote?: string | null;
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

/**
 * A car without photos: instead of an empty picture, a button that opens the
 * phone's camera roll or the file picker, uploads to the agency's folder and
 * saves the photos on the car. Same shrink and bucket as the car's form.
 */
function AddPhoto({ itemId, dealerId, name, className, onDone }: { itemId: number; dealerId: number; name: string; className?: string; onDone: () => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);

  async function upload(files: FileList | null) {
    const picked = Array.from(files ?? []).filter((f) => f.type.startsWith("image/")).slice(0, 10);
    if (!picked.length) return;
    setBusy(true);
    const supabase = createClient();
    const urls: string[] = [];
    for (const file of picked) {
      try {
        const path = `${dealerId}/${crypto.randomUUID()}.jpg`;
        const { error } = await supabase.storage.from(BUCKET).upload(path, await shrink(file), { contentType: "image/jpeg", cacheControl: "31536000" });
        if (error) throw error;
        urls.push(supabase.storage.from(BUCKET).getPublicUrl(path).data.publicUrl);
      } catch {
        // counted below
      }
    }
    const saved = urls.length ? await addItemPhotos(itemId, urls) : { error: "No pudimos subir la foto. Probá de nuevo con JPG o PNG." };
    setBusy(false);
    if (input.current) input.current.value = "";
    if (saved.error) return void toast.error(saved.error);
    toast.success(urls.length === 1 ? "Foto cargada" : `${urls.length} fotos cargadas`);
    onDone();
  }

  return (
    <>
      <button
        type="button"
        disabled={busy}
        onClick={() => input.current?.click()}
        aria-label={`Subir fotos del ${name}`}
        title="Subir fotos"
        data-testid="stock-add-photo"
        className={cn(
          "flex shrink-0 flex-col items-center justify-center gap-0.5 rounded-md border border-dashed border-foreground/40 text-[10px] leading-none font-semibold text-foreground hover:bg-muted disabled:opacity-60",
          className,
        )}
      >
        {busy ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <Camera className="size-4" aria-hidden />}
        {busy ? "Subiendo" : "Subir foto"}
      </button>
      <input ref={input} type="file" accept="image/*" multiple hidden onChange={(e) => upload(e.target.files)} />
    </>
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

export function StockTable({ rows, unconfirmed, dealerId }: { rows: StockRow[]; unconfirmed: number; dealerId: number }) {
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
                            {/* A synced car takes its photos from its portal listing: nothing to upload here. */}
                            {r.photo || r.origin === "sync" ? <StockPhoto url={r.photo} className="h-9 w-12" />
                              : <AddPhoto itemId={r.itemId} dealerId={dealerId} name={r.name} className="h-11 w-14" onDone={() => router.refresh()} />}
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
                        <td className="px-3 py-2.5 text-right whitespace-nowrap">
                          <span className="type-figure">{r.price}</span>
                          {r.margin ? (
                            <p className={cn("text-xs", r.marginNegative ? "text-warn" : "text-muted-foreground")} data-testid="stock-margin">{r.margin}</p>
                          ) : null}
                        </td>
                        <td className="px-3 py-2.5" data-testid="stock-market">
                          <span className={cn("inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-semibold whitespace-nowrap", TONE[r.facts.tone])}>
                            {r.facts.tone === "check" ? <AlertTriangle className="size-3.5" aria-hidden /> : null}
                            {r.facts.priceLabel}
                          </span>
                          <p className="mt-0.5 text-xs whitespace-nowrap text-muted-foreground">
                            {r.suggested ? <span data-testid="stock-suggested" title={SUGGESTED_PRICE_NOTE}>{r.suggested} · </span>
                              : r.facts.enough ? <>Mediana {usd(r.facts.medianUsd)} · </> : null}
                            {r.facts.n > 0 ? (
                              <Link href={`/agencia/stock/${r.itemId}/mercado`} className="font-medium text-foreground underline underline-offset-2">Ver el mercado</Link>
                            ) : null}
                          </p>
                          {r.basisNote ? (
                            <p className="mt-0.5 text-xs whitespace-nowrap" data-testid="stock-basis">
                              <Link href={`/agencia/stock/${r.itemId}`} className="font-medium text-warn hover:underline">{r.basisNote}</Link>
                            </p>
                          ) : null}
                          {r.why ? (
                            <p className="mt-0.5 text-xs whitespace-nowrap" data-testid="stock-why">
                              <Link href={`/agencia/stock/${r.itemId}#por-que`} className="hover:underline" title="Ver por qué">
                                <span className="text-muted-foreground">Por qué: </span>{r.why}
                              </Link>
                            </p>
                          ) : null}
                        </td>
                        <td className="px-3 py-2.5 whitespace-nowrap" data-testid="stock-demand">
                          {r.facts.demandApproved ? (
                            <>
                              <p className="font-semibold">{r.facts.demand.zone} en tu zona</p>
                              <p className="text-xs text-muted-foreground">{r.facts.demand.fits} en todo el país</p>
                            </>
                          ) : <span className="text-xs text-muted-foreground">Con el plan Pro activo</span>}
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

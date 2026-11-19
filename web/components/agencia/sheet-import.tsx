"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState, useTransition } from "react";

import { importSheet, previewSheet, type SheetPreview } from "@/app/agencia/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import type { Catalog } from "@/lib/catalog";
import { type ColumnMap, FIELD_LABEL, ISSUE_TEXT, SHEET_FIELDS, type SheetField, type SheetRow } from "@/lib/dealer-sheet";
import { cn } from "@/lib/utils";

type Fix = { make: string; model: string };

const BLOCKING = new Set(["no_make", "no_model", "not_in_catalog", "no_year", "no_price"]);
const CATALOG_ISSUES = new Set(["no_make", "no_model", "not_in_catalog"]);

/**
 * /agencia/stock/planilla (spec §5): upload, preview with each row's problems
 * and the column picker, then «Cargar N autos». The preview writes nothing;
 * the server reads the file again to load it.
 */
export function SheetImport({ catalog }: { catalog: Catalog }) {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<SheetPreview | null>(null);
  const [map, setMap] = useState<ColumnMap | null>(null);
  const [skip, setSkip] = useState<Set<number>>(new Set());
  const [fixes, setFixes] = useState<Record<number, Fix>>({});
  const [priceOk, setPriceOk] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState<number | null>(null);
  const [pending, run] = useTransition();

  function form(extra: Record<string, string> = {}): FormData | null {
    if (!file) return null;
    const data = new FormData();
    data.set("file", file);
    if (map) data.set("map", JSON.stringify(map));
    const overrides = Object.fromEntries(Object.entries(fixes).filter(([, f]) => f.make && f.model));
    if (Object.keys(overrides).length) data.set("overrides", JSON.stringify(overrides));
    for (const [k, v] of Object.entries(extra)) data.set(k, v);
    return data;
  }

  function load(next: File | null, resetMap: boolean) {
    setError(null);
    setLoaded(null);
    if (!next) return;
    run(async () => {
      const data = new FormData();
      data.set("file", next);
      if (!resetMap && map) data.set("map", JSON.stringify(map));
      const overrides = Object.fromEntries(Object.entries(fixes).filter(([, f]) => f.make && f.model));
      if (!resetMap && Object.keys(overrides).length) data.set("overrides", JSON.stringify(overrides));
      const result = await previewSheet(data).catch(() => ({ error: "No pudimos leer la planilla. Probá de nuevo." }) as SheetPreview);
      if (result.error) {
        setError(result.error);
        setPreview(null);
        return;
      }
      setPreview(result);
      setMap(result.map ?? {});
      if (resetMap) {
        setSkip(new Set());
        setFixes({});
        setPriceOk(!result.priceGuessed);
      }
    });
  }

  const rows = useMemo(() => preview?.rows ?? [], [preview]);
  const accepted = rows.filter((r) => !skip.has(r.line) && !r.issues.some((i) => BLOCKING.has(i)));

  function submit() {
    const data = form({ skip: JSON.stringify([...skip]) });
    if (!data) return;
    setError(null);
    run(async () => {
      const result = await importSheet(data).catch(() => ({ error: "No pudimos cargar la planilla. Probá de nuevo." }) as { error?: string; count?: number });
      if (result.error) setError(result.error);
      else {
        setLoaded(result.count ?? accepted.length);
        setPreview(null);
        setFile(null);
        router.refresh();
      }
    });
  }

  const priceCol = map?.price;
  const priceSample = priceCol !== undefined ? (preview?.sample ?? []).map((r) => r[priceCol]).filter(Boolean).slice(0, 3) : [];

  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <Input
          type="file"
          accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          aria-label="Planilla"
          className="h-auto max-w-md py-2"
          onChange={(e) => {
            const next = e.target.files?.[0] ?? null;
            setFile(next);
            setPreview(null);
            load(next, true);
          }}
        />
        <p className="text-xs text-muted-foreground">CSV o XLSX, hasta 1 MB y 500 autos. Las columnas de patente o dominio no se leen ni se guardan.</p>
      </div>

      {loaded !== null ? <p role="status" className="rounded-lg bg-muted p-4 text-[15px] font-semibold">Listo: cargamos {loaded} {loaded === 1 ? "auto" : "autos"}. En unos minutos aparecen con sus precios contra el mercado.</p> : null}
      {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}
      {pending && !preview ? <p className="text-sm text-muted-foreground">Leyendo la planilla…</p> : null}

      {preview && map ? (
        <>
          <section className="space-y-2">
            <h2 className="text-[17px] font-bold">Columnas</h2>
            <div className="grid gap-2 sm:grid-cols-3">
              {SHEET_FIELDS.map((field) => (
                <label key={field} className="flex items-center justify-between gap-2 text-sm">
                  <span>{FIELD_LABEL[field]}</span>
                  <NativeSelect
                    size="sm"
                    value={map[field] ?? ""}
                    onChange={(e) => {
                      const next = { ...map };
                      if (e.target.value === "") delete next[field as SheetField];
                      else next[field as SheetField] = Number(e.target.value);
                      setMap(next);
                      if (field === "price") setPriceOk(false);
                    }}
                  >
                    <option value="">No está</option>
                    {(preview.headers ?? []).map((h, i) => <option key={i} value={i}>{h || `Columna ${i + 1} (sin título)`}</option>)}
                  </NativeSelect>
                </label>
              ))}
            </div>
            <Button variant="outline" size="sm" disabled={pending} onClick={() => load(file, false)}>Actualizar vista previa</Button>
          </section>

          {priceCol !== undefined && (preview.priceGuessed || !priceOk) ? (
            <label className="flex items-start gap-2.5 rounded-lg bg-warn-soft p-4 text-[15px]" data-testid="price-column-check">
              <input type="checkbox" className="mt-1 size-4 shrink-0 accent-foreground" checked={priceOk} onChange={(e) => setPriceOk(e.target.checked)} />
              <span>
                <b className="font-semibold">¿Esta columna es el precio de venta?</b> «{preview.headers?.[priceCol] || `Columna ${priceCol + 1}`}»
                {priceSample.length ? <>, por ejemplo {priceSample.join(", ")}</> : null}. Si es lo que pagaste, elegí otra columna.
              </span>
            </label>
          ) : null}

          <section className="space-y-2">
            <h2 className="text-[17px] font-bold">{rows.length} {rows.length === 1 ? "fila" : "filas"}</h2>
            <ul className="border-t-2 border-foreground" data-testid="sheet-rows">
              {rows.map((r) => (
                <SheetRowView
                  key={r.line}
                  row={r}
                  catalog={catalog}
                  skipped={skip.has(r.line)}
                  fix={fixes[r.line]}
                  onSkip={(value) => {
                    const next = new Set(skip);
                    if (value) next.add(r.line);
                    else next.delete(r.line);
                    setSkip(next);
                  }}
                  onFix={(f) => setFixes({ ...fixes, [r.line]: f })}
                />
              ))}
            </ul>
            {Object.values(fixes).some((f) => f.make && f.model) ? (
              <Button variant="outline" size="sm" disabled={pending} onClick={() => load(file, false)}>Aplicar correcciones</Button>
            ) : null}
          </section>

          <div className="flex flex-wrap items-center gap-3">
            <Button className="h-11 text-[15px]" disabled={pending || accepted.length === 0 || (priceCol !== undefined && !priceOk) || priceCol === undefined} onClick={submit} data-testid="sheet-import">
              {pending ? "Cargando…" : `Cargar ${accepted.length} ${accepted.length === 1 ? "auto" : "autos"}`}
            </Button>
            {priceCol === undefined ? <p className="text-sm text-destructive">Elegí la columna del precio de venta.</p> : null}
          </div>
        </>
      ) : null}
    </div>
  );
}

function SheetRowView({ row, catalog, skipped, fix, onSkip, onFix }: {
  row: SheetRow; catalog: Catalog; skipped: boolean; fix: Fix | undefined; onSkip: (v: boolean) => void; onFix: (f: Fix) => void;
}) {
  const blocked = row.issues.some((i) => BLOCKING.has(i));
  const needsCatalog = row.issues.some((i) => CATALOG_ISSUES.has(i));
  const v = row.values;
  const make = catalog.find((m) => m.make === (fix?.make ?? ""));
  return (
    <li className={cn("grid gap-x-4 gap-y-1 border-b py-2.5 text-sm sm:grid-cols-[3rem_minmax(0,1fr)_auto]", (blocked || skipped) && "text-muted-foreground")}>
      <span className="text-xs text-muted-foreground">Fila {row.line}</span>
      <div className="min-w-0">
        <p className="font-semibold">{[v.make, v.model, v.trim, v.year].filter(Boolean).join(" ") || "Sin datos"}</p>
        <p className="text-[13px]">{v.price != null ? `${v.currency ?? ""} ${v.price.toLocaleString("es-AR")}` : "Sin precio"}{v.mileage_km != null ? ` · ${v.mileage_km.toLocaleString("es-AR")} km` : ""}</p>
        {row.issues.length ? <p className="text-[13px] font-semibold text-warn">{row.issues.map((i) => ISSUE_TEXT[i]).join(" · ")}</p> : null}
        {needsCatalog ? (
          <div className="mt-1.5 flex flex-wrap gap-2">
            <NativeSelect size="sm" aria-label={`Marca de la fila ${row.line}`} value={fix?.make ?? ""} onChange={(e) => onFix({ make: e.target.value, model: "" })}>
              <option value="">Marca</option>
              {catalog.map((m) => <option key={m.make} value={m.make}>{m.make}</option>)}
            </NativeSelect>
            <NativeSelect size="sm" aria-label={`Modelo de la fila ${row.line}`} value={fix?.model ?? ""} disabled={!make} onChange={(e) => onFix({ make: fix?.make ?? "", model: e.target.value })}>
              <option value="">Modelo</option>
              {make?.models.map((m) => <option key={m.model} value={m.model}>{m.model}</option>)}
            </NativeSelect>
          </div>
        ) : null}
      </div>
      <label className="flex items-center gap-2 text-[13px]">
        <input type="checkbox" className="size-4 accent-foreground" checked={!blocked && !skipped} disabled={blocked} onChange={(e) => onSkip(!e.target.checked)} />
        Cargar
      </label>
    </li>
  );
}

"use client";

import { useCallback, useEffect, useRef, useState, useTransition } from "react";

import { saveReview } from "@/app/admin/matches/audit/actions";
import { Pill, TextLink } from "@/components/admin/ui";
import { LevelBadge } from "@/components/app/badges";
import { Button } from "@/components/ui/button";
import {
  criteriaLines, nextPending, progress, REASON_LABEL, REASONS, type Reason, type ReviewItem, verdictProblem, type Verdict, VERDICT_LABEL,
} from "@/lib/admin-match-audit";
import { km, money, vehicle } from "@/lib/format";
import { cn } from "@/lib/utils";

const VERDICT_KEYS: { verdict: Verdict; key: string; tone: string }[] = [
  { verdict: "good", key: "1", tone: "border-emerald-300 bg-emerald-50 text-emerald-900 hover:bg-emerald-100" },
  { verdict: "fair", key: "2", tone: "border-amber-300 bg-amber-50 text-amber-950 hover:bg-amber-100" },
  { verdict: "bad", key: "3", tone: "border-red-300 bg-red-50 text-red-900 hover:bg-red-100" },
];

const typing = (t: EventTarget | null) => t instanceof HTMLElement && (t.tagName === "TEXTAREA" || t.tagName === "INPUT" || t.isContentEditable);

type Saved = { verdict: Verdict; reasons: Reason[]; note: string };

/** One match at a time: the search's criteria next to the listing, three buttons, and the reasons. */
export function MatchAuditBoard({ initial }: { initial: ReviewItem[] }) {
  const [items, setItems] = useState(initial);
  const [index, setIndex] = useState(() => progress(initial).firstPending ?? 0);
  const total = items.length;
  const { done } = progress(items);
  const item = items[index];

  const go = useCallback((i: number) => setIndex(Math.min(Math.max(i, 0), Math.max(total - 1, 0))), [total]);
  const saved = useCallback(
    (id: number, v: Saved) => {
      const next = items.map((i) => (i.id === id ? { ...i, ...v } : i));
      setItems(next);
      const n = nextPending(next, index);
      if (n !== null) setIndex(n);
    },
    [items, index],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (typing(e.target) || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "ArrowRight") go(index + 1);
      else if (e.key === "ArrowLeft") go(index - 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go, index]);

  if (!item) return null;
  return (
    <div className="space-y-3" data-testid="audit-board">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-medium" data-testid="audit-progress">
          {index + 1} de {total} <span className="font-normal text-muted-foreground">· {done} revisados</span>
        </p>
        <div className="flex items-center gap-1">
          <Button variant="outline" size="sm" onClick={() => go(index - 1)} disabled={index === 0}>
            ← Anterior
          </Button>
          <Button variant="outline" size="sm" onClick={() => go(index + 1)} disabled={index >= total - 1}>
            Siguiente →
          </Button>
        </div>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-muted" aria-hidden>
        <div className="h-full bg-foreground/70" style={{ width: `${total ? (done / total) * 100 : 0}%` }} />
      </div>
      <ReviewCard key={item.id} item={item} onSaved={saved} />
      <div className="flex flex-wrap gap-1">
        {items.map((it, i) => (
          <button
            key={it.id}
            type="button"
            onClick={() => go(i)}
            aria-label={`Match ${i + 1}${it.verdict ? `: ${VERDICT_LABEL[it.verdict]}` : ": sin revisar"}`}
            aria-current={i === index ? "step" : undefined}
            className={cn(
              "size-3.5 rounded-sm ring-1 ring-foreground/15",
              it.verdict === "good" && "bg-emerald-400",
              it.verdict === "fair" && "bg-amber-400",
              it.verdict === "bad" && "bg-red-400",
              !it.verdict && "bg-muted",
              i === index && "ring-2 ring-foreground",
            )}
          />
        ))}
      </div>
    </div>
  );
}

function ReviewCard({ item, onSaved }: { item: ReviewItem; onSaved: (id: number, v: Saved) => void }) {
  const [verdict, setVerdict] = useState<Verdict | null>(item.verdict);
  const [reasons, setReasons] = useState<Reason[]>(item.reasons);
  const [note, setNote] = useState(item.note);
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const busy = useRef(false);

  const save = useCallback(
    (v: Verdict, r: Reason[]) => {
      if (busy.current) return;
      const problem = verdictProblem(v, r);
      if (problem) return setError(problem);
      busy.current = true;
      setError(null);
      const finalReasons = v === "good" ? [] : r;
      start(async () => {
        try {
          const res = await saveReview({ id: item.id, verdict: v, reasons: finalReasons, note });
          if (res.error) setError(res.error);
          else onSaved(item.id, { verdict: v, reasons: finalReasons, note: note.trim() });
        } catch {
          setError("No pudimos conectarnos. Probá de nuevo.");
        } finally {
          busy.current = false;
        }
      });
    },
    [item.id, note, onSaved],
  );

  // Bien se guarda al toque; Regular y Mal esperan las razones.
  const choose = useCallback(
    (v: Verdict) => {
      setVerdict(v);
      setError(null);
      if (v === "good") save("good", []);
    },
    [save],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (typing(e.target) || e.metaKey || e.ctrlKey || e.altKey) return;
      const hit = VERDICT_KEYS.find((k) => k.key === e.key);
      if (hit) choose(hit.verdict);
      else if (e.key === "Enter" && verdict && verdict !== "good") save(verdict, reasons);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [choose, save, verdict, reasons]);

  const l = item.listing;
  const criteria = criteriaLines(item.search);
  const needsReasons = verdict === "fair" || verdict === "bad";
  const changed = item.verdict !== null && (verdict !== item.verdict || note.trim() !== item.note || reasons.join() !== item.reasons.join());

  return (
    <div className="space-y-4 rounded-xl bg-card p-4 ring-1 ring-foreground/10">
      <div className="grid gap-4 md:grid-cols-2">
        <section aria-label="Lo que pidió la búsqueda" className="space-y-2 rounded-lg bg-muted/50 p-3" data-testid="audit-criteria">
          <h3 className="text-sm font-semibold">Lo que pidió la búsqueda{item.search ? ` #${item.search.id}` : ""}</h3>
          {criteria.length ? (
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
              {criteria.map((c) => (
                <div key={c.label} className="contents">
                  <dt className="text-muted-foreground">{c.label}</dt>
                  <dd>{c.value}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="text-sm text-muted-foreground">{item.search ? "Sin filtros: cualquier auto." : "La búsqueda ya no existe."}</p>
          )}
        </section>
        <section aria-label="Lo que se avisó" className="space-y-2 rounded-lg bg-muted/50 p-3" data-testid="audit-listing">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold">Lo que se avisó</h3>
            <LevelBadge level={item.level} score={item.score} />
            <Pill>{item.source}</Pill>
            {l?.status === "gone" ? <Pill tone="warn">Ya no está publicado</Pill> : null}
          </div>
          {l ? (
            <>
              <p className="text-sm font-medium">{l.title}</p>
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
                <dt className="text-muted-foreground">Vehículo</dt>
                <dd>
                  {vehicle(l)}
                  {l.make && l.model && !l.trim ? " (sin versión)" : ""}
                </dd>
                <dt className="text-muted-foreground">Año</dt>
                <dd>{l.year ?? "—"}</dd>
                <dt className="text-muted-foreground">Precio</dt>
                <dd>{l.priceUsd != null ? money(l.priceUsd, "USD") : l.price != null ? money(l.price, l.currency) : "—"}</dd>
                <dt className="text-muted-foreground">Kilómetros</dt>
                <dd>{km(l.mileageKm) ?? "—"}</dd>
                <dt className="text-muted-foreground">Ubicación</dt>
                <dd>{l.locationText ?? "—"}</dd>
              </dl>
              <p className="flex flex-wrap gap-x-4 text-sm">
                {l.url ? (
                  <a href={l.url} target="_blank" rel="noopener noreferrer" className="font-medium underline-offset-2 hover:underline">
                    Abrir el aviso original ↗
                  </a>
                ) : null}
                {item.matchId ? <TextLink href={`/admin/matches/${item.matchId}`}>Inspeccionar el match</TextLink> : null}
              </p>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">La publicación ya no está en la base.</p>
          )}
        </section>
      </div>

      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Veredicto">
          {VERDICT_KEYS.map(({ verdict: v, key, tone }) => (
            <button
              key={v}
              type="button"
              onClick={() => choose(v)}
              aria-pressed={verdict === v}
              disabled={pending}
              className={cn(
                "inline-flex h-10 min-w-28 items-center justify-center gap-2 rounded-lg border px-4 text-sm font-medium transition-colors disabled:opacity-60",
                tone,
                verdict === v && "ring-2 ring-foreground",
              )}
            >
              {VERDICT_LABEL[v]} <kbd className="rounded border bg-background/70 px-1 text-xs font-normal">{key}</kbd>
            </button>
          ))}
          {item.verdict ? <span className="text-xs text-muted-foreground">Ya revisado: podés cambiarlo.</span> : null}
        </div>

        {needsReasons ? (
          <fieldset className="space-y-1.5">
            <legend className="text-xs text-muted-foreground">¿Qué falló? Elegí al menos una.</legend>
            <div className="flex flex-wrap gap-1.5">
              {REASONS.map((r) => {
                const on = reasons.includes(r);
                return (
                  <button
                    key={r}
                    type="button"
                    aria-pressed={on}
                    onClick={() => setReasons(on ? reasons.filter((x) => x !== r) : [...reasons, r])}
                    className={cn(
                      "h-8 rounded-full px-3 text-sm ring-1 ring-foreground/15 transition-colors",
                      on ? "bg-foreground text-background" : "bg-background hover:bg-muted",
                    )}
                  >
                    {REASON_LABEL[r]}
                  </button>
                );
              })}
            </div>
          </fieldset>
        ) : null}

        <label className="block space-y-1">
          <span className="text-xs text-muted-foreground">Nota (opcional)</span>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            maxLength={1000}
            rows={2}
            className="w-full rounded-lg border bg-background px-2.5 py-1.5 text-sm"
          />
        </label>

        <div className="flex flex-wrap items-center gap-3">
          {needsReasons || changed ? (
            <Button onClick={() => verdict && save(verdict, reasons)} disabled={pending || !verdict}>
              {pending ? "Guardando…" : item.verdict ? "Guardar cambio" : "Guardar y seguir"}
            </Button>
          ) : null}
          {error ? (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          ) : null}
        </div>
        <p className="text-xs text-muted-foreground">
          Atajos: <kbd>1</kbd> Bien (se guarda solo) · <kbd>2</kbd> Regular · <kbd>3</kbd> Mal · <kbd>Enter</kbd> guarda · <kbd>←</kbd> <kbd>→</kbd> cambian de match.
        </p>
      </div>
    </div>
  );
}

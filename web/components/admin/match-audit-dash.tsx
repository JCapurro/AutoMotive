"use client";

import { useState, useTransition } from "react";

import { drawSample } from "@/app/admin/matches/audit/actions";
import { EmptyRow, Pill, Table, Td, Th } from "@/components/admin/ui";
import { Button } from "@/components/ui/button";
import { LEVEL, type Level } from "@/lib/copy";
import { dayMonth } from "@/lib/format";
import { REASON_LABEL, type Reason, shareText, type Tally } from "@/lib/admin-match-audit";

/** «Sortear muestra»: draws this week's 60 or tops it up. */
export function DrawButton({ have, target }: { have: number; target: number }) {
  const [msg, setMsg] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const full = have >= target;
  return (
    <div className="flex flex-wrap items-center gap-3">
      <Button
        disabled={pending || full}
        onClick={() =>
          start(async () => {
            setMsg(null);
            const r = await drawSample();
            if (r.error) setMsg(r.error);
            else if (!r.added) setMsg("No hay más matches enviados para sumar a la muestra.");
            else setMsg(`Listo: se sumaron ${r.added}.`);
          })
        }
      >
        {pending ? "Sorteando…" : have ? "Completar la muestra" : "Sortear la muestra de la semana"}
      </Button>
      {full ? <span className="text-xs text-muted-foreground">La muestra ya está completa.</span> : null}
      {msg ? (
        <span role="status" className="text-sm text-muted-foreground">
          {msg}
        </span>
      ) : null}
    </div>
  );
}

const keyLabel: Record<string, (k: string) => string> = {
  week: (k) => `Semana del ${dayMonth(`${k}T12:00:00`)}`,
  level: (k) => `${LEVEL[k as Level]?.emoji ?? ""} ${LEVEL[k as Level]?.label ?? k}`,
  source: (k) => k,
};

/** A table of shares: every percentage is written with the sample behind it. */
export function ShareTable({ title, kind, rows }: { title: string; kind: "week" | "level" | "source"; rows: Tally[] }) {
  return (
    <Table>
      <thead>
        <tr>
          <Th>{title}</Th>
          <Th numeric>Bien</Th>
          <Th numeric>Bien + Regular</Th>
          <Th numeric>Revisados</Th>
        </tr>
      </thead>
      <tbody>
        {rows.length ? (
          rows.map((t) => (
            <tr key={t.key} data-testid={`share-${kind}-${t.key}`}>
              <Td>{keyLabel[kind](t.key)}</Td>
              <Td numeric className="whitespace-nowrap">{shareText(t.good, t.reviewed)}</Td>
              <Td numeric className="whitespace-nowrap">{shareText(t.good + t.fair, t.reviewed)}</Td>
              <Td numeric>
                {t.reviewed} de {t.sampled} {t.reviewed > 0 && t.smallSample ? <Pill tone="warn">muestra chica</Pill> : null}
              </Td>
            </tr>
          ))
        ) : (
          <EmptyRow colSpan={4}>Todavía no hay matches revisados.</EmptyRow>
        )}
      </tbody>
    </Table>
  );
}

export function ReasonList({ rows }: { rows: { reason: Reason; n: number; fair: number; bad: number }[] }) {
  if (!rows.length) return <p className="text-sm text-muted-foreground">Todavía no hay razones cargadas.</p>;
  const max = Math.max(...rows.map((r) => r.n));
  return (
    <ul className="space-y-1.5" data-testid="audit-reasons">
      {rows.map((r) => (
        <li key={r.reason} className="grid grid-cols-[8rem_1fr_auto] items-center gap-2 text-sm">
          <span>{REASON_LABEL[r.reason]}</span>
          <span className="h-2 rounded-full bg-muted">
            <span className="block h-full rounded-full bg-foreground/60" style={{ width: `${(r.n / max) * 100}%` }} />
          </span>
          <span className="tabular-nums text-muted-foreground">
            {r.n} <span className="text-xs">({r.bad} mal, {r.fair} regular)</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

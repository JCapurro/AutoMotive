"use client";

import { useState, useTransition } from "react";
import { toast } from "sonner";

import { updateSource } from "@/app/admin/actions";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";

/** Inline edit of a source's cadence and state (Fuentes, sección 10). */
export function SourceForm({ id, enabled, interval }: { id: string; enabled: boolean; interval: number }) {
  const [baseline, setBaseline] = useState({ enabled, interval });
  const [on, setOn] = useState(enabled);
  const [seconds, setSeconds] = useState(String(interval));
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const cadence = Number(seconds);
  const valid = seconds.trim() !== "" && Number.isInteger(cadence) && cadence >= 60 && cadence <= 86_400;
  const dirty = on !== baseline.enabled || cadence !== baseline.interval;
  return (
    <form
      className="space-y-2"
      onSubmit={(e) => {
        e.preventDefault();
        start(async () => {
          const res = await updateSource({ id, enabled: on, crawl_interval_seconds: cadence, expected: { enabled: baseline.enabled, crawl_interval_seconds: baseline.interval } });
          setError(res.error ?? null);
          if (res.error) toast.error(res.error);
          else {
            setBaseline({ enabled: on, interval: cadence });
            toast.success("Fuente actualizada");
          }
        });
      }}
    >
      <div className="flex flex-wrap items-center gap-2">
      <label className="flex items-center gap-1.5 text-xs">
        <Checkbox checked={on} disabled={pending} onCheckedChange={(v) => setOn(v === true)} aria-label={`${id} habilitada`} />
        Activa
      </label>
      <Input
        type="number"
        min={60}
        max={86_400}
        step={1}
        value={seconds}
        disabled={pending}
        onChange={(e) => setSeconds(e.target.value)}
        aria-label={`Intervalo de rastreo de ${id}, en segundos`}
        className="h-7 w-24 text-right tabular-nums"
      />
      <span className="text-xs text-muted-foreground">segundos</span>
      <Button type="submit" size="xs" variant="outline" disabled={!dirty || !valid || pending}>
        Guardar
      </Button>
      </div>
      {dirty ? <p className="max-w-sm text-xs">Propuesto: {baseline.enabled ? "activa" : "pausada"} → {on ? "activa" : "pausada"}; cada {baseline.interval} → {seconds || "—"} segundos. Se aplica al próximo ciclo; no interrumpe el rastreo en curso.</p> : null}
      {dirty && (enabled !== baseline.enabled || interval !== baseline.interval) ? <p role="alert" className="max-w-sm text-xs text-destructive">La fuente cambió mientras editabas. Recargá la página y revisá el valor más reciente antes de guardar.</p> : null}
      {!valid ? <p role="alert" className="text-xs text-destructive">Usá un intervalo entero entre 60 y 86.400 segundos.</p> : null}
      {error ? <p role="alert" className="max-w-sm text-xs text-destructive">{error}</p> : null}
      <a className="text-xs text-muted-foreground underline" href="/admin/config">Ver historial de cambios</a>
    </form>
  );
}

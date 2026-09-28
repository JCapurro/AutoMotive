"use client";

import { useState, useTransition } from "react";
import { toast } from "sonner";

import { updateSource } from "@/app/admin/actions";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";

/** Inline edit of a source's cadence and state (Fuentes, sección 10). */
export function SourceForm({ id, enabled, interval }: { id: string; enabled: boolean; interval: number }) {
  const [on, setOn] = useState(enabled);
  const [minutes, setMinutes] = useState(String(Math.round(interval / 60)));
  const [pending, start] = useTransition();
  const dirty = on !== enabled || Math.round(Number(minutes) * 60) !== interval;
  return (
    <form
      className="flex items-center gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        start(async () => {
          const res = await updateSource({ id, enabled: on, crawl_interval_seconds: Math.round(Number(minutes) * 60) });
          if (res.error) toast.error(res.error);
          else toast.success("Fuente actualizada");
        });
      }}
    >
      <label className="flex items-center gap-1.5 text-xs">
        <Checkbox checked={on} onCheckedChange={(v) => setOn(v === true)} aria-label={`${id} habilitada`} />
        Activa
      </label>
      <Input
        type="number"
        min={1}
        step={1}
        value={minutes}
        onChange={(e) => setMinutes(e.target.value)}
        aria-label={`Cada cuántos minutos se scrapea ${id}`}
        className="h-7 w-16 text-right tabular-nums"
      />
      <span className="text-xs text-muted-foreground">min</span>
      <Button type="submit" size="xs" variant="outline" disabled={!dirty || pending}>
        Guardar
      </Button>
    </form>
  );
}

"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { createGuide, generateMissing, type GuideActionResult, requestGuide, setGuideStatus } from "@/app/admin/guides/actions";
import { Button } from "@/components/ui/button";

/** Runs a guide action and says what went wrong, next to the button. */
function useGuideAction() {
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const run = (action: () => Promise<GuideActionResult>, after?: (r: GuideActionResult) => void) => start(async () => {
    setError(null);
    setNote(null);
    let result: GuideActionResult;
    try {
      result = await action();
    } catch {
      setError("No pudimos conectarnos. Probá de nuevo.");
      return;
    }
    if (result.error) setError(result.error);
    else after?.(result);
  });
  return { error, note, setNote, pending, run };
}

function Feedback({ error, note }: { error: string | null; note: string | null }) {
  if (error) return <p role="alert" className="text-xs text-destructive">{error}</p>;
  if (note) return <p role="status" className="text-xs text-muted-foreground">{note}</p>;
  return null;
}

/** «Crear borrador» from a candidate (or any catalog model): goes to its editor. */
export function CreateGuideButton({ make, model, yearFrom, yearTo, label = "Crear borrador" }: { make: string; model: string; yearFrom?: number | null; yearTo?: number | null; label?: string }) {
  const router = useRouter();
  const { error, note, pending, run } = useGuideAction();
  return (
    <div className="space-y-1">
      <Button type="button" size="sm" variant="outline" disabled={pending}
        onClick={() => run(() => createGuide({ make, model, year_from: yearFrom ?? null, year_to: yearTo ?? null }), (r) => router.push(`/admin/guides/${r.id}`))}>
        {pending ? "Creando…" : label}
      </Button>
      <Feedback error={error} note={note} />
    </div>
  );
}

/** A form to start a guide of a model that is not among the candidates. */
export function CreateOtherGuide() {
  const [make, setMake] = useState("");
  const [model, setModel] = useState("");
  return (
    <div className="flex flex-wrap items-end gap-2">
      <label className="space-y-1 text-sm">
        <span className="block text-xs text-muted-foreground">Marca</span>
        <input value={make} onChange={(e) => setMake(e.target.value)} className="h-8 w-40 rounded-md border bg-background px-2" name="make" />
      </label>
      <label className="space-y-1 text-sm">
        <span className="block text-xs text-muted-foreground">Modelo</span>
        <input value={model} onChange={(e) => setModel(e.target.value)} className="h-8 w-40 rounded-md border bg-background px-2" name="model" />
      </label>
      {make.trim() && model.trim() ? <CreateGuideButton make={make} model={model} label="Crear guía" /> : null}
    </div>
  );
}

export function GuideStatusButton({ id, status }: { id: number; status: string }) {
  const { error, note, pending, run } = useGuideAction();
  const publish = status !== "published";
  return (
    <div className="space-y-1">
      <Button type="button" size="sm" variant={publish ? "default" : "outline"} disabled={pending}
        onClick={() => {
          if (!publish && !window.confirm("¿Despublicar? La página deja de verse y sus preguntas salen de los avisos.")) return;
          run(() => setGuideStatus({ id, status: publish ? "published" : "draft" }));
        }}>
        {pending ? "Guardando…" : publish ? "Publicar" : "Despublicar"}
      </Button>
      <Feedback error={error} note={note} />
    </div>
  );
}

/** «Generar borrador» / «Regenerar»: only rendered with the generation switched on. */
export function RequestGuideButton({ id, force = false }: { id: number; force?: boolean }) {
  const { error, note, setNote, pending, run } = useGuideAction();
  return (
    <div className="space-y-1">
      <Button type="button" size="sm" variant="outline" disabled={pending}
        onClick={() => {
          if (force && !window.confirm("Vas a reemplazar tus cambios por un borrador nuevo. ¿Seguimos?")) return;
          run(() => requestGuide({ id, force }), () => setNote("Pedido en cola. El borrador aparece acá cuando termine."));
        }}>
        {pending ? "Pidiendo…" : force ? "Regenerar" : "Generar borrador"}
      </Button>
      <Feedback error={error} note={note} />
    </div>
  );
}

export function GenerateMissingButton() {
  const { error, note, setNote, pending, run } = useGuideAction();
  return (
    <div className="space-y-1">
      <Button type="button" size="sm" variant="outline" disabled={pending}
        onClick={() => run(() => generateMissing(), (r) => setNote(`Pedimos ${r.requested ?? 0} borradores; quedaron ${r.left ?? 0} sin pedir.`))}>
        {pending ? "Pidiendo…" : "Generar los que faltan"}
      </Button>
      <Feedback error={error} note={note} />
    </div>
  );
}

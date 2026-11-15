"use client";

import { useState, useTransition } from "react";
import { toast } from "sonner";

import { createExperiment, type ExperimentActionResult, recordVerdict, updateExperiment } from "@/app/admin/experiments/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { type ExperimentStatus, STATUS_LABEL, toArtInput } from "@/lib/admin-experiments-data";

/** Runs a server action and shows what went wrong next to the button. */
function useRun(done: string, after?: () => void) {
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const run = (action: () => Promise<ExperimentActionResult>) => start(async () => {
    setError(null);
    let result: ExperimentActionResult;
    try {
      result = await action();
    } catch {
      setError("No pudimos conectarnos. Probá de nuevo.");
      return;
    }
    if (result.error) setError(result.error);
    else {
      toast.success(done);
      after?.();
    }
  });
  return { error, pending, run };
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1 text-sm">
      <span className="block text-xs font-medium text-muted-foreground">{label}</span>
      {children}
      {hint ? <span className="block text-xs text-muted-foreground">{hint}</span> : null}
    </label>
  );
}

export type ExperimentValues = {
  slug: string; title: string; config_key: string | null; hypothesis: string; metric: string;
  baseline_text: string | null; baseline_value: number | null; started_at: string | null; review_at: string | null;
};

const EMPTY: ExperimentValues = { slug: "", title: "", config_key: null, hypothesis: "", metric: "", baseline_text: null, baseline_value: null, started_at: null, review_at: null };

/** Add an experiment (no `initial`) or edit one: same fields; the identifier is fixed once created. */
export function ExperimentForm({ initial }: { initial?: ExperimentValues }) {
  const editing = Boolean(initial);
  const v = initial ?? EMPTY;
  const [slug, setSlug] = useState(v.slug);
  const [title, setTitle] = useState(v.title);
  const [configKey, setConfigKey] = useState(v.config_key ?? "");
  const [hypothesis, setHypothesis] = useState(v.hypothesis);
  const [metric, setMetric] = useState(v.metric);
  const [baselineText, setBaselineText] = useState(v.baseline_text ?? "");
  const [baselineValue, setBaselineValue] = useState(v.baseline_value === null ? "" : String(v.baseline_value));
  const [startedAt, setStartedAt] = useState(toArtInput(v.started_at));
  const [reviewAt, setReviewAt] = useState(v.review_at ?? "");
  const reset = () => {
    setSlug(""); setTitle(""); setConfigKey(""); setHypothesis(""); setMetric(""); setBaselineText(""); setBaselineValue(""); setStartedAt(""); setReviewAt("");
  };
  const { error, pending, run } = useRun(editing ? "Experimento guardado" : "Experimento agregado", editing ? undefined : reset);
  return (
    <form
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault();
        const input = { slug, title, config_key: configKey, hypothesis, metric, baseline_text: baselineText, baseline_value: baselineValue, started_at: startedAt, review_at: reviewAt };
        run(() => (editing ? updateExperiment(input) : createExperiment(input)));
      }}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Título"><Input value={title} onChange={(e) => setTitle(e.target.value)} disabled={pending} required maxLength={120} /></Field>
        <Field label="Identificador" hint={editing ? undefined : "Minúsculas, números y guion bajo. No se puede cambiar después."}>
          <Input value={slug} onChange={(e) => setSlug(e.target.value)} disabled={pending || editing} required pattern="[a-z0-9_]{1,60}" />
        </Field>
        <Field label="Clave del interruptor (opcional)" hint="La clave de app_config que lo prende o apaga, ej. trial_reserve.">
          <Input value={configKey} onChange={(e) => setConfigKey(e.target.value)} disabled={pending} maxLength={200} />
        </Field>
        <Field label="Empezó (hora argentina)"><Input type="datetime-local" value={startedAt} onChange={(e) => setStartedAt(e.target.value)} disabled={pending} /></Field>
        <Field label="Volver a medir el" hint="Desde ese día figura «listo para medir».">
          <Input type="date" value={reviewAt} onChange={(e) => setReviewAt(e.target.value)} disabled={pending} />
        </Field>
      </div>
      <Field label="Qué esperamos que pase"><Textarea value={hypothesis} onChange={(e) => setHypothesis(e.target.value)} disabled={pending} maxLength={2000} /></Field>
      <Field label="Qué se mide y cómo"><Textarea value={metric} onChange={(e) => setMetric(e.target.value)} disabled={pending} maxLength={2000} /></Field>
      <div className="grid gap-3 sm:grid-cols-[1fr_10rem]">
        <Field label="Cómo estábamos antes (texto)"><Input value={baselineText} onChange={(e) => setBaselineText(e.target.value)} disabled={pending} maxLength={1000} /></Field>
        <Field label="Número de base (opcional)"><Input inputMode="decimal" value={baselineValue} onChange={(e) => setBaselineValue(e.target.value)} disabled={pending} /></Field>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" size="sm" disabled={pending}>{pending ? "Guardando…" : editing ? "Guardar cambios" : "Agregar experimento"}</Button>
        {error ? <p role="alert" className="text-xs text-destructive">{error}</p> : null}
      </div>
    </form>
  );
}

const CHOICES: ExperimentStatus[] = ["won", "lost", "inconclusive", "paused", "running"];
const CHOICE_TEXT: Record<ExperimentStatus, string> = {
  won: "Ganó: lo dejamos",
  lost: "Perdió: lo sacamos",
  inconclusive: "Sin conclusión",
  paused: "Pausar",
  running: "Reabrir (vuelve a estar en marcha)",
};

/** Result and verdict by hand; «Reabrir» undoes a verdict and clears its result. */
export function VerdictForm({ slug, status, resultText, resultValue, note }: {
  slug: string; status: ExperimentStatus; resultText: string | null; resultValue: number | null; note: string | null;
}) {
  const [choice, setChoice] = useState<ExperimentStatus>(status === "running" ? "won" : status === "paused" ? "running" : status);
  const [text, setText] = useState(resultText ?? "");
  const [value, setValue] = useState(resultValue === null ? "" : String(resultValue));
  const [noteText, setNoteText] = useState(note ?? "");
  const keepsResult = choice === "won" || choice === "lost" || choice === "inconclusive";
  const { error, pending, run } = useRun(choice === "running" ? "Experimento reabierto" : "Veredicto guardado");
  return (
    <form
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault();
        run(() => recordVerdict({ slug, status: choice, result_text: keepsResult ? text : "", result_value: keepsResult ? value : "", verdict_note: keepsResult || choice === "paused" ? noteText : "" }));
      }}
    >
      <Field label="Qué decidimos">
        <NativeSelect value={choice} onChange={(e) => setChoice(e.target.value as ExperimentStatus)} disabled={pending}>
          {CHOICES.map((c) => <NativeSelectOption key={c} value={c}>{CHOICE_TEXT[c]}</NativeSelectOption>)}
        </NativeSelect>
      </Field>
      {keepsResult ? (
        <div className="grid gap-3 sm:grid-cols-[1fr_10rem]">
          <Field label="Resultado (texto)"><Input value={text} onChange={(e) => setText(e.target.value)} disabled={pending} maxLength={1000} placeholder="Ej. 61 % recibieron una alerta" /></Field>
          <Field label="Número (opcional)"><Input inputMode="decimal" value={value} onChange={(e) => setValue(e.target.value)} disabled={pending} /></Field>
        </div>
      ) : null}
      {keepsResult || choice === "paused" ? (
        <Field label={choice === "paused" ? "Por qué se pausa" : "Nota del veredicto"}>
          <Textarea value={noteText} onChange={(e) => setNoteText(e.target.value)} disabled={pending} maxLength={2000} />
        </Field>
      ) : null}
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" size="sm" disabled={pending}>{pending ? "Guardando…" : choice === "running" ? "Reabrir" : "Guardar"}</Button>
        <span className="text-xs text-muted-foreground">Estado actual: {STATUS_LABEL[status]}</span>
        {error ? <p role="alert" className="text-xs text-destructive">{error}</p> : null}
      </div>
    </form>
  );
}

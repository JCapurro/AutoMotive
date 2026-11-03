"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { saveGuide } from "@/app/admin/guides/actions";
import { GuideContent } from "@/components/guides/guide-content";
import { Button } from "@/components/ui/button";
import {
  type GenerationLine,
  GUIDE_SECTION_NAME,
  GUIDE_SECTIONS,
  type GuideBody,
  type GuideLine,
  type GuideQuestion,
  type GuideSource,
  type GuideValues,
  GuideValuesInput,
  lintGuide,
  publishProblem,
  SOURCE_KINDS,
} from "@/lib/guides";

const FIELD = "w-full rounded-md border bg-background px-2 py-1.5 text-sm";
const SMALL = "rounded-md border bg-background px-2 py-1.5 text-sm";

type LineSection = Exclude<(typeof GUIDE_SECTIONS)[number], "generations">;

function yearValue(raw: string): number | null {
  const n = Number(raw);
  return raw.trim() && Number.isInteger(n) ? n : null;
}

/**
 * PAR-04: the guide's editor. A form per section with rows to add (text and
 * «aplica a»), the questions (text and «por qué»), the sources (title, URL,
 * kind and «La revisé») and the years. The copy lint and the money rule run
 * before saving and say which row fails; the preview is the public page's own
 * component.
 */
export function GuideEditor({ id, initial, updatedAt, status }: { id: number; initial: GuideValues; updatedAt: string; status: string }) {
  const router = useRouter();
  const [values, setValues] = useState<GuideValues>(initial);
  const [expected, setExpected] = useState(updatedAt);
  // Publishing or unpublishing moves updated_at: the next save expects the new one.
  const [seenUpdatedAt, setSeenUpdatedAt] = useState(updatedAt);
  if (updatedAt !== seenUpdatedAt) {
    setSeenUpdatedAt(updatedAt);
    setExpected(updatedAt);
  }
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [pending, start] = useTransition();
  const issues = lintGuide(values);
  const problem = publishProblem(values);

  const set = (patch: Partial<GuideValues>) => {
    setValues((v) => ({ ...v, ...patch }));
    setSaved(false);
  };
  const setBody = (patch: Partial<GuideBody>) => set({ body: { ...values.body, ...patch } });
  const setLine = (key: LineSection, n: number, patch: Partial<GuideLine>) =>
    setBody({ [key]: values.body[key].map((l, i) => (i === n ? { ...l, ...patch } : l)) } as Partial<GuideBody>);
  const setGeneration = (n: number, patch: Partial<GenerationLine>) =>
    setBody({ generations: values.body.generations.map((l, i) => (i === n ? { ...l, ...patch } : l)) });
  const setQuestion = (n: number, patch: Partial<GuideQuestion>) =>
    set({ questions: values.questions.map((q, i) => (i === n ? { ...q, ...patch } : q)) });
  const setSource = (n: number, patch: Partial<GuideSource>) =>
    set({ sources: values.sources.map((s, i) => (i === n ? { ...s, ...patch } : s)) });

  const save = () => start(async () => {
    setError(null);
    const parsed = GuideValuesInput.safeParse(values);
    if (!parsed.success) {
      const issue = parsed.error.issues[0];
      setError(`${issue?.path.join(" › ") || "Guía"}: ${issue?.message ?? "revisá los datos."}`);
      return;
    }
    if (issues.length) {
      setError(`${issues[0].where}: ${issues[0].message}.`);
      return;
    }
    if (status === "published" && problem) {
      setError(`La guía está publicada y tiene que seguir completa. ${problem}`);
      return;
    }
    try {
      const result = await saveGuide({ id, expectedUpdatedAt: expected, values: parsed.data });
      if (result.error) setError(result.error);
      else {
        if (result.updatedAt) setExpected(result.updatedAt);
        setSaved(true);
        router.refresh();
      }
    } catch {
      setError("No pudimos conectarnos. Tus cambios siguen acá: probá de nuevo.");
    }
  });

  return (
    <div className="grid gap-8 xl:grid-cols-2">
      <form className="space-y-6" onSubmit={(e) => { e.preventDefault(); save(); }} aria-label="Editor de la guía">
        <fieldset className="grid gap-3 sm:grid-cols-3">
          <legend className="mb-2 text-sm font-semibold">Generación y años</legend>
          <label className="space-y-1 text-sm">
            <span className="block text-xs text-muted-foreground">Generación (vacío: todo el modelo)</span>
            <input className={FIELD} name="generation_label" value={values.generation_label ?? ""} onChange={(e) => set({ generation_label: e.target.value || null })} />
          </label>
          <label className="space-y-1 text-sm">
            <span className="block text-xs text-muted-foreground">Desde</span>
            <input className={FIELD} name="year_from" inputMode="numeric" value={values.year_from ?? ""} onChange={(e) => set({ year_from: yearValue(e.target.value) })} />
          </label>
          <label className="space-y-1 text-sm">
            <span className="block text-xs text-muted-foreground">Hasta</span>
            <input className={FIELD} name="year_to" inputMode="numeric" value={values.year_to ?? ""} onChange={(e) => set({ year_to: yearValue(e.target.value) })} />
          </label>
        </fieldset>

        {GUIDE_SECTIONS.filter((k): k is LineSection => k !== "generations").map((key) => (
          <fieldset key={key} className="space-y-2" data-section={key}>
            <legend className="text-sm font-semibold">{GUIDE_SECTION_NAME[key]}</legend>
            {values.body[key].map((line, n) => (
              <div key={n} className="grid gap-2 rounded-lg bg-card p-2 ring-1 ring-foreground/10 sm:grid-cols-[1fr_12rem_auto]">
                <textarea aria-label={`${GUIDE_SECTION_NAME[key]}, renglón ${n + 1}`} className={FIELD} rows={2} value={line.text} onChange={(e) => setLine(key, n, { text: e.target.value })} />
                <input aria-label={`${GUIDE_SECTION_NAME[key]}, renglón ${n + 1}: aplica a`} placeholder="Aplica a (opcional)" className={SMALL} value={line.applies_to ?? ""} onChange={(e) => setLine(key, n, { applies_to: e.target.value || null })} />
                <Button type="button" size="sm" variant="ghost" onClick={() => setBody({ [key]: values.body[key].filter((_, i) => i !== n) } as Partial<GuideBody>)}>Borrar</Button>
              </div>
            ))}
            <Button type="button" size="sm" variant="outline" onClick={() => setBody({ [key]: [...values.body[key], { text: "", applies_to: null }] } as Partial<GuideBody>)}>
              Agregar renglón
            </Button>
          </fieldset>
        ))}

        <fieldset className="space-y-2" data-section="generations">
          <legend className="text-sm font-semibold">{GUIDE_SECTION_NAME.generations}</legend>
          {values.body.generations.map((line, n) => (
            <div key={n} className="grid gap-2 rounded-lg bg-card p-2 ring-1 ring-foreground/10 sm:grid-cols-[8rem_5rem_5rem_1fr_auto]">
              <input aria-label={`Generación ${n + 1}: nombre`} placeholder="Nombre" className={SMALL} value={line.label ?? ""} onChange={(e) => setGeneration(n, { label: e.target.value || null })} />
              <input aria-label={`Generación ${n + 1}: desde`} placeholder="Desde" inputMode="numeric" className={SMALL} value={line.year_from ?? ""} onChange={(e) => setGeneration(n, { year_from: yearValue(e.target.value) })} />
              <input aria-label={`Generación ${n + 1}: hasta`} placeholder="Hasta" inputMode="numeric" className={SMALL} value={line.year_to ?? ""} onChange={(e) => setGeneration(n, { year_to: yearValue(e.target.value) })} />
              <textarea aria-label={`${GUIDE_SECTION_NAME.generations}, renglón ${n + 1}`} className={FIELD} rows={2} value={line.text} onChange={(e) => setGeneration(n, { text: e.target.value })} />
              <Button type="button" size="sm" variant="ghost" onClick={() => setBody({ generations: values.body.generations.filter((_, i) => i !== n) })}>Borrar</Button>
            </div>
          ))}
          <Button type="button" size="sm" variant="outline" onClick={() => setBody({ generations: [...values.body.generations, { label: null, year_from: null, year_to: null, text: "" }] })}>
            Agregar generación
          </Button>
        </fieldset>

        <fieldset className="space-y-2" data-section="questions">
          <legend className="text-sm font-semibold">Preguntas para el vendedor (de 3 a 8, cada una termina en «?»)</legend>
          {values.questions.map((q, n) => (
            <div key={n} className="grid gap-2 rounded-lg bg-card p-2 ring-1 ring-foreground/10 sm:grid-cols-[1fr_12rem_auto]">
              <input aria-label={`Pregunta ${n + 1}`} className={FIELD} value={q.text} onChange={(e) => setQuestion(n, { text: e.target.value })} />
              <input aria-label={`Pregunta ${n + 1}: por qué`} placeholder="Por qué (opcional)" className={SMALL} value={q.why} onChange={(e) => setQuestion(n, { why: e.target.value })} />
              <Button type="button" size="sm" variant="ghost" onClick={() => set({ questions: values.questions.filter((_, i) => i !== n) })}>Borrar</Button>
            </div>
          ))}
          <Button type="button" size="sm" variant="outline" onClick={() => set({ questions: [...values.questions, { text: "", why: "" }] })}>Agregar pregunta</Button>
        </fieldset>

        <fieldset className="space-y-2" data-section="sources">
          <legend className="text-sm font-semibold">Fuentes (para publicar, cada una con «La revisé»)</legend>
          {values.sources.map((s, n) => (
            <div key={n} className="grid gap-2 rounded-lg bg-card p-2 ring-1 ring-foreground/10 sm:grid-cols-[1fr_1fr_8rem_auto_auto]">
              <input aria-label={`Fuente ${n + 1}: título`} placeholder="Título" className={SMALL} value={s.title} onChange={(e) => setSource(n, { title: e.target.value })} />
              <input aria-label={`Fuente ${n + 1}: URL`} placeholder="https://…" className={SMALL} value={s.url} onChange={(e) => setSource(n, { url: e.target.value })} />
              <select aria-label={`Fuente ${n + 1}: tipo`} className={SMALL} value={s.kind} onChange={(e) => setSource(n, { kind: e.target.value as GuideSource["kind"] })}>
                {SOURCE_KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
              </select>
              <label className="flex items-center gap-1.5 text-sm">
                <input type="checkbox" checked={s.verified} onChange={(e) => setSource(n, { verified: e.target.checked })} />
                La revisé
              </label>
              <Button type="button" size="sm" variant="ghost" onClick={() => set({ sources: values.sources.filter((_, i) => i !== n) })}>Borrar</Button>
            </div>
          ))}
          <Button type="button" size="sm" variant="outline" onClick={() => set({ sources: [...values.sources, { title: "", url: "https://", kind: "otra", verified: false }] })}>Agregar fuente</Button>
        </fieldset>

        {issues.length ? (
          <ul className="space-y-1 rounded-lg bg-red-50 p-3 text-sm text-red-900" aria-label="Problemas de copy">
            {issues.map((i, n) => <li key={n}>{i.where}: {i.message}.</li>)}
          </ul>
        ) : null}
        {problem ? <p className="text-sm text-muted-foreground">Para publicar: {problem}</p> : null}
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" disabled={pending}>{pending ? "Guardando…" : "Guardar"}</Button>
          {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}
          {saved && !error ? <p role="status" className="text-sm text-muted-foreground">Guardada.</p> : null}
        </div>
      </form>

      <section aria-label="Vista previa" className="space-y-3">
        <h2 className="text-base font-semibold">Vista previa</h2>
        <div className="rounded-xl bg-background p-4 ring-1 ring-foreground/10">
          <GuideContent guides={[{
            id, make: values.make, model: values.model, generationLabel: values.generation_label, yearFrom: values.year_from, yearTo: values.year_to,
            slugMake: "", slugModel: "", body: values.body, questions: values.questions.filter((q) => q.text.trim()), sources: values.sources.filter((s) => s.verified),
            updatedAt: expected,
          }]} />
        </div>
      </section>
    </div>
  );
}

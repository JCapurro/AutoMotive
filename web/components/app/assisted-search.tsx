"use client";

import { Check, Loader2, PenLine, RotateCcw, Sparkles, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useId, useState, useTransition } from "react";
import { toast } from "sonner";

import { startAssisted } from "@/app/app/searches/actions";
import { SearchForm } from "@/components/app/search-form";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  ASSISTED_DEADLINE_MS,
  ASSISTED_EXAMPLES,
  ASSISTED_MAX_CHARS,
  ASSISTED_POLL_MS,
  AssistedOutput,
  draftTitle,
  draftToValues,
} from "@/lib/assisted";
import type { Catalog } from "@/lib/catalog";
import type { SearchValues } from "@/lib/search-form";
import { createClient } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";

type Source = { id: string; name: string };
type Origin = { label: string; lat: number; lon: number } | null;

type Reviewed = {
  title: string;
  values: SearchValues;
  notes: string[];
  state: "pending" | "saved" | "discarded";
  savedId?: number;
};

type Phase =
  | { kind: "idle" }
  | { kind: "waiting"; jobId: number }
  | { kind: "review"; jobId: number; drafts: Reviewed[]; active: number }
  | { kind: "failed"; jobId: number | null; reason: "error" | "empty" | "manual" | "unavailable" };

type JobRow = { status: string; output: unknown };

// Sección 8.4, paso 6: the structured form takes over.
const FALLBACK_TITLE = {
  error: "No pude interpretarlo, completá los filtros",
  empty: "No encontramos un vehículo en tu pedido, completá los filtros",
  manual: "Completá los filtros",
  unavailable: "El intérprete no está disponible ahora, completá los filtros",
} as const;

/**
 * Modo asistido (§12, sección 8.4): the user writes what they want, the
 * worker's LLM proposes one search per vehicle, and each proposal opens as a
 * pre-filled structured form to correct and confirm. If the LLM fails, times
 * out or finds no vehicle, the empty structured form takes over.
 */
export function AssistedSearch({
  catalog,
  sources,
  base,
  defaultOrigin,
}: {
  catalog: Catalog;
  sources: Source[];
  base: SearchValues;
  defaultOrigin: Origin;
}) {
  const [text, setText] = useState("");
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const [error, setError] = useState<string | null>(null);
  const [sending, startSending] = useTransition();
  const [supabase] = useState(createClient);
  const router = useRouter();
  const textId = useId();

  const waitingJob = phase.kind === "waiting" ? phase.jobId : null;

  // Wait for the worker: Realtime on the job's row, a poll in case the
  // subscription drops, and a deadline after which the form takes over.
  useEffect(() => {
    if (waitingJob == null) return;
    let settled = false;
    let channel: ReturnType<typeof supabase.channel> | null = null;

    const settle = (row: JobRow | null) => {
      if (settled || !row || row.status === "queued" || row.status === "running") return;
      settled = true;
      if (row.status === "failed") {
        setPhase({ kind: "failed", jobId: waitingJob, reason: "error" });
        return;
      }
      const parsed = AssistedOutput.safeParse(row.output);
      if (!parsed.success) {
        setPhase({ kind: "failed", jobId: waitingJob, reason: "error" });
      } else if (!parsed.data.drafts.length) {
        setPhase({ kind: "failed", jobId: waitingJob, reason: "empty" });
      } else {
        setPhase({
          kind: "review",
          jobId: waitingJob,
          active: 0,
          drafts: parsed.data.drafts.map((draft, i) => ({
            title: draftTitle(draft, i),
            ...draftToValues(draft, base),
            state: "pending",
          })),
        });
      }
    };

    const poll = async () => {
      const { data } = await supabase.from("llm_jobs").select("status, output").eq("id", waitingJob).maybeSingle();
      settle(data);
    };

    (async () => {
      // Realtime has to carry the user's token, or RLS filters the row out.
      const { data } = await supabase.auth.getSession();
      if (settled) return;
      if (data.session) await supabase.realtime.setAuth(data.session.access_token);
      channel = supabase
        .channel(`llm_job:${waitingJob}`)
        .on(
          "postgres_changes",
          { event: "UPDATE", schema: "public", table: "llm_jobs", filter: `id=eq.${waitingJob}` },
          (change) => settle(change.new as JobRow),
        )
        .subscribe();
    })();
    const interval = setInterval(() => void poll(), ASSISTED_POLL_MS);
    const deadline = setTimeout(() => {
      if (settled) return;
      settled = true;
      setPhase({ kind: "failed", jobId: waitingJob, reason: "error" });
    }, ASSISTED_DEADLINE_MS);

    return () => {
      settled = true;
      clearInterval(interval);
      clearTimeout(deadline);
      if (channel) void supabase.removeChannel(channel);
    };
  }, [waitingJob, supabase, base]);

  function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    startSending(async () => {
      const result = await startAssisted(text);
      if (result.jobId != null) setPhase({ kind: "waiting", jobId: result.jobId });
      else if (result.unavailable) setPhase({ kind: "failed", jobId: null, reason: "unavailable" });
      else setError(result.error ?? "No pudimos enviar tu búsqueda.");
    });
  }

  function update(index: number, patch: Partial<Reviewed>) {
    setPhase((prev) => {
      if (prev.kind !== "review") return prev;
      const drafts = prev.drafts.map((d, i) => (i === index ? { ...d, ...patch } : d));
      const next = drafts.findIndex((d) => d.state === "pending");
      return { ...prev, drafts, active: patch.state && patch.state !== "pending" && next >= 0 ? next : prev.active };
    });
  }

  // Every proposal saved or discarded: back to the dashboard with the new searches.
  const review = phase.kind === "review" ? phase : null;
  const done = review != null && review.drafts.every((d) => d.state !== "pending");
  const savedCount = review?.drafts.filter((d) => d.state === "saved").length ?? 0;
  useEffect(() => {
    if (!done) return;
    if (savedCount) {
      toast(savedCount === 1 ? "Guardamos tu búsqueda" : `Guardamos tus ${savedCount} búsquedas`);
      router.push("/app");
    }
  }, [done, savedCount, router]);

  if (phase.kind === "review") {
    const single = phase.drafts.length === 1;
    return (
      <div className="space-y-4">
        <RequestSummary text={text} onEdit={() => setPhase({ kind: "idle" })}>
          {single
            ? "Encontramos este vehículo en tu pedido. Revisá los filtros y corregí lo que haga falta antes de guardar."
            : `Encontramos ${phase.drafts.length} vehículos: cada uno es una búsqueda. Revisalos y guardá los que quieras.`}
        </RequestSummary>

        {!single ? (
          <nav aria-label="Vehículos del pedido" className="flex flex-wrap gap-2">
            {phase.drafts.map((d, i) => (
              <Button
                key={i}
                type="button"
                size="sm"
                variant={phase.active === i ? "default" : "outline"}
                aria-current={phase.active === i ? "step" : undefined}
                onClick={() => setPhase({ ...phase, active: i })}
                className={cn(d.state === "discarded" && "line-through opacity-60")}
              >
                {d.state === "saved" ? <Check aria-hidden /> : null}
                {i + 1}. {d.title}
              </Button>
            ))}
          </nav>
        ) : null}

        {phase.drafts.map((d, i) => (
          <section
            key={i}
            aria-label={`Vehículo ${i + 1} de ${phase.drafts.length}: ${d.title}`}
            data-testid="assisted-draft"
            hidden={phase.active !== i}
            className="space-y-3"
          >
            {d.state === "saved" ? (
              <Alert>
                <Check aria-hidden />
                <AlertTitle>Guardamos «{d.title}»</AlertTitle>
                <AlertDescription>
                  <Link href={`/app/searches/${d.savedId}`}>Ver la búsqueda</Link>
                </AlertDescription>
              </Alert>
            ) : d.state === "discarded" ? (
              <Alert>
                <Trash2 aria-hidden />
                <AlertTitle>Descartaste «{d.title}»</AlertTitle>
                <AlertDescription>
                  <button type="button" className="underline underline-offset-3" onClick={() => update(i, { state: "pending" })}>
                    Recuperarlo
                  </button>
                </AlertDescription>
              </Alert>
            ) : (
              <>
                {!single ? (
                  <div className="flex items-center justify-between gap-2">
                    <h2 className="font-medium">
                      Vehículo {i + 1} de {phase.drafts.length}
                    </h2>
                    <Button type="button" variant="ghost" size="sm" onClick={() => update(i, { state: "discarded" })}>
                      <Trash2 aria-hidden /> Descartar este vehículo
                    </Button>
                  </div>
                ) : null}
                <SearchForm
                  catalog={catalog}
                  sources={sources}
                  initial={d.values}
                  profileId={null}
                  defaultOrigin={defaultOrigin}
                  idPrefix={single ? undefined : `draft-${i}`}
                  notes={d.notes}
                  origin={{ mode: "assisted", jobId: phase.jobId, stay: !single }}
                  onSaved={(id) => update(i, { state: "saved", savedId: id })}
                />
              </>
            )}
          </section>
        ))}
      </div>
    );
  }

  if (phase.kind === "failed") {
    return (
      <div className="space-y-4">
        <Alert variant={phase.reason === "manual" ? "default" : "destructive"} data-testid="assisted-fallback">
          <PenLine aria-hidden />
          <AlertTitle>
            {FALLBACK_TITLE[phase.reason]}
          </AlertTitle>
          <AlertDescription>
            <button
              type="button"
              className="inline-flex items-center gap-1 underline underline-offset-3"
              onClick={() => setPhase({ kind: "idle" })}
            >
              <RotateCcw className="size-3.5" aria-hidden /> Escribirlo de otra forma
            </button>
          </AlertDescription>
        </Alert>
        <SearchForm
          catalog={catalog}
          sources={sources}
          initial={base}
          profileId={null}
          defaultOrigin={defaultOrigin}
          origin={{ mode: "assisted_fallback", jobId: phase.jobId, stay: false }}
        />
      </div>
    );
  }

  const waiting = phase.kind === "waiting";
  return (
    <form onSubmit={submit} className="max-w-2xl">
      <Card>
        <CardHeader>
          <CardTitle>
            <Label htmlFor={textId} className="text-base">
              ¿Qué auto buscás?
            </Label>
          </CardTitle>
          <CardDescription>
            Escribilo como se lo contarías a alguien: modelo, versión, años, presupuesto, kilómetros, zona. Si buscás
            varios, nombralos todos. Revisás los filtros antes de guardar.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Textarea
            id={textId}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={ASSISTED_EXAMPLES[0]}
            maxLength={ASSISTED_MAX_CHARS}
            rows={3}
            disabled={waiting}
            aria-describedby={`${textId}-count`}
          />
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
            <span id={`${textId}-count`}>
              {text.length}/{ASSISTED_MAX_CHARS}
            </span>
          </div>
          {!text && !waiting ? (
            <div className="space-y-1.5">
              <p className="text-xs text-muted-foreground">Ejemplos:</p>
              <ul className="flex flex-col gap-1.5">
                {ASSISTED_EXAMPLES.map((example) => (
                  <li key={example}>
                    <button
                      type="button"
                      onClick={() => setText(example)}
                      className="w-full rounded-md bg-muted px-2.5 py-1.5 text-left text-sm hover:bg-muted/70"
                    >
                      «{example}»
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {error ? (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          ) : null}
          {waiting ? (
            <div role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" aria-hidden />
              Interpretando tu búsqueda… suele tardar entre 5 y 20 segundos.
            </div>
          ) : null}
          <div className="flex flex-wrap items-center gap-2">
            <Button type="submit" disabled={sending || waiting || text.trim().length < 3}>
              {sending || waiting ? <Loader2 className="animate-spin" aria-hidden /> : <Sparkles aria-hidden />}
              Interpretar
            </Button>
            {waiting ? (
              <Button
                type="button"
                variant="ghost"
                onClick={() => setPhase({ kind: "failed", jobId: phase.jobId, reason: "manual" })}
              >
                Completar el formulario a mano
              </Button>
            ) : null}
          </div>
        </CardContent>
      </Card>
    </form>
  );
}

function RequestSummary({ text, onEdit, children }: { text: string; onEdit: () => void; children: React.ReactNode }) {
  return (
    <div className="space-y-2 rounded-xl bg-card p-4 ring-1 ring-foreground/10">
      <div className="flex items-start justify-between gap-3">
        <blockquote className="text-sm italic">«{text.trim()}»</blockquote>
        <Button type="button" variant="ghost" size="sm" onClick={onEdit} className="shrink-0">
          <PenLine aria-hidden /> Editar
        </Button>
      </div>
      <p className="text-sm text-muted-foreground">{children}</p>
    </div>
  );
}

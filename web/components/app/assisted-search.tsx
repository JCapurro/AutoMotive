"use client";

import { Check, Loader2, PenLine, Plus, RotateCcw, Sparkles, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState, useTransition } from "react";
import { toast } from "sonner";

import { startAssisted } from "@/app/app/searches/actions";
import { SearchForm } from "@/components/app/search-form";
import { SearchPromptInput } from "@/components/search-prompt-input";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  ASSISTED_DEADLINE_MS,
  ASSISTED_MIN_CHARS,
  ASSISTED_MAX_VEHICLES,
  ASSISTED_POLL_MS,
  AssistedOutput,
  addedVehicle,
  draftTitle,
  draftToValues,
} from "@/lib/assisted";
import type { Catalog } from "@/lib/catalog";
import type { SearchValues } from "@/lib/search-form";
import type { DetectedLocation } from "@/lib/search-location";
import { createClient } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";

type Source = { id: string; name: string };

type Reviewed = {
  title: string;
  values: SearchValues;
  notes: string[];
  state: "pending" | "saved" | "discarded";
  savedId?: number;
  /** Added by the user on the review screen, not found in the text. */
  added?: boolean;
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
  initialText = "",
  approximateLocation = null,
}: {
  catalog: Catalog;
  sources: Source[];
  base: SearchValues;
  initialText?: string;
  approximateLocation?: DetectedLocation | null;
}) {
  const [text, setText] = useState(initialText);
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const [error, setError] = useState<string | null>(null);
  const [sending, startSending] = useTransition();
  const [supabase] = useState(createClient);
  const router = useRouter();
  const autoStarted = useRef(false);
  const requestInFlight = useRef(false);

  const sendPrompt = useCallback((prompt: string) => {
    if (requestInFlight.current) return;
    requestInFlight.current = true;
    setError(null);
    startSending(async () => {
      try {
        const result = await startAssisted(prompt);
        if (result.jobId != null) setPhase({ kind: "waiting", jobId: result.jobId });
        else if (result.unavailable) setPhase({ kind: "failed", jobId: null, reason: "unavailable" });
        else setError(result.error ?? "No pudimos enviar tu búsqueda.");
        // Consume the intent after sending it, so a refresh or tab change won't send it again.
        const url = new URL(window.location.href);
        if (url.searchParams.has("prompt")) {
          url.searchParams.delete("prompt");
          window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
        }
      } catch {
        setError("No pudimos enviar tu búsqueda. Probá de nuevo.");
      } finally {
        requestInFlight.current = false;
      }
    });
  }, [startSending]);

  useEffect(() => {
    if (!initialText || autoStarted.current) return;
    // Native history updates don't rerender the server page. Check the URL too
    // in case the assisted tab is remounted with its original server props.
    if (new URL(window.location.href).searchParams.get("prompt")?.trim() !== initialText) return;
    autoStarted.current = true;
    sendPrompt(initialText);
  }, [initialText, sendPrompt]);

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
    if (sending || phase.kind === "waiting") return;
    sendPrompt(text);
  }

  function update(index: number, patch: Partial<Reviewed>) {
    setPhase((prev) => {
      if (prev.kind !== "review") return prev;
      const drafts = prev.drafts.map((d, i) => (i === index ? { ...d, ...patch } : d));
      const next = drafts.findIndex((d) => d.state === "pending");
      return { ...prev, drafts, active: patch.state && patch.state !== "pending" && next >= 0 ? next : prev.active };
    });
  }

  // Another vehicle for the same request: the first proposal's shared filters, make and model to pick.
  function addVehicle() {
    setPhase((prev) => {
      if (prev.kind !== "review" || prev.drafts.length >= ASSISTED_MAX_VEHICLES) return prev;
      const n = prev.drafts.length + 1;
      const draft: Reviewed = {
        title: `Vehículo ${n}`,
        values: addedVehicle(prev.drafts[0].values),
        notes: ["Copiamos los años, kilómetros, precio y zona del pedido: elegí marca y modelo."],
        state: "pending",
        added: true,
      };
      return { ...prev, drafts: [...prev.drafts, draft], active: n - 1 };
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
    const found = phase.drafts.filter((d) => !d.added).length;
    const canAdd = phase.drafts.length < ASSISTED_MAX_VEHICLES;
    const addButton = canAdd ? (
      <Button type="button" size="sm" variant="ghost" onClick={addVehicle}>
        <Plus aria-hidden /> Agregar otro vehículo
      </Button>
    ) : null;
    return (
      <div className="space-y-4">
        <RequestSummary text={text} onEdit={() => setPhase({ kind: "idle" })}>
          {found === 1
            ? "Encontramos este vehículo en tu pedido. Revisá los filtros y corregí lo que haga falta antes de guardar."
            : `Encontramos ${found} vehículos: cada uno es una búsqueda. Revisalos y guardá los que quieras.`}
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
            {addButton}
          </nav>
        ) : (
          <div>{addButton}</div>
        )}

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
                  approximateLocation={approximateLocation}
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
          approximateLocation={approximateLocation}
          origin={{ mode: "assisted_fallback", jobId: phase.jobId, stay: false }}
        />
      </div>
    );
  }

  const waiting = phase.kind === "waiting";
  const busy = sending || waiting;
  return (
    <form onSubmit={submit} className="max-w-2xl">
      <Card>
        <CardContent className="space-y-3">
          <SearchPromptInput value={text} onChange={setText} disabled={busy} />
          {error ? (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          ) : null}
          {busy ? (
            <div role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin motion-reduce:animate-none" aria-hidden />
              Interpretando tu búsqueda… suele tardar entre 5 y 20 segundos.
            </div>
          ) : null}
          <div className="flex flex-wrap items-center gap-2">
            <Button type="submit" disabled={busy || text.trim().length < ASSISTED_MIN_CHARS}>
              {!busy ? <Sparkles aria-hidden /> : null}
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

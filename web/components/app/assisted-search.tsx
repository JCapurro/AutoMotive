"use client";

import { BellRing, Check, CircleAlert, Loader2, PenLine, Plus, RotateCcw, Sparkles, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState, useTransition } from "react";
import { toast } from "sonner";

import { type SaveResult, finishAssisted, saveSearch, startAssisted, trackAssistedView } from "@/app/app/searches/actions";
import { SearchForm } from "@/components/app/search-form";
import { SearchPromptInput } from "@/components/search-prompt-input";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import {
  ASSISTED_DEADLINE_MS,
  ASSISTED_MIN_CHARS,
  ASSISTED_MAX_VEHICLES,
  ASSISTED_POLL_MS,
  AssistedOutput,
  type SearchLimit,
  addedVehicle,
  afterParse,
  draftTitle,
  draftToValues,
  roomText,
  toggleChoice,
} from "@/lib/assisted";
import type { Catalog } from "@/lib/catalog";
import type { SearchValues } from "@/lib/search-form";
import type { DetectedLocation } from "@/lib/search-location";
import { autoSaveValues, sameProposal } from "@/lib/assisted-autosave";
import { roughDraft } from "@/lib/assisted-fallback";
import { analyticsEvent } from "@/lib/google-analytics";
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
  /** The worker matched it to the catalog (AssistedDraft.resolved). */
  resolved?: boolean;
};

type Phase =
  | { kind: "idle" }
  | { kind: "waiting"; jobId: number }
  /**
   * `error`: the autosave failed, so the proposal is back to review.
   * `repeated`: a rewritten request read exactly as the previous one.
   */
  | { kind: "review"; jobId: number; drafts: Reviewed[]; active: number; error?: string; repeated?: boolean }
  /** A single unambiguous proposal being saved without the user (lib/assisted-autosave.ts). */
  | { kind: "autosaving"; jobId: number; draft: Reviewed }
  /** …and saved: the form below edits that search. */
  | { kind: "active"; jobId: number; draft: Reviewed; savedId: number }
  /** More models than the plan has room for: pick which ones to review. */
  | { kind: "choose"; jobId: number; drafts: Reviewed[]; selected: number[] }
  /** The plan has no room for another active search. */
  | { kind: "full"; jobId: number; found: number }
  | { kind: "failed"; jobId: number | null; reason: FailReason };

/** Why the form took over: the job failed, its output didn't parse, no vehicle, the deadline, no worker. */
type FailReason = "error" | "invalid" | "empty" | "timeout" | "unavailable";

type JobRow = { status: string; output: unknown };

// Sección 8.4, paso 6: the structured form takes over.
const UNREAD = "No pudimos leer tu descripción automáticamente. Revisá y completá los datos del auto abajo.";
const FALLBACK_TITLE: Record<FailReason, string> = {
  error: UNREAD,
  invalid: UNREAD,
  timeout: UNREAD,
  empty: "No encontramos una marca y modelo en tu descripción. Completá los datos del auto abajo.",
  unavailable: UNREAD,
};

const AUTOSAVE_FAILED = "No pudimos activar tu búsqueda automáticamente. Revisala y tocá «Crear búsqueda».";

/**
 * Modo asistido (§12, sección 8.4): the user writes what they want, the
 * worker's LLM proposes one search per vehicle, and each proposal opens as a
 * pre-filled structured form to correct and confirm. If the LLM fails, times
 * out or finds no vehicle, the empty structured form takes over. With
 * enforced plan limits (`limit`), a request with more models than the plan's
 * room first asks which ones to activate. A single proposal without doubts is
 * saved at once (autosave) and the form below adjusts the saved search.
 */
export function AssistedSearch({
  catalog,
  sources,
  base,
  initialText = "",
  approximateLocation = null,
  limit = null,
  thresholdAlerts = false,
  modelLessSearch = false,
}: {
  catalog: Catalog;
  sources: Source[];
  base: SearchValues;
  initialText?: string;
  approximateLocation?: DetectedLocation | null;
  limit?: SearchLimit | null;
  /** The plan's features, for every form below (as the structured tab's). */
  thresholdAlerts?: boolean;
  modelLessSearch?: boolean;
}) {
  const [text, setText] = useState(initialText);
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const [error, setError] = useState<string | null>(null);
  const [sending, startSending] = useTransition();
  const [supabase] = useState(createClient);
  const router = useRouter();
  const autoStarted = useRef(false);
  const requestInFlight = useRef(false);
  // Jobs already autosaved and screens already recorded: StrictMode and re-renders run effects twice.
  const autosaved = useRef(new Set<number>());
  const tracked = useRef(new Set<string>());
  // What the last review proposed, to notice a rewritten request read the same way.
  const lastProposal = useRef<SearchValues[] | null>(null);
  const reviewRef = useRef<HTMLDivElement>(null);
  // The review form's own button on screen: the sticky one (mobile) steps aside.
  const [formButtonVisible, setFormButtonVisible] = useState(false);

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
        setPhase({ kind: "failed", jobId: waitingJob, reason: "invalid" });
      } else if (!parsed.data.drafts.length) {
        setPhase({ kind: "failed", jobId: waitingJob, reason: "empty" });
      } else {
        const drafts: Reviewed[] = parsed.data.drafts.map((draft, i) => ({
          title: draftTitle(draft, i),
          ...draftToValues(draft, base, modelLessSearch),
          state: "pending",
          resolved: draft.resolved,
        }));
        const next = afterParse(drafts.length, limit);
        const auto = next === "review" && drafts.length === 1
          ? autoSaveValues({ drafts: parsed.data.drafts, values: drafts[0].values, notes: drafts[0].notes, catalog, limit, approximateLocation })
          : null;
        if (auto) {
          setPhase({ kind: "autosaving", jobId: waitingJob, draft: drafts[0] });
          void autoSave(waitingJob, drafts[0], auto);
        } else if (next === "choose") setPhase({ kind: "choose", jobId: waitingJob, drafts, selected: [] });
        else if (next === "full") {
          setPhase({ kind: "full", jobId: waitingJob, found: drafts.length });
          void finishAssisted(waitingJob);
        } else {
          const proposal = drafts.map((d) => d.values);
          const previous = lastProposal.current;
          const repeated = previous != null && previous.length === proposal.length && proposal.every((v, i) => sameProposal(v, previous[i]));
          lastProposal.current = proposal;
          setPhase({ kind: "review", jobId: waitingJob, active: 0, drafts, repeated });
        }
      }
    };

    // Once per job, whatever the re-renders. A refusal (or a network error) goes back to the review with the reason.
    // `auto`: what autoSaveValues settled (the zone it placed and its note); a refusal reviews the draft as it came.
    const autoSave = async (jobId: number, draft: Reviewed, { values, notes }: { values: SearchValues; notes: string[] }) => {
      if (autosaved.current.has(jobId)) return;
      autosaved.current.add(jobId);
      let result: SaveResult;
      try {
        result = await saveSearch(null, values, { mode: "assisted_auto", jobId, edited: false, stay: true });
      } catch {
        result = { error: AUTOSAVE_FAILED };
      }
      if (result.savedId != null) {
        analyticsEvent("search", { search_type: "assisted" });
        analyticsEvent("search_created", { search_type: "assisted" });
        setPhase({ kind: "active", jobId, draft: { ...draft, values, notes, state: "saved", savedId: result.savedId }, savedId: result.savedId });
        void finishAssisted(jobId);
      } else {
        lastProposal.current = [draft.values];
        setPhase({ kind: "review", jobId, active: 0, drafts: [draft], error: result.error ?? AUTOSAVE_FAILED });
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
      setPhase({ kind: "failed", jobId: waitingJob, reason: "timeout" });
    }, ASSISTED_DEADLINE_MS);

    return () => {
      settled = true;
      clearInterval(interval);
      clearTimeout(deadline);
      if (channel) void supabase.removeChannel(channel);
    };
  }, [waitingJob, supabase, base, limit, modelLessSearch, catalog, approximateLocation]);

  // Medición (sección 8.4): what each request ended up showing, once per job and screen.
  const shownKey = phase.kind === "review" || phase.kind === "active" || phase.kind === "choose" || phase.kind === "full"
    ? `review:${phase.jobId}`
    : phase.kind === "failed" ? `fallback:${phase.jobId ?? "none"}:${phase.reason}` : null;
  useEffect(() => {
    if (!shownKey || tracked.current.has(shownKey)) return;
    tracked.current.add(shownKey);
    if (phase.kind === "failed") {
      void trackAssistedView(phase.jobId, { name: "assisted_fallback_shown", reason: phase.reason });
      return;
    }
    if (phase.kind !== "review" && phase.kind !== "active" && phase.kind !== "choose") return;
    const drafts = phase.kind === "active" ? [phase.draft] : phase.drafts;
    void trackAssistedView(phase.jobId, {
      name: "assisted_review_shown",
      drafts: drafts.length,
      resolved: drafts.filter((d) => d.resolved).length,
      values: drafts.length === 1 ? drafts[0].values : undefined,
      autosaved: phase.kind === "active",
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per screen: shownKey names it
  }, [shownKey]);

  // The same proposal again: point at the button that's missing.
  const repeatedJob = phase.kind === "review" && phase.repeated ? phase.jobId : null;
  useEffect(() => {
    if (repeatedJob == null) return;
    const button = reviewRef.current?.querySelector<HTMLButtonElement>("section:not([hidden]) form button[type=submit]");
    button?.scrollIntoView({ behavior: "smooth", block: "center" });
    button?.focus({ preventScroll: true });
  }, [repeatedJob]);

  const reviewedDraft = phase.kind === "review" ? `${phase.jobId}:${phase.active}:${phase.drafts[phase.active]?.state}` : null;
  useEffect(() => {
    if (reviewedDraft == null) return;
    const button = reviewRef.current?.querySelector("section:not([hidden]) form button[type=submit]");
    if (!button || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(([entry]) => setFormButtonVisible(entry.isIntersecting));
    observer.observe(button);
    return () => observer.disconnect();
  }, [reviewedDraft]);

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
  const reviewJob = review?.jobId ?? null;
  useEffect(() => {
    if (!done) return;
    if (reviewJob != null) void finishAssisted(reviewJob);
    if (savedCount) {
      toast(savedCount === 1 ? "Guardamos tu búsqueda" : `Guardamos tus ${savedCount} búsquedas`);
      router.push("/app");
    }
  }, [done, savedCount, reviewJob, router]);

  if (phase.kind === "autosaving") {
    return (
      <div className="space-y-4">
        <RequestSummary text={text} onEdit={() => setPhase({ kind: "idle" })}>
          Encontramos «{phase.draft.title}» en tu pedido.
        </RequestSummary>
        <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin motion-reduce:animate-none" aria-hidden /> Activando tu búsqueda…
        </p>
      </div>
    );
  }

  if (phase.kind === "active") {
    return (
      <div className="space-y-4">
        <Alert data-testid="assisted-active">
          <BellRing aria-hidden />
          <AlertTitle>Tu búsqueda ya está activa</AlertTitle>
          <AlertDescription>
            <p>
              Te avisamos cuando aparezca un «{phase.draft.title}» que coincida. Si querés ajustar algo, cambialo abajo y
              tocá «Guardar cambios».
            </p>
            <p>
              <Link href={`/app/searches/${phase.savedId}`} className="font-medium underline underline-offset-3">
                Ver la búsqueda
              </Link>
            </p>
          </AlertDescription>
        </Alert>
        <RequestSummary text={text} onEdit={() => setPhase({ kind: "idle" })}>
          Así leímos tu pedido. Escribir otro crea una búsqueda nueva.
        </RequestSummary>
        <SearchForm
          catalog={catalog}
          sources={sources}
          initial={phase.draft.values}
          profileId={phase.savedId}
          approximateLocation={approximateLocation}
          notes={phase.draft.notes}
          thresholdAlerts={thresholdAlerts}
          modelLessSearch={modelLessSearch}
        />
      </div>
    );
  }

  if (phase.kind === "review") {
    const single = phase.drafts.length === 1;
    const found = phase.drafts.filter((d) => !d.added).length;
    const room = Math.min(limit?.capacity ?? ASSISTED_MAX_VEHICLES, ASSISTED_MAX_VEHICLES);
    const canAdd = phase.drafts.length < ASSISTED_MAX_VEHICLES && phase.drafts.filter((d) => d.state !== "discarded").length < room;
    const addButton = canAdd ? (
      <Button type="button" size="sm" variant="ghost" onClick={addVehicle}>
        <Plus aria-hidden /> Agregar otro vehículo
      </Button>
    ) : null;
    // Mobile: the form's own button is below every field; this one is always at hand.
    const submitActive = () =>
      reviewRef.current?.querySelector<HTMLFormElement>("section:not([hidden]) form")?.requestSubmit();
    const pending = phase.drafts[phase.active]?.state === "pending";
    return (
      <div ref={reviewRef} className="space-y-4 pb-20 lg:pb-0">
        <Alert data-testid="assisted-step-left" variant={phase.error ? "destructive" : "default"}>
          {phase.error ? <CircleAlert aria-hidden /> : <BellRing aria-hidden />}
          <AlertTitle>{phase.error ?? "Falta un paso: guardá para activar las alertas"}</AlertTitle>
          {phase.repeated ? (
            <AlertDescription data-testid="assisted-repeated">
              Leímos tu pedido igual que la vez anterior: la búsqueda ya está lista, solo falta guardarla.
            </AlertDescription>
          ) : phase.error ? (
            <AlertDescription>Falta un paso: guardá para activar las alertas.</AlertDescription>
          ) : null}
        </Alert>
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
                  thresholdAlerts={thresholdAlerts}
                  modelLessSearch={modelLessSearch}
                />
              </>
            )}
          </section>
        ))}

        {pending && !formButtonVisible ? (
          <div className="fixed inset-x-0 bottom-[calc(3.75rem+env(safe-area-inset-bottom))] z-30 border-t bg-background/95 p-3 backdrop-blur md:bottom-0 lg:hidden">
            <Button type="button" className="h-11 w-full text-base" onClick={submitActive} data-testid="assisted-sticky-save">
              Guardar y activar alertas
            </Button>
          </div>
        ) : null}
      </div>
    );
  }

  if (phase.kind === "choose" && limit) {
    return (
      <ModelChoice
        text={text}
        onEdit={() => setPhase({ kind: "idle" })}
        limit={limit}
        titles={phase.drafts.map((d) => d.title)}
        selected={phase.selected}
        onToggle={(i) => setPhase({ ...phase, selected: toggleChoice(phase.selected, i, limit.capacity) })}
        onContinue={() => setPhase({
          kind: "review",
          jobId: phase.jobId,
          active: 0,
          drafts: [...phase.selected].sort((a, b) => a - b).map((i) => phase.drafts[i]),
        })}
      />
    );
  }

  if (phase.kind === "full" && limit) {
    return <PlanFull text={text} onEdit={() => setPhase({ kind: "idle" })} limit={limit} found={phase.found} />;
  }

  if (phase.kind === "failed") {
    // What could be read from the text without the interpreter: the user corrects instead of starting over.
    const rough = roughDraft(text, catalog);
    return (
      <div className="space-y-4">
        <Alert data-testid="assisted-fallback">
          <PenLine aria-hidden />
          <AlertTitle>
            {Object.keys(rough).length ? "Completamos lo que pudimos de tu descripción. Revisá los datos del auto abajo." : FALLBACK_TITLE[phase.reason]}
          </AlertTitle>
          <AlertDescription>
            {text.trim() ? <p className="[overflow-wrap:anywhere]">Escribiste: «{text.trim()}»</p> : null}
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
          initial={{ ...base, ...rough }}
          profileId={null}
          approximateLocation={approximateLocation}
          origin={{ mode: "assisted_fallback", jobId: phase.jobId, stay: false }}
          thresholdAlerts={thresholdAlerts}
          modelLessSearch={modelLessSearch}
        />
      </div>
    );
  }

  const busy = sending || phase.kind === "waiting";
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
          <div className="flex flex-wrap items-center gap-2">
            <Button type="submit" disabled={busy || text.trim().length < ASSISTED_MIN_CHARS}>
              <Sparkles aria-hidden />
              Interpretar
            </Button>
          </div>
        </CardContent>
      </Card>
      <Dialog open={busy}>
        <DialogContent
          showCloseButton={false}
          onEscapeKeyDown={(e) => e.preventDefault()}
          onInteractOutside={(e) => e.preventDefault()}
          className="justify-items-center gap-3 py-8 text-center sm:max-w-xs"
        >
          <Loader2 className="size-8 animate-spin text-primary motion-reduce:animate-none" aria-hidden />
          <div role="status" className="space-y-1">
            <DialogTitle>Interpretando tu búsqueda…</DialogTitle>
            <DialogDescription>Un momento, estamos armando los filtros.</DialogDescription>
          </div>
        </DialogContent>
      </Dialog>
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

/** More models than the plan's room: the detected ones, to pick which to activate. */
export function ModelChoice({ text, onEdit, limit, titles, selected, onToggle, onContinue }: {
  text: string;
  onEdit: () => void;
  limit: SearchLimit;
  titles: string[];
  selected: number[];
  onToggle: (index: number) => void;
  onContinue: () => void;
}) {
  const one = limit.capacity === 1;
  return (
    <div className="space-y-4">
      <RequestSummary text={text} onEdit={onEdit}>
        Encontramos {titles.length} modelos en tu pedido. Cada modelo es una búsqueda y {roomText(limit)}
      </RequestSummary>
      <form
        className="max-w-2xl space-y-4 rounded-xl bg-card p-4 ring-1 ring-foreground/10"
        onSubmit={(e) => {
          e.preventDefault();
          if (selected.length) onContinue();
        }}
      >
        <fieldset className="space-y-2.5">
          <legend className="mb-1 text-sm font-medium">
            {one ? "Elegí cuál querés activar" : `Elegí cuáles querés activar (hasta ${limit.capacity})`}
          </legend>
          {titles.map((title, i) => (
            <label key={i} className="flex items-center gap-2.5 text-sm">
              <input
                type={one ? "radio" : "checkbox"}
                name="assisted-model"
                value={i}
                checked={selected.includes(i)}
                disabled={!one && !selected.includes(i) && selected.length >= limit.capacity}
                onChange={() => onToggle(i)}
                className="size-4 accent-primary"
              />
              {title}
            </label>
          ))}
        </fieldset>
        {limit.upsell ? (
          <p className="text-sm text-muted-foreground">
            {limit.upsell}{" "}
            <Link href="/app/pro?plan=pass_30" className="font-medium underline underline-offset-3">Ver planes</Link>
          </p>
        ) : null}
        <Button type="submit" disabled={!selected.length}>Continuar</Button>
      </form>
    </div>
  );
}

/** The plan's active searches are all in use. */
export function PlanFull({ text, onEdit, limit, found }: { text: string; onEdit: () => void; limit: SearchLimit; found: number }) {
  const active = limit.activeSearches === 1 ? "una búsqueda activa" : `${limit.activeSearches} búsquedas activas`;
  return (
    <div className="space-y-4">
      <RequestSummary text={text} onEdit={onEdit}>
        Encontramos {found === 1 ? "un modelo" : `${found} modelos`} en tu pedido, pero ya tenés {active}: el máximo de tu plan.
      </RequestSummary>
      <Alert data-testid="assisted-plan-full">
        <AlertTitle>Para activar otra búsqueda, pausá una de las que tenés.</AlertTitle>
        <AlertDescription>
          {limit.upsell ? <p>{limit.upsell}</p> : null}
          <p>
            <Link href="/app" className="underline underline-offset-3">Ver mis búsquedas</Link>
            {" · "}
            <Link href="/app/pro" className="underline underline-offset-3">Ver planes</Link>
          </p>
        </AlertDescription>
      </Alert>
    </div>
  );
}

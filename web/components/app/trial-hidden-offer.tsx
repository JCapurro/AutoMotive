"use client";

import { MessageSquare, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Fragment, lazy, Suspense, useEffect, useId, useRef, useState, useTransition } from "react";

import { trackTrialOffer } from "@/app/app/pro/actions";
import { startPayment } from "@/app/app/pro/billing-actions";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { analyticsEvent } from "@/lib/google-analytics";
import { pixel } from "@/lib/meta-pixel";
import { OFFER_DAYS, PASS_GUARANTEE, PLAN_COPY, PLAN_NAMES, planPrice, type PassOffer, type ProOffer } from "@/lib/pro";
import { cardLead, cardTitle, COMPLETE_BADGE, COMPLETE_STRIP_BUTTON, completeKeepLabel, completeLead, completePayLabel, completeStripText, completeTitle, keepLabel, NOTICE_KEEP_LABEL, noticeSheetLead, noticeSheetTitle, noticeStripText, opensSheet, payLabel, seeAllLabel, type Segment, sheetLead, sheetTitle, stripText, type TrialOffer, type TrialOfferSurface } from "@/lib/trial-offer";
import { cn } from "@/lib/utils";

/**
 * Oferta cuando la prueba oculta autos (docs/OFERTA_PRUEBA.md). The trial
 * shows part of what matches (the reserve: at most 30 already published); this
 * is where the page says so and offers the pass, in the first minutes:
 *   - a sheet that opens by itself, once per search (TrialHiddenOffer);
 *   - a strip above the list, which opens it again (TrialHiddenOffer);
 *   - a card at the end of the list (TrialHiddenCard).
 * Only counts come from the server: nothing of a hidden listing is here.
 *
 * Notice mode (docs/PRUEBA_COMPLETA.md): the texts say how many match, not
 * what the trial shows, and the sheet never opens by itself until the quota
 * fills (`complete`, the limit); then it opens once per tab session and search
 * in its "complete" variant, which takes the place of FreeResultLimit, and the
 * strip reopens it.
 */
export type TrialCheckout = { offer: ProOffer; automatic: boolean };

/** The complete variant's «Enviar feedback», loaded only when it is used (its action is server-side). */
const ProductFeedback = lazy(() => import("@/components/app/product-feedback").then((m) => ({ default: m.ProductFeedback })));

const PASSES = ["pass_7", "pass_30"] as const satisfies readonly PassOffer[];

function stored(key: string): boolean {
  try { return window.localStorage.getItem(key) === "1"; } catch { return false; }
}
function store(key: string) {
  try { window.localStorage.setItem(key, "1"); } catch { /* no storage: the in-memory set below still holds for this visit */ }
}
/** Searches whose sheet already opened in this page session, for browsers without storage. */
const opened = new Set<number>();
/** The same for the complete variant, which opens once per tab session (sessionStorage). */
const completeOpened = new Set<number>();
function sessionStored(key: string): boolean {
  try { return window.sessionStorage.getItem(key) === "1"; } catch { return false; }
}
function sessionStore(key: string) {
  try { window.sessionStorage.setItem(key, "1"); } catch { /* no storage: completeOpened holds for this visit */ }
}

/** What the events carry: the counts the person saw, and `complete: true` for the complete variant. */
function eventCounts(offer: TrialOffer, complete: boolean) {
  return complete ? { shown: offer.shown, hidden: offer.hidden, complete: true } : { shown: offer.shown, hidden: offer.hidden };
}

/** A surface was seen: once per tab session, search and surface (and variant). */
function recordView(profileId: number, surface: TrialOfferSurface, offer: TrialOffer, complete = false) {
  const key = `ea_trial_offer_viewed:${surface}:${profileId}${complete ? ":complete" : ""}`;
  try {
    if (sessionStorage.getItem(key)) return;
    sessionStorage.setItem(key, "1");
  } catch {
    // No storage (private mode): count it every time rather than never.
  }
  void trackTrialOffer("viewed", profileId, surface, eventCounts(offer, complete));
}

function Marked({ segments, className = "mark font-semibold text-foreground" }: { segments: Segment[]; className?: string }) {
  return <>{segments.map((segment, i) => typeof segment === "string"
    ? <Fragment key={i}>{segment}</Fragment>
    : <b key={i} className={className}>{segment.mark}</b>)}</>;
}

/**
 * A pass, one tap from Mercado Pago (as ExpiredMissed). An account that entered
 * with just its email proves it first (/app/cuenta: a code, no password) and
 * goes on to the checkout from there.
 */
function usePassCheckout(profileId: number, offer: TrialOffer, surface: TrialOfferSurface, { offer: prices, automatic }: TrialCheckout, complete = false) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [selected, setSelected] = useState<PassOffer | null>(null);
  const [error, setError] = useState<string | null>(null);

  function choose(plan: PassOffer) {
    void trackTrialOffer("plan_selected", profileId, surface, eventCounts(offer, complete), plan);
    if (!automatic) { router.push(`/app/pro?plan=${plan}&from=results`); return; }
    setSelected(plan);
    setError(null);
    start(async () => {
      try {
        const result = await startPayment(plan, true, prices.version, prices[plan].amount);
        if (result.needsAccount) router.push(`/app/cuenta?${new URLSearchParams({ next: `/app/pro?plan=${plan}` })}`);
        else if (result.error) setError(result.error);
        else if (result.url) {
          pixel("InitiateCheckout", { content_ids: [plan], value: prices[plan].amount, currency: prices[plan].currency });
          analyticsEvent("begin_checkout", { currency: prices[plan].currency, value: prices[plan].amount, items: [{ item_id: plan, item_name: PLAN_COPY[plan].name }] });
          window.location.assign(result.url);
        }
      } catch {
        setError("No pudimos continuar. Probá de nuevo en unos segundos.");
      }
    });
  }
  return { choose, pending, selected, error };
}

function Terms({ automatic }: { automatic: boolean }) {
  return automatic
    ? <>Pagás en Mercado Pago, sin renovación automática. Al elegir un pase aceptás los <a href="/terminos" target="_blank" rel="noreferrer" className="underline underline-offset-2">Términos y condiciones</a>.</>
    : <>Pago único, sin renovación automática. Coordinamos el pago y la activación.</>;
}

/**
 * The sheet's pass: the 7 days first (the lower step, Juan 14/11), the 30 one
 * tap away on the toggle, the guarantee, and the button to the checkout.
 */
export function TrialPassChoice({ offer, checkout, pending, error, onPay, label = payLabel }: {
  offer: TrialOffer; checkout: TrialCheckout; pending: boolean; error: string | null; onPay: (plan: PassOffer) => void;
  /** The pay button's text (completePayLabel in the complete variant). */
  label?: (offer: TrialOffer, days: number, price: string) => string;
}) {
  const id = useId();
  const [pass, setPass] = useState<PassOffer>("pass_7");
  const days = OFFER_DAYS[pass];
  const price = planPrice(checkout.offer[pass].amount);
  return <>
    <section aria-labelledby={`${id}-pass`} className="mt-4 rounded-lg border-2 border-foreground p-3.5">
      <div className="flex items-center justify-between gap-3">
        <h3 id={`${id}-pass`} className="text-base font-bold">{PLAN_NAMES.pass}</h3>
        <div role="group" aria-label="Duración del pase" className="grid grid-cols-2 gap-0.5 rounded-lg bg-muted p-[3px]">
          {PASSES.map((plan) => (
            <button key={plan} type="button" aria-pressed={plan === pass} onClick={() => setPass(plan)}
              className={cn("h-8 rounded-md px-3.5 text-sm font-medium transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring",
                plan === pass ? "bg-background text-foreground shadow-[0_0_0_1px_var(--border)]" : "text-muted-foreground hover:text-foreground")}>
              {OFFER_DAYS[plan]} días
            </button>
          ))}
        </div>
      </div>
      <p className="mt-3 flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="type-figure text-[26px] leading-none">{price}</span>
        <span className="text-xs font-medium text-muted-foreground">ARS</span>
        <span id={`${id}-terms`} className="text-xs text-muted-foreground">pago único por {days} días</span>
      </p>
      <p id={`${id}-guarantee`} className="mt-2.5 flex items-start gap-2 text-xs font-medium"><ShieldCheck className="size-4 shrink-0" aria-hidden />{PASS_GUARANTEE}</p>
    </section>
    <Button type="button" className="mt-3 h-12 w-full whitespace-normal text-base" aria-describedby={`${id}-terms ${id}-guarantee`} disabled={pending} onClick={() => onPay(pass)}>
      {pending ? "Abriendo…" : label(offer, days, price)}
    </Button>
    {error ? <p role="alert" className="mt-2 text-sm text-destructive">{error}</p> : null}
  </>;
}

/**
 * The strip and the sheet. `autoOpen`: the search is ready and nothing else is
 * asking for attention; then the sheet opens by itself the first time this
 * browser sees the search hide enough (opensSheet), and never again.
 * `notice`: notice mode, before the quota fills: its texts, and no opening by itself.
 * `complete`: the trial's limit, once the quota filled (notice mode); the
 * complete variant then opens with autoOpen once per tab session and search.
 */
export function TrialHiddenOffer({ profileId, offer, autoOpen, checkout, notice = false, complete = null }: {
  profileId: number; offer: TrialOffer; autoOpen: boolean; checkout: TrialCheckout; notice?: boolean; complete?: number | null;
}) {
  const done = complete != null;
  const [open, setOpen] = useState(false);
  const [feedback, setFeedback] = useState(false);
  const chosen = useRef(false);
  const content = useRef<HTMLDivElement>(null);
  const { choose, pending, error } = usePassCheckout(profileId, offer, "sheet", checkout, done);
  const opens = autoOpen && (done || (!notice && opensSheet(offer)));
  const counts = useRef(offer);
  useEffect(() => { counts.current = offer; });

  useEffect(() => { recordView(profileId, "strip", counts.current, done); }, [profileId, done]);
  useEffect(() => {
    if (!opens) return;
    if (done) {
      const key = `ea_trial_complete_opened:${profileId}`;
      if (completeOpened.has(profileId) || sessionStored(key)) return;
      completeOpened.add(profileId);
      sessionStore(key);
    } else {
      const key = `ea_trial_offer_opened:${profileId}`;
      if (opened.has(profileId) || stored(key)) return;
      opened.add(profileId);
      store(key);
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect -- read once after hydration: storage is the browser's
    setOpen(true);
  }, [opens, done, profileId]);
  useEffect(() => { if (open) recordView(profileId, "sheet", counts.current, done); }, [open, profileId, done]);

  function changeOpen(next: boolean) {
    // Closing without having picked a pass is the signal; picking one navigates away.
    if (!next && open && !chosen.current) void trackTrialOffer("dismissed", profileId, "sheet", eventCounts(offer, done));
    if (!next) setFeedback(false);
    setOpen(next);
  }
  function pay(plan: PassOffer) {
    chosen.current = true;
    choose(plan);
  }

  return <>
    <aside aria-label="Lo que tu prueba no muestra" data-testid="trial-offer-strip" className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 rounded-lg bg-muted px-4 py-3 text-sm">
      <p className="min-w-0 flex-1 basis-56"><Marked segments={done ? completeStripText(complete) : notice ? noticeStripText(offer) : stripText(offer)} className="font-semibold" /></p>
      <Button size="sm" className="h-9 px-3.5" onClick={() => setOpen(true)}>{done ? COMPLETE_STRIP_BUTTON : seeAllLabel(offer)}</Button>
    </aside>
    <Dialog open={open} onOpenChange={changeOpen}>
      {/* Centered from sm up; on a phone, a sheet from the bottom (as FreeResultLimit). */}
      {/* Focus the dialog itself, not the first button: «7 días» would look chosen twice. */}
      <DialogContent data-testid="trial-offer-sheet" ref={content} onOpenAutoFocus={(event) => { event.preventDefault(); content.current?.focus(); }}
        className="flex max-h-[calc(100dvh-2rem)] flex-col gap-0 overflow-hidden rounded-2xl p-0 sm:max-w-[520px] max-sm:top-auto max-sm:bottom-0 max-sm:left-0 max-sm:max-h-[92dvh] max-sm:max-w-none max-sm:translate-x-0 max-sm:translate-y-0 max-sm:rounded-b-none">
        <div aria-hidden className="mx-auto mt-2.5 h-1 w-10 shrink-0 rounded-full bg-border sm:hidden" />
        <div className="min-h-0 flex-1 overflow-y-auto px-5 pt-4 pb-[max(1rem,env(safe-area-inset-bottom))] sm:px-7 sm:pt-7 sm:pb-6">
          <DialogHeader className="gap-2.5">
            <span className="inline-flex w-fit items-center gap-1.5 rounded-full bg-muted px-2.5 py-1 text-xs font-medium text-muted-foreground">
              {feedback ? <><MessageSquare className="size-3.5" aria-hidden /> Tu experiencia</> : done ? COMPLETE_BADGE : "Prueba gratis"}
            </span>
            <DialogTitle className="max-w-[20ch] pr-6 text-2xl leading-[1.12] font-semibold tracking-tight sm:text-[28px]">
              {feedback ? "¿Qué podemos mejorar?" : done ? completeTitle(complete) : notice ? noticeSheetTitle(offer) : sheetTitle(offer)}
            </DialogTitle>
            <DialogDescription className="text-[15px] leading-relaxed">
              {feedback ? "Contanos qué te faltó, qué no funcionó o qué te gustaría encontrar en Ese Auto." : <Marked segments={done ? completeLead() : notice ? noticeSheetLead(offer) : sheetLead(offer)} />}
            </DialogDescription>
          </DialogHeader>
          {feedback ? <div className="mt-4"><Suspense fallback={null}><ProductFeedback profileId={profileId} onBack={() => setFeedback(false)} /></Suspense></div> : <>
            <TrialPassChoice offer={offer} checkout={checkout} pending={pending} error={error} onPay={pay} label={done ? completePayLabel : payLabel} />
            <Button type="button" variant="ghost" className="mt-1 h-11 w-full text-muted-foreground" onClick={() => changeOpen(false)}>{done ? completeKeepLabel() : notice ? NOTICE_KEEP_LABEL : keepLabel(offer)}</Button>
            {/* The pop-up it replaces (FreeResultLimit) asks for feedback too. */}
            {done ? <Button type="button" variant="link" className="h-9 w-full gap-2 text-xs text-muted-foreground" onClick={() => setFeedback(true)}><MessageSquare className="size-3.5" aria-hidden /> Enviar feedback</Button> : null}
            <p className="text-center text-xs leading-relaxed text-muted-foreground">
              <Terms automatic={checkout.automatic} />{" "}
              <Link href="/app/pro?plan=pro_monthly&from=results" className="underline underline-offset-2">¿Comprás y vendés autos? Mirá Pro</Link>.
            </p>
          </>}
        </div>
      </DialogContent>
    </Dialog>
  </>;
}

/**
 * The card where the list ends: what the trial shows, what it doesn't, and both passes.
 * `plain`: notice mode or a random sample of what was published: the lead says only what Particular gives (cardLead).
 */
export function TrialHiddenCard({ profileId, offer, checkout, plain = false }: { profileId: number; offer: TrialOffer; checkout: TrialCheckout; plain?: boolean }) {
  const id = useId();
  const ref = useRef<HTMLElement>(null);
  const { choose, pending, selected, error } = usePassCheckout(profileId, offer, "card", checkout);
  const counts = useRef(offer);
  useEffect(() => { counts.current = offer; });

  // Seen when it reaches the screen: how many people get to the end of the list.
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    if (typeof IntersectionObserver === "undefined") { recordView(profileId, "card", counts.current); return; }
    const observer = new IntersectionObserver((entries) => {
      if (!entries.some((entry) => entry.isIntersecting)) return;
      observer.disconnect();
      recordView(profileId, "card", counts.current);
    }, { threshold: 0.5 });
    observer.observe(node);
    return () => observer.disconnect();
  }, [profileId]);

  return <section ref={ref} aria-labelledby={`${id}-title`} data-testid="trial-hidden" className="rounded-xl border-2 border-foreground p-5">
    <h2 id={`${id}-title`} className="type-heading text-[22px] leading-tight"><Marked segments={cardTitle(offer)} className="mark" /></h2>
    <p className="mt-2 text-muted-foreground">{cardLead(offer, plain)}</p>
    <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:flex-wrap">
      {PASSES.map((plan, i) => {
        const price = planPrice(checkout.offer[plan].amount);
        return <Button key={plan} type="button" variant={i === 0 ? "default" : "outline"} className="h-11 whitespace-normal px-4.5 text-[15px]" disabled={pending} onClick={() => choose(plan)}>
          {pending && selected === plan ? "Abriendo…" : i === 0 ? payLabel(offer, OFFER_DAYS[plan], price) : `${OFFER_DAYS[plan]} días por ${price}`}
        </Button>;
      })}
    </div>
    {error ? <p role="alert" className="mt-2 text-sm text-destructive">{error}</p> : null}
    <p className="mt-3 flex items-start gap-2 text-xs font-medium"><ShieldCheck className="size-4 shrink-0" aria-hidden />{PASS_GUARANTEE}</p>
    <p className="mt-2 text-xs leading-relaxed text-muted-foreground"><Terms automatic={checkout.automatic} /></p>
  </section>;
}

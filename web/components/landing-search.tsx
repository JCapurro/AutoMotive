"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useId, useRef, useState, useSyncExternalStore, useTransition } from "react";

import { codeForFreeSearch, enterForFreeSearch, type FreeSearchResult, linkForFreeSearch, startFreeSearch } from "@/app/actions";
import { LandingBuilder } from "@/components/landing-builder";
import { type LandingHow, logLandingEvent } from "@/components/landing-events";
import { SearchPromptInput } from "@/components/search-prompt-input";
import { createClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ASSISTED_MIN_CHARS } from "@/lib/assisted";
import { emailSuggestion } from "@/lib/email-typos";
import { analyticsEvent } from "@/lib/google-analytics";
import { type Builder, builderPrompt, EMPTY_BUILDER, type HeroVariant } from "@/lib/landing-hero";
import { pixel } from "@/lib/meta-pixel";
import { searchStartHref } from "@/lib/search-intent";

const OFFLINE = "No pudimos conectarnos. Revisá tu conexión y probá de nuevo.";
const noop = () => () => {};
const RESUME_KEY = "ea_signup_code";

/**
 * This browser's signup code (startFreeSearch's `resume`): if a reload eats
 * the answer, the retry from here gets the session instead of a link. Kept
 * until a signup succeeds; without storage there is simply no resume.
 */
function signupCode(): string | undefined {
  try {
    let code = localStorage.getItem(RESUME_KEY);
    if (!code) {
      const bytes = crypto.getRandomValues(new Uint8Array(24));
      code = btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
      localStorage.setItem(RESUME_KEY, code);
    }
    return code;
  } catch {
    return undefined;
  }
}

function forgetSignupCode() {
  try {
    localStorage.removeItem(RESUME_KEY);
  } catch {}
}

/**
 * Whether this browser has a session, read from the cookie on the client
 * (PAR-04: the guide pages are static and never read the session on the
 * server). null until known.
 */
function useClientSession(skip: boolean): boolean | null {
  const [signedIn, setSignedIn] = useState<boolean | null>(null);
  useEffect(() => {
    if (skip) return;
    let live = true;
    createClient().auth.getSession()
      .then(({ data }) => { if (live) setSignedIn(Boolean(data.session)); })
      .catch(() => { if (live) setSignedIn(false); });
    return () => { live = false; };
  }, [skip]);
  return signedIn;
}

/**
 * The landing's search. Signed in, it goes straight to the search. Signed
 * out, "Crear mi búsqueda" opens a pop-up that asks only for an email (no
 * password, no confirmation, no login page: startFreeSearch). An email that
 * already has a password is asked for it in the same pop-up.
 *
 * PAR-04: a guide page passes `initialText` (the prefilled search), leaves
 * `signedIn` out (the session is read here, in the browser) and `onStart`
 * (guide_cta_clicked).
 *
 * The home passes `hero`, the variant of its hero test (lib/landing-hero.ts),
 * so both are counted the same way, and with variant b also `quick`: the
 * search is then built by tapping (LandingBuilder) instead of typed.
 */
export function LandingSearch({ signedIn: serverSignedIn, initialText = "", onStart, hero, quick }: {
  signedIn?: boolean;
  initialText?: string;
  onStart?: () => void;
  hero?: HeroVariant;
  quick?: { models: string[] };
}) {
  const clientSignedIn = useClientSession(serverSignedIn !== undefined);
  const signedIn = serverSignedIn ?? Boolean(clientSignedIn);
  const sessionKnown = serverSignedIn !== undefined || clientSignedIn !== null;
  const [text, setText] = useState(initialText);
  const [builder, setBuilder] = useState<Builder>(EMPTY_BUILDER);
  /** What is sent to be read: the box as typed, or the builder's text without «cerca de mi ubicación». */
  const prompt = quick ? builderPrompt(builder) : text;
  const started = useRef(false);
  const startedOnce = useCallback((how: LandingHow) => {
    if (started.current || !hero) return;
    started.current = true;
    logLandingEvent("landing_search_started", hero, how);
  }, [hero]);
  useEffect(() => {
    if (hero) logLandingEvent("landing_viewed", hero);
  }, [hero]);
  const [promptError, setPromptError] = useState("");
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  /** The email the code went to, kept while a wrong code is retried. */
  const [sent, setSent] = useState<{ email: string; unconfirmed?: boolean } | null>(null);
  const [company, setCompany] = useState("");
  const [result, setResult] = useState<FreeSearchResult | null>(null);
  // An error keeps the pop-up on the step where it happened.
  const [step, setStep] = useState<"email" | "password" | "code">("email");
  const [pending, start] = useTransition();
  // Before hydration a tap would submit the bare form and reload the page, losing the text: the button waits for it.
  const hydrated = useSyncExternalStore(noop, () => true, () => false);
  const router = useRouter();
  const promptErrorId = useId();
  const emailId = useId();
  const passwordId = useId();
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const codeRef = useRef<HTMLInputElement>(null);
  const codeId = useId();
  const suggestion = emailSuggestion(email);
  const fieldError = result?.status === "error" ? result.field : undefined;
  // Each step's field takes the focus: the one that had it was just unmounted (autoFocus loses to the dialog's focus trap).
  useEffect(() => {
    // While an action runs the fields are disabled and can't take it.
    if (!open || pending) return;
    const field = step === "password" ? passwordRef : step === "code" ? codeRef : emailRef;
    const id = window.setTimeout(() => field?.current?.focus(), 0);
    return () => window.clearTimeout(id);
  }, [open, pending, step, result]);
  const message = result?.status === "unavailable" || (result?.status === "error" && result.field !== "email" && result.field !== "password" && result.field !== "code") ? result.error : null;

  /** Runs an action from the pop-up; a dropped connection keeps everything typed. */
  const run = (action: () => Promise<FreeSearchResult>) => start(async () => {
    let next: FreeSearchResult;
    try {
      next = await action();
    } catch {
      setResult({ status: "error", error: OFFLINE });
      return;
    }
    if (next.status === "error" && next.field === "prompt") {
      setOpen(false);
      setPromptError(next.error);
    }
    if (next.status === "existing_account") setStep("password");
    else if (next.status === "existing_email_only") {
      setCode("");
      setSent(next.error ? null : { email: next.email, unconfirmed: next.unconfirmed });
      setStep("code");
    }
    setResult(next);
    if (next.status !== "created") return;
    forgetSignupCode();
    if (next.signedUp) {
      pixel("Lead");
      analyticsEvent("sign_up", { method: "email_only" });
    }
    router.push(next.href);
  });

  const otherEmail = () => {
    setResult(null);
    setPassword("");
    setCode("");
    setSent(null);
    setEmail("");
    setStep("email");
  };

  return (
    <>
      <form id="landing-search" className="mt-6 space-y-4" onSubmit={(event) => {
        event.preventDefault();
        if (pending || !sessionKnown) return;
        onStart?.();
        if (signedIn) {
          start(() => router.push(searchStartHref(true, prompt)));
          return;
        }
        if (prompt.trim().length < ASSISTED_MIN_CHARS) {
          setPromptError("Contanos qué auto buscás.");
          event.currentTarget.querySelector("textarea")?.focus();
          return;
        }
        setPromptError("");
        // Reopening starts over at the email (it stays typed).
        setResult(null);
        setPassword("");
        setCode("");
        setSent(null);
        setStep("email");
        setOpen(true);
        if (hero) logLandingEvent("landing_dialog_opened", hero);
      }}>
        {quick ? (
          <LandingBuilder state={builder} onState={(update) => { setBuilder(update); setPromptError(""); }} models={quick.models} disabled={pending}
            invalid={Boolean(promptError)} describedBy={promptError ? promptErrorId : undefined} onStarted={startedOnce} />
        ) : (
          <SearchPromptInput value={text} onChange={(value) => { if (value.trim()) startedOnce("typed"); setText(value); setPromptError(""); }} disabled={pending} showExamples={false} compact
            invalid={Boolean(promptError)} describedBy={promptError ? promptErrorId : undefined} />
        )}
        {promptError ? <p id={promptErrorId} role="alert" className="-mt-2 text-sm text-destructive">{promptError}</p> : null}
        {quick ? (
          // Once there is a search the button follows the screen while the form is in view.
          <div className={prompt.trim().length >= ASSISTED_MIN_CHARS
            ? "sticky bottom-0 z-10 -mx-4 bg-[linear-gradient(to_bottom,transparent,var(--background)_10px)] px-4 py-2.5 sm:static sm:mx-0 sm:bg-none sm:p-0"
            : ""}>
            <Button type="submit" disabled={pending || !hydrated || !sessionKnown} className="h-13 w-full text-[16.5px] sm:h-11 sm:w-auto sm:px-4.5 sm:text-[15px]">
              {pending && signedIn ? "Continuando…" : "Crear mi búsqueda"}
            </Button>
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
            <Button type="submit" disabled={pending || !hydrated || !sessionKnown} className="h-11 px-4.5 text-[15px]">
              {pending && signedIn ? "Continuando…" : "Crear mi búsqueda"}
            </Button>
            <Link href="/planes" className="inline-flex min-h-11 items-center text-[15px] font-medium underline underline-offset-4">Ver planes</Link>
          </div>
        )}
        <p className={quick ? "text-center text-sm text-muted-foreground sm:text-left" : "text-sm text-muted-foreground"}>
          {signedIn ? "Prueba gratis por 3 días. Sin tarjeta." : "Probá gratis 3 días. Sin tarjeta y sin contraseña: solo tu email."}
        </p>
        {/* The cookie notice sits here, in the page, so it never covers the button (components/meta-pixel.tsx). */}
        {quick ? <div id="consent-slot" /> : null}
      </form>

      {signedIn ? null : <Dialog open={open} onOpenChange={(next) => { if (!pending) setOpen(next); }}>
        <DialogContent className="sm:max-w-md">
          {step === "email" ? <form className="space-y-4" noValidate onSubmit={(event) => {
            event.preventDefault();
            if (!pending) run(() => startFreeSearch({ prompt, email, company, resume: signupCode() }));
          }}>
            <DialogHeader>
              <DialogTitle>¿A qué email te avisamos?</DialogTitle>
              <DialogDescription>Ahí te mandamos las alertas. Con este email creamos tu cuenta, sin contraseña y sin confirmar nada. Después revisás los datos del auto y activás la búsqueda.</DialogDescription>
            </DialogHeader>
            <div className="space-y-1.5">
              <Label htmlFor={emailId}>Tu email</Label>
              <Input
                ref={emailRef}
                id={emailId}
                name="email"
                type="email"
                inputMode="email"
                autoComplete="email"
                autoCapitalize="none"
                autoCorrect="off"
                spellCheck={false}
                enterKeyHint="go"
                required
                autoFocus
                placeholder="vos@email.com"
                value={email}
                disabled={pending}
                aria-invalid={fieldError === "email" || undefined}
                aria-describedby={fieldError === "email" ? `${emailId}-error` : undefined}
                onChange={(event) => { setEmail(event.target.value); setResult(null); }}
                className="h-11 bg-background text-base"
              />
              <div aria-live="polite">
                {suggestion ? <p className="text-sm [overflow-wrap:anywhere]">
                  ¿Quisiste decir{" "}
                  <button type="button" className="font-medium underline underline-offset-4 [overflow-wrap:anywhere]" onClick={() => { setEmail(suggestion); emailRef.current?.focus(); }}>{suggestion}</button>?
                </p> : null}
              </div>
              {fieldError === "email" && result?.status === "error" ? <p id={`${emailId}-error`} role="alert" className="text-sm text-destructive">{result.error}</p> : null}
              {/* Bots fill every field; people never see this one. */}
              <div aria-hidden="true" className="absolute -left-[9999px] size-px overflow-hidden">
                <label>Dejar vacío<input tabIndex={-1} autoComplete="off" name="ea_hp_field" value={company} onChange={(event) => setCompany(event.target.value)} /></label>
              </div>
            </div>
            {message ? <p role="alert" className="text-sm text-destructive">{message}</p> : null}
            <Button type="submit" className="h-11 w-full text-[15px]" disabled={pending}>{pending ? "Un momento…" : "Seguir"}</Button>
            <p className="text-xs text-muted-foreground">
              Al seguir aceptás los <Link href="/terminos" className="underline">Términos de uso</Link> y
              la <Link href="/privacidad" className="underline">Política de privacidad</Link>.
            </p>
          </form> : null}

          {step === "password" ? <form className="space-y-4" onSubmit={(event) => {
            event.preventDefault();
            if (!pending) run(() => enterForFreeSearch({ prompt, email, password }));
          }}>
            <DialogHeader>
              <DialogTitle>Ya tenés una cuenta</DialogTitle>
              <DialogDescription className="[overflow-wrap:anywhere]">{email} ya está en Ese Auto. Escribí tu contraseña y seguimos con la búsqueda.</DialogDescription>
            </DialogHeader>
            <div className="space-y-1.5">
              <Label htmlFor={passwordId}>Contraseña</Label>
              <Input ref={passwordRef} id={passwordId} name="password" type="password" autoComplete="current-password" required autoFocus value={password} disabled={pending}
                aria-invalid={fieldError === "password" || undefined} aria-describedby={fieldError === "password" ? `${passwordId}-error` : undefined}
                onChange={(event) => setPassword(event.target.value)} className="h-11 bg-background text-base" />
              {fieldError === "password" && result?.status === "error" ? <p id={`${passwordId}-error`} role="alert" className="text-sm text-destructive">{result.error}</p> : null}
            </div>
            {message ? <p role="alert" className="text-sm text-destructive">{message}</p> : null}
            <Button type="submit" className="h-11 w-full text-[15px]" disabled={pending}>{pending ? "Entrando…" : "Entrar y crear la búsqueda"}</Button>
            <div className="flex flex-col gap-2 text-center text-sm">
              <button type="button" className="underline underline-offset-4" disabled={pending} onClick={() => run(() => linkForFreeSearch({ prompt, email }))}>
                No me acuerdo: mandame un código
              </button>
              <button type="button" className="underline underline-offset-4" disabled={pending} onClick={otherEmail}>Usar otro email</button>
            </div>
          </form> : null}

          {step === "code" && !sent && result?.status === "existing_email_only" ? <div className="space-y-4">
            <DialogHeader>
              <DialogTitle>No pudimos mandarte el código</DialogTitle>
              <DialogDescription className="[overflow-wrap:anywhere]">{result.error}</DialogDescription>
            </DialogHeader>
            <div className="flex flex-col gap-2">
              <Button type="button" variant="outline" className="h-11 w-full" onClick={() => setOpen(false)}>Cerrar</Button>
              <button type="button" className="text-sm underline underline-offset-4" onClick={otherEmail}>Usar otro email</button>
            </div>
          </div> : null}

          {step === "code" && sent ? <form className="space-y-4" noValidate onSubmit={(event) => {
            event.preventDefault();
            if (!pending) run(() => codeForFreeSearch({ prompt, email: sent.email, code }));
          }}>
            <DialogHeader>
              <DialogTitle>Revisá tu email</DialogTitle>
              <DialogDescription className="[overflow-wrap:anywhere]">
                Ya tenés una cuenta con este email. Te mandamos un código a {sent.email}{sent.unconfirmed ? " para confirmarlo y elegir tu contraseña" : ""}: escribilo acá y seguimos con la búsqueda. Si no lo ves, revisá Spam.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-1.5">
              <Label htmlFor={codeId}>Código</Label>
              <Input ref={codeRef} id={codeId} name="code" inputMode="numeric" autoComplete="one-time-code" maxLength={9} required placeholder="123456" value={code} disabled={pending}
                aria-invalid={fieldError === "code" || undefined} aria-describedby={fieldError === "code" ? `${codeId}-error` : undefined}
                onChange={(event) => setCode(event.target.value)} className="h-11 bg-background text-lg tracking-[0.3em] tabular-nums" />
              {fieldError === "code" && result?.status === "error" ? <p id={`${codeId}-error`} role="alert" className="text-sm text-destructive">{result.error}</p> : null}
              <p className="text-xs text-muted-foreground">También podés tocar el botón del email. Sirve el último que te mandamos.</p>
            </div>
            {message ? <p role="alert" className="text-sm text-destructive">{message}</p> : null}
            <Button type="submit" className="h-11 w-full text-[15px]" disabled={pending}>{pending ? "Entrando…" : "Entrar y crear la búsqueda"}</Button>
            <div className="flex flex-col gap-2 text-center text-sm">
              <button type="button" className="underline underline-offset-4" disabled={pending} onClick={() => run(() => linkForFreeSearch({ prompt, email: sent.email }))}>Mandame otro código</button>
              <button type="button" className="underline underline-offset-4" disabled={pending} onClick={otherEmail}>Usar otro email</button>
            </div>
          </form> : null}
        </DialogContent>
      </Dialog>}
    </>
  );
}

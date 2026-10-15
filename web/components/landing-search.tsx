"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState, useTransition } from "react";

import { enterForFreeSearch, type FreeSearchResult, linkForFreeSearch, startFreeSearch } from "@/app/actions";
import { SearchPromptInput } from "@/components/search-prompt-input";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ASSISTED_MIN_CHARS } from "@/lib/assisted";
import { emailSuggestion } from "@/lib/email-typos";
import { analyticsEvent } from "@/lib/google-analytics";
import { pixel } from "@/lib/meta-pixel";
import { searchStartHref } from "@/lib/search-intent";

const OFFLINE = "No pudimos conectarnos. Revisá tu conexión y probá de nuevo.";

/**
 * The landing's search. Signed in, it goes straight to the search. Signed
 * out, "Crear mi búsqueda" opens a pop-up that asks only for an email (no
 * password, no confirmation, no login page: startFreeSearch). An email that
 * already has a password is asked for it in the same pop-up.
 */
export function LandingSearch({ signedIn }: { signedIn: boolean }) {
  const [text, setText] = useState("");
  const [promptError, setPromptError] = useState("");
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [company, setCompany] = useState("");
  const [result, setResult] = useState<FreeSearchResult | null>(null);
  // An error keeps the pop-up on the step where it happened.
  const [step, setStep] = useState<"email" | "password" | "sent">("email");
  const [pending, start] = useTransition();
  const router = useRouter();
  const promptErrorId = useId();
  const emailId = useId();
  const passwordId = useId();
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const suggestion = emailSuggestion(email);
  const fieldError = result?.status === "error" ? result.field : undefined;
  // Each step's field takes the focus: the one that had it was just unmounted (autoFocus loses to the dialog's focus trap).
  useEffect(() => {
    // While an action runs the fields are disabled and can't take it.
    if (!open || pending) return;
    const field = step === "password" ? passwordRef : step === "email" ? emailRef : null;
    const id = window.setTimeout(() => field?.current?.focus(), 0);
    return () => window.clearTimeout(id);
  }, [open, pending, step, result]);
  const message = result?.status === "unavailable" || (result?.status === "error" && result.field !== "email" && result.field !== "password") ? result.error : null;

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
    else if (next.status === "existing_email_only") setStep("sent");
    setResult(next);
    if (next.status !== "created") return;
    if (next.signedUp) {
      pixel("Lead");
      analyticsEvent("sign_up", { method: "email_only" });
    }
    router.push(next.href);
  });

  const otherEmail = () => {
    setResult(null);
    setPassword("");
    setEmail("");
    setStep("email");
  };

  return (
    <>
      <form id="landing-search" className="mt-6 space-y-4" onSubmit={(event) => {
        event.preventDefault();
        if (pending) return;
        if (signedIn) {
          start(() => router.push(searchStartHref(true, text)));
          return;
        }
        if (text.trim().length < ASSISTED_MIN_CHARS) {
          setPromptError("Contanos qué auto buscás.");
          event.currentTarget.querySelector("textarea")?.focus();
          return;
        }
        setPromptError("");
        // Reopening starts over at the email (it stays typed).
        setResult(null);
        setPassword("");
        setStep("email");
        setOpen(true);
      }}>
        <SearchPromptInput value={text} onChange={(value) => { setText(value); setPromptError(""); }} disabled={pending} showExamples={false} compact
          invalid={Boolean(promptError)} describedBy={promptError ? promptErrorId : undefined} />
        {promptError ? <p id={promptErrorId} role="alert" className="-mt-2 text-sm text-destructive">{promptError}</p> : null}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
          <Button type="submit" disabled={pending} className="h-11 px-4.5 text-[15px]">
            {pending && signedIn ? "Continuando…" : "Crear mi búsqueda"}
          </Button>
          <Link href="/planes" className="py-2 text-[15px] font-medium underline underline-offset-4">Ver planes</Link>
        </div>
        <p className="text-sm text-muted-foreground">
          {signedIn ? "Prueba gratis por 3 días. Sin tarjeta." : "Probá gratis 3 días. Sin tarjeta y sin contraseña: solo tu email."}
        </p>
      </form>

      {signedIn ? null : <Dialog open={open} onOpenChange={(next) => { if (!pending) setOpen(next); }}>
        <DialogContent className="sm:max-w-md">
          {step === "email" ? <form className="space-y-4" onSubmit={(event) => {
            event.preventDefault();
            if (!pending) run(() => startFreeSearch({ prompt: text, email, company }));
          }}>
            <DialogHeader>
              <DialogTitle>¿A qué email te avisamos?</DialogTitle>
              <DialogDescription>Ahí te mandamos las alertas de esta búsqueda. Sin contraseña y sin confirmar nada.</DialogDescription>
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
            <Button type="submit" className="h-11 w-full text-[15px]" disabled={pending}>{pending ? "Creando tu búsqueda…" : "Crear mi búsqueda"}</Button>
            <p className="text-xs text-muted-foreground">
              Al crear tu búsqueda aceptás los <Link href="/terminos" className="underline">Términos de uso</Link> y
              la <Link href="/privacidad" className="underline">Política de privacidad</Link>.
            </p>
          </form> : null}

          {step === "password" ? <form className="space-y-4" onSubmit={(event) => {
            event.preventDefault();
            if (!pending) run(() => enterForFreeSearch({ prompt: text, email, password }));
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
              <button type="button" className="underline underline-offset-4" disabled={pending} onClick={() => run(() => linkForFreeSearch({ prompt: text, email }))}>
                No me acuerdo: mandame un link para entrar
              </button>
              <button type="button" className="underline underline-offset-4" disabled={pending} onClick={otherEmail}>Usar otro email</button>
            </div>
          </form> : null}

          {step === "sent" && result?.status === "existing_email_only" ? <div className="space-y-4">
            <DialogHeader>
              <DialogTitle>{result.error ? "No pudimos mandarte el link" : "Revisá tu email"}</DialogTitle>
              <DialogDescription className="[overflow-wrap:anywhere]">
                {result.error ?? `Te mandamos un link a ${result.email} para entrar${result.unconfirmed ? " y elegir tu contraseña" : ""}. Revisá también Spam: solo funciona el último link.`}
              </DialogDescription>
            </DialogHeader>
            <div className="flex flex-col gap-2">
              <Button type="button" variant="outline" className="h-11 w-full" onClick={() => setOpen(false)}>Listo</Button>
              <button type="button" className="text-sm underline underline-offset-4" onClick={otherEmail}>Usar otro email</button>
            </div>
          </div> : null}
        </DialogContent>
      </Dialog>}
    </>
  );
}

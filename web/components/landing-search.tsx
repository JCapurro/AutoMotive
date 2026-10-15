"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState, useTransition } from "react";

import { type FreeSearchResult, startFreeSearch } from "@/app/actions";
import { SearchPromptInput } from "@/components/search-prompt-input";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ASSISTED_MIN_CHARS } from "@/lib/assisted";
import { emailSuggestion } from "@/lib/email-typos";
import { analyticsEvent } from "@/lib/google-analytics";
import { pixel } from "@/lib/meta-pixel";
import { searchStartHref } from "@/lib/search-intent";

const OFFLINE = "No pudimos conectarnos. Revisá tu conexión y probá de nuevo.";

/**
 * Signed out, the free search asks only for an email: no password, no
 * confirmation (startFreeSearch). Signed in, it goes straight to the search.
 */
export function LandingSearch({ signedIn }: { signedIn: boolean }) {
  const [text, setText] = useState("");
  const [email, setEmail] = useState("");
  const [company, setCompany] = useState("");
  const [result, setResult] = useState<FreeSearchResult | null>(null);
  const [pending, start] = useTransition();
  const router = useRouter();
  const emailId = useId();
  const promptErrorId = useId();
  const emailRef = useRef<HTMLInputElement>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const suggestion = emailSuggestion(email);
  const fieldError = result?.status === "error" ? result.field : undefined;

  // Back to the field that needs fixing (the submit disabled the one that had focus).
  useEffect(() => {
    if (fieldError === "email") emailRef.current?.focus();
    else if (fieldError === "prompt") formRef.current?.querySelector("textarea")?.focus();
  }, [fieldError, result]);

  return (
    <form ref={formRef} id="landing-search" className="mt-6 space-y-4" noValidate={!signedIn} onSubmit={(event) => {
      event.preventDefault();
      if (pending) return;
      if (signedIn) {
        start(() => router.push(searchStartHref(true, text)));
        return;
      }
      if (text.trim().length < ASSISTED_MIN_CHARS) {
        setResult({ status: "error", field: "prompt", error: "Contanos qué auto buscás." });
        return;
      }
      start(async () => {
        let next: FreeSearchResult;
        try {
          next = await startFreeSearch({ prompt: text, email, company });
        } catch {
          // A dropped connection or a deploy in between must not take the page down with what was typed.
          setResult({ status: "error", error: OFFLINE });
          return;
        }
        setResult(next);
        if (next.status !== "created") return;
        if (next.signedUp) {
          pixel("Lead");
          analyticsEvent("sign_up", { method: "email_only" });
        }
        router.push(next.href);
      });
    }}>
      <SearchPromptInput value={text} onChange={setText} disabled={pending} showExamples={false} compact
        invalid={fieldError === "prompt"} describedBy={fieldError === "prompt" ? promptErrorId : undefined} />
      {fieldError === "prompt" && result?.status === "error" ? <p id={promptErrorId} role="alert" className="-mt-2 text-sm text-destructive">{result.error}</p> : null}

      {signedIn ? null : <div className="space-y-1.5">
        <Label htmlFor={emailId} className="text-base font-semibold">Tu email</Label>
        <p id={`${emailId}-help`} className="text-sm text-muted-foreground">Ahí te avisamos cuando aparezca.</p>
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
          placeholder="vos@email.com"
          value={email}
          disabled={pending}
          aria-invalid={fieldError === "email" || undefined}
          aria-describedby={fieldError === "email" ? `${emailId}-help ${emailId}-error` : `${emailId}-help`}
          onChange={(event) => { setEmail(event.target.value); if (result?.status !== "created") setResult(null); }}
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
      </div>}

      {result?.status === "existing_email_only" ? <div role="status" className="space-y-2 rounded-lg bg-muted p-4 text-sm [overflow-wrap:anywhere]">
        {result.error ? <p>{result.error}</p> : <>
          <p className="font-medium">{result.email} ya está en Ese Auto.</p>
          <p>Te mandamos un link para entrar{result.unconfirmed ? " y elegir tu contraseña" : ""}: revisá tu email (y Spam). Solo funciona el último link.</p>
        </>}
        <button type="button" className="underline underline-offset-4" onClick={() => { setResult(null); setEmail(""); emailRef.current?.focus(); }}>Usar otro email</button>
      </div> : null}
      {result?.status === "existing_account" ? <div role="status" className="space-y-3 rounded-lg bg-muted p-4 text-sm">
        <p>Ya tenés una cuenta con este email. Ingresá para crear tu búsqueda.</p>
        <Button asChild variant="outline"><Link href={result.href}>Ingresar</Link></Button>
      </div> : null}
      {result?.status === "signup" ? <div role="status" className="space-y-3 rounded-lg bg-muted p-4 text-sm">
        <p>Ahora no podemos crear búsquedas solo con el email. Para seguir, creá tu cuenta con una contraseña: tu búsqueda te espera del otro lado.</p>
        <Button asChild variant="outline"><Link href={result.href}>Crear mi cuenta</Link></Button>
      </div> : null}

      <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
        <Button type="submit" disabled={pending} className="h-11 px-4.5 text-[15px]">
          {pending ? (signedIn ? "Continuando…" : "Un momento…") : "Crear mi búsqueda"}
        </Button>
        <Link href="/planes" className="py-2 text-[15px] font-medium underline underline-offset-4">Ver planes</Link>
      </div>
      {result?.status === "error" && !result.field ? <p role="alert" className="text-sm text-destructive">{result.error}</p> : null}
      {signedIn ? <p className="text-sm text-muted-foreground">Prueba gratis por 3 días. Sin tarjeta.</p> : <div className="space-y-1 text-sm text-muted-foreground">
        <p>Probá gratis 3 días. Sin tarjeta y sin contraseña: solo tu email.</p>
        <p className="text-xs">
          Al crear tu búsqueda aceptás los <Link href="/terminos" className="underline">Términos de uso</Link> y
          la <Link href="/privacidad" className="underline">Política de privacidad</Link>.
        </p>
      </div>}
    </form>
  );
}

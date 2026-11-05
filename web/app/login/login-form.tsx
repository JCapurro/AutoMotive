"use client";

import Link from "next/link";
import { useActionState, useEffect, useRef } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { pixel } from "@/lib/meta-pixel";
import { analyticsEvent } from "@/lib/google-analytics";
import { type LoginState, login, signInWithGoogle } from "./actions";

/**
 * Entrar, email first (docs/AUTENTICACION.md): «Continuar», then the password
 * if the account has one, or the code we mail otherwise. An email without an
 * account gets one with the code, so there's no separate signup. Google stays
 * as the other way.
 */
export function LoginForm({ next, linkError, googleError = false, mailbox = "", passwordUpdated = false, inApp = false }: {
  next: string; linkError: boolean; googleError?: boolean; mailbox?: string; passwordUpdated?: boolean;
  /** Instagram/Facebook browsers: Google refuses to sign in there. */
  inApp?: boolean;
}) {
  const [state, submit, pending] = useActionState(login, { step: "email", next } satisfies LoginState);
  const [google, googleSubmit, googlePending] = useActionState(signInWithGoogle, { next });
  const codeRef = useRef<HTMLInputElement>(null);
  const busy = pending || googlePending;
  // A paid plan needs a password; everything else starts with the free search.
  const paying = next.startsWith("/app/pro");
  // An email with no account got one with the code: that's the signup.
  const signedUp = state.step === "code" && state.signedUp === true;
  useEffect(() => {
    if (!signedUp) return;
    pixel("Lead");
    analyticsEvent("sign_up", { method: "email_code" });
  }, [signedUp]);
  useEffect(() => { if (state.step === "code") codeRef.current?.focus(); }, [state.step, state.error]);

  return <div className="space-y-4">
    {linkError ? <Alert variant="destructive"><AlertDescription>Este link ya se usó o venció. Escribí tu email y te mandamos un código nuevo.</AlertDescription></Alert> : null}
    {googleError ? <Alert variant="destructive"><AlertDescription>No se completó el ingreso con Google. Probá de nuevo o entrá con un código por email.</AlertDescription></Alert> : null}
    {passwordUpdated ? <Alert><AlertDescription>Contraseña actualizada. Ya podés ingresar.</AlertDescription></Alert> : null}

    {state.step === "code" ? <form action={submit} className="space-y-4">
      <input type="hidden" name="next" value={next} />
      <input type="hidden" name="email" value={state.email ?? ""} />
      <div className="space-y-1" role="status">
        <p className="font-medium">Revisá tu email</p>
        <p className="text-sm text-muted-foreground [overflow-wrap:anywhere]">
          {state.notice ? `${state.notice} ` : null}Si <b className="text-foreground">{state.email}</b> está bien escrito, te llega un código para entrar. Revisá también Spam.
        </p>
      </div>
      <div className="space-y-2">
        <Label htmlFor="code">Código</Label>
        <Input ref={codeRef} id="code" name="code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9 ]*" maxLength={9} required placeholder="123456"
          aria-invalid={state.error ? true : undefined} aria-describedby={state.error ? "code-error" : undefined} className="h-11 text-lg tracking-[0.3em] tabular-nums" />
        <p className="text-xs text-muted-foreground">También podés tocar el botón del email. Sirve el último que te mandamos y vence en 1 hora.</p>
      </div>
      {state.error ? <p id="code-error" role="alert" className="text-sm text-destructive">{state.error}</p> : null}
      <Button className="h-10 w-full" name="intent" value="verify" disabled={busy}>{pending ? "Entrando…" : "Entrar"}</Button>
      {mailbox ? <p className="text-sm" data-testid="local-mailbox">El email local está en <a className="underline" href={mailbox} target="_blank" rel="noreferrer">Mailpit</a>.</p> : null}
      <div className="flex flex-col gap-2 text-center text-sm">
        <button type="submit" name="intent" value="send-code" formNoValidate className="underline underline-offset-4" disabled={busy}>Mandame otro código</button>
        <button type="submit" name="intent" value="change-email" formNoValidate className="underline underline-offset-4" disabled={busy}>Usar otro email</button>
      </div>
    </form> : state.step === "password" ? <form action={submit} className="space-y-4">
      <input type="hidden" name="next" value={next} />
      <div className="space-y-1">
        <p className="text-sm text-muted-foreground">Entrás como</p>
        <div className="flex items-center justify-between gap-3">
          <b className="min-w-0 [overflow-wrap:anywhere]" data-testid="login-email">{state.email}</b>
          <button type="submit" name="intent" value="change-email" formNoValidate className="shrink-0 text-sm underline underline-offset-4" disabled={busy}>Cambiar</button>
        </div>
        {/* For password managers: the account the password belongs to. */}
        <input type="email" name="email" value={state.email ?? ""} autoComplete="username" readOnly tabIndex={-1} aria-hidden="true" className="sr-only" />
      </div>
      <div className="space-y-2">
        <Label htmlFor="password">Contraseña</Label>
        <Input id="password" name="password" type="password" autoComplete="current-password" required autoFocus className="h-10"
          aria-invalid={state.error ? true : undefined} aria-describedby={state.error ? "password-error" : undefined} />
      </div>
      {state.error ? <p id="password-error" role="alert" className="text-sm text-destructive">{state.error}</p> : null}
      <Button className="h-10 w-full" name="intent" value="password" disabled={busy}>{pending ? "Entrando…" : "Ingresar"}</Button>
      <button type="submit" name="intent" value="send-code" formNoValidate className="block w-full text-center text-sm underline underline-offset-4" disabled={busy}>Olvidé mi contraseña: mandame un código</button>
    </form> : <form action={submit} className="space-y-4">
      <input type="hidden" name="next" value={next} />
      <div className="space-y-2">
        <Label htmlFor="email">Email</Label>
        <Input id="email" name="email" type="email" inputMode="email" autoComplete="email" autoCapitalize="none" spellCheck={false} required placeholder="vos@email.com"
          defaultValue={state.email} autoFocus={Boolean(state.email)} className="h-10"
          aria-invalid={state.error ? true : undefined} aria-describedby={state.error ? "email-error" : undefined} />
      </div>
      {state.error ? <p id="email-error" role="alert" className="text-sm text-destructive">{state.error}</p> : null}
      <Button className="h-10 w-full" name="intent" value="continue" disabled={busy}>{pending ? "Un momento…" : "Continuar"}</Button>
    </form>}

    {state.step === "email" && inApp ? <p className="text-center text-xs text-muted-foreground">Para entrar con Google, abrí esta página en tu navegador (menú ⋯ › Abrir en el navegador).</p> : null}
    {state.step === "email" && !inApp ? <>
      <div className="flex items-center gap-3 text-xs text-muted-foreground"><span className="h-px flex-1 bg-border" />o<span className="h-px flex-1 bg-border" /></div>
      <form action={googleSubmit} className="space-y-2">
        <input type="hidden" name="next" value={next} />
        <Button type="submit" variant="outline" className="h-10 w-full" disabled={busy}>
          <svg aria-hidden="true" viewBox="0 0 24 24" className="size-4"><path fill="#4285F4" d="M21.6 12.23c0-.71-.06-1.39-.18-2.05H12v3.88h5.38a4.6 4.6 0 0 1-2 3.02v2.51h3.24c1.9-1.75 2.98-4.33 2.98-7.36Z" /><path fill="#34A853" d="M12 22c2.7 0 4.96-.9 6.62-2.41l-3.24-2.51c-.9.6-2.05.96-3.38.96-2.6 0-4.8-1.76-5.59-4.12H3.07v2.59A10 10 0 0 0 12 22Z" /><path fill="#FBBC05" d="M6.41 13.92a6 6 0 0 1 0-3.84V7.49H3.07a10 10 0 0 0 0 9.02l3.34-2.59Z" /><path fill="#EA4335" d="M12 5.96c1.47 0 2.79.51 3.82 1.51l2.86-2.87A9.6 9.6 0 0 0 12 2a10 10 0 0 0-8.93 5.49l3.34 2.59A6 6 0 0 1 12 5.96Z" /></svg>
          {googlePending ? "Conectando con Google…" : "Continuar con Google"}
        </Button>
        {google.error ? <p role="alert" className="text-sm text-destructive">{google.error}</p> : null}
      </form>
    </> : null}

    {state.step === "email" && !paying ? <p className="text-center text-sm"><Link className="underline" href="/#crear-busqueda">¿Buscás un auto? Creá tu búsqueda gratis</Link></p> : null}
  </div>;
}

"use client";

import Link from "next/link";
import { useActionState, useEffect } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { pixel } from "@/lib/meta-pixel";
import { analyticsEvent } from "@/lib/google-analytics";
import { type AuthMode, type LoginState, authenticate, resendConfirmation, signInWithGoogle } from "./actions";

export function LoginForm({ next, linkError, googleError = false, mailbox = "", mode = "login", passwordUpdated = false }: {
  next: string; linkError: boolean; googleError?: boolean; mailbox?: string; mode?: AuthMode; passwordUpdated?: boolean;
}) {
  const [state, submit, pending] = useActionState(authenticate.bind(null, mode), { next } satisfies LoginState);
  const [resent, resend, resending] = useActionState(resendConfirmation, { next } satisfies LoginState);
  const [google, googleSubmit, googlePending] = useActionState(signInWithGoogle, { next } satisfies LoginState);
  const href = (target: AuthMode) => `/login?mode=${target}&next=${encodeURIComponent(next)}`;
  useEffect(() => { if (mode === "signup" && state.sent) pixel("Lead"); }, [mode, state.sent]);
  useEffect(() => { if (mode === "signup" && state.sent) analyticsEvent("sign_up", { method: "email" }); }, [mode, state.sent]);
  return <div className="space-y-4">
    {linkError ? <Alert variant="destructive"><AlertDescription>{mode === "recover" ? "Este enlace ya se usó o venció. Pedí una nueva recuperación con tu email." : "Este enlace ya se usó o venció. Si ya confirmaste tu cuenta, ingresá con tu email y contraseña. Si todavía está pendiente, pedí una nueva confirmación abajo."}</AlertDescription></Alert> : null}
    {googleError ? <Alert variant="destructive"><AlertDescription>No se completó el ingreso con Google. Probá de nuevo o ingresá con email y contraseña.</AlertDescription></Alert> : null}
    {passwordUpdated ? <Alert><AlertDescription>Contraseña actualizada. Ya podés ingresar.</AlertDescription></Alert> : null}
    {state.sent ? <div className="space-y-4" role="status">
      <p className="font-medium">Revisá tu email</p>
      <p className="text-sm text-muted-foreground">{mode === "signup" ? "Si el registro puede completarse, recibirás un email para confirmar tu cuenta. Abrí el enlace antes de ingresar." : "Si existe una cuenta con ese email, recibirás un enlace para elegir una nueva contraseña."}</p>
      {mailbox ? <p className="text-sm" data-testid="local-mailbox">El email local está en <a className="underline" href={mailbox} target="_blank" rel="noreferrer">Mailpit</a>.</p> : null}
    </div> : <form action={submit} className="space-y-4">
      <input type="hidden" name="next" value={next} />
      <div className="space-y-2"><Label htmlFor="email">Email</Label><Input id="email" name="email" type="email" autoComplete="email" required placeholder="vos@email.com" defaultValue={state.email} className="h-10" /></div>
      {mode !== "recover" ? <div className="space-y-2"><Label htmlFor="password">Contraseña</Label><Input id="password" name="password" type="password" autoComplete={mode === "signup" ? "new-password" : "current-password"} required minLength={mode === "signup" ? 8 : undefined} className="h-10" />{mode === "signup" ? <p className="text-xs text-muted-foreground">Al menos 8 caracteres.</p> : null}</div> : null}
      {mode === "signup" ? <div className="space-y-2"><Label htmlFor="confirmPassword">Repetí la contraseña</Label><Input id="confirmPassword" name="confirmPassword" type="password" autoComplete="new-password" required minLength={8} className="h-10" /></div> : null}
      {state.error ? <p role="alert" className="text-sm text-destructive">{state.error}</p> : null}
      <Button className="h-10 w-full" disabled={pending || googlePending}>{pending ? "Procesando…" : mode === "signup" ? "Crear cuenta" : mode === "recover" ? "Enviar recuperación" : "Ingresar"}</Button>
    </form>}
    {(mode === "signup" && state.sent) || (mode === "login" && (linkError || state.confirmationRequired)) ? <form action={resend} className="space-y-2 border-t pt-4">
      <input type="hidden" name="next" value={next} />
      <Label htmlFor="confirmation-email">Email para reenviar la confirmación</Label>
      <Input id="confirmation-email" name="email" type="email" autoComplete="email" required defaultValue={resent.email ?? state.email} placeholder="vos@email.com" />
      <Button type="submit" variant="outline" disabled={resending || googlePending}>{resending ? "Enviando…" : "Reenviar confirmación"}</Button>
      {resent.error ? <p role="alert" className="text-sm text-destructive">{resent.error}</p> : null}
      {resent.sent ? <p role="status" className="text-sm">Solicitud recibida. Si tu cuenta está pendiente, recibirás otro email; revisá también spam. Si ya la confirmaste, ingresá con tu contraseña.</p> : null}
    </form> : null}
    {mode !== "recover" ? <>
      <div className="flex items-center gap-3 text-xs text-muted-foreground"><span className="h-px flex-1 bg-border" />o<span className="h-px flex-1 bg-border" /></div>
      <form action={googleSubmit} className="space-y-2">
        <input type="hidden" name="next" value={next} />
        <Button type="submit" variant="outline" className="h-10 w-full" disabled={googlePending || pending || resending}>
          <svg aria-hidden="true" viewBox="0 0 24 24" className="size-4"><path fill="#4285F4" d="M21.6 12.23c0-.71-.06-1.39-.18-2.05H12v3.88h5.38a4.6 4.6 0 0 1-2 3.02v2.51h3.24c1.9-1.75 2.98-4.33 2.98-7.36Z" /><path fill="#34A853" d="M12 22c2.7 0 4.96-.9 6.62-2.41l-3.24-2.51c-.9.6-2.05.96-3.38.96-2.6 0-4.8-1.76-5.59-4.12H3.07v2.59A10 10 0 0 0 12 22Z" /><path fill="#FBBC05" d="M6.41 13.92a6 6 0 0 1 0-3.84V7.49H3.07a10 10 0 0 0 0 9.02l3.34-2.59Z" /><path fill="#EA4335" d="M12 5.96c1.47 0 2.79.51 3.82 1.51l2.86-2.87A9.6 9.6 0 0 0 12 2a10 10 0 0 0-8.93 5.49l3.34 2.59A6 6 0 0 1 12 5.96Z" /></svg>
          {googlePending ? "Conectando con Google…" : "Continuar con Google"}
        </Button>
        {google.error ? <p role="alert" className="text-sm text-destructive">{google.error}</p> : null}
      </form>
    </> : null}
    <div className="flex flex-col gap-3 text-center text-sm">{mode === "login" ? <><Link className="underline" href={href("recover")}>Olvidé mi contraseña</Link><Link className="underline" href={href("signup")}>Crear cuenta</Link></> : <Link className="underline" href={href("login")}>Volver a ingresar</Link>}</div>
  </div>;
}

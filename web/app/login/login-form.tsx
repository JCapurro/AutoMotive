"use client";

import Link from "next/link";
import { useActionState, useEffect } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { pixel } from "@/lib/meta-pixel";
import { type AuthMode, type LoginState, authenticate, resendConfirmation } from "./actions";

export function LoginForm({ next, linkError, mailbox = "", mode = "login", passwordUpdated = false }: {
  next: string; linkError: boolean; mailbox?: string; mode?: AuthMode; passwordUpdated?: boolean;
}) {
  const [state, submit, pending] = useActionState(authenticate.bind(null, mode), { next } satisfies LoginState);
  const [resent, resend, resending] = useActionState(resendConfirmation, { next } satisfies LoginState);
  const href = (target: AuthMode) => `/login?mode=${target}&next=${encodeURIComponent(next)}`;
  useEffect(() => { if (mode === "signup" && state.sent) pixel("Lead"); }, [mode, state.sent]);
  return <div className="space-y-4">
    {linkError ? <Alert variant="destructive"><AlertDescription>El link venció o ya se usó. Pedí un nuevo email.</AlertDescription></Alert> : null}
    {passwordUpdated ? <Alert><AlertDescription>Contraseña actualizada. Ya podés ingresar.</AlertDescription></Alert> : null}
    {state.sent ? <div className="space-y-4" role="status">
      <p className="font-medium">Revisá tu email</p>
      <p className="text-sm text-muted-foreground">{mode === "signup" ? "Si el registro puede completarse, recibirás un email para confirmar tu cuenta. Abrí el enlace antes de ingresar." : "Si existe una cuenta con ese email, recibirás un enlace para elegir una nueva contraseña."}</p>
      {mailbox ? <p className="text-sm" data-testid="local-mailbox">El email local está en <a className="underline" href={mailbox} target="_blank" rel="noreferrer">Mailpit</a>.</p> : null}
      {mode === "signup" ? <form action={resend} className="space-y-2">
        <input type="hidden" name="email" value={state.email} /><input type="hidden" name="next" value={next} />
        <Button variant="outline" disabled={resending}>{resending ? "Enviando…" : "Reenviar confirmación"}</Button>
        {resent.error ? <p role="alert" className="text-sm text-destructive">{resent.error}</p> : null}
        {resent.sent ? <p className="text-sm">Si tu cuenta está pendiente, recibirás una nueva confirmación.</p> : null}
      </form> : null}
    </div> : <form action={submit} className="space-y-4">
      <input type="hidden" name="next" value={next} />
      <div className="space-y-2"><Label htmlFor="email">Email</Label><Input id="email" name="email" type="email" autoComplete="email" required placeholder="vos@email.com" defaultValue={state.email} className="h-10" /></div>
      {mode !== "recover" ? <div className="space-y-2"><Label htmlFor="password">Contraseña</Label><Input id="password" name="password" type="password" autoComplete={mode === "signup" ? "new-password" : "current-password"} required minLength={mode === "signup" ? 8 : undefined} className="h-10" />{mode === "signup" ? <p className="text-xs text-muted-foreground">Al menos 8 caracteres.</p> : null}</div> : null}
      {mode === "signup" ? <div className="space-y-2"><Label htmlFor="confirmPassword">Repetí la contraseña</Label><Input id="confirmPassword" name="confirmPassword" type="password" autoComplete="new-password" required minLength={8} className="h-10" /></div> : null}
      {state.error ? <p role="alert" className="text-sm text-destructive">{state.error}</p> : null}
      <Button className="h-10 w-full" disabled={pending}>{pending ? "Procesando…" : mode === "signup" ? "Crear cuenta" : mode === "recover" ? "Enviar recuperación" : "Ingresar"}</Button>
    </form>}
    <div className="flex flex-col gap-3 text-center text-sm">{mode === "login" ? <><Link className="underline" href={href("recover")}>Olvidé mi contraseña</Link><Link className="underline" href={href("signup")}>Crear cuenta</Link></> : <Link className="underline" href={href("login")}>Volver a ingresar</Link>}</div>
  </div>;
}

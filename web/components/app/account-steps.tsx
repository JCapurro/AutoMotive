"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { startTransition, useActionState, useEffect, useRef } from "react";

import { type AccountState, completeAccount, confirmAccountCode, sendAccountLink } from "@/app/app/cuenta/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { planPrice } from "@/lib/pro";

/** On the way to paying: the code goes out by itself, and the price is on the confirm button. */
export type CodeCheckout = { amount: number | null };

// Within a minute GoTrue refuses another email anyway: a reload doesn't ask again.
const AUTO_SEND_KEY = "account-code-sent";
const AUTO_SEND_GAP_MS = 60_000;

function sentRecently(email: string): boolean {
  try {
    const at = Number(window.sessionStorage.getItem(`${AUTO_SEND_KEY}:${email}`));
    return Number.isFinite(at) && Date.now() - at < AUTO_SEND_GAP_MS;
  } catch {
    return false;
  }
}

function markSent(email: string) {
  try { window.sessionStorage.setItem(`${AUTO_SEND_KEY}:${email}`, String(Date.now())); } catch { /* private mode: at most one extra send */ }
}

/**
 * /app/cuenta for an email-only account: the code (or the link) proves the inbox, then the
 * same session chooses a password. Paying needs both; otherwise it can wait. With `checkout`
 * (paying a plan, docs/PAGO_CON_CODIGO.md) the code is sent on arrival and the page goes on
 * to Mercado Pago after it, with no password.
 */
export function AccountSteps({ email, next, proven, paying, checkout }: {
  email: string; next: string; proven: boolean; paying: boolean; checkout?: CodeCheckout;
}) {
  const [link, sendLink, sending] = useActionState(sendAccountLink.bind(null, next), {} satisfies AccountState);
  const [code, submitCode, checking] = useActionState(confirmAccountCode.bind(null, next), {} satisfies AccountState);
  const autoSent = useRef(false);

  useEffect(() => {
    if (!checkout || proven || autoSent.current) return;
    autoSent.current = true;
    if (sentRecently(email)) return;
    markSent(email);
    startTransition(() => sendLink());
  }, [checkout, proven, email, sendLink]);

  if (proven) return <PasswordForm next={next} paying={paying} />;

  // Paying: the code is on its way already, so its box is there from the start.
  const codeOpen = Boolean(checkout) || link.sent || code.sent;
  const confirmLabel = checkout ? checkout.amount ? `Confirmar y pagar ${planPrice(checkout.amount)}` : "Confirmar y seguir" : "Confirmar";
  return <div className="space-y-4">
    {codeOpen ? <form action={submitCode} className="space-y-3">
      <div role="status" className="space-y-1 rounded-lg bg-muted p-4 text-sm">
        <p className="font-medium [overflow-wrap:anywhere]">
          {sending ? `Mandando un código a ${email}…` : link.sent || code.sent ? `Listo: te mandamos un código a ${email}.`
            // The automatic send failed: an earlier code may still work, so nothing is claimed.
            : link.error ? `Escribí el código que te llegó a ${email}.` : `Te mandamos un código a ${email}.`}
        </p>
        <p className="text-muted-foreground">Escribilo acá o tocá el botón del email. Revisá también Spam. Vence en 1 hora y solo funciona el último.</p>
      </div>
      <div className="space-y-2">
        <Label htmlFor="account-code">Código</Label>
        <Input id="account-code" name="code" inputMode="numeric" autoComplete="one-time-code" maxLength={9} required placeholder="123456" autoFocus
          aria-invalid={code.error ? true : undefined} className="h-11 text-lg tracking-[0.3em] tabular-nums" />
      </div>
      {code.error ? <p role="alert" className="text-sm text-destructive">{code.error}</p> : null}
      <Button className="h-11 w-full text-[15px]" disabled={checking}>{checking ? "Comprobando…" : confirmLabel}</Button>
      {checkout?.amount ? <p className="text-xs text-muted-foreground">
        Al confirmar aceptás los <a href="/terminos" target="_blank" rel="noreferrer" className="underline underline-offset-2">Términos y condiciones</a>.
      </p> : null}
    </form> : null}
    <form action={sendLink} className="space-y-3">
      {link.error ? <p role="alert" className="text-sm text-destructive">{link.error}</p> : null}
      <Button className="h-10 w-full" variant={codeOpen ? "outline" : "default"} disabled={sending}>
        {sending ? "Enviando…" : codeOpen ? "Mandarme otro código" : "Mandarme el código"}
      </Button>
    </form>
    {checkout ? <p className="text-xs text-muted-foreground">
      No hace falta una contraseña para pagar. Después entrás con un código como este, o elegís una contraseña desde <Link href="/app/datos" className="underline">Mis datos</Link>.
    </p> : null}
    <p className="text-xs text-muted-foreground">¿No es tu email? Borrá tu cuenta desde <Link href="/app/settings" className="underline">Ajustes</Link> y creá la búsqueda de nuevo con el correcto.</p>
  </div>;
}

/** The proven session chooses its password: the account is completed first (completeAccount). */
export function PasswordForm({ next, paying }: { next: string; paying: boolean }) {
  const [password, submitPassword, saving] = useActionState(completeAccount.bind(null, next), {} satisfies AccountState);
  const router = useRouter();
  // The proof is gone: the page's heading and copy go back to "confirmá tu email".
  useEffect(() => { if (password.expired) router.refresh(); }, [password.expired, router]);

  if (password.expired) return <p role="alert" className="text-sm text-destructive">{password.error}</p>;
  return <form action={submitPassword} className="space-y-4">
    <div className="space-y-2"><Label htmlFor="password">Contraseña</Label><Input id="password" name="password" type="password" autoComplete="new-password" minLength={8} required className="h-10" />
      <p className="text-xs text-muted-foreground">Al menos 8 caracteres.</p></div>
    <div className="space-y-2"><Label htmlFor="confirmPassword">Repetí la contraseña</Label><Input id="confirmPassword" name="confirmPassword" type="password" autoComplete="new-password" minLength={8} required className="h-10" /></div>
    {password.error ? <p role="alert" className="text-sm text-destructive">{password.error}</p> : null}
    <Button className="h-10 w-full" disabled={saving}>{saving ? "Guardando…" : "Guardar contraseña"}</Button>
    {paying ? null : <p className="text-center text-sm"><Link href={next} className="underline underline-offset-4">Ahora no, seguir</Link></p>}
  </form>;
}

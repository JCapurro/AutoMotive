"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useActionState, useEffect } from "react";

import { type AccountState, completeAccount, sendAccountLink } from "@/app/app/cuenta/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/**
 * /app/cuenta for an email-only account: the link proves the inbox, then the
 * same session chooses a password. Paying needs both; otherwise it can wait.
 */
export function AccountSteps({ email, next, proven, paying }: { email: string; next: string; proven: boolean; paying: boolean }) {
  const [password, submitPassword, saving] = useActionState(completeAccount.bind(null, next), {} satisfies AccountState);
  const [link, sendLink, sending] = useActionState(sendAccountLink.bind(null, next), {} satisfies AccountState);
  const router = useRouter();
  // The proof is gone: the page's heading and copy go back to "confirmá tu email".
  useEffect(() => { if (password.expired) router.refresh(); }, [password.expired, router]);

  if (proven && !password.expired) {
    return <form action={submitPassword} className="space-y-4">
      <div className="space-y-2"><Label htmlFor="password">Contraseña</Label><Input id="password" name="password" type="password" autoComplete="new-password" minLength={8} required className="h-10" />
        <p className="text-xs text-muted-foreground">Al menos 8 caracteres.</p></div>
      <div className="space-y-2"><Label htmlFor="confirmPassword">Repetí la contraseña</Label><Input id="confirmPassword" name="confirmPassword" type="password" autoComplete="new-password" minLength={8} required className="h-10" /></div>
      {password.error ? <p role="alert" className="text-sm text-destructive">{password.error}</p> : null}
      <Button className="h-10 w-full" disabled={saving}>{saving ? "Guardando…" : "Guardar contraseña"}</Button>
      {paying ? null : <p className="text-center text-sm"><Link href={next} className="underline underline-offset-4">Ahora no, seguir</Link></p>}
    </form>;
  }

  return <div className="space-y-4">
    {password.error ? <p role="alert" className="text-sm text-destructive">{password.error}</p> : null}
    {link.sent ? <div role="status" className="space-y-1 rounded-lg bg-muted p-4 text-sm">
      <p className="font-medium [overflow-wrap:anywhere]">Listo: abrí el link que te mandamos a {email}.</p>
      <p className="text-muted-foreground">Revisá también Spam. Vence en 1 hora y solo funciona el último.</p>
    </div> : null}
    <form action={sendLink} className="space-y-3">
      {link.error ? <p role="alert" className="text-sm text-destructive">{link.error}</p> : null}
      <Button className="h-10 w-full" variant={link.sent ? "outline" : "default"} disabled={sending}>
        {sending ? "Enviando…" : link.sent ? "Mandarme otro link" : "Mandarme el link"}
      </Button>
    </form>
    <p className="text-xs text-muted-foreground">¿No es tu email? Borrá tu cuenta desde <Link href="/app/settings" className="underline">Ajustes</Link> y creá la búsqueda de nuevo con el correcto.</p>
  </div>;
}

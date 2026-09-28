"use client";

import { MailCheck } from "lucide-react";
import { useActionState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { type LoginState, sendMagicLink, verifyCode } from "./actions";

export function LoginForm({ next, linkError }: { next: string; linkError: boolean }) {
  const [sent, send, sending] = useActionState(sendMagicLink, { step: "email", next } satisfies LoginState);
  const [checked, verify, verifying] = useActionState(verifyCode, { step: "code", next } satisfies LoginState);

  if (sent.step === "code") {
    const codeError = checked.email === sent.email ? checked.error : undefined;
    return (
      <div className="space-y-5">
        <div className="flex gap-3 rounded-lg bg-muted p-4">
          <MailCheck className="mt-0.5 size-5 shrink-0" aria-hidden />
          <div className="space-y-1 text-sm">
            <p className="font-medium">Revisá tu email</p>
            <p className="text-muted-foreground">
              Te mandamos un link a <span className="font-medium text-foreground">{sent.email}</span>. Abrilo desde
              este dispositivo para entrar.
            </p>
          </div>
        </div>
        <form action={verify} className="space-y-2">
          <input type="hidden" name="email" value={sent.email} />
          <input type="hidden" name="next" value={next} />
          <Label htmlFor="code">¿Lo abriste en otro dispositivo? Ingresá el código del email</Label>
          <div className="flex gap-2">
            <Input
              id="code"
              name="code"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={7}
              placeholder="123456"
              className="h-10 tracking-widest"
            />
            <Button type="submit" className="h-10" disabled={verifying}>
              {verifying ? "Verificando…" : "Entrar"}
            </Button>
          </div>
          {codeError ? (
            <p role="alert" className="text-sm text-destructive">
              {codeError}
            </p>
          ) : null}
        </form>
        <form action={send}>
          <input type="hidden" name="email" value={sent.email} />
          <input type="hidden" name="next" value={next} />
          <Button type="submit" variant="link" className="h-auto p-0" disabled={sending}>
            {sending ? "Reenviando…" : "Reenviar el link"}
          </Button>
        </form>
      </div>
    );
  }

  return (
    <form action={send} className="space-y-4">
      {linkError ? (
        <Alert variant="destructive">
          <AlertDescription>El link venció o ya se usó. Pedí uno nuevo.</AlertDescription>
        </Alert>
      ) : null}
      <input type="hidden" name="next" value={next} />
      <div className="space-y-2">
        <Label htmlFor="email">Email</Label>
        <Input
          id="email"
          name="email"
          type="email"
          autoComplete="email"
          required
          placeholder="vos@email.com"
          defaultValue={sent.email}
          className="h-10"
        />
      </div>
      {sent.error ? (
        <p role="alert" className="text-sm text-destructive">
          {sent.error}
        </p>
      ) : null}
      <Button type="submit" className="h-10 w-full" disabled={sending}>
        {sending ? "Enviando…" : "Enviarme el link"}
      </Button>
      <p className="text-center text-xs text-muted-foreground">
        Sin contraseñas: te mandamos un link para entrar. Si es tu primera vez, creamos tu cuenta.
      </p>
    </form>
  );
}

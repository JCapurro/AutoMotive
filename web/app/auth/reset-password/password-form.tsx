"use client";

import { useActionState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { type PasswordState, updatePassword } from "./actions";

export function PasswordForm() {
  const [state, action, pending] = useActionState(updatePassword, {} satisfies PasswordState);
  return <form action={action} className="space-y-4">
    <div className="space-y-2"><Label htmlFor="password">Nueva contraseña</Label><Input id="password" name="password" type="password" autoComplete="new-password" minLength={8} required /></div>
    <div className="space-y-2"><Label htmlFor="confirmPassword">Repetí la contraseña</Label><Input id="confirmPassword" name="confirmPassword" type="password" autoComplete="new-password" minLength={8} required /></div>
    {state.error ? <p role="alert" className="text-sm text-destructive">{state.error}</p> : null}
    <Button className="w-full" disabled={pending}>{pending ? "Guardando…" : "Guardar contraseña"}</Button>
  </form>;
}

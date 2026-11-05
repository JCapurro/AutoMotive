"use client";

import { useActionState, useEffect, useState, useSyncExternalStore } from "react";
import { X } from "lucide-react";

import { type PhoneState, phonePromptEvent, savePhone } from "@/app/app/datos/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatArPhone } from "@/lib/phone";

/** «Mis datos»: change or remove the mobile. */
export function PhoneForm({ phone }: { phone: string | null }) {
  const [state, submit, pending] = useActionState(savePhone.bind(null, "datos"), {} satisfies PhoneState);
  const current = state.saved ? state.phone ?? null : phone;
  return (
    <form action={submit} className="space-y-2">
      <Label htmlFor="phone">Celular</Label>
      <div className="flex flex-wrap gap-2">
        <Input id="phone" name="phone" type="tel" inputMode="tel" autoComplete="tel-national" placeholder="11 2345-6789"
          defaultValue={formatArPhone(current)} key={current ?? ""} aria-invalid={state.error ? true : undefined}
          aria-describedby={state.error ? "phone-error" : "phone-help"} className="h-10 max-w-64 flex-1" />
        <Button type="submit" variant="outline" className="h-10" disabled={pending}>{pending ? "Guardando…" : "Guardar"}</Button>
      </div>
      {state.error ? <p id="phone-error" role="alert" className="text-sm text-destructive">{state.error}</p>
        : <p id="phone-help" role={state.saved ? "status" : undefined} className="text-xs text-muted-foreground">
          {state.saved ? current ? "Listo, guardamos tu celular." : "Listo, borramos tu celular." : "Con código de área. Para borrarlo, dejalo vacío y guardá."}
        </p>}
    </form>
  );
}

const noop = () => () => {};
const DISMISSED_KEY = "ea_phone_prompt_closed";
const VIEWED_KEY = "ea_phone_prompt_viewed";

function stored(key: string): boolean {
  try { return window.localStorage.getItem(key) === "1"; } catch { return false; }
}
function store(key: string) {
  try { window.localStorage.setItem(key, "1"); } catch { /* private mode: it shows again next time */ }
}

/**
 * On the results, once they're there (option B, 04/11): the mobile is asked
 * after the search shows its value, never before. Closing it keeps it closed
 * in this browser; «Mis datos» can always add it.
 */
export function PhonePrompt({ profileId }: { profileId: number }) {
  const [state, submit, pending] = useActionState(savePhone.bind(null, "results"), {} satisfies PhoneState);
  // Shown only after hydration, so a prompt closed before never flashes.
  const hydrated = useSyncExternalStore(noop, () => true, () => false);
  const [closed, setClosed] = useState(false);
  const visible = hydrated && !closed && !stored(DISMISSED_KEY);
  useEffect(() => {
    if (!visible || stored(VIEWED_KEY)) return;
    store(VIEWED_KEY);
    void phonePromptEvent("viewed", profileId).catch(() => {});
  }, [visible, profileId]);
  if (!visible && !state.saved) return null;
  if (state.saved) {
    return <p role="status" className="rounded-lg border bg-muted/50 p-4 text-sm">Listo, guardamos tu celular. Lo cambiás cuando quieras en Mis datos.</p>;
  }
  const close = () => {
    store(DISMISSED_KEY);
    setClosed(true);
    void phonePromptEvent("dismissed", profileId).catch(() => {});
  };
  return (
    <section aria-labelledby="phone-prompt-title" className="relative rounded-lg border bg-card p-4 pr-10">
      <button type="button" onClick={close} aria-label="Cerrar" className="absolute top-2 right-2 grid size-8 place-items-center rounded-full text-muted-foreground hover:bg-muted hover:text-foreground">
        <X className="size-4" aria-hidden />
      </button>
      <h2 id="phone-prompt-title" className="font-medium">Dejanos tu celular</h2>
      <p className="mt-1 text-sm text-muted-foreground">Es opcional. Lo usamos solo por si necesitamos contactarte sobre tu búsqueda o tu cuenta. No se lo damos a vendedores ni a nadie.</p>
      <form action={submit} className="mt-3 flex flex-wrap items-start gap-2">
        <div className="min-w-48 flex-1 space-y-1">
          <Label htmlFor="phone-prompt" className="sr-only">Celular</Label>
          <Input id="phone-prompt" name="phone" type="tel" inputMode="tel" autoComplete="tel-national" placeholder="11 2345-6789" required
            aria-invalid={state.error ? true : undefined} aria-describedby={state.error ? "phone-prompt-error" : undefined} className="h-10 bg-background" />
          {state.error ? <p id="phone-prompt-error" role="alert" className="text-sm text-destructive">{state.error}</p> : null}
        </div>
        <Button type="submit" className="h-10" disabled={pending}>{pending ? "Guardando…" : "Guardar"}</Button>
      </form>
    </section>
  );
}

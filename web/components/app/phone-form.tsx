"use client";

import { useActionState, useEffect, useState, useSyncExternalStore } from "react";
import { X } from "lucide-react";

import { type PhoneState, phonePromptEvent, savePhone } from "@/app/app/datos/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatArPhone } from "@/lib/phone";
import { closedKey, PHONE_PROMPT_TEXT, type PhonePromptPlace, promptQuiet, viewedKey } from "@/lib/phone-prompt";

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

function read(key: string): string | null {
  try { return window.localStorage.getItem(key); } catch { return null; }
}
/** Closed in this place less than a week ago (read from the browser, like the marks above). */
function quiet(place: PhonePromptPlace): boolean {
  return promptQuiet(read(closedKey(place)), new Date().getTime());
}
function store(key: string, value: string) {
  try { window.localStorage.setItem(key, value); } catch { /* private mode: it shows again next time */ }
}

/**
 * The mobile, for whoever has none: asked with the email when the account is
 * created, on the results once they're there (option B, 04/11) and again on the
 * home, the saved cars and a listing (Juan, 20/11). Closing it keeps it closed
 * in that place and this browser for a week (lib/phone-prompt.ts); «Mis datos»
 * can always add it.
 */
export function PhonePrompt({ profileId = null, place = "results" }: { profileId?: number | null; place?: PhonePromptPlace }) {
  const [state, submit, pending] = useActionState(savePhone.bind(null, place), {} satisfies PhoneState);
  // Shown only after hydration, so a prompt closed before never flashes.
  const hydrated = useSyncExternalStore(noop, () => true, () => false);
  const [closed, setClosed] = useState(false);
  const visible = hydrated && !closed && !quiet(place);
  useEffect(() => {
    if (!visible || read(viewedKey(place)) === "1") return;
    store(viewedKey(place), "1");
    void phonePromptEvent("viewed", profileId, place).catch(() => {});
  }, [visible, profileId, place]);
  if (!visible && !state.saved) return null;
  if (state.saved) {
    return <p role="status" className="rounded-lg border bg-muted/50 p-4 text-sm">Listo, guardamos tu celular. Lo cambiás cuando quieras en Mis datos.</p>;
  }
  const close = () => {
    store(closedKey(place), String(Date.now()));
    setClosed(true);
    void phonePromptEvent("dismissed", profileId, place).catch(() => {});
  };
  return (
    <section aria-labelledby="phone-prompt-title" className="relative rounded-lg border bg-card p-4 pr-10" data-testid="phone-prompt" data-place={place}>
      <button type="button" onClick={close} aria-label="Cerrar" className="absolute top-2 right-2 grid size-8 place-items-center rounded-full text-muted-foreground hover:bg-muted hover:text-foreground">
        <X className="size-4" aria-hidden />
      </button>
      <h2 id="phone-prompt-title" className="font-medium">{PHONE_PROMPT_TEXT[place].title}</h2>
      <p className="mt-1 text-sm text-muted-foreground">{PHONE_PROMPT_TEXT[place].body}</p>
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

import { BellRing, Check, Loader2 } from "lucide-react";

import { AutoRefresh } from "@/components/app/auto-refresh";
import { Button } from "@/components/ui/button";

export function SearchLoadingButton() {
  return (
    <Button disabled className="h-9 gap-2 px-4 disabled:opacity-100">
      <Loader2 className="size-4 animate-spin motion-reduce:animate-none" aria-hidden />
      Cargando…
    </Button>
  );
}

/**
 * A search being prepared. It splits "now" (what is already published) from
 * "from now on" (the new listings we alert about), so nobody reads the first
 * pass as the whole value and nobody feels they must watch the page.
 * `email`: where its alerts go. `trialEnds`: the free trial's end, already formatted.
 */
export function SearchPreparation({ email = null, trialEnds = null }: { email?: string | null; trialEnds?: string | null } = {}) {
  return (
    <section role="status" aria-label="Preparación de resultados" data-testid="search-preparation" className="rounded-lg border bg-muted/50 p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-5">
        <div className="max-w-xl space-y-4">
          <h2 className="type-heading text-[22px] leading-tight" data-testid="search-active">Tu búsqueda ya está vigilando</h2>
          <ul className="space-y-3 text-sm leading-relaxed">
            <li className="flex gap-3">
              <Check className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
              <span>
                <strong className="font-semibold">Ahora:</strong> revisamos lo publicado en los últimos 30 días. Lleva{" "}
                <strong className="font-semibold">al menos 2 minutos</strong> y esta página se actualiza sola.
              </span>
            </li>
            <li className="flex gap-3">
              <BellRing className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
              <span>
                <strong className="font-semibold">Desde ahora:</strong> cada auto nuevo que encaje te llega{" "}
                {email ? <>a <span className="[overflow-wrap:anywhere]">{email}</span></> : "por email"}. No hace falta que vuelvas a entrar.
              </span>
            </li>
          </ul>
          {trialEnds ? <p className="text-xs text-muted-foreground">Tu prueba gratis sigue hasta el {trialEnds} (hora argentina).</p> : null}
        </div>
        <SearchLoadingButton />
      </div>
      <AutoRefresh />
    </section>
  );
}

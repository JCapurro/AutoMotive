import { Loader2 } from "lucide-react";

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
 * A search being prepared. `email`: where its alerts go, so the first search
 * ends on "it's active" rather than only a spinner, and nobody feels they
 * must watch the page. `trialEnds`: the free trial's end, already formatted.
 */
export function SearchPreparation({ email = null, trialEnds = null }: { email?: string | null; trialEnds?: string | null } = {}) {
  return (
    <section role="status" aria-label="Preparación de resultados" data-testid="search-preparation" className="rounded-lg border bg-muted/50 p-5 sm:p-6">
      <p className="mb-3 max-w-xl text-sm font-medium" data-testid="search-active">
        Tu búsqueda está activa.{email ? <> Te avisamos a <span className="[overflow-wrap:anywhere]">{email}</span> cuando aparezca un auto que valga la pena.</> : null}
        {trialEnds ? <> Tu prueba gratis sigue hasta el {trialEnds} (hora argentina).</> : null}
      </p>
      <div className="flex flex-wrap items-center justify-between gap-5">
        <div className="max-w-lg space-y-2">
          <h2 className="type-heading text-[22px] leading-tight">Estamos preparando tus resultados</h2>
          <p className="text-sm leading-relaxed text-muted-foreground">
            La revisión necesita <strong className="font-semibold text-foreground">al menos 2 minutos.</strong>
            <br />
            Los resultados se actualizan solos. Podés cerrar la página: te avisamos por email.
          </p>
        </div>
        <SearchLoadingButton />
      </div>
      <AutoRefresh />
    </section>
  );
}

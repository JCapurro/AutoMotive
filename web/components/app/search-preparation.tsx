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

export function SearchPreparation() {
  return (
    <section role="status" aria-label="Preparación de resultados" data-testid="search-preparation" className="rounded-lg border bg-muted/50 p-5 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-5">
        <div className="max-w-lg space-y-2">
          <h2 className="type-heading text-[22px] leading-tight">Estamos preparando tus resultados</h2>
          <p className="text-sm leading-relaxed text-muted-foreground">
            La revisión necesita <strong className="font-semibold text-foreground">al menos 2 minutos.</strong>
            <br />
            Los resultados se actualizan solos.
          </p>
        </div>
        <SearchLoadingButton />
      </div>
      <AutoRefresh />
    </section>
  );
}

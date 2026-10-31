"use client";

import { SearchX, X } from "lucide-react";
import Link from "next/link";
import { useTransition } from "react";

import { dismissDiagnosis } from "@/app/app/searches/actions";
import { Button } from "@/components/ui/button";

/**
 * Bot de pocos resultados (docs/POCOS_RESULTADOS.md): why this search brings
 * few results, written by the worker from its filter funnel, and that we keep
 * watching. The page decides whether it still applies.
 */
export function LowResultsNotice({
  profileId,
  explanation,
  suggestions,
}: {
  profileId: number;
  explanation: string;
  suggestions: string[];
}) {
  const [pending, start] = useTransition();
  return (
    <section data-testid="low-results" aria-labelledby="low-results-title" className="relative space-y-2 rounded-lg border bg-muted/50 p-4 pr-10 text-sm">
      <h2 id="low-results-title" className="flex items-center gap-2 font-semibold">
        <SearchX aria-hidden className="size-4" /> ¿Por qué hay pocos resultados?
      </h2>
      <p>{explanation}</p>
      {suggestions.length ? (
        <div className="space-y-1">
          <p className="font-medium">Si querés ver más:</p>
          <ul className="list-disc space-y-0.5 pl-5">
            {suggestions.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <Button asChild variant="outline" size="sm">
        <Link href={`/app/searches/${profileId}/edit`}>Ajustar filtros</Link>
      </Button>
      <Button
        variant="ghost"
        size="icon"
        aria-label="Ocultar"
        disabled={pending}
        className="absolute right-2 top-2 size-7"
        onClick={() => start(() => dismissDiagnosis(profileId))}
      >
        <X aria-hidden />
      </Button>
    </section>
  );
}

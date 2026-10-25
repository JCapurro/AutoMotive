"use client";

import { useEffect, useState, useTransition } from "react";

import { relaxSuggestions } from "@/app/app/searches/actions";
import { Button } from "@/components/ui/button";
import { analyticsEvent } from "@/lib/google-analytics";
import type { SearchInput } from "@/lib/search-form";
import type { RelaxSuggestion } from "@/lib/search-relax";
import { cn } from "@/lib/utils";

/**
 * Under a preview of 0 (lib/search-relax.ts): what to loosen, each with its
 * count and a button that applies it. `inputKey` is the preview's key: the
 * suggestions are counted once it settles, with the preview's debounce.
 */
export function RelaxSuggestions({
  input,
  inputKey,
  onApply,
}: {
  input: SearchInput;
  inputKey: string;
  onApply: (suggestion: RelaxSuggestion) => void;
}) {
  const [result, setResult] = useState<{ key: string; suggestions: RelaxSuggestion[] } | null>(null);
  const [loading, startLoading] = useTransition();

  useEffect(() => {
    let current = true;
    const timer = setTimeout(() => {
      startLoading(async () => {
        const suggestions = await relaxSuggestions(input).catch(() => []);
        if (current) setResult({ key: inputKey, suggestions });
      });
    }, 400);
    return () => {
      current = false;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- inputKey is the input minus the alert settings
  }, [inputKey]);
  const suggestions = result?.key === inputKey ? result.suggestions : [];

  return (
    <div data-testid="relax-suggestions" className="space-y-2">
      <p className="text-xs text-muted-foreground">Hoy no hay ninguna publicada. Es normal con autos buscados: duran poco.</p>
      {suggestions.length ? (
        <div className={cn("space-y-1.5", loading && "opacity-60")}>
          <p className="text-xs font-medium">Si aflojás un filtro:</p>
          <ul className="space-y-1.5">
            {suggestions.map((s) => (
              <li key={s.key}>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-auto w-full justify-between gap-2 whitespace-normal py-1.5 text-left"
                  onClick={() => {
                    analyticsEvent("search_relax_applied", { relax: s.key, count: s.count });
                    onApply(s);
                  }}
                >
                  <span>{s.label}</span>
                  <span className="shrink-0 tabular-nums text-muted-foreground">
                    {s.count} {s.count === 1 ? "publicación" : "publicaciones"}
                  </span>
                </Button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <p className="text-xs text-muted-foreground">Igual te avisamos cuando aparezca una que coincida.</p>
    </div>
  );
}

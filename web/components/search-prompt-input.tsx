"use client";

import { useId } from "react";

import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ASSISTED_EXAMPLES, ASSISTED_MAX_CHARS } from "@/lib/assisted";

export function SearchPromptInput({ value, onChange, disabled = false, showExamples = true }: {
  value: string;
  onChange: (text: string) => void;
  disabled?: boolean;
  showExamples?: boolean;
}) {
  const id = useId();
  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        <Label htmlFor={id} className="text-base font-semibold">¿Qué auto buscás?</Label>
        <p id={`${id}-help`} className="text-sm leading-relaxed text-muted-foreground">
          Escribilo como se lo contarías a alguien: modelo, versión, años, presupuesto, kilómetros, zona.
          Si buscás varios, nombralos todos. Revisás los filtros antes de guardar.
        </p>
      </div>
      <Textarea
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={ASSISTED_EXAMPLES[0]}
        maxLength={ASSISTED_MAX_CHARS}
        rows={3}
        disabled={disabled}
        aria-describedby={`${id}-help ${id}-count`}
        className="min-h-28 bg-background text-base"
      />
      <p id={`${id}-count`} className="text-right text-xs text-muted-foreground">
        {value.length}/{ASSISTED_MAX_CHARS}
      </p>
      {showExamples && !value && !disabled ? (
        <div className="space-y-1.5">
          <p className="text-xs text-muted-foreground">Ejemplos:</p>
          <ul className="flex flex-col gap-1.5">
            {ASSISTED_EXAMPLES.map((example) => (
              <li key={example}>
                <button
                  type="button"
                  onClick={() => onChange(example)}
                  className="w-full rounded-md bg-muted px-2.5 py-1.5 text-left text-sm hover:bg-muted/70"
                >
                  «{example}»
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

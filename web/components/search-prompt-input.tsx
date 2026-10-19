"use client";

import { useId } from "react";

import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ASSISTED_EXAMPLES, ASSISTED_MAX_CHARS } from "@/lib/assisted";

export function SearchPromptInput({ value, onChange, disabled = false, showExamples = true, compact = false, invalid = false, describedBy }: {
  value: string;
  onChange: (text: string) => void;
  disabled?: boolean;
  showExamples?: boolean;
  /** The landing: shorter help and no counter, so the button stays near the fold. */
  compact?: boolean;
  invalid?: boolean;
  /** An error shown next to the field, read along with the help. */
  describedBy?: string;
}) {
  const id = useId();
  // The landing never shows the counter: appearing midway would shift the form (maxLength still applies).
  const counter = !compact;
  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        <Label htmlFor={id} className="text-base font-semibold">¿Qué auto buscás?</Label>
        <p id={`${id}-help`} className="text-sm leading-relaxed text-muted-foreground">
          {compact ? "Modelo, años, presupuesto, kilómetros y zona, como se lo contarías a alguien."
            : <>Escribilo como se lo contarías a alguien: modelo, versión, años, presupuesto, kilómetros, zona.
              Si buscás varios, nombralos todos (cada modelo cuenta como una búsqueda). Revisás los datos antes de guardar.</>}
        </p>
      </div>
      {/* Fixed size: it doesn't grow while typing nor resize by hand; long text scrolls inside. */}
      <Textarea
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={`Ej.: ${ASSISTED_EXAMPLES[0]}`}
        maxLength={ASSISTED_MAX_CHARS}
        rows={3}
        disabled={disabled}
        aria-invalid={invalid || undefined}
        aria-describedby={[`${id}-help`, counter ? `${id}-count` : null, describedBy].filter(Boolean).join(" ")}
        className={compact ? "h-24 resize-none bg-background text-base field-sizing-fixed" : "h-28 resize-none bg-background text-base field-sizing-fixed"}
      />
      {counter ? <p id={`${id}-count`} className="text-right text-xs text-muted-foreground">
        {value.length}/{ASSISTED_MAX_CHARS}
      </p> : null}
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

"use client";

import { useState, useTransition } from "react";
import { toast } from "sonner";

import { updateConfig } from "@/app/admin/actions";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

/** One app_config value, edited as JSON. */
export function ConfigEditor({ configKey, value }: { configKey: string; value: unknown }) {
  const initial = JSON.stringify(value, null, 2);
  const [text, setText] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const rows = Math.min(Math.max(initial.split("\n").length, 1), 14);
  return (
    <form
      className="space-y-2"
      onSubmit={(e) => {
        e.preventDefault();
        start(async () => {
          const res = await updateConfig(configKey, text);
          setError(res.error ?? null);
          if (res.ok) toast.success(`${configKey} guardado`);
        });
      }}
    >
      <Textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={rows}
        spellCheck={false}
        aria-label={configKey}
        aria-invalid={error ? true : undefined}
        className="font-mono text-xs"
      />
      <div className="flex items-center gap-2">
        <Button type="submit" size="sm" variant="outline" disabled={pending || text === initial}>
          Guardar
        </Button>
        {text !== initial ? (
          <Button type="button" size="sm" variant="ghost" onClick={() => (setText(initial), setError(null))}>
            Descartar
          </Button>
        ) : null}
        {error ? (
          <p role="alert" className="text-xs text-destructive">
            {error}
          </p>
        ) : null}
      </div>
    </form>
  );
}

"use client";

import { useState, useTransition } from "react";
import { toast } from "sonner";

import { updateConfig } from "@/app/admin/actions";
import { LifecycleForm, LimitsForm, OfferForm } from "@/components/admin/config-forms";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { configDifferences, configFieldLabel, sameConfig, validateConfigChange, type ConfigAudit } from "@/lib/admin-config";
import { when } from "@/lib/admin-format";
import type { Json } from "@/types/database";

function display(value: unknown) {
  return value === undefined ? "Campo ausente (ver comportamiento indicado en el formulario)" : JSON.stringify(value);
}

/** One draft feeds both the guided controls and advanced editor; untouched fields survive. */
export function ConfigEditor({ configKey, value, history = [] }: { configKey: string; value: Json; history?: ConfigAudit[] }) {
  const initial = JSON.stringify(value, null, 2);
  const [text, setText] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const rows = Math.min(Math.max(initial.split("\n").length, 1), 14);
  let draft: unknown;
  let parseError: string | null = null;
  try { draft = JSON.parse(text); } catch { parseError = "No es JSON válido."; }
  const dirty = !parseError ? !sameConfig(value, draft) : text !== initial;
  const validation = parseError ?? validateConfigChange(configKey, draft, value);
  const differences = !parseError ? configDifferences(value, draft) : [];
  const Guided = configKey === "pro_offer" ? OfferForm : configKey === "plan_limits" ? LimitsForm : configKey === "lifecycle_emails" ? LifecycleForm : null;
  const reset = () => { setText(initial); setError(null); };
  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        start(async () => {
          if (validation) { setError(validation); return; }
          try {
            const res = await updateConfig(configKey, text, value);
            setError(res.error ?? null);
            if (res.ok) toast.success("Configuración guardada");
          } catch {
            setError("No pudimos confirmar el guardado. Recargá la página antes de reintentar.");
          }
        });
      }}
    >
      <fieldset disabled={pending} className="min-w-0 space-y-4">
      {Guided && !parseError ? <Guided value={draft} onChange={(next) => { setText(JSON.stringify(next, null, 2)); setError(null); }} /> : null}
      <details open={!Guided}>
        <summary className="cursor-pointer text-sm font-medium">JSON avanzado{Guided ? " (conserva las demás opciones)" : ""}</summary>
        <p className="my-2 text-xs text-muted-foreground">Solo claves ya existentes. Revisá el resumen antes de guardar. Las opciones no mostradas en el formulario se conservan.</p>
        <Textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={rows}
        spellCheck={false}
        aria-label={configKey}
        aria-invalid={error ? true : undefined}
        className="font-mono text-xs"
      />
      </details>
      {dirty ? <div className="space-y-2 rounded-md border p-3" aria-live="polite"><p className="text-sm font-medium">Cambios propuestos (todavía sin aplicar)</p>{validation ? <p className="text-sm text-destructive">{validation}</p> : <ul className="space-y-2 text-xs">{differences.map((item) => <li key={item.path} className="break-words"><span className="font-medium">{configFieldLabel(configKey, item.path)}</span><div className="text-muted-foreground">Antes: {display(item.before)}</div><div>Después: {display(item.after)}</div></li>)}</ul>}</div> : null}
      <div className="flex items-center gap-2">
        <Button type="submit" size="sm" variant="outline" disabled={pending || !dirty || Boolean(validation)}>
          {pending ? "Guardando…" : "Guardar cambios"}
        </Button>
        {dirty ? (
          <Button type="button" size="sm" variant="ghost" onClick={reset}>
            Descartar
          </Button>
        ) : null}
        {error ? (
          <p role="alert" className="text-xs text-destructive">
            {error}
          </p>
        ) : null}
      </div>
      {history.length ? <details className="border-t pt-3"><summary className="cursor-pointer text-sm font-medium">Historial reciente ({history.length})</summary><ol className="mt-3 space-y-4">{history.map((entry) => <li key={entry.id} className="space-y-2 text-xs"><p><strong>{entry.actor_email ?? entry.actor_id}</strong> · {when(entry.created_at)}</p><ul className="space-y-1">{configDifferences(entry.before_value, entry.after_value).map((item) => <li key={item.path} className="break-words"><strong>{configFieldLabel(configKey, item.path)}</strong><div className="text-muted-foreground">Antes: {display(item.before)}</div><div>Después: {display(item.after)}</div></li>)}</ul><Button type="button" variant="outline" size="sm" disabled={pending} onClick={() => { setText(JSON.stringify(entry.before_value, null, 2)); setError(null); }}>Preparar restauración al valor anterior</Button><p className="text-muted-foreground">Carga el valor para revisarlo; requiere guardar y pasa las mismas validaciones.</p></li>)}</ol></details> : null}
      </fieldset>
    </form>
  );
}

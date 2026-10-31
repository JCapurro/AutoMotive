"use client";

import { Input } from "@/components/ui/input";
import { configObject, LIFECYCLE_DEFAULTS, LIFECYCLE_KINDS, MAX_LIFECYCLE_WINDOW_HOURS, MAX_OFFER_ARS } from "@/lib/admin-config";
import { DEFAULT_PLAN_LIMITS, DEFAULT_PRO_OFFER, PLAN_NAMES, planLimits } from "@/lib/pro";

type FormProps = { value: unknown; onChange: (value: Record<string, unknown>) => void };
function put(value: unknown, path: string[], next: unknown): Record<string, unknown> {
  const out = { ...configObject(value) }, [key, ...rest] = path;
  if (rest.length) out[key] = put(out[key], rest, next);
  else if (next === undefined) delete out[key];
  else out[key] = next;
  return out;
}

function Toggle({ label, checked, onChange, inherited = false }: { label: string; checked: boolean; onChange: (v: boolean) => void; inherited?: boolean }) {
  return <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="mt-1 size-4 shrink-0" /><span>{label}{inherited ? <span className="block text-xs text-muted-foreground">Valor predeterminado; se conserva hasta que lo cambies.</span> : null}</span></label>;
}

export function OfferForm({ value, onChange }: FormProps) {
  const raw = configObject(value);
  return <div className="space-y-4">
    <label className="grid gap-1 text-sm">Versión de la oferta<Input value={typeof raw.version === "string" ? raw.version : ""} placeholder={DEFAULT_PRO_OFFER.version} maxLength={80} onChange={(e) => onChange(put(raw, ["version"], e.target.value))} /><span className="text-xs text-muted-foreground">Usá una versión nueva si cambiás un importe; por ejemplo, ars-2026-11.</span></label>
    <div className="grid gap-4 sm:grid-cols-2">{([ ["pass_30", "Particular"], ["pro_monthly", "Pro"] ] as const).map(([key, name]) => <label key={key} className="grid gap-1 text-sm">{name}: importe en pesos (ARS)<Input type="number" min={1} max={MAX_OFFER_ARS} step={1} value={String(configObject(raw[key]).amount ?? "")} placeholder={String(DEFAULT_PRO_OFFER[key].amount)} onChange={(e) => onChange(put(raw, [key, "amount"], e.target.value === "" ? "" : Number(e.target.value)))} /><span className="text-xs text-muted-foreground">30 días · moneda y duración fijas. Máximo compatible con el registro de pagos: 9.999.999.999 ARS.</span></label>)}</div>
    <p className="text-xs text-muted-foreground">Afecta las nuevas confirmaciones de compra. Los pagos ya registrados conservan su importe y período. No inicia cobros por sí solo.</p>
  </div>;
}

const LIMIT_FIELDS = [
  { key: "max_profiles", label: "Búsquedas activas", min: 0, fallback: "maxProfiles" },
  { key: "max_visible_results", label: "Resultados por búsqueda", min: 1, fallback: "maxVisibleResults" },
  { key: "immediate_alerts_per_day", label: "Avisos inmediatos por día", min: 0, fallback: "immediateAlertsPerDay" },
  { key: "max_locations", label: "Zonas por búsqueda", min: 1, fallback: "maxLocations" },
] as const;

export function LimitsForm({ value, onChange }: FormProps) {
  const raw = configObject(value), effective = planLimits(value);
  return <div className="space-y-4">
    <p className="rounded-md bg-muted p-3 text-sm">{raw.enforced === true ? "Los límites se están aplicando." : "Piloto: los límites solo se miden, todavía no se aplican."} La activación se administra desde <a className="underline" href="/admin/billing">Cobros</a>.</p>
    <div className="grid gap-4 xl:grid-cols-3">{(["free", "pass", "pro"] as const).map((tier) => {
      const current = configObject(raw[tier]), defaults = DEFAULT_PLAN_LIMITS[tier], caps = effective[tier], tierMissing = !(tier in raw);
      return <fieldset key={tier} disabled={!(tier in raw)} className="min-w-0 space-y-3 rounded-lg border p-3"><legend className="px-1 font-medium">{PLAN_NAMES[tier]}</legend>
        {tierMissing ? <p className="text-xs text-muted-foreground">Este plan hereda los valores predeterminados de la web que se muestran aquí. La base puede usar otros topes sin su bloque; completalo en JSON avanzado antes de usar estos controles. Abrir el formulario no agrega esos valores.</p> : null}
        {tier === "free" ? <label className="grid gap-1 text-sm">Resultados acumulados durante la prueba<Input type="number" aria-label="Prueba gratis: Resultados acumulados durante la prueba" min={1} max={2_147_483_647} step={1} value={String(current.max_total_results ?? 50)} onChange={(e) => onChange(put(raw, [tier, "max_total_results"], e.target.value === "" ? undefined : Number(e.target.value)))} /><span className="text-xs text-muted-foreground">Cada publicación cuenta una sola vez. Editar o recrear búsquedas no reinicia el cupo.</span></label> : null}
        {LIMIT_FIELDS.map(({ key, label, min, fallback }) => {
          const inherited = !(key in current), unlimited = current[key] === null;
          // Legacy immediate_alerts is intentionally kept until this field is explicitly edited.
          const hint = key === "immediate_alerts_per_day" ? ("immediate_alerts" in current ? "Sin este campo: usa immediate_alerts (true = tope global; false = sin avisos inmediatos)." : "Sin campo: 0 avisos inmediatos.") : key === "max_profiles" ? `Sin campo: la base no limita búsquedas y la web muestra ${defaults.maxProfiles}. Indicá un número para mantener un límite coherente.` : key === "max_visible_results" ? "Sin campo: sin tope de resultados." : `Sin campo: ${defaults[fallback] ?? "sin tope"}.`;
          return <div key={key} className="space-y-1"><label className="grid gap-1 text-sm">{label}<Input type="number" aria-label={`${PLAN_NAMES[tier]}: ${label}`} min={min} max={2_147_483_647} step={1} disabled={unlimited} value={String((tierMissing ? caps[fallback] : current[key]) ?? "")} placeholder={inherited ? "Campo ausente" : unlimited ? "Sin tope" : ""} onChange={(e) => onChange(put(raw, [tier, key], e.target.value === "" ? key === "max_profiles" ? "" : undefined : Number(e.target.value)))} /></label>
            <p className="text-xs text-muted-foreground">{hint}{key === "immediate_alerts_per_day" ? " 0 = solo resumen diario." : ""}</p>
            {key === "max_visible_results" || key === "max_locations" ? <Toggle label="Sin tope" checked={caps[fallback] === null} onChange={(checked) => onChange(put(raw, [tier, key], checked ? null : defaults[fallback] ?? 1))} /> : null}
          </div>;
        })}
        <Toggle label="Umbral de oportunidad por búsqueda" checked={caps.thresholdAlerts} inherited={!("threshold_alerts" in current)} onChange={(checked) => onChange(put(raw, [tier, "threshold_alerts"], checked))} />
        <Toggle label="Buscar por carrocería sin modelo" checked={caps.modelLessSearch} inherited={!("model_less_search" in current)} onChange={(checked) => onChange(put(raw, [tier, "model_less_search"], checked))} />
        <Toggle label="Costo total estimado (PAR-01)" checked={current.total_cost === true} inherited={!("total_cost" in current)} onChange={(checked) => onChange(put(raw, [tier, "total_cost"], checked))} />
      </fieldset>;
    })}</div>
    <p className="text-xs text-muted-foreground">La web usa los cambios en la próxima lectura y el worker al renovar su caché (aproximadamente un minuto). No elimina búsquedas existentes. Los avisos que superan el tope diario van al resumen; el umbral de oportunidad puede exceptuar ese tope.</p>
  </div>;
}

export function LifecycleForm({ value, onChange }: FormProps) {
  const raw = configObject(value), kinds = configObject(raw.kinds);
  return <div className="space-y-4">
    <Toggle label="Enviar emails del plan" checked={typeof raw.enabled === "boolean" ? raw.enabled : LIFECYCLE_DEFAULTS.enabled} inherited={!("enabled" in raw)} onChange={(checked) => onChange(put(raw, ["enabled"], checked))} />
    <div className="grid gap-4 sm:grid-cols-2">
      {([ ["send_from", "Enviar desde"], ["send_until", "Enviar hasta (sin incluir)"] ] as const).map(([key, label]) => <label key={key} className="grid gap-1 text-sm">{label}<Input type="time" value={typeof raw[key] === "string" ? raw[key] : LIFECYCLE_DEFAULTS[key]} onChange={(e) => onChange(put(raw, [key], e.target.value))} /><span className="text-xs text-muted-foreground">Hora argentina{key in raw ? "" : " · predeterminado"}.</span></label>)}
      {([ ["window_hours", "Vigencia del evento (horas)", 1], ["max_per_day", "Máximo total de emails del plan por día", 0] ] as const).map(([key, label, min]) => <label key={key} className="grid gap-1 text-sm">{label}<Input type="number" min={min} max={key === "window_hours" ? MAX_LIFECYCLE_WINDOW_HOURS : 2_147_483_647} step={1} value={String(raw[key] ?? LIFECYCLE_DEFAULTS[key])} onChange={(e) => onChange(put(raw, [key], e.target.value === "" ? "" : Number(e.target.value)))} /><span className="text-xs text-muted-foreground">{key === "window_hours" ? "Debe superar la noche fuera de horario. Máximo 720 horas (30 días); eventos más viejos no se envían." : "Compartido entre estos tipos. 0 detiene los envíos. Las alertas usan su propio tope."}{key in raw ? "" : " Valor predeterminado."}</span></label>)}
    </div>
    <fieldset className="space-y-3"><legend className="mb-2 text-sm font-medium">Tipos de email</legend><div className="grid gap-3 sm:grid-cols-2">{Object.entries(LIFECYCLE_KINDS).map(([key, kind]) => <Toggle key={key} label={kind.label} checked={typeof kinds[key] === "boolean" ? kinds[key] : kind.enabled} inherited={!(key in kinds)} onChange={(checked) => onChange(put(raw, ["kinds", key], checked))} />)}</div></fieldset>
    <p className="text-xs text-muted-foreground">Se toma en el próximo ciclo del worker, después de renovar su caché (aproximadamente un minuto). Apagar conteos después del vencimiento también detiene el rastreo diario de esas búsquedas. Los tipos de prueba adicional y reactivación siguen las reglas existentes; este formulario no modifica su duración ni contenido.</p>
  </div>;
}

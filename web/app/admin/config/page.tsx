import type { Metadata } from "next";

import { ConfigEditor } from "@/components/admin/config-editor";
import { PageHeader } from "@/components/admin/ui";
import { when } from "@/lib/admin-format";
import { createAdminClient } from "@/lib/supabase/admin";

export const metadata: Metadata = { title: "Config" };

// What each app_config key rules (Apéndice A). Unknown keys still show up.
const HINTS: Record<string, string> = {
  plan_limits: "Límites por plan (§33). Con enforced = false solo se mide plan_limit_hit; con true se aplican.",
  validation_criteria: "Umbrales de los 6 criterios del §53 (v_validation_criteria) y el objetivo de activación.",
  pro_cta: "Cuándo aparece «Probar Automotive Pro»: alertas clickeadas o límites alcanzados (§52).",
  pro_offer: "Precios que muestra la pantalla de planes (hipótesis, sin cobro).",
  collector_failure_alert_after: "Fallas seguidas de una fuente antes de avisar por Telegram al admin.",
  alerts_max_per_user_day: "Tope diario de alertas inmediatas; el resto va al digest.",
  score_weights: "Pesos del Opportunity Score (sección 6.3).",
  level_thresholds: "Umbrales de 🔥 / 🟢 / 🟡 (sección 6.4).",
  comparables: "Cascada de comparables (sección 6.2).",
  digest_hour: "Hora del digest diario (ART).",
  price_drop_min_pct: "Baja mínima para alertar «Bajó de precio».",
  llm_limits: "Jobs del LLM por usuario y hora.",
};

// sección 10, "Config": business rules, editable without a deploy.
export default async function ConfigPage() {
  const { data } = await createAdminClient().from("app_config").select("*").order("key");
  const rows = (data ?? []).sort((a, b) => Number(b.key in HINTS) - Number(a.key in HINTS));
  return (
    <>
      <PageHeader title="Config" description="app_config (Apéndice A). El worker toma los cambios en menos de un minuto; la web, en el próximo request." />
      <ul className="grid gap-4 lg:grid-cols-2">
        {rows.map((row) => (
          <li key={row.key} id={row.key} className="space-y-2 rounded-xl bg-card p-4 ring-1 ring-foreground/10">
            <div className="flex items-baseline justify-between gap-2">
              <h2 className="font-mono text-sm font-semibold">{row.key}</h2>
              <span className="text-xs text-muted-foreground">{when(row.updated_at)}</span>
            </div>
            {HINTS[row.key] ? <p className="text-xs text-muted-foreground">{HINTS[row.key]}</p> : null}
            <ConfigEditor configKey={row.key} value={row.value} />
          </li>
        ))}
      </ul>
    </>
  );
}

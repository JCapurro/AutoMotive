import type { Metadata } from "next";

import { ConfigEditor } from "@/components/admin/config-editor";
import { PageHeader } from "@/components/admin/ui";
import { when } from "@/lib/admin-format";
import { createAdminClient } from "@/lib/supabase/admin";

export const metadata: Metadata = { title: "Config" };

// What each app_config key rules (Apéndice A). Unknown keys still show up.
const HINTS: Record<string, string> = {
  plan_limits: "Límites por plan: max_profiles (búsquedas activas), max_visible_results (resultados por búsqueda; sin valor = todos) e immediate_alerts_per_day (avisos inmediatos por día, hora argentina; el resto va al resumen). Funciones: threshold_alerts (umbral de oportunidad por búsqueda) y model_less_search (búsqueda por carrocería, sin modelo; los admins la tienen siempre), true para darlas. La web muestra estos mismos valores. Con enforced = false solo se mide plan_limit_hit; con true se aplican.",
  body_type_targets: "Rastreo de las búsquedas por carrocería, sin modelo (docs/CARROCERIA.md): sources (las fuentes con un target por carrocería; además cada collector declara las carrocerías que sabe buscar) e interval_seconds (cada cuántos segundos corre cada uno).",
  validation_criteria: "Umbrales de los 6 criterios del §53 (v_validation_criteria) y el objetivo de activación.",
  pro_cta: "Cuándo se ofrece ver planes: alertas clickeadas o límites alcanzados (§52).",
  pro_offer: "Oferta en ARS por 30 días y versión. Las nuevas confirmaciones usan estos importes; los pagos anteriores conservan su precio.",
  agency_founders: "Precio fundador: cuántas suscripciones de Agencia (Pro desde la fase 3) son fundadoras (slots) y cuántos meses mantienen el precio de su primer pago (months). Solo lo registra en billing_checkouts; no cambia ningún cobro.",
  commercial_pilot: "Habilitar desde Cobros para iniciar las pruebas existentes y aplicar límites en la misma operación.",
  lifecycle_emails: "Mails del plan (docs/MAILS_DE_PLAN.md). enabled (false los apaga todos), kinds (cada tipo prendido o apagado: trial_no_matches, prueba sin coincidencias a las 24 h; trial_ended, fin de la prueba; pass_expiring y pass_expires_today, vencimiento de Particular; count_after_expiry, conteo a los 7, 14 y 21 días de vencer, que apagado también deja de rastrear una vez por día los modelos de las búsquedas vencidas), send_from / send_until (horario de envío, hora argentina, HH:MM), window_hours (pasado ese plazo ya no se manda; mayor que la noche fuera de horario) y max_per_day (tope de mails por día entre todos los tipos; Resend gratis permite 100 por día entre alertas y estos mails).",
  collector_failure_alert_after: "Fallas seguidas de una fuente antes de avisar por Telegram al admin.",
  alerts_max_per_user_day: "Tope diario de alertas inmediatas mientras plan_limits no se aplica (piloto); con límites, cada plan usa su immediate_alerts_per_day.",
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

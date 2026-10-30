import type { Metadata } from "next";

import { ConfigEditor } from "@/components/admin/config-editor";
import { PageHeader } from "@/components/admin/ui";
import { requireAdmin } from "@/lib/admin";
import { when } from "@/lib/admin-format";
import { createAdminClient } from "@/lib/supabase/admin";

export const metadata: Metadata = { title: "Configuración" };
const NAMES: Record<string, string> = { pro_offer: "Precios y oferta", plan_limits: "Límites por plan", lifecycle_emails: "Emails del plan" };

// What each app_config key rules (Apéndice A). Unknown keys still show up.
const HINTS: Record<string, string> = {
  plan_limits: "Límites por plan: max_profiles (búsquedas activas), max_visible_results (resultados por búsqueda; sin valor = todos) e immediate_alerts_per_day (avisos inmediatos por día, hora argentina; el resto va al resumen). Funciones: threshold_alerts (umbral de oportunidad por búsqueda) y model_less_search (búsqueda por carrocería, sin modelo; los admins la tienen siempre), true para darlas. La web muestra estos mismos valores. Con enforced = false solo se mide plan_limit_hit; con true se aplican.",
  body_type_targets: "Rastreo de las búsquedas por carrocería, sin modelo (docs/CARROCERIA.md): sources (las fuentes con un target por carrocería; además cada collector declara las carrocerías que sabe buscar) e interval_seconds (cada cuántos segundos corre cada uno).",
  validation_criteria: "Umbrales de los 6 criterios del §53 (v_validation_criteria) y el objetivo de activación.",
  pro_cta: "Cuándo se ofrece ver planes: alertas clickeadas o límites alcanzados (§52).",
  pro_offer: "Oferta en ARS por 30 días y versión. Las nuevas confirmaciones usan estos importes; los pagos anteriores conservan su precio.",
  agency_founders: "Precio fundador: cuántas suscripciones de Agencia (Pro desde la fase 3) son fundadoras (slots) y cuántos meses mantienen el precio de su primer pago (months). Solo lo registra en billing_checkouts; no cambia ningún cobro.",
  commercial_pilot: "Habilitar desde Cobros para iniciar las pruebas existentes y aplicar límites en la misma operación.",
  lifecycle_emails: "Mails del plan (docs/MAILS_DE_PLAN.md). enabled (false los apaga todos), kinds (cada tipo prendido o apagado: trial_no_matches, prueba sin coincidencias a las 24 h; trial_ended, fin de la prueba; pass_expiring y pass_expires_today, vencimiento de Particular; count_after_expiry, conteo a los 7, 14 y 21 días de vencer, que apagado también deja de rastrear una vez por día los modelos de las búsquedas vencidas; search_activated, bienvenida a los 45 minutos de la primera búsqueda), send_from / send_until (horario de envío, hora argentina, HH:MM), window_hours (pasado ese plazo ya no se manda; mayor que la noche fuera de horario) y max_per_day (tope de mails por día entre todos los tipos; Resend gratis permite 100 por día entre alertas y estos mails).",
  collector_failure_alert_after: "Fallas seguidas de una fuente antes de avisar por Telegram al admin.",
  alerts_max_per_user_day: "Tope diario de alertas inmediatas mientras plan_limits no se aplica (piloto); con límites, cada plan usa su immediate_alerts_per_day.",
  score_weights: "Pesos del Opportunity Score (sección 6.3).",
  level_thresholds: "Umbrales de 🔥 / 🟢 / 🟡 (sección 6.4).",
  comparables: "Cascada de comparables (sección 6.2).",
  listing_tracking: "Seguimiento de publicaciones (X-01). note_max_chars: largo máximo de la nota por publicación (500).",
  digest_hour: "Hora del digest diario (ART).",
  price_drop_min_pct: "Baja mínima para alertar «Bajó de precio».",
  price_track:
    "Bajas de precio por aviso (PAR-03). min_drop_pct: baja mínima en % para contarla en tarjeta, ficha y emails (distinta de price_drop_min_pct, que decide si se avisa).",
  llm_limits: "Jobs del LLM por usuario y hora.",
  red_flags: "Señales «Conviene verificar» (sección 6). much_cheaper_pct: desde cuánto % debajo de publicaciones comparables sale la señal de precio; much_cheaper_verify_pct (PAR-02, 35): desde ahí el texto pide verificar todo antes de señar; anticipo_pct: desde ahí pide verificar que el precio no sea un anticipo. Tiene que valer much_cheaper_pct < much_cheaper_verify_pct <= anticipo_pct. Solo cambia el texto, no el score ni las alertas; los matches lo toman en el próximo rescore.",
  risk: "Checklist «Antes de señar» de la ficha (PAR-02). checklist_enabled: con false el bloque desaparece sin deploy. links: los links oficiales (dnrpa, vtv, form_08, y listas patentes e infracciones por jurisdicción), cada uno {\"label\": \"...\", \"url\": \"https://...\"} o null; solo https://, sin usuario ni contraseña, hasta 300 caracteres. Sin links el bloque se muestra sin ellos.",
  email_only_signup: "Búsqueda gratis solo con email (docs/AUTENTICACION.md). enabled (con false, el pop-up de la portada avisa que por ahora no se pueden crear búsquedas nuevas), per_ip_hour y per_day (cuentas nuevas), links_per_user_hour y links_per_ip_hour (links para entrar), lookups_per_ip_hour (búsquedas de cuenta) y alert_sessions_per_user_hour (sesiones por cuenta y hora que pueden iniciar los links firmados de los emails; sin la clave, 10; 0 las apaga).",
};

// sección 10, "Config": business rules, editable without a deploy.
export default async function ConfigPage() {
  await requireAdmin();
  const admin = createAdminClient();
  const [{ data, error }, { data: history, error: historyError }] = await Promise.all([
    admin.from("app_config").select("*").order("key"),
    admin.from("admin_config_audit").select("*").order("created_at", { ascending: false }).order("id", { ascending: false }).limit(100),
  ]);
  const rows = (data ?? []).sort((a, b) => Number(b.key in HINTS) - Number(a.key in HINTS));
  return (
    <>
      <PageHeader title="Configuración" description="Revisá los cambios antes de guardarlos. Cada operación registra quién la hizo, su fecha y los valores anteriores. La web los toma en la próxima lectura; el worker, al renovar su caché (aproximadamente un minuto)." />
      {error ? <p role="alert" className="rounded-lg border border-destructive p-4 text-sm text-destructive">No pudimos leer la configuración. Recargá la página para volver a intentar.</p> : null}
      {historyError ? <p role="alert" className="text-sm text-destructive">No pudimos leer el historial. Los guardados solo se completan si también se registra su auditoría.</p> : <p className="text-xs text-muted-foreground">El historial muestra los últimos 100 cambios de configuración y fuentes, con hasta 5 por formulario. Fechas en hora argentina.</p>}
      <ul className="grid gap-4 lg:grid-cols-2">
        {rows.map((row) => (
          <li key={`${row.key}-${row.updated_at}`} id={row.key} className={`min-w-0 space-y-3 rounded-xl bg-card p-4 ring-1 ring-foreground/10 ${row.key in NAMES ? "lg:col-span-2" : ""}`}>
            <div className="flex items-baseline justify-between gap-2">
              <h2 className="text-base font-semibold">{NAMES[row.key] ?? row.key}</h2>
              <span className="text-xs text-muted-foreground">{when(row.updated_at)}</span>
            </div>
            {HINTS[row.key] && !(row.key in NAMES) ? <p className="text-xs text-muted-foreground">{HINTS[row.key]}</p> : null}
            {row.key === "commercial_pilot" ? <p className="text-sm">Administrar desde <a className="underline" href="/admin/billing">Cobros</a>.</p> : <ConfigEditor configKey={row.key} value={row.value} history={(history ?? []).filter((entry) => entry.target_type === "app_config" && entry.target_key === row.key).slice(0, 5)} />}
          </li>
        ))}
      </ul>
      {(history ?? []).some((entry) => entry.target_type === "sources") ? <details className="rounded-xl bg-card p-4 ring-1 ring-foreground/10"><summary className="cursor-pointer font-medium">Historial de fuentes</summary><ol className="mt-4 space-y-4">{(history ?? []).filter((entry) => entry.target_type === "sources").map((entry) => <li key={entry.id} className="space-y-1 text-sm"><p><a href="/admin/sources" className="font-medium underline">{entry.target_key}</a> · {entry.actor_email ?? entry.actor_id} · {when(entry.created_at)}</p><p className="break-words text-xs text-muted-foreground">Antes: {JSON.stringify(entry.before_value)}</p><p className="break-words text-xs">Después: {JSON.stringify(entry.after_value)}</p></li>)}</ol></details> : null}
    </>
  );
}

import type { Metadata } from "next";

import { DashboardNav, DashboardUnavailable } from "@/components/admin/dashboard-ui";
import { EmptyRow, PageHeader, Section as BaseSection, Stat, Table, Td, Th } from "@/components/admin/ui";
import { requireAdmin } from "@/lib/admin";
import { count, percent, when } from "@/lib/admin-format";
import { CHANNEL, INFLUENCE, LEVEL, type Level } from "@/lib/copy";
import { FEEDBACK_REASONS, type FeedbackReason } from "@/lib/email-feedback-reasons";
import { dayMonth, money } from "@/lib/format";
import { createAdminClient } from "@/lib/supabase/admin";

export const metadata: Metadata = { title: "Diagnóstico" };

const WAITLIST: Record<string, string> = { pro_monthly: "Pro", pass_30: "Particular", pass_90: "Pase anterior 90 días" };
const CTA_EVENTS = ["pro_cta_viewed", "pro_cta_clicked", "waitlist_joined", "purchase_requested", "plan_limit_hit"] as const;

function levelLabel(level: string | null): string {
  return level && level in LEVEL ? `${LEVEL[level as Level].emoji} ${LEVEL[level as Level].short}` : "Sin nivel";
}

function median(values: number[]): number | null {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

/** A date column from SQL (YYYY-MM-DD) as 28/09. */
function day(value: string | null): string {
  return value ? dayMonth(`${value}T12:00:00`) : "Total";
}

// sección 11: every metrics view, as the admin reads them (the admins themselves are left out).
export default async function DiagnosticPage() {
  await requireAdmin();
  const admin = createAdminClient();
  const [northStar, activation, firstValue, funnel, engagement, perDay, outcomes, llm, waitlist, feedback, ...cta] = await Promise.all([
    admin.from("v_north_star_weekly").select("*").order("week", { ascending: false }).limit(12),
    admin.from("v_activation").select("*"),
    admin.from("v_first_value").select("*").order("created_at", { ascending: false }).limit(1000),
    admin.from("v_alert_funnel").select("*"),
    admin.from("v_high_score_engagement").select("*"),
    admin.from("v_alerts_per_user_day").select("*").order("day", { ascending: false }).limit(14),
    admin.from("v_outcomes").select("*").order("created_at", { ascending: false }),
    admin.from("llm_job_stats").select("*").order("day", { ascending: false }).limit(14),
    admin.from("pro_waitlist").select("plan"),
    admin.from("email_feedback").select("id, reason, comment, created_at, lifecycle_emails(kind)")
      .order("created_at", { ascending: false }).limit(200),
    ...CTA_EVENTS.map((name) => admin.from("events").select("id", { count: "exact", head: true }).eq("name", name)),
  ]);
  const fv = firstValue.data ?? [];
  const reached = fv.filter((r) => r.hours_to_first_value != null);
  const plans = new Map<string, number>();
  for (const w of waitlist.data ?? []) plans.set(w.plan, (plans.get(w.plan) ?? 0) + 1);

  return (
    <>
      <PageHeader title="Diagnóstico" description="Detalle histórico de la sección 11 (§35–38). Cada bloque conserva sus ventanas y límites originales; no sigue el filtro del nuevo panel." />
      <DashboardNav days={30} active="diagnostic" />

      <Section error={northStar.error?.message} title="North Star (§35)" description="Últimas 12 semanas. Publicaciones relevantes abiertas desde una alerta, por usuario activo y semana. Relevante: no descartada como «no era lo que busco» (caja, versión, zona).">
        <Table>
          <thead>
            <tr>
              <Th>Semana</Th>
              <Th numeric>Usuarios activos</Th>
              <Th numeric>Relevantes abiertas</Th>
              <Th numeric>Por usuario activo</Th>
            </tr>
          </thead>
          <tbody>
            {(northStar.data ?? []).map((w) => (
              <tr key={w.week}>
                <Td>{day(w.week)}</Td>
                <Td numeric>{count(w.active_users)}</Td>
                <Td numeric>{count(w.relevant_opens)}</Td>
                <Td numeric className="font-medium">
                  {String(w.relevant_opens_per_active_user ?? 0).replace(".", ",")}
                </Td>
              </tr>
            ))}
            {!northStar.data?.length ? <EmptyRow colSpan={4} /> : null}
          </tbody>
        </Table>
      </Section>

      <div className="grid gap-6 lg:grid-cols-2">
        <Section error={activation.error?.message} title="Activación (§36)" description="Histórico acumulado, sin ventana de 24 h. Con email en la web → con al menos una búsqueda, por semana de alta. Desde el 15/10/2026 incluye las cuentas creadas solo con el email (búsqueda gratis).">
          <Table>
            <thead>
              <tr>
                <Th>Cohorte</Th>
                <Th numeric>Con email</Th>
                <Th numeric>Con búsqueda</Th>
                <Th numeric>Activación</Th>
              </tr>
            </thead>
            <tbody>
              {(activation.data ?? []).map((a) => (
                <tr key={a.cohort_week ?? "total"} className={a.cohort_week ? undefined : "bg-muted/50 font-medium"}>
                  <Td>{day(a.cohort_week)}</Td>
                  <Td numeric>{count(a.signed_up)}</Td>
                  <Td numeric>{count(a.with_search)}</Td>
                  <Td numeric>
                    {percent(a.activation_pct)}
                    {a.cohort_week ? null : <span className="block text-xs font-normal text-muted-foreground">objetivo {percent(a.target_pct)}</span>}
                  </Td>
                </tr>
              ))}
              {!activation.data?.length ? <EmptyRow colSpan={4} /> : null}
            </tbody>
          </Table>
        </Section>

        <Section error={firstValue.error?.message} title="First value (§36)" description="Últimas 1.000 búsquedas. De crear la búsqueda al primer match 🟢 o 🔥 (incluye el backfill), sin límite de 24 h. Mediana solo entre las que lo lograron.">
          <div className="grid grid-cols-2 gap-3">
            <Stat
              label="Mediana"
              value={reached.length ? `${String(median(reached.map((r) => Number(r.hours_to_first_value)))?.toFixed(1)).replace(".", ",")} h` : "—"}
              note={`${count(reached.length)} búsquedas con primer valor`}
            />
            <Stat label="Sin primer valor todavía" value={count(fv.length - reached.length)} note={`de ${count(fv.length)} búsquedas`} />
          </div>
        </Section>
      </div>

      <Section error={funnel.error?.message} title="Embudo de alertas (§37)" description="Histórico acumulado. Por nivel al enviarse y canal: enviadas → abiertas → clic → guardadas → descartadas.">
        <Table>
          <thead>
            <tr>
              <Th>Nivel</Th>
              <Th>Canal</Th>
              <Th numeric>Enviadas</Th>
              <Th numeric>Abiertas</Th>
              <Th numeric>Clic</Th>
              <Th numeric>Guardadas</Th>
              <Th numeric>Descartadas</Th>
            </tr>
          </thead>
          <tbody>
            {(funnel.data ?? []).map((f) => (
              <tr key={`${f.level}-${f.channel}`}>
                <Td className="whitespace-nowrap">{levelLabel(f.level)}</Td>
                <Td>{CHANNEL[f.channel ?? ""] ?? f.channel}</Td>
                <Td numeric>{count(f.sent)}</Td>
                <Rate n={f.opened} rate={f.open_rate_pct} />
                <Rate n={f.clicked} rate={f.click_rate_pct} />
                <Rate n={f.saved} rate={f.save_rate_pct} />
                <Rate n={f.discarded} rate={f.dismiss_rate_pct} />
              </tr>
            ))}
            {!funnel.data?.length ? <EmptyRow colSpan={7} /> : null}
          </tbody>
        </Table>
      </Section>

      <div className="grid gap-6 lg:grid-cols-2">
        <Section error={engagement.error?.message} title="High Score Engagement (§37)" description="Histórico acumulado. 🔥 contra 🟢/🟡. Si no hay diferencia, el score no está aportando.">
          <Table>
            <thead>
              <tr>
                <Th>Segmento</Th>
                <Th numeric>Alertas</Th>
                <Th numeric>Apertura</Th>
                <Th numeric>Clic</Th>
                <Th numeric>Guardado</Th>
                <Th numeric>Engagement</Th>
              </tr>
            </thead>
            <tbody>
              {(engagement.data ?? []).map((e) => (
                <tr key={e.segment}>
                  <Td>{e.segment === "high" ? "🔥 Oportunidad" : "🟢 / 🟡 Coincidencia"}</Td>
                  <Td numeric>{count(e.alerts)}</Td>
                  <Td numeric>{percent(e.open_rate_pct)}</Td>
                  <Td numeric>{percent(e.click_rate_pct)}</Td>
                  <Td numeric>{percent(e.save_rate_pct)}</Td>
                  <Td numeric className="font-medium">
                    {percent(e.engagement_pct)}
                  </Td>
                </tr>
              ))}
              {!engagement.data?.length ? <EmptyRow colSpan={6} /> : null}
            </tbody>
          </Table>
        </Section>

        <Section error={perDay.error?.message} title="Alertas por usuario y día (§47)" description="Últimos 14 días con filas. Solo inmediatas (lo del digest no cuenta), contra el tope diario.">
          <Table>
            <thead>
              <tr>
                <Th>Día</Th>
                <Th numeric>Usuarios</Th>
                <Th numeric>Alertas</Th>
                <Th numeric>Por usuario</Th>
                <Th numeric>Máximo</Th>
              </tr>
            </thead>
            <tbody>
              {(perDay.data ?? []).map((d) => (
                <tr key={d.day}>
                  <Td>{day(d.day)}</Td>
                  <Td numeric>{count(d.users)}</Td>
                  <Td numeric>{count(d.alerts)}</Td>
                  <Td numeric>{String(d.alerts_per_user ?? 0).replace(".", ",")}</Td>
                  <Td numeric className={d.cap != null && (d.max_per_user ?? 0) >= d.cap ? "font-medium text-amber-800" : undefined}>
                    {count(d.max_per_user)} / {count(d.cap)}
                  </Td>
                </tr>
              ))}
              {!perDay.data?.length ? <EmptyRow colSpan={5} /> : null}
            </tbody>
          </Table>
        </Section>
      </div>

      <Section error={outcomes.error?.message} title="Outcomes (§38)" description="Compras de autos autodeclaradas: «Compré este vehículo», la respuesta a «¿Ese Auto influyó?» y el tiempo usando Ese Auto. No son cobros del producto.">
        <Table>
          <thead>
            <tr>
              <Th>Cuándo</Th>
              <Th>Vehículo</Th>
              <Th numeric>Precio</Th>
              <Th>Influencia</Th>
              <Th numeric>Días usando</Th>
              <Th numeric>Días desde la búsqueda</Th>
              <Th>Desde una alerta</Th>
            </tr>
          </thead>
          <tbody>
            {(outcomes.data ?? []).map((o) => (
              <tr key={o.owned_vehicle_id}>
                <Td className="whitespace-nowrap">{when(o.created_at)}</Td>
                <Td className="max-w-64 truncate">{o.title ?? `#${o.listing_id}`}</Td>
                <Td numeric className="whitespace-nowrap">
                  {o.purchase_price != null ? money(o.purchase_price, o.purchase_currency) : "—"}
                </Td>
                <Td>{o.automotive_influence ? INFLUENCE[o.automotive_influence] : "Sin responder"}</Td>
                <Td numeric>{count(o.days_using_automotive)}</Td>
                <Td numeric>{count(o.days_since_search)}</Td>
                <Td>{o.came_from_alert ? "Sí" : "No"}</Td>
              </tr>
            ))}
            {!outcomes.data?.length ? <EmptyRow colSpan={7}>Todavía nadie marcó una compra.</EmptyRow> : null}
          </tbody>
        </Table>
      </Section>

      <div className="grid gap-6 lg:grid-cols-2">
        <Section error={[waitlist.error?.message, ...cta.map((r) => r.error?.message)].filter(Boolean).join(" · ")} title="Interés en los planes" description="Eventos históricos acumulados: vistas, solicitudes y límites. Los pagos confirmados y las mensualidades vigentes se muestran en Cobros.">
          <div className="grid grid-cols-2 gap-3">
            {CTA_EVENTS.map((name, i) => (
              <Stat key={name} label={name} value={count(cta[i]?.count ?? 0)} note="eventos" />
            ))}
          </div>
          <Table>
            <thead>
              <tr>
                <Th>Plan elegido en la lista de espera</Th>
                <Th numeric>Usuarios</Th>
              </tr>
            </thead>
            <tbody>
              {[...plans].map(([plan, n]) => (
                <tr key={plan}>
                  <Td>{WAITLIST[plan] ?? plan}</Td>
                  <Td numeric>{count(n)}</Td>
                </tr>
              ))}
              {!plans.size ? <EmptyRow colSpan={2}>Nadie se sumó todavía.</EmptyRow> : null}
            </tbody>
          </Table>
        </Section>

        <Section error={llm.error?.message} title="LLM del modo asistido" description="Últimas 14 filas de llm_job_stats: volumen, fallas y latencia por proveedor y día UTC.">
          <Table>
            <thead>
              <tr>
                <Th>Día (UTC)</Th>
                <Th>Proveedor</Th>
                <Th numeric>Jobs</Th>
                <Th numeric>Fallidos</Th>
                <Th numeric>p50</Th>
                <Th numeric>p95</Th>
              </tr>
            </thead>
            <tbody>
              {(llm.data ?? []).map((j) => (
                <tr key={`${j.day}-${j.provider}-${j.kind}`}>
                  <Td>{j.day ? j.day.slice(0, 10) : "—"}</Td>
                  <Td>
                    {j.provider}
                    <span className="block text-xs text-muted-foreground">{j.kind}</span>
                  </Td>
                  <Td numeric>{count(j.jobs)}</Td>
                  <Td numeric>{count(j.failed)}</Td>
                  <Td numeric>{j.latency_p50_ms != null ? `${(j.latency_p50_ms / 1000).toFixed(1)} s` : "—"}</Td>
                  <Td numeric>{j.latency_p95_ms != null ? `${(j.latency_p95_ms / 1000).toFixed(1)} s` : "—"}</Td>
                </tr>
              ))}
              {!llm.data?.length ? <EmptyRow colSpan={6} /> : null}
            </tbody>
          </Table>
        </Section>
      </div>

      <Section error={feedback.error?.message} title="Por qué no armaron su búsqueda" description="Últimas 200 respuestas de remarketing (/f): una por email, la última que eligieron. Las respuestas por email llegan a la casilla de remarketing.reply_to.">
        <Table>
          <thead>
            <tr>
              <Th>Fecha</Th>
              <Th>Email</Th>
              <Th>Motivo</Th>
              <Th>Comentario</Th>
            </tr>
          </thead>
          <tbody>
            {(feedback.data ?? []).map((f) => (
              <tr key={f.id}>
                <Td>{when(f.created_at)}</Td>
                <Td>{REMARKETING_EMAIL[f.lifecycle_emails?.kind ?? ""] ?? f.lifecycle_emails?.kind ?? "—"}</Td>
                <Td>{FEEDBACK_REASONS[f.reason as FeedbackReason] ?? f.reason}</Td>
                <Td className="max-w-md whitespace-pre-wrap">{f.comment ?? "—"}</Td>
              </tr>
            ))}
            {!feedback.data?.length ? <EmptyRow colSpan={4} /> : null}
          </tbody>
        </Table>
      </Section>
    </>
  );
}

const REMARKETING_EMAIL: Record<string, string> = {
  search_abandoned: "Búsqueda sin activar",
  search_not_started: "¿Qué auto buscás?",
  search_feedback: "¿Qué te frenó?",
};

function Section({ error, children, ...props }: {
  title: string;
  description?: string;
  error?: string;
  children: React.ReactNode;
}) {
  return <BaseSection {...props}>{error ? <DashboardUnavailable title="No se pudo leer este bloque" error={error} /> : children}</BaseSection>;
}

function Rate({ n, rate }: { n: number | null; rate: number | null }) {
  return (
    <Td numeric>
      {count(n)}
      <span className="block text-xs text-muted-foreground">{percent(rate)}</span>
    </Td>
  );
}

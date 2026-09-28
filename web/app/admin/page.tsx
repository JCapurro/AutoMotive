import type { Metadata } from "next";

import { CriteriaGrid } from "@/components/admin/criteria";
import { NotificationTable } from "@/components/admin/inspector";
import { SourceHealthTable } from "@/components/admin/sources";
import { PageHeader, Section, Stat, TextLink } from "@/components/admin/ui";
import { count, daysAgo, percent } from "@/lib/admin-format";
import { createAdminClient } from "@/lib/supabase/admin";

export const metadata: Metadata = { title: "Resumen" };

// sección 10, "Resumen": the §53 criteria, the headline metrics and the sources.
export default async function AdminHome() {
  const admin = createAdminClient();
  const since = daysAgo(7, true);
  const [criteria, northStar, activation, perDay, sources, recent] = await Promise.all([
    admin.from("v_validation_criteria").select("*").order("ordinal"),
    admin.from("v_north_star_weekly").select("*").order("week", { ascending: false }).limit(1),
    admin.from("v_activation").select("*").is("cohort_week", null).maybeSingle(),
    admin.from("v_alerts_per_user_day").select("*").gte("day", since),
    admin.from("admin_source_health").select("*").order("id"),
    admin.from("notifications").select("*").neq("kind", "digest").order("id", { ascending: false }).limit(8),
  ]);
  const week = northStar.data?.[0];
  const days = perDay.data ?? [];
  const alerts7 = days.reduce((sum, d) => sum + (d.alerts ?? 0), 0);
  const userDays = days.reduce((sum, d) => sum + (d.users ?? 0), 0);

  return (
    <>
      <PageHeader title="Resumen" description="¿Está validado el MVP? Los criterios del §53 con los datos de hoy." />

      <Section title="Criterios de validación (§53)" description="v_validation_criteria · los umbrales se editan en Config (validation_criteria).">
        <CriteriaGrid rows={criteria.data ?? []} />
      </Section>

      <Section title="Métricas clave">
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat
            label="North Star, última semana"
            value={week ? String(week.relevant_opens_per_active_user ?? 0).replace(".", ",") : "—"}
            note={week ? `${count(week.relevant_opens)} publicaciones relevantes · ${count(week.active_users)} usuarios activos` : "Sin actividad"}
          />
          <Stat
            label="Activación"
            value={percent(activation.data?.activation_pct ?? null)}
            note={`${count(activation.data?.with_search)} de ${count(activation.data?.signed_up)} registrados · objetivo ${percent(activation.data?.target_pct ?? 70)}`}
          />
          <Stat
            label="Alertas por usuario y día (7 días)"
            value={userDays ? (alerts7 / userDays).toFixed(2).replace(".", ",") : "—"}
            note={`${count(alerts7)} alertas inmediatas · tope ${count(days[0]?.cap ?? null)}`}
          />
          <Stat
            label="Fuentes con fallas"
            value={count((sources.data ?? []).filter((s) => (s.consecutive_failures ?? 0) > 0).length)}
            note={`de ${count(sources.data?.length ?? 0)} fuentes`}
          />
        </div>
        <TextLink href="/admin/metrics" className="text-sm">
          Todas las métricas →
        </TextLink>
      </Section>

      <Section title="Fuentes">
        <SourceHealthTable rows={sources.data ?? []} />
      </Section>

      <Section title="Últimas alertas" description="«¿Por qué?» abre el inspector.">
        <NotificationTable rows={recent.data ?? []} />
        <TextLink href="/admin/notifications" className="text-sm">
          Todas las notificaciones →
        </TextLink>
      </Section>
    </>
  );
}

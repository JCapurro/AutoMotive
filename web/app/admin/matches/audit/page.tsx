import type { Metadata } from "next";

import { DrawButton, ReasonList, ShareTable } from "@/components/admin/match-audit-dash";
import { MatchAuditBoard } from "@/components/admin/match-audit-board";
import { Card } from "@/components/admin/dash";
import { PageHeader, Stat, TextLink } from "@/components/admin/ui";
import {
  byLevel, bySource, byWeek, overall, parseQueue, parseStats, progress, SAMPLE_SIZE, shareText, topReasons,
} from "@/lib/admin-match-audit";
import { createAdminClient } from "@/lib/supabase/admin";

export const metadata: Metadata = { title: "Auditoría de matches" };

// Weekly audit: 60 alerted matches are drawn each week and judged by hand (Bien / Regular / Mal).
export default async function MatchAuditPage() {
  const admin = createAdminClient();
  const [queueRes, statsRes, weekRes] = await Promise.all([
    admin.rpc("admin_match_review_queue", {}),
    admin.rpc("admin_match_review_stats", { p_weeks: 12 }),
    admin.rpc("admin_match_review_week", {}),
  ]);
  const items = parseQueue(queueRes.data);
  const stats = parseStats(statsRes.data);
  const week = typeof weekRes.data === "string" ? weekRes.data : null;
  const failed = queueRes.error || statsRes.error;

  const { done, total } = progress(items);
  const weeks = byWeek(stats.rows);
  const current = weeks.find((w) => w.key === week);
  const windowRows = stats.rows;
  const all = overall(windowRows);

  return (
    <>
      <PageHeader
        title="Auditoría de matches"
        description="Cada semana se sortean 60 matches que llegaron en una alerta. Los revisás a mano y acá se ve qué porcentaje era bueno."
      >
        <TextLink href="/admin/matches" className="text-sm">
          ← Matches
        </TextLink>
      </PageHeader>

      {failed ? (
        <p role="alert" className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive">
          No pudimos leer la auditoría. ¿Está aplicada la migración 20261221120000?
        </p>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-3">
        <Stat
          label="Esta semana: bien"
          value={current ? shareText(current.good, current.reviewed) : "—"}
          note={current ? `${current.reviewed} revisados de ${current.sampled} sorteados` : "Todavía no hay revisados"}
        />
        <Stat
          label="Esta semana: bien + regular"
          value={current ? shareText(current.good + current.fair, current.reviewed) : "—"}
          note="Sobre los revisados"
        />
        <Stat
          label="Últimas 12 semanas: bien"
          value={shareText(all.good, all.reviewed)}
          note={all.reviewed ? `${all.reviewed} revisados` : "Sin datos"}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Por semana" description="Entre paréntesis, cuántos revisados hay detrás de cada porcentaje.">
          <ShareTable title="Semana" kind="week" rows={weeks} />
        </Card>
        <Card title="Por nivel" description="Últimas 12 semanas.">
          <ShareTable title="Nivel" kind="level" rows={byLevel(windowRows)} />
        </Card>
        <Card title="Por fuente" description="Últimas 12 semanas. Con pocos revisados, el porcentaje engaña.">
          <ShareTable title="Fuente" kind="source" rows={bySource(windowRows)} />
        </Card>
        <Card title="Razones más repetidas" description="Lo que falló en los Regular y Mal de las últimas 12 semanas.">
          <ReasonList rows={topReasons(stats.reasons)} />
        </Card>
      </div>

      <section className="space-y-3" aria-label="Revisión de la semana">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="space-y-0.5">
            <h2 className="text-base font-semibold tracking-tight">Revisión de la semana{week ? ` del ${week.split("-").reverse().slice(0, 2).join("/")}` : ""}</h2>
            <p className="text-xs text-muted-foreground" data-testid="audit-summary">
              {total ? `${done} de ${total} revisados.` : "Todavía no se sorteó la muestra de esta semana."}
            </p>
          </div>
          <DrawButton have={total} target={SAMPLE_SIZE} />
        </div>
        {items.length ? <MatchAuditBoard initial={items} /> : null}
      </section>
    </>
  );
}

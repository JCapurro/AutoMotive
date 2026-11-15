import type { Metadata } from "next";

import { ExperimentForm, VerdictForm } from "@/components/admin/experiment-forms";
import { Card } from "@/components/admin/dash";
import { PageHeader, Pill, Section, TextLink } from "@/components/admin/ui";
import { requireAdmin } from "@/lib/admin";
import {
  buildExperimentsBoard, type AuditRow, type ConfigRow, type ExperimentCard, type ExperimentRow, isDecided, STATUS_LABEL,
} from "@/lib/admin-experiments-data";
import { when } from "@/lib/admin-format";
import { createAdminClient } from "@/lib/supabase/admin";

export const metadata: Metadata = { title: "Experimentos" };

const STATUS_TONE = { running: "ok", won: "ok", lost: "bad", inconclusive: "muted", paused: "warn" } as const;
const day = (d: string) => d.split("-").reverse().join("/");

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-0.5">
      <dt className="text-xs font-medium text-muted-foreground">{label}</dt>
      <dd className="text-sm break-words">{children}</dd>
    </div>
  );
}

function ExperimentCardView({ c }: { c: ExperimentCard }) {
  const decided = isDecided(c.status);
  const switchTone = c.switch.kind === "on" ? "ok" : c.switch.kind === "off" ? "muted" : "warn";
  return (
    <Card
      title={c.title}
      description={<span className="font-mono">{c.slug}</span>}
      className="lg:col-span-2"
    >
      <div id={c.slug} className="flex flex-wrap items-center gap-2">
        <Pill tone={STATUS_TONE[c.status]}>{STATUS_LABEL[c.status]}</Pill>
        {!decided ? <Pill tone={c.review.kind === "due" ? "warn" : "muted"}>{c.review.label}</Pill> : null}
      </div>
      <dl className="grid gap-3 sm:grid-cols-2">
        <Row label="Qué esperamos que pase">{c.hypothesis || "—"}</Row>
        <Row label="Qué se mide y cómo">{c.metric || "—"}</Row>
        <Row label="Cómo estábamos antes">{c.baseline_text ?? "Sin dato de base"}</Row>
        <Row label="Interruptor ahora">
          {c.config_key ? (
            <span className="flex flex-wrap items-center gap-2">
              <Pill tone={switchTone}>{c.switch.label}</Pill>
              {"detail" in c.switch && c.switch.detail ? <span className="text-xs text-muted-foreground">{c.switch.detail}</span> : null}
              <TextLink href={`/admin/config#${c.config_key}`} className="text-xs">{c.config_key}</TextLink>
            </span>
          ) : (
            c.switch.label
          )}
        </Row>
        <Row label="Empezó">{when(c.started_at)}</Row>
        <Row label="Volver a medir el">{c.review_at ? day(c.review_at) : "Sin fecha"}</Row>
        {decided ? (
          <>
            <Row label="Resultado">{c.result_text ?? (c.result_value === null ? "Sin resultado cargado" : String(c.result_value))}</Row>
            <Row label="Decidido">{when(c.decided_at)}</Row>
          </>
        ) : null}
        {c.verdict_note ? <Row label={decided ? "Nota del veredicto" : "Nota"}>{c.verdict_note}</Row> : null}
      </dl>

      {c.config_key ? (
        <details className="rounded-lg bg-muted/40 p-3">
          <summary className="cursor-pointer text-sm font-medium">Historial del interruptor ({c.history.length})</summary>
          {c.history.length ? (
            <ol className="mt-3 space-y-2">
              {c.history.map((h) => (
                <li key={h.id} className="text-sm">
                  <span className="font-medium">{h.text}</span>
                  <span className="block text-xs text-muted-foreground">{h.who} · {when(h.at)}</span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="mt-3 text-sm text-muted-foreground">Nadie lo cambió desde el panel.</p>
          )}
        </details>
      ) : null}

      <details className="rounded-lg bg-muted/40 p-3">
        <summary className="cursor-pointer text-sm font-medium">{decided ? "Cambiar el veredicto o reabrir" : "Cargar resultado y veredicto"}</summary>
        <div className="mt-3">
          <VerdictForm slug={c.slug} status={c.status} resultText={c.result_text} resultValue={c.result_value} note={c.verdict_note} />
        </div>
      </details>
      <details className="rounded-lg bg-muted/40 p-3">
        <summary className="cursor-pointer text-sm font-medium">Editar datos del experimento</summary>
        <div className="mt-3">
          <ExperimentForm
            initial={{
              slug: c.slug, title: c.title, config_key: c.config_key, hypothesis: c.hypothesis, metric: c.metric,
              baseline_text: c.baseline_text, baseline_value: c.baseline_value, started_at: c.started_at, review_at: c.review_at,
            }}
          />
        </div>
      </details>
    </Card>
  );
}

export default async function ExperimentsPage() {
  await requireAdmin();
  const admin = createAdminClient();
  const [{ data: rows, error }, { data: config }, { data: audit }] = await Promise.all([
    admin.from("admin_experiments").select("*"),
    admin.from("app_config").select("key, value"),
    admin.from("admin_config_audit").select("*").eq("target_type", "app_config").order("created_at", { ascending: false }).order("id", { ascending: false }).limit(300),
  ]);
  const board = buildExperimentsBoard((rows ?? []) as ExperimentRow[], (config ?? []) as ConfigRow[], (audit ?? []) as AuditRow[], new Date());

  return (
    <>
      <PageHeader
        title="Experimentos"
        description="Lo que probamos, desde cuándo, contra qué base y cuándo toca volver a medir. Los resultados se cargan a mano. Fechas en hora argentina."
      />
      {error ? <p role="alert" className="rounded-lg border border-destructive p-4 text-sm text-destructive">No pudimos leer los experimentos. Recargá la página para volver a intentar.</p> : null}
      {board.due ? (
        <p role="status" className="rounded-lg bg-amber-50 p-3 text-sm text-amber-950 ring-1 ring-amber-200">
          {board.due === 1 ? "Hay 1 experimento listo para medir." : `Hay ${board.due} experimentos listos para medir.`}
        </p>
      ) : null}

      <Section title="En marcha y pausados">
        <ul className="grid gap-4 lg:grid-cols-2">
          {board.open.map((c) => <li key={c.slug} className="contents"><ExperimentCardView c={c} /></li>)}
        </ul>
        {!board.open.length && !error ? <p className="text-sm text-muted-foreground">No hay experimentos abiertos.</p> : null}
      </Section>

      <details className="rounded-xl bg-card p-4 ring-1 ring-foreground/10">
        <summary className="cursor-pointer text-sm font-medium">Experimentos decididos ({board.decided.length})</summary>
        <ul className="mt-4 grid gap-4 lg:grid-cols-2">
          {board.decided.map((c) => <li key={c.slug} className="contents"><ExperimentCardView c={c} /></li>)}
        </ul>
        {!board.decided.length ? <p className="mt-3 text-sm text-muted-foreground">Todavía no se decidió ninguno.</p> : null}
      </details>

      <details className="rounded-xl bg-card p-4 ring-1 ring-foreground/10">
        <summary className="cursor-pointer text-sm font-medium">Agregar un experimento</summary>
        <div className="mt-4"><ExperimentForm /></div>
      </details>
    </>
  );
}

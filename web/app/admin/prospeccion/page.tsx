import type { Metadata } from "next";

import { MessageCard, RepliedRow, RepliesList, WaitingRow } from "@/components/admin/prospect-cards";
import { PageHeader, Pill, Section } from "@/components/admin/ui";
import { requireAdmin } from "@/lib/admin";
import {
  buildBoard, DAILY_CAP, type EventRow, type MessageRow, type ProspectRow, type RateRow, replyRates,
} from "@/lib/admin-prospecting";
import { createAdminClient } from "@/lib/supabase/admin";

export const metadata: Metadata = { title: "Prospección" };

const DAY_MS = 86_400_000;

function Rates({ title, rows }: { title: string; rows: RateRow[] }) {
  return (
    <div className="rounded-xl bg-card p-3 ring-1 ring-foreground/10">
      <p className="mb-2 text-sm font-medium">{title}</p>
      {rows.length ? (
        <ul className="space-y-1 text-sm">
          {rows.map((r) => (
            <li key={r.key} className="flex justify-between gap-3">
              <span className="min-w-0 truncate">{r.label}</span>
              <span className="tabular-nums text-muted-foreground">
                {r.replied}/{r.sent} · {r.sent ? Math.round((100 * r.replied) / r.sent) : 0} %
              </span>
            </li>
          ))}
        </ul>
      ) : <p className="text-xs text-muted-foreground">Sin envíos en la semana.</p>}
    </div>
  );
}

export default async function ProspectingPage() {
  await requireAdmin();
  const admin = createAdminClient();
  const now = new Date();
  const since = new Date(now.getTime() - 35 * DAY_MS).toISOString();
  const [prospects, messages, events, noContact] = await Promise.all([
    admin.from("prospects").select("*").not("status", "in", "(new,no_contact)").order("id").limit(5000),
    admin.from("prospect_messages").select("*").or(`status.eq.ready,sent_at.gte.${since}`).order("id").limit(5000),
    admin.from("prospect_events").select("prospect_id, message_id, kind, created_at").gte("created_at", new Date(now.getTime() - 2 * DAY_MS).toISOString()).limit(2000),
    admin.from("prospects").select("id", { count: "exact", head: true }).eq("status", "no_contact"),
  ]);
  const error = prospects.error ?? messages.error ?? events.error;
  const P = (prospects.data ?? []) as unknown as ProspectRow[];
  const M = (messages.data ?? []) as unknown as MessageRow[];
  const board = buildBoard(P, M, (events.data ?? []) as EventRow[], now);
  const week = replyRates(P, M, new Date(now.getTime() - 7 * DAY_MS), now);
  const lastFacts = new Map<number, Record<string, unknown>>();
  for (const m of M) if (m.status === "sent") lastFacts.set(m.prospect_id, m.facts);
  const over = board.sentToday >= DAILY_CAP;

  return (
    <>
      <PageHeader
        title="Prospección"
        description="Los mensajes que dejó el bot hoy. Abrí cada uno en WhatsApp, mandalo desde tu número y marcá «Enviado». Las respuestas te llegan a tu WhatsApp: marcá acá quién respondió."
      >
        <div className="flex flex-wrap gap-2">
          <Pill tone={over ? "bad" : board.sentToday >= DAILY_CAP * 0.8 ? "warn" : "muted"}>Enviados hoy: {board.sentToday} de {DAILY_CAP}</Pill>
          <Pill>Sin contacto: {noContact.count ?? 0}</Pill>
        </div>
      </PageHeader>
      {error ? (
        <p role="alert" className="rounded-lg border border-destructive p-4 text-sm text-destructive">
          No pudimos leer la prospección. Si la migración 20261225120000 todavía no está aplicada, es eso; si no, recargá la página.
        </p>
      ) : null}
      {over ? (
        <p role="status" className="rounded-lg bg-red-50 p-3 text-sm text-red-950 ring-1 ring-red-200">
          Ya mandaste {board.sentToday} hoy. WhatsApp marca como spam a los números que escriben a muchos desconocidos: lo que queda, mejor mañana.
        </p>
      ) : null}

      <Section title={`Seguimientos que vencen hoy (${board.dueToday.length})`} description="Cada uno trae un gancho nuevo, no un «¿viste mi mensaje?».">
        {board.dueToday.length ? (
          <ul className="grid gap-4 lg:grid-cols-2">
            {board.dueToday.map((r) => <li key={r.message.id}><MessageCard message={r.message} prospect={r.prospect} /></li>)}
          </ul>
        ) : <p className="text-sm text-muted-foreground">Ninguno vence hoy.</p>}
      </Section>

      <Section title={`Tanda de hoy (${board.newToday.length})`} description="Primeros mensajes, ya revisados contra los datos. El texto se puede editar antes de abrir WhatsApp.">
        {board.newToday.length ? (
          <ul className="grid gap-4 lg:grid-cols-2">
            {board.newToday.map((r) => <li key={r.message.id}><MessageCard message={r.message} prospect={r.prospect} /></li>)}
          </ul>
        ) : <p className="text-sm text-muted-foreground">No hay mensajes nuevos listos. El bot corre todos los días a las 7:30.</p>}
      </Section>

      <Section title={`Respondieron (${board.replied.length})`} description="Las respuestas armadas abren su WhatsApp con el texto listo.">
        {board.replied.length ? (
          <ul className="grid gap-3 lg:grid-cols-2">
            {board.replied.map((p) => <RepliedRow key={p.id} p={p} hookFacts={lastFacts.get(p.id) ?? null} />)}
          </ul>
        ) : <p className="text-sm text-muted-foreground">Todavía nadie.</p>}
      </Section>

      <Section title="Resumen de la semana" description={`Primeros mensajes enviados en los últimos 7 días: ${week.sent}, respondieron ${week.replied}${week.sent ? ` (${Math.round((100 * week.replied) / week.sent)} %)` : ""}.`}>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Rates title="Por tipo de gancho" rows={week.hook} />
          <Rates title="Por fuente" rows={week.source} />
          <Rates title="Agencia o persona" rows={week.kind} />
          <Rates title="Por región" rows={week.region} />
        </div>
      </Section>

      <details className="rounded-xl bg-card p-4 ring-1 ring-foreground/10">
        <summary className="cursor-pointer text-sm font-medium">Esperando respuesta ({board.waiting.length})</summary>
        <ul className="mt-3 grid gap-3 lg:grid-cols-2">
          {board.waiting.map((p) => <WaitingRow key={p.id} p={p} />)}
        </ul>
        {!board.waiting.length ? <p className="mt-2 text-sm text-muted-foreground">Nadie.</p> : null}
      </details>

      <details className="rounded-xl bg-card p-4 ring-1 ring-foreground/10">
        <summary className="cursor-pointer text-sm font-medium">Respuestas armadas</summary>
        <div className="mt-3"><RepliesList /></div>
      </details>
    </>
  );
}

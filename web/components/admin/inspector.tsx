import { AlertTriangle, ExternalLink, Info } from "lucide-react";

import { LevelBadge } from "@/components/app/badges";
import { EmptyRow, Json, Pill, Section, Table, Td, TextLink, Th } from "@/components/admin/ui";
import { count, filterSummary, percent, when } from "@/lib/admin-format";
import type { Inspection, NotificationRow } from "@/lib/admin-inspect";
import { CHANNEL, COMPARABLE_LEVEL, COMPONENT, COMPONENTS, LEVEL, type Level, NOTIFICATION_TITLE, REASON_NAME } from "@/lib/copy";
import { money, number, vehicle } from "@/lib/format";
import type { Component, PriceRef, Reason, RedFlag } from "@/lib/types";
import { orderReasons, whyText } from "@/lib/why";

const LEVEL_RANK: Record<string, number> = { low: 0, match: 1, good: 2, high: 3 };
const CASCADE = ["trim_transmission", "transmission", "model"];

const STATUS_TONE: Record<string, "ok" | "warn" | "bad" | "muted"> = {
  sent: "ok",
  digest: "muted",
  queued: "warn",
  failed: "bad",
  skipped: "muted",
};

/**
 * "¿Por qué se envió?" (sección 10, §45): the listing ↔ search, match_reasons
 * field by field, score_breakdown, price_ref with the cascade level used and
 * the red flags — plus, for an alert, the engine's decision.
 */
export function Inspector({ data }: { data: Inspection }) {
  const { notification: n, match, listing, profile } = data;
  const reasons = (match?.match_reasons ?? {}) as Record<string, Reason>;
  const breakdown = (match?.score_breakdown ?? {}) as Record<string, Component | string>;
  const ref = (match?.price_ref ?? null) as PriceRef | null;
  const flags = (match?.red_flags ?? []) as RedFlag[];

  return (
    <div className="space-y-6">
      {n ? <Decision n={n} siblings={data.siblings} profile={profile} currentScore={match?.score ?? null} /> : null}

      {match && listing && profile ? (
        <Section title="Listing ↔ búsqueda" description="El formato del §45: cada campo de la búsqueda contra la publicación.">
          <pre data-testid="why-block" className="overflow-x-auto rounded-xl bg-card p-4 font-mono text-sm leading-relaxed ring-1 ring-foreground/10">
            {whyText(listing.id, profile.id, reasons, match.score)}
          </pre>
        </Section>
      ) : (
        <p className="rounded-xl bg-muted p-4 text-sm text-muted-foreground">
          Esta alerta no tiene un match asociado (por ejemplo, un aviso de «desapareció» de una publicación guardada).
        </p>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        {listing ? (
          <Section title={`Publicación #${listing.id}`}>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 rounded-xl bg-card p-4 text-sm ring-1 ring-foreground/10">
              <Row label="Vehículo">{vehicle(listing)}</Row>
              <Row label="Fuente">
                {data.sourceName ?? listing.source} · {listing.external_id}{" "}
                <a href={listing.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 underline-offset-2 hover:underline">
                  ver <ExternalLink className="size-3" aria-hidden />
                </a>
              </Row>
              <Row label="Precio">
                {money(listing.price, listing.currency)}
                {listing.currency === "ARS" && listing.price_usd ? ` (≈ ${money(listing.price_usd, "USD")})` : ""}
                {listing.price_partial ? ` · parcial: ${listing.price_partial_reason ?? "sí"}` : ""}
                {listing.price_source === "description"
                  ? ` · de la descripción (publicado ${money(listing.price_published, listing.price_published_currency)})`
                  : ""}
              </Row>
              <Row label="Km · caja">
                {listing.mileage_km != null ? `${number(listing.mileage_km)} km` : "km ?"} · {listing.transmission ?? "caja ?"}
              </Row>
              <Row label="Ubicación">{listing.location_text ?? "—"}</Row>
              <Row label="Publicado">{when(listing.published_at)}</Row>
              <Row label="Detectado">{when(listing.first_seen_at)}</Row>
              <Row label="Estado">
                {listing.status}
                {listing.probable_repost_of ? ` · re-publicación de #${listing.probable_repost_of}` : ""}
              </Row>
              <Row label="Normalización">{listing.normalization_confidence ?? "—"}</Row>
            </dl>
            <TextLink href={`/admin/listings/${listing.id}`} className="text-sm">
              Snapshots y otros matches →
            </TextLink>
          </Section>
        ) : null}

        {profile ? (
          <Section title={`Búsqueda #${profile.id} · ${profile.name}`}>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 rounded-xl bg-card p-4 text-sm ring-1 ring-foreground/10">
              <Row label="Usuario">{data.email ?? profile.user_id}</Row>
              <Row label="Filtros">{filterSummary(profile.filters)}</Row>
              <Row label="Alerta mínima">
                {LEVEL[profile.notify_min_level].emoji} {LEVEL[profile.notify_min_level].label}
              </Row>
              <Row label="Frecuencia">{profile.notification_frequency === "immediate" ? "Inmediata" : "Diaria (digest)"}</Row>
              <Row label="Canales">{profile.channels.map((c) => CHANNEL[c] ?? c).join(", ")}</Row>
              <Row label="Estado">{profile.enabled ? "Activa" : "Pausada"}</Row>
            </dl>
            <details className="text-sm">
              <summary className="cursor-pointer text-muted-foreground">filters y preferences (JSON)</summary>
              <Json value={{ filters: profile.filters, preferences: profile.preferences }} className="mt-2" />
            </details>
          </Section>
        ) : null}
      </div>

      {match ? (
        <>
          <Section title="Razones, campo por campo" description="match_reasons: hard filters y preferencias blandas.">
            <Table>
              <thead>
                <tr>
                  <Th>Campo</Th>
                  <Th>Tipo</Th>
                  <Th>Resultado</Th>
                  <Th>Detalle</Th>
                </tr>
              </thead>
              <tbody>
                {orderReasons(reasons).map(([key, r]) => (
                  <tr key={key} data-result={r.result}>
                    <Td>
                      <span className="font-mono text-xs">{key}</span>
                      <span className="block text-xs text-muted-foreground">{REASON_NAME[key] ?? ""}</span>
                    </Td>
                    <Td>{r.kind === "soft" ? "preferencia" : "filtro"}</Td>
                    <Td>
                      {r.result === "ok" ? (
                        <Pill tone="ok">✓ cumple</Pill>
                      ) : r.result === "fail" ? (
                        <Pill tone="bad">✗ no cumple</Pill>
                      ) : (
                        <Pill>? no informado</Pill>
                      )}
                    </Td>
                    <Td className="text-muted-foreground">{r.detail || "—"}</Td>
                  </tr>
                ))}
                {!Object.keys(reasons).length ? <EmptyRow colSpan={4} /> : null}
              </tbody>
            </Table>
          </Section>

          <div className="grid gap-6 lg:grid-cols-2">
            <Section
              title={`Opportunity Score ${match.score}`}
              description={`score_breakdown · scoring ${match.scoring_version} · calculado ${when(match.updated_at)}`}
            >
              <div className="flex flex-wrap items-center gap-2">
                <LevelBadge level={match.level} score={match.score} long />
                {match.is_backfill ? <Pill>backfill</Pill> : null}
                {breakdown.guard ? <Pill tone="warn">guarda: {String(breakdown.guard)}</Pill> : null}
              </div>
              <Table>
                <thead>
                  <tr>
                    <Th>Componente</Th>
                    <Th numeric>c</Th>
                    <Th numeric>peso</Th>
                    <Th numeric>aporte</Th>
                    <Th>Explicación</Th>
                  </tr>
                </thead>
                <tbody>
                  {COMPONENTS.filter((c) => typeof breakdown[c] === "object").map((c) => {
                    const comp = breakdown[c] as Component;
                    return (
                      <tr key={c}>
                        <Td>{COMPONENT[c]}</Td>
                        <Td numeric>{comp.c.toFixed(2)}</Td>
                        <Td numeric>{comp.w}</Td>
                        <Td numeric>{comp.contribution.toFixed(1)}</Td>
                        <Td className="text-muted-foreground">{comp.explanation}</Td>
                      </tr>
                    );
                  })}
                  {!COMPONENTS.some((c) => typeof breakdown[c] === "object") ? <EmptyRow colSpan={5} /> : null}
                </tbody>
              </Table>
            </Section>

            <Section title="Comparables" description="price_ref: la cascada de la sección 6.2 y el nivel que se usó.">
              {ref ? (
                <>
                  <ol className="flex flex-wrap gap-2 text-xs">
                    {CASCADE.map((lvl, i) => (
                      <li key={lvl}>
                        <Pill tone={lvl === ref.level_used ? "ok" : "muted"}>
                          {i + 1}. {COMPARABLE_LEVEL[lvl]}
                          {lvl === ref.level_used ? " · usado" : ""}
                        </Pill>
                      </li>
                    ))}
                  </ol>
                  <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 rounded-xl bg-card p-4 text-sm ring-1 ring-foreground/10">
                    <Row label="n">{count(ref.n)}</Row>
                    <Row label="Mediana">{money(ref.median, "USD")}</Row>
                    <Row label="p25 – p75">
                      {money(ref.p25, "USD")} – {money(ref.p75, "USD")}
                    </Row>
                    <Row label="Km mediana">{ref.median_km != null ? `${number(ref.median_km)} km` : "—"}</Row>
                    <Row label="Diferencia">
                      {ref.diff_pct != null ? `${percent(ref.diff_pct)} ${ref.diff_pct >= 0 ? "debajo" : "arriba"} de la mediana` : "—"}
                    </Row>
                  </dl>
                </>
              ) : (
                <p className="rounded-xl bg-muted p-4 text-sm text-muted-foreground">Sin comparables.</p>
              )}
            </Section>
          </div>

          <Section title="Red flags">
            {flags.length ? (
              <ul className="space-y-2 rounded-xl bg-card p-4 ring-1 ring-foreground/10">
                {flags.map((f) => (
                  <li key={f.id} className="flex gap-2 text-sm">
                    {f.severity === "warning" ? (
                      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-600" aria-label="warning" />
                    ) : (
                      <Info className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-label="info" />
                    )}
                    <span>
                      <span className="font-mono text-xs">{f.id}</span> · {f.text}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="rounded-xl bg-muted p-4 text-sm text-muted-foreground">Ninguna.</p>
            )}
          </Section>
        </>
      ) : null}

      {data.related.length ? (
        <Section title="Alertas de esta publicación a este usuario">
          <NotificationTable rows={data.related} />
        </Section>
      ) : null}

      {n ? (
        <details className="text-sm">
          <summary className="cursor-pointer text-muted-foreground">payload de la notificación (JSON)</summary>
          <Json value={n.payload} className="mt-2" />
        </details>
      ) : null}
    </div>
  );
}

/** The engine's decision (sección 7.1) for this alert. */
function Decision({
  n,
  siblings,
  profile,
  currentScore,
}: {
  n: NotificationRow;
  siblings: NotificationRow[];
  profile: Inspection["profile"];
  currentScore: number | null;
}) {
  const payload = (n.payload ?? {}) as { match?: { level?: Level; score?: number }; degraded?: string; repost?: boolean };
  const level = payload.match?.level ?? null;
  const min = profile?.notify_min_level ?? null;
  const reasons: string[] = [];
  if (n.kind === "opportunity" || n.kind === "new_match") {
    if (level && min) {
      reasons.push(
        `Nivel al enviarse ${LEVEL[level].emoji} ${LEVEL[level].label} ${
          LEVEL_RANK[level] >= LEVEL_RANK[min] ? "≥" : "<"
        } alerta mínima de la búsqueda (${LEVEL[min].emoji} ${LEVEL[min].label}).`,
      );
    }
    if (n.kind === "opportunity") reasons.push("Nivel 🔥: sale como «Nueva oportunidad».");
    if (payload.repost) reasons.push("Marcada como re-publicada (probable_repost_of).");
  } else if (n.kind === "price_drop") {
    reasons.push("Bajó de precio una publicación guardada o con match (baja ≥ price_drop_min_pct).");
  } else if (n.kind === "listing_gone") {
    reasons.push("Desapareció una publicación guardada o en seguimiento: va al digest.");
  }
  if (n.status === "digest") {
    reasons.push(
      payload.degraded === "daily_cap"
        ? "Pasó el tope diario (alerts_max_per_user_day): se degradó al digest."
        : "La búsqueda tiene frecuencia diaria: va al digest.",
    );
  }
  if (payload.match?.score != null && currentScore != null && payload.match.score !== currentScore) {
    reasons.push(`Se re-calculó después: score ${payload.match.score} al enviarse, ${currentScore} ahora.`);
  }

  return (
    <Section title="Decisión del motor" description="Por qué salió esta alerta, por este canal (sección 7.1).">
      <div className="space-y-3 rounded-xl bg-card p-4 ring-1 ring-foreground/10">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="font-medium">{NOTIFICATION_TITLE[n.kind] ?? n.kind}</span>
          <Pill>{CHANNEL[n.channel] ?? n.channel}</Pill>
          <Pill tone={STATUS_TONE[n.status] ?? "muted"}>{n.status}</Pill>
          {level ? <LevelBadge level={level} score={payload.match?.score ?? null} /> : null}
        </div>
        <ul className="list-disc space-y-1 pl-5 text-sm">
          {reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <Row label="dedupe_key">
            <span className="font-mono">{n.dedupe_key}</span>
          </Row>
          <Row label="Creada">{when(n.created_at)}</Row>
          <Row label="Enviada">{when(n.sent_at)}</Row>
          <Row label="Abierta · clic">
            {when(n.opened_at)} · {when(n.clicked_at)}
          </Row>
          {n.error ? <Row label="Error">{n.error}</Row> : null}
          {n.digested_in ? (
            <Row label="Digest">
              <TextLink href={`/admin/notifications/${n.digested_in}`}>#{n.digested_in}</TextLink>
            </Row>
          ) : null}
          {siblings.length ? (
            <Row label="Otros canales">
              {siblings.map((s, i) => (
                <span key={s.id}>
                  {i ? ", " : ""}
                  <TextLink href={`/admin/notifications/${s.id}`}>
                    {CHANNEL[s.channel] ?? s.channel} ({s.status})
                  </TextLink>
                </span>
              ))}
            </Row>
          ) : null}
        </dl>
      </div>
    </Section>
  );
}

export function NotificationTable({ rows, showUser }: { rows: (NotificationRow & { email?: string | null })[]; showUser?: boolean }) {
  return (
    <Table>
      <thead>
        <tr>
          <Th>#</Th>
          <Th>Tipo</Th>
          <Th>Canal</Th>
          <Th>Estado</Th>
          {showUser ? <Th>Usuario</Th> : null}
          <Th>Nivel</Th>
          <Th>Creada</Th>
          <Th>Clic</Th>
          <Th>
            <span className="sr-only">Inspeccionar</span>
          </Th>
        </tr>
      </thead>
      <tbody>
        {rows.map((n) => {
          const p = (n.payload ?? {}) as { match?: { level?: Level; score?: number }; degraded?: string };
          return (
            <tr key={n.id}>
              <Td className="tabular-nums">{n.id}</Td>
              <Td>{NOTIFICATION_TITLE[n.kind] ?? n.kind}</Td>
              <Td>{CHANNEL[n.channel] ?? n.channel}</Td>
              <Td>
                <Pill tone={STATUS_TONE[n.status] ?? "muted"}>{n.status}</Pill>
                {p.degraded ? <span className="ml-1 text-xs text-muted-foreground">tope</span> : null}
              </Td>
              {showUser ? <Td className="max-w-40 truncate">{n.email ?? n.user_id}</Td> : null}
              <Td>{p.match?.level ? <LevelBadge level={p.match.level} score={p.match.score ?? null} /> : "—"}</Td>
              <Td className="whitespace-nowrap">{when(n.created_at)}</Td>
              <Td className="whitespace-nowrap">{n.clicked_at ? when(n.clicked_at) : "—"}</Td>
              <Td>
                <TextLink href={`/admin/notifications/${n.id}`} className="whitespace-nowrap">
                  ¿Por qué?
                </TextLink>
              </Td>
            </tr>
          );
        })}
        {!rows.length ? <EmptyRow colSpan={showUser ? 9 : 8} /> : null}
      </tbody>
    </Table>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </>
  );
}

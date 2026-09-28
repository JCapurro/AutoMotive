import { AlertTriangle, ArrowLeft, Car, CircleCheck, CircleHelp, CircleMinus, Info } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { LevelBadge } from "@/components/app/badges";
import { ListingActions } from "@/components/app/listing-actions";
import { type PricePoint, PriceHistory } from "@/components/app/price-history";
import { SellerQuestions } from "@/components/app/seller-questions";
import { ViewTracker } from "@/components/app/view-tracker";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { requireUser } from "@/lib/auth";
import { webConfig } from "@/lib/config";
import {
  BASE_SELLER_QUESTIONS,
  COMPARABLE_LEVEL,
  COMPONENT,
  COMPONENTS,
  FUEL,
  type Influence,
  type InteractionStatus,
  LEVEL,
  REASON_NAME,
  REASON_OK,
  type RejectionReason,
  SELLER,
  TRANSMISSION,
} from "@/lib/copy";
import { ageLine, imageUrls, km, money, number, pct, vehicle } from "@/lib/format";
import { createClient } from "@/lib/supabase/server";
import type { Component, PriceRef, Reason, RedFlag } from "@/lib/types";
import { cn } from "@/lib/utils";
import { orderReasons } from "@/lib/why";

export const metadata: Metadata = { title: "Publicación" };

export default async function ListingPage({ params, searchParams }: PageProps<"/app/listings/[id]">) {
  await requireUser();
  const { id } = await params;
  if (!/^\d+$/.test(id)) notFound();
  const listingId = Number(id);
  const query = await searchParams;
  const n = typeof query.n === "string" && /^\d+$/.test(query.n) ? Number(query.n) : null;

  const supabase = await createClient();
  const [
    { data: listing },
    { data: matches },
    { data: interaction },
    { data: snapshots },
    { data: owned },
    { data: notification },
    cfg,
  ] = await Promise.all([
    supabase.from("listings").select("*, sources(name)").eq("id", listingId).maybeSingle(),
    supabase
      .from("matches")
      .select(
        "id, search_profile_id, score, level, score_breakdown, match_reasons, price_ref, red_flags, seller_questions, search_profiles(id, name)",
      )
      .eq("listing_id", listingId)
      .order("score", { ascending: false }),
    supabase.from("user_listing_interactions").select("status, saved, rejection_reason").eq("listing_id", listingId).maybeSingle(),
    supabase
      .from("listing_snapshots")
      .select("observed_at, price, currency, price_usd, change_kind")
      .eq("listing_id", listingId)
      .order("observed_at"),
    supabase.from("owned_vehicles").select("id, automotive_influence").eq("listing_id", listingId).order("id").limit(1).maybeSingle(),
    n ? supabase.from("notifications").select("id").eq("id", n).maybeSingle() : Promise.resolve({ data: null }),
    webConfig(),
  ]);
  if (!listing) notFound();

  const best = matches?.[0] ?? null;
  const others = (matches ?? []).slice(1);
  const reasons = (best?.match_reasons ?? {}) as Record<string, Reason>;
  const breakdown = (best?.score_breakdown ?? {}) as Record<string, Component | string>;
  const priceRef = (best?.price_ref ?? null) as PriceRef | null;
  const flags = ((best?.red_flags ?? []) as RedFlag[]).slice().sort((a, b) => Number(b.severity === "warning") - Number(a.severity === "warning"));
  const status = (interaction?.status ?? "new") as InteractionStatus;
  const fromAlert = notification?.id ?? null;
  const outboundHref = fromAlert ? `/r/${fromAlert}?to=listing` : `/app/listings/${listingId}/out`;
  const images = imageUrls(listing.images).slice(0, 10);
  const name = vehicle(listing);
  const history = priceHistory(snapshots ?? []);
  const profiles = (matches ?? [])
    .map((m) => m.search_profiles)
    .filter((p): p is { id: number; name: string } => Boolean(p));
  const back = best ? `/app/searches/${best.search_profile_id}` : "/app";

  return (
    <div className="space-y-5">
      <ViewTracker listingId={listingId} notificationId={fromAlert} />
      <Link href={back} className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:underline">
        <ArrowLeft className="size-4" aria-hidden /> {best?.search_profiles?.name ?? "Inicio"}
      </Link>

      {listing.status === "gone" ? (
        <p role="status" className="rounded-xl bg-muted p-4 text-sm">
          🚫 Esta publicación ya no está disponible: se pausó, se vendió o se dio de baja.
        </p>
      ) : null}

      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">{name}</h1>
          <p className="text-sm text-muted-foreground">
            {[listing.sources?.name ?? listing.source, listing.location_text, ageLine(listing)].filter(Boolean).join(" · ")}
            {listing.probable_repost_of ? " · 🔁 Re-publicada" : ""}
          </p>
        </div>
        {best ? (
          <div className="text-right">
            <p className="text-4xl font-semibold tabular-nums" data-testid="score">
              {best.score}
              <span className="text-lg font-normal text-muted-foreground">/100</span>
            </p>
            <LevelBadge level={best.level} score={best.score} long className="mt-1" />
          </div>
        ) : null}
      </header>

      {images.length ? (
        <div className="-mx-4 flex snap-x snap-mandatory gap-2 overflow-x-auto px-4 sm:mx-0 sm:px-0">
          {images.map((src, i) => (
            // eslint-disable-next-line @next/next/no-img-element -- listing photos live on each source's CDN
            <img
              key={src}
              src={src}
              alt={i === 0 ? name : ""}
              loading={i < 2 ? "eager" : "lazy"}
              referrerPolicy="no-referrer"
              className="h-52 w-auto max-w-[85%] shrink-0 snap-start rounded-xl bg-muted object-cover sm:h-64"
            />
          ))}
        </div>
      ) : (
        <div className="grid h-40 place-items-center rounded-xl bg-muted">
          <Car className="size-10 text-muted-foreground/60" aria-hidden />
        </div>
      )}

      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 rounded-xl bg-card p-4 text-sm ring-1 ring-foreground/10 sm:grid-cols-4">
        <Fact label="Precio publicado">
          <span className="text-lg font-semibold tabular-nums">{money(listing.price, listing.currency)}</span>
          {listing.currency === "ARS" && listing.price_usd ? (
            <span className="block text-xs text-muted-foreground">≈ {money(listing.price_usd, "USD")}</span>
          ) : null}
          {listing.price_partial ? <span className="block text-xs text-destructive">Parece un anticipo o una cuota</span> : null}
        </Fact>
        <Fact label="Kilometraje">{km(listing.mileage_km) ?? "No informado"}</Fact>
        <Fact label="Año">{listing.year ?? "No informado"}</Fact>
        <Fact label="Ubicación">
          {reasons.location?.result === "ok" ? reasons.location.detail : (listing.location_text ?? "No informada")}
        </Fact>
        <Fact label="Transmisión">{listing.transmission ? TRANSMISSION[listing.transmission] : "No informada"}</Fact>
        <Fact label="Combustible">{listing.fuel ? (FUEL[listing.fuel] ?? listing.fuel) : "No informado"}</Fact>
        <Fact label="Vendedor">
          {[listing.seller_type ? SELLER[listing.seller_type] : null, listing.seller_name].filter(Boolean).join(" · ") ||
            "No informado"}
        </Fact>
        <Fact label={listing.published_at ? "Publicado" : "Detectado"}>{ageLine(listing)?.replace(/^\S+ /, "") ?? "—"}</Fact>
      </dl>

      <ListingActions
        listingId={listingId}
        status={status}
        saved={interaction?.saved ?? false}
        rejectionReason={(interaction?.rejection_reason ?? null) as RejectionReason | null}
        outboundHref={outboundHref}
        price={listing.price}
        currency={listing.currency}
        profiles={profiles}
        owned={owned ? { id: owned.id, influence: owned.automotive_influence as Influence | null } : null}
      />

      <div className="grid gap-5 lg:grid-cols-2">
        {best ? (
          <Card>
            <CardHeader>
              <CardTitle>¿Por qué apareció?</CardTitle>
              <CardDescription>
                Coincide con tu búsqueda «{best.search_profiles?.name}»
                {others.length ? ` (y con ${others.map((o) => `«${o.search_profiles?.name}»`).join(", ")})` : ""}.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2.5" data-testid="match-reasons">
                {orderReasons(reasons).map(([key, r]) => (
                  <ReasonRow key={key} name={key} reason={r} />
                ))}
              </ul>
            </CardContent>
          </Card>
        ) : null}

        <Card>
          <CardHeader>
            <CardTitle>Análisis de precio</CardTitle>
            <CardDescription>Contra publicaciones comparables del mercado observado, en dólares.</CardDescription>
          </CardHeader>
          <CardContent>
            <PriceAnalysis
              price={listing.price}
              currency={listing.currency}
              priceUsd={listing.price_usd}
              refs={priceRef}
              minN={cfg.minComparables}
            />
          </CardContent>
        </Card>

        {best ? (
          <Card>
            <CardHeader>
              <CardTitle>Opportunity Score: {best.score}/100</CardTitle>
              <CardDescription>
                {LEVEL[best.level].emoji} {LEVEL[best.level].label}. Así se compone:
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {COMPONENTS.filter((c) => typeof breakdown[c] === "object").map((c) => {
                const comp = breakdown[c] as Component;
                return (
                  <div key={c} className="space-y-1">
                    <div className="flex justify-between gap-2 text-sm">
                      <span className="font-medium">{COMPONENT[c]}</span>
                      <span className="text-muted-foreground tabular-nums">
                        {comp.contribution.toFixed(1).replace(".", ",")} / {Math.round((comp.w / totalWeight(breakdown)) * 100)}
                      </span>
                    </div>
                    <Progress value={Math.round(comp.c * 100)} aria-label={COMPONENT[c]} />
                    <p className="text-xs text-muted-foreground">{comp.explanation}</p>
                  </div>
                );
              })}
              {breakdown.guard === "suspicious" ? (
                <p className="text-xs text-muted-foreground">
                  El nivel quedó limitado a 🟢: la diferencia con el mercado observado es tan grande que conviene verificarla.
                </p>
              ) : null}
            </CardContent>
          </Card>
        ) : null}

        {history.length >= 2 ? (
          <Card>
            <CardHeader>
              <CardTitle>Histórico de precios</CardTitle>
              <CardDescription>Cada cambio de precio publicado que detectamos.</CardDescription>
            </CardHeader>
            <CardContent>
              <PriceHistory points={history} />
            </CardContent>
          </Card>
        ) : null}

        <Card>
          <CardHeader>
            <CardTitle>Conviene verificar</CardTitle>
            <CardDescription>Información que conviene confirmar. No indica un problema.</CardDescription>
          </CardHeader>
          <CardContent>
            {flags.length ? (
              <ul className="space-y-2" data-testid="red-flags">
                {flags.map((f) => (
                  <li key={f.id} className="flex gap-2 text-sm">
                    {f.severity === "warning" ? (
                      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-600" aria-hidden />
                    ) : (
                      <Info className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
                    )}
                    {f.text}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">
                {listing.description || listing.enriched_at
                  ? "No encontramos nada puntual para verificar en esta publicación."
                  : "Todavía no leímos la descripción completa; las señales aparecen cuando la leamos."}
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>¿Qué le pregunto al vendedor?</CardTitle>
            <CardDescription>Un mensaje con lo que falta saber, listo para copiar.</CardDescription>
          </CardHeader>
          <CardContent>
            <SellerQuestions listingId={listingId} text={best?.seller_questions ?? BASE_SELLER_QUESTIONS} />
          </CardContent>
        </Card>
      </div>

      {listing.description ? (
        <details className="rounded-xl bg-card p-4 ring-1 ring-foreground/10">
          <summary className="cursor-pointer text-sm font-medium">Descripción de la publicación</summary>
          <p className="mt-3 text-sm whitespace-pre-line text-muted-foreground">{listing.description}</p>
        </details>
      ) : null}
    </div>
  );
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0 space-y-0.5">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="break-words">{children}</dd>
    </div>
  );
}

/** ✅ versión buscada · ❔ caja no informada · ➖ preferencia que no se cumple (§23). */
function ReasonRow({ name, reason }: { name: string; reason: Reason }) {
  const label = REASON_NAME[name] ?? name;
  let title: string;
  let Icon = CircleCheck;
  let tone = "text-emerald-600";
  if (reason.result === "ok") {
    title =
      name === "transmission" || name === "fuel"
        ? `${label} ${reason.detail.toLowerCase()}`
        : (REASON_OK[name] ?? label);
  } else if (reason.result === "unknown") {
    title = `${label}: no informado`;
    Icon = CircleHelp;
    tone = "text-muted-foreground";
  } else {
    title = `${label}: no coincide con tu preferencia`;
    Icon = CircleMinus;
    tone = "text-amber-600";
  }
  return (
    <li className="flex gap-2.5 text-sm" data-result={reason.result}>
      <Icon className={cn("mt-0.5 size-4 shrink-0", tone)} aria-label={reason.result === "ok" ? "Cumple" : reason.result === "unknown" ? "No informado" : "No cumple"} />
      <div className="min-w-0">
        <p className="font-medium">
          {title}
          {reason.kind === "soft" ? <span className="ml-1 text-xs font-normal text-muted-foreground">(preferencia)</span> : null}
        </p>
        {reason.detail && reason.result !== "unknown" ? (
          <p className="text-xs text-muted-foreground">{reason.detail}</p>
        ) : null}
      </div>
    </li>
  );
}

function totalWeight(breakdown: Record<string, Component | string>): number {
  return COMPONENTS.reduce((sum, c) => sum + (typeof breakdown[c] === "object" ? (breakdown[c] as Component).w : 0), 0) || 1;
}

/** §19: precio publicado vs. la mediana de publicaciones comparables, with prudent language. */
function PriceAnalysis({
  price,
  currency,
  priceUsd,
  refs,
  minN,
}: {
  price: number | null;
  currency: string | null;
  priceUsd: number | null;
  refs: PriceRef | null;
  minN: number;
}) {
  const enough = refs && refs.n >= minN && refs.median;
  return (
    <dl className="space-y-2.5 text-sm" data-testid="price-analysis">
      <div className="flex justify-between gap-3">
        <dt className="text-muted-foreground">Precio publicado</dt>
        <dd className="text-right font-medium tabular-nums">
          {money(price, currency)}
          {currency === "ARS" && priceUsd ? <span className="block text-xs text-muted-foreground">≈ {money(priceUsd, "USD")}</span> : null}
        </dd>
      </div>
      {enough ? (
        <>
          <div className="flex justify-between gap-3">
            <dt className="text-muted-foreground">Publicaciones comparables</dt>
            <dd className="text-right tabular-nums">
              {money(refs.median, "USD")} mediana
              <span className="block text-xs text-muted-foreground">
                n={refs.n} · {COMPARABLE_LEVEL[refs.level_used] ?? refs.level_used}
              </span>
            </dd>
          </div>
          {refs.diff_pct != null ? (
            <div className="flex justify-between gap-3">
              <dt className="text-muted-foreground">Diferencia</dt>
              <dd className={cn("text-right font-semibold tabular-nums", refs.diff_pct > 0 ? "text-emerald-700" : "text-foreground")}>
                {refs.diff_pct > 0 ? "-" : "+"}
                {pct(Math.abs(refs.diff_pct))}
              </dd>
            </div>
          ) : null}
          {refs.diff_pct != null ? (
            <p className="rounded-lg bg-muted p-3 text-sm">
              {Math.round(refs.diff_pct) === 0
                ? "En línea con el mercado observado."
                : `${pct(Math.abs(refs.diff_pct))} ${refs.diff_pct > 0 ? "debajo" : "arriba"} del mercado observado.`}
              {refs.p25 != null && refs.p75 != null ? (
                <span className="block text-xs text-muted-foreground">
                  La mitad de las publicaciones comparables está entre {money(refs.p25, "USD")} y {money(refs.p75, "USD")}.
                </span>
              ) : null}
            </p>
          ) : null}
        </>
      ) : (
        <p className="rounded-lg bg-muted p-3 text-sm text-muted-foreground">
          Sin comparables suficientes (n={number(refs?.n ?? 0)}): todavía no hay {minN} publicaciones parecidas para
          comparar el precio publicado.
        </p>
      )}
    </dl>
  );
}

/** One point per price the listing had (§31); consecutive repeats collapse. */
function priceHistory(
  snapshots: { observed_at: string; price: number | null; currency: string | null; price_usd: number | null }[],
): PricePoint[] {
  const points: PricePoint[] = [];
  for (const s of snapshots) {
    if (s.price == null) continue;
    const last = points[points.length - 1];
    const currency = s.currency ?? "USD";
    if (last && last.price === s.price && last.currency === currency) continue;
    points.push({ at: s.observed_at, price: s.price, currency });
  }
  // Mixed currencies can't share an axis: fall back to USD.
  if (new Set(points.map((p) => p.currency)).size > 1) {
    return snapshots
      .filter((s) => s.price_usd != null)
      .map((s) => ({ at: s.observed_at, price: s.price_usd as number, currency: "USD" }))
      .filter((p, i, all) => i === 0 || all[i - 1].price !== p.price);
  }
  return points;
}

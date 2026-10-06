import { AlertTriangle, ArrowLeft, Ban, Car, CircleCheck, CircleHelp, CircleMinus, Info } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ListingActions } from "@/components/app/listing-actions";
import { DealerFeesNotice } from "@/components/app/dealer-fees-notice";
import { DescriptionPriceContext, SellerDescription } from "@/components/app/description-insights";
import { type PricePoint, PriceHistory } from "@/components/app/price-history";
import { SellerQuestions } from "@/components/app/seller-questions";
import { ViewTracker } from "@/components/app/view-tracker";
import { requireUser } from "@/lib/auth";
import { type WebConfig, webConfig } from "@/lib/config";
import {
  BASE_SELLER_QUESTIONS,
  COMPONENT,
  COMPONENTS,
  FUEL,
  type InteractionStatus,
  LEVEL,
  type Level,
  REASON_NAME,
  REASON_OK,
  SELLER,
  TRANSMISSION,
} from "@/lib/copy";
import { ageLine, imageUrls, km, money, number, pct, vehicle } from "@/lib/format";
import { financingOffered, financingTerms, isCashPrice, publishedKind } from "@/lib/price";
import { createClient } from "@/lib/supabase/server";
import type { Component, Listing, PriceRef, Reason, RedFlag } from "@/lib/types";
import { cn } from "@/lib/utils";
import { orderReasons } from "@/lib/why";

export const metadata: Metadata = { title: "Publicación" };

type Supabase = Awaited<ReturnType<typeof createClient>>;
type Similar = { id: number; name: string; mileage: string | null; source: string; usd: number };

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
    n ? supabase.from("notifications").select("id").eq("id", n).maybeSingle() : Promise.resolve({ data: null }),
    webConfig(),
  ]);
  if (!listing) notFound();

  const best = matches?.[0] ?? null;
  const gone = listing.status === "gone";
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
  const sourceName = listing.sources?.name ?? listing.source;
  const history = priceHistory(snapshots ?? []);
  const similar = gone ? [] : await similarListings(supabase, listing, priceRef, cfg.comparables);
  const back = best ? `/app/searches/${best.search_profile_id}` : "/app";

  return (
    <div>
      <ViewTracker listingId={listingId} notificationId={fromAlert} />
      <Link href={back} className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground hover:underline">
        <ArrowLeft className="size-4" aria-hidden /> {best?.search_profiles?.name ?? "Inicio"}
      </Link>

      {gone ? (
        <p role="status" className="mt-4 flex items-start gap-2.5 rounded-lg bg-muted p-4 text-[15px]">
          <Ban className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden />
          Esta publicación ya no está disponible. Conservamos sus datos y precios como referencia histórica.
        </p>
      ) : null}

      <header className="mt-4 grid gap-5 md:grid-cols-[1fr_auto] md:items-end">
        <div className="min-w-0">
          <h1 className="type-heading text-[1.9rem] leading-[1.05] md:text-[2.6rem]">{name}</h1>
          <p className="mt-2.5 flex flex-wrap gap-x-4.5 gap-y-1 text-sm text-muted-foreground">
            <span>
              En <b className="font-semibold text-foreground">{sourceName}</b>
            </span>
            {listing.location_text ? <span>{listing.location_text}</span> : null}
            {ageLine(listing) ? <span>{ageLine(listing)}</span> : null}
            {listing.probable_repost_of ? <span>Re-publicada</span> : null}
          </p>
        </div>
        {best && !gone ? (
          <div className="flex items-center gap-3.5">
            <span data-testid="score" className="type-figure text-[64px] leading-none tracking-[-0.03em]">
              <span className={markFor(best.level)}>{best.score}</span>
            </span>
            <p className="text-sm leading-snug text-muted-foreground">
              <b className="block text-[17px] font-bold text-foreground">{LEVEL[best.level].label}</b>
              Opportunity Score de 0 a 100
            </p>
          </div>
        ) : null}
      </header>

      <Gallery images={images} name={name} more={outboundHref} />

      <dl className="mt-6 grid grid-cols-2 gap-x-6 border-t-2 border-foreground md:grid-cols-[1.6fr_repeat(3,1fr)]">
        <Fact label={isCashPrice(listing.description_facts) ? "Precio de contado" : "Precio publicado"} className="col-span-2 md:col-span-1 md:row-span-2">
          <span className="type-figure block text-2xl leading-tight" data-testid="price">
            {money(listing.price, listing.currency)}
          </span>
          {listing.currency === "ARS" && listing.price_usd ? (
            <span className="block text-[13px] text-muted-foreground">≈ {money(listing.price_usd, "USD")} al dólar del día</span>
          ) : null}
          {listing.price_source === "description" && listing.price_published != null ? (
            <span className="block text-[13px] text-muted-foreground">
              Publicado {money(listing.price_published, listing.price_published_currency)}
              {publishedKind(listing.description_facts) ? ` (${publishedKind(listing.description_facts)})` : ""}: el precio sale
              de la descripción
            </span>
          ) : null}
          {listing.price_partial ? <span className="block text-[13px] text-destructive">Parece un anticipo o una cuota</span> : null}
          {financingOffered(listing.description_facts) ? (
            <span className="mt-1 block text-[13px]" data-testid="financing">
              También se puede financiar
              {financingTerms(listing.description_facts) ? (
                <span className="block text-muted-foreground">{financingTerms(listing.description_facts)}</span>
              ) : null}
            </span>
          ) : null}
          <DealerFeesNotice sellerType={listing.seller_type} />
        </Fact>
        <Fact label="Kilometraje">{km(listing.mileage_km) ?? "No informado"}</Fact>
        <Fact label="Año">{listing.year ?? "No informado"}</Fact>
        <Fact label="Caja">{listing.transmission ? TRANSMISSION[listing.transmission] : "No informada"}</Fact>
        <Fact label="Combustible">{listing.fuel ? (FUEL[listing.fuel] ?? listing.fuel) : "No informado"}</Fact>
        <Fact label="Vendedor">
          {[listing.seller_type ? SELLER[listing.seller_type] : null, listing.seller_name].filter(Boolean).join(", ") ||
            "No informado"}
        </Fact>
        <Fact label="Ubicación">
          {reasons.location?.result === "ok" ? reasons.location.detail : (listing.location_text ?? "No informada")}
        </Fact>
      </dl>

      <div className="mt-5">
        <ListingActions
          listingId={listingId}
          status={status}
          saved={interaction?.saved ?? false}
          outboundHref={outboundHref}
        />
      </div>

      <div className="mt-11 grid gap-11 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)] lg:gap-14">
        <div className="space-y-11">
          <Section title={gone ? "Precio de referencia" : "¿Está bien de precio?"}>
            {gone ? (
              <p className="mt-3 text-[15px] text-muted-foreground">
                El precio corresponde al último aviso que observamos. Es una referencia histórica, no una oferta disponible ni un precio de venta confirmado.
              </p>
            ) : (
              <PriceVerdict
                listing={listing}
                sourceName={sourceName}
                refs={priceRef}
                minN={cfg.minComparables}
                window={cfg.comparables}
                similar={similar}
                cautious={flags.some((f) => f.id === "much_cheaper") || breakdown.guard === "suspicious"}
              />
            )}
            {!gone ? <DescriptionPriceContext listing={listing} refs={priceRef} minN={cfg.minComparables} /> : null}
          </Section>

          {best && !gone ? (
            <Section
              title={`¿Por qué tiene ${best.score}?`}
              hint="El Opportunity Score va de 0 a 100: mientras más alto, mejor oportunidad para lo que buscás."
            >
              <ScoreInWords breakdown={breakdown} />
            </Section>
          ) : null}
        </div>

        <div className="space-y-11">
          <SellerDescription listing={listing} />
          {best ? (
            <Section
              title="¿Por qué apareció?"
              hint={`Coincide con tu búsqueda «${best.search_profiles?.name}»${
                others.length ? ` (y con ${others.map((o) => `«${o.search_profiles?.name}»`).join(", ")})` : ""
              }.`}
            >
              <ul className="mt-2" data-testid="match-reasons">
                {orderReasons(reasons).map(([key, r]) => (
                  <ReasonRow key={key} name={key} reason={r} />
                ))}
              </ul>
            </Section>
          ) : null}

          <Section title="Conviene verificar" hint="Información que conviene confirmar. No indica un problema.">
            {flags.length ? (
              <ul className="mt-2" data-testid="red-flags">
                {flags.map((f) => (
                  <li key={f.id} className="grid grid-cols-[20px_1fr] gap-2.5 border-b py-2.5 text-[15px] last:border-b-0">
                    {f.severity === "warning" ? (
                      <AlertTriangle className="mt-0.5 size-4 text-warn" aria-label="Importante" />
                    ) : (
                      <Info className="mt-0.5 size-4 text-faint" aria-hidden />
                    )}
                    <span className={f.severity === "warning" ? "font-semibold text-warn" : undefined}>{f.text}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-3 text-sm text-muted-foreground">
                {listing.description || listing.enriched_at
                  ? "No encontramos nada puntual para verificar en esta publicación."
                  : "Todavía no leímos la descripción completa; las señales aparecen cuando la leamos."}
              </p>
            )}
          </Section>

          <Section title="¿Qué le pregunto al vendedor?" hint="Un mensaje con lo que falta saber, listo para copiar.">
            <div className="mt-3">
              <SellerQuestions listingId={listingId} text={best?.seller_questions ?? BASE_SELLER_QUESTIONS} />
            </div>
          </Section>

          {history.length >= 2 ? (
            <Section title="Histórico de precios" hint="Cada cambio de precio publicado que detectamos.">
              <div className="mt-3">
                <PriceHistory points={history} />
              </div>
            </Section>
          ) : null}
        </div>
      </div>

      {listing.description ? (
        <details className="mt-11 rounded-lg bg-muted p-4">
          <summary className="cursor-pointer text-sm font-semibold">Descripción de la publicación</summary>
          <p className="mt-3 text-sm whitespace-pre-line text-muted-foreground">{listing.description}</p>
        </details>
      ) : null}
    </div>
  );
}

function markFor(level: Level) {
  return level === "high" ? "mark" : level === "good" ? "mark-under" : level === "low" ? "text-faint" : undefined;
}

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="type-heading text-[21px] leading-tight">{title}</h2>
      {hint ? <p className="mt-1 text-sm text-muted-foreground">{hint}</p> : null}
      {children}
    </section>
  );
}

function Fact({ label, className, children }: { label: string; className?: string; children: React.ReactNode }) {
  return (
    <div className={cn("min-w-0 border-b py-3", className)}>
      <dt className="text-[13px] text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 font-semibold break-words">{children}</dd>
    </div>
  );
}

/** First photo big, four more beside it; the rest are on the source. */
function Gallery({ images, name, more }: { images: string[]; name: string; more: string }) {
  if (!images.length) {
    return (
      <div className="mt-6 grid h-40 place-items-center rounded-md bg-muted">
        <Car className="size-10 text-faint" aria-hidden />
      </div>
    );
  }
  const shown = images.slice(0, 5);
  return (
    <div className="mt-6 grid grid-cols-4 gap-1.5 md:grid-cols-[2fr_1fr_1fr] md:grid-rows-2">
      {shown.map((src, i) => (
        <div
          key={src}
          className={cn(
            "relative overflow-hidden rounded bg-muted",
            i === 0 ? "col-span-full aspect-video md:col-span-1 md:row-span-2 md:aspect-auto" : "aspect-[4/3] md:aspect-auto md:min-h-36",
          )}
        >
          {/* eslint-disable-next-line @next/next/no-img-element -- listing photos live on each source's CDN */}
          <img
            src={src}
            alt={i === 0 ? name : ""}
            loading={i < 2 ? "eager" : "lazy"}
            referrerPolicy="no-referrer"
            className="size-full object-cover"
          />
          {i === shown.length - 1 && images.length > shown.length ? (
            <a
              href={more}
              target="_blank"
              rel="noopener noreferrer"
              className="absolute inset-0 grid place-items-center bg-[#14213d]/60 text-sm font-semibold text-white hover:bg-[#14213d]/70"
            >
              +{images.length - shown.length} fotos
            </a>
          ) : null}
        </div>
      ))}
    </div>
  );
}

/** ✅ versión buscada · ❔ caja no informada · ➖ preferencia que no se cumple (§23). */
function ReasonRow({ name, reason }: { name: string; reason: Reason }) {
  const label = REASON_NAME[name] ?? name;
  let title: string;
  let Icon = CircleCheck;
  let tone = "text-ok";
  if (reason.result === "ok") {
    title =
      name === "transmission" || name === "fuel"
        ? `${label} ${reason.detail.toLowerCase()}`
        : (REASON_OK[name] ?? label);
  } else if (reason.result === "unknown") {
    title = `${label}: no informado`;
    Icon = CircleHelp;
    tone = "text-faint";
  } else {
    title = `${label}: no coincide con tu preferencia`;
    Icon = CircleMinus;
    tone = "text-warn";
  }
  return (
    <li className="grid grid-cols-[20px_1fr] gap-2.5 border-b py-2.5 last:border-b-0" data-result={reason.result}>
      <Icon
        className={cn("mt-0.5 size-4.5", tone)}
        aria-label={reason.result === "ok" ? "Cumple" : reason.result === "unknown" ? "No informado" : "No cumple"}
      />
      <div className="min-w-0">
        <p className="font-semibold">
          {title}
          {reason.kind === "soft" ? <span className="ml-1 text-xs font-normal text-muted-foreground">(preferencia)</span> : null}
        </p>
        {reason.detail && reason.result !== "unknown" ? <p className="text-sm text-muted-foreground">{reason.detail}</p> : null}
      </div>
    </li>
  );
}

const SAME: Record<string, string> = {
  trim_transmission: " de la misma versión y caja",
  transmission: " con la misma caja",
  model: "",
};

/**
 * §19 in plain words: is the published price good? One sentence, the two
 * prices side by side and a few of the cars it was compared with — the
 * prudent terms ("mercado observado", "publicaciones comparables") stay.
 */
function PriceVerdict({
  listing,
  sourceName,
  refs,
  minN,
  window,
  similar,
  cautious,
}: {
  listing: Listing;
  sourceName: string;
  refs: PriceRef | null;
  minN: number;
  window: WebConfig["comparables"];
  similar: Similar[];
  cautious: boolean;
}) {
  const usd = listing.price_usd;
  const median = refs?.median ?? null;
  if (listing.price_partial || !usd || !refs || !median || refs.n < minN) {
    return (
      <div data-testid="price-analysis">
        <p className="mt-3 rounded-lg bg-muted p-4 text-[15px]">
          {listing.price_partial
            ? "El precio publicado parece un anticipo o una cuota, así que no lo comparamos con otros autos."
            : !usd
              ? "Todavía no pudimos pasar el precio publicado a dólares para compararlo."
              : !refs?.n
                ? "Todavía no encontramos autos parecidos para comparar el precio."
                : `Todavía no podemos decirlo: hay ${number(refs.n)} autos parecidos y necesitamos al menos ${minN} para comparar el precio publicado.`}
        </p>
      </div>
    );
  }

  const diff = refs.diff_pct ?? (1 - usd / median) * 100;
  const gap = Math.round(Math.abs(median - usd) / 100) * 100;
  const inLine = Math.abs(diff) < 2.5 || gap < 100;
  const years = listing.year ? `, de ${listing.year - window.yearTol} a ${listing.year + window.yearTol}` : "";
  const mileage = listing.mileage_km ? " y con kilometraje parecido" : "";
  const model = [listing.make, listing.model].filter(Boolean).join(" ");

  return (
    <div data-testid="price-analysis">
      <p className="mt-2.5 max-w-[34ch] text-xl leading-snug">
        {inLine ? (
          <>Está en línea con lo que suelen pedir por autos parecidos.</>
        ) : diff > 0 ? (
          <>
            <span className="mark">Sí, está unos {money(gap, "USD")} más barato</span> que lo que suelen pedir por autos parecidos.
          </>
        ) : (
          <>Está unos {money(gap, "USD")} más caro que lo que suelen pedir por autos parecidos.</>
        )}
      </p>
      <p className="mt-1 text-sm text-muted-foreground">
        {inLine
          ? "En línea con el mercado observado."
          : `${pct(Math.abs(diff))} ${diff > 0 ? "debajo" : "arriba"} del mercado observado.`}
      </p>

      <dl className="mt-4.5 grid gap-2.5 sm:grid-cols-2">
        <div className={cn("rounded-lg px-4 pt-3.5 pb-4", diff > 0 && !inLine ? "bg-mark-soft ring-2 ring-mark ring-inset" : "bg-muted")}>
          <dt className="text-sm">Pide este auto</dt>
          <dd>
            <b className="type-figure mt-1 block text-[28px] leading-none md:text-[32px]">{money(usd, "USD")}</b>
            {listing.currency !== "USD" ? (
              <span className="mt-1.5 block text-[13px]">Publicado en {money(listing.price, listing.currency)}</span>
            ) : null}
          </dd>
        </div>
        <div className="rounded-lg bg-muted px-4 pt-3.5 pb-4">
          <dt className="text-sm text-muted-foreground">Suelen pedir por autos parecidos</dt>
          <dd>
            <b className="type-figure mt-1 block text-[28px] leading-none md:text-[32px]">{money(median, "USD")}</b>
            {refs.p25 != null && refs.p75 != null ? (
              <span className="mt-1.5 block text-[13px] text-muted-foreground">
                La mitad pide entre {money(refs.p25, "USD")} y {money(refs.p75, "USD")}
              </span>
            ) : null}
          </dd>
        </div>
      </dl>

      <p className="mt-3 max-w-[62ch] text-sm text-muted-foreground">
        Lo comparamos con {number(refs.n)} {model}
        {SAME[refs.level_used] ?? ""}
        {years}
        {mileage}, publicados en los últimos {window.maxAgeDays} días.
      </p>

      {cautious && diff > 0 ? (
        <p className="mt-4 grid grid-cols-[20px_1fr] gap-2.5 rounded-lg bg-warn-soft px-3.5 py-3 text-[15px]">
          <AlertTriangle className="mt-0.5 size-4 text-warn" aria-hidden />
          <span>
            <b className="font-bold">Un precio tan bajo puede tener una explicación.</b> Antes de ir a verlo, preguntale al vendedor
            por qué lo vende a ese precio.
          </span>
        </p>
      ) : null}

      {similar.length ? (
        <>
          <h3 className="mt-6 text-[15px] font-bold">Algunos autos parecidos</h3>
          <ol className="mt-1">
            <li className="mark-row -mx-2.5 grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 px-2.5 py-2.5">
              <span className="min-w-0 leading-tight font-semibold">
                Este auto
                <span className="mt-0.5 block text-[13px] font-normal">
                  {[vehicle(listing), km(listing.mileage_km), sourceName].filter(Boolean).join(", ")}
                </span>
              </span>
              <span className="type-figure text-right text-[17px]">{money(usd, "USD")}</span>
            </li>
            {similar.map((s) => (
              <li key={s.id} className="-mx-2.5 border-t px-2.5">
                <Link href={`/app/listings/${s.id}`} className="group grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 py-2.5">
                  <span className="min-w-0 leading-tight font-semibold group-hover:underline">
                    {s.name}
                    <span className="mt-0.5 block text-[13px] font-normal text-muted-foreground">
                      {[s.mileage, s.source].filter(Boolean).join(", ")}
                    </span>
                  </span>
                  <span className="type-figure text-right text-[17px]">{money(s.usd, "USD")}</span>
                </Link>
              </li>
            ))}
          </ol>
        </>
      ) : null}
    </div>
  );
}

/** "Suma mucho / algo / poco" from each part's share of its maximum (§6.3 in words). */
function ScoreInWords({ breakdown }: { breakdown: Record<string, Component | string> }) {
  const parts = COMPONENTS.filter((c) => typeof breakdown[c] === "object").map((c) => ({ key: c, ...(breakdown[c] as Component) }));
  return (
    <>
      <ul className="mt-3">
        {parts.map((p) => {
          const adds = p.c === 0 ? "nada" : p.c >= 0.9 ? "mucho" : p.c >= 0.5 ? "algo" : "poco";
          return (
            <li key={p.key} className="grid grid-cols-[104px_minmax(0,1fr)] items-baseline gap-3.5 border-b py-3 last:border-b-0">
              <span className={cn("justify-self-start text-[13px] font-bold whitespace-nowrap", (adds === "poco" || adds === "nada") && "text-faint")}>
                <span className={adds === "mucho" ? "mark" : adds === "algo" ? "mark-under" : undefined}>Suma {adds}</span>
              </span>
              <p>
                <b className="block font-semibold">{SCORE_PART[p.key] ?? COMPONENT[p.key]}</b>
                <span className="block text-sm text-muted-foreground">{plain(p.explanation)}</span>
              </p>
            </li>
          );
        })}
      </ul>
      {breakdown.guard === "suspicious" ? (
        <p className="mt-2 text-sm text-muted-foreground">
          El nivel quedó limitado a {LEVEL.good.label.toLowerCase()}: la diferencia con el mercado observado es tan grande que conviene
          verificarla.
        </p>
      ) : null}

    </>
  );
}

const SCORE_PART: Record<string, string> = {
  price: "El precio",
  match: "Lo que pediste",
  km: "El kilometraje",
  trim: "La versión",
  recency: "Qué tan nuevo es el aviso",
  completeness: "Los datos del aviso",
};

/** The scorer's explanation without the technical tail: "7/10 datos" → "7 de 10 datos". */
function plain(text: string): string {
  const t = text
    .split(" · ")[0]
    .replace(/\s*\(n=\d+\)/, "")
    .replace(/(\d+)\/(\d+)/, "$1 de $2")
    .trim();
  return t.charAt(0).toUpperCase() + t.slice(1);
}

/**
 * A few of the listings behind the price comparison: public.comparables' pool
 * (same make and model, year ± tol, km ± tol%, seen in the window, no partial
 * prices nor reposts) at the level the score used, spread from cheapest to
 * dearest. The stored price_ref may predate a listing or two.
 */
async function similarListings(
  supabase: Supabase,
  listing: Listing,
  refs: PriceRef | null,
  window: WebConfig["comparables"],
): Promise<Similar[]> {
  if (!refs || !listing.make || !listing.model) return [];
  const literal = (value: string) => value.replace(/[\\%_]/g, (c) => `\\${c}`);
  let query = supabase
    .from("listings")
    .select("id, make, model, trim, year, title, mileage_km, price_usd, source, sources(name)")
    .neq("id", listing.id)
    .ilike("make", literal(listing.make))
    .ilike("model", literal(listing.model))
    .gt("price_usd", 0)
    .eq("price_partial", false)
    .is("probable_repost_of", null)
    .gte("last_seen_at", new Date(Date.now() - window.maxAgeDays * 86_400_000).toISOString());
  if (listing.year) query = query.gte("year", listing.year - window.yearTol).lte("year", listing.year + window.yearTol);
  if (listing.mileage_km) {
    const lo = Math.floor(listing.mileage_km * (1 - window.kmTolPct / 100));
    const hi = Math.ceil(listing.mileage_km * (1 + window.kmTolPct / 100));
    query = query.or(`mileage_km.is.null,and(mileage_km.gte.${lo},mileage_km.lte.${hi})`);
  }
  if (refs.level_used !== "model") {
    if (!listing.transmission) return [];
    query = query.eq("transmission", listing.transmission);
  }
  if (refs.level_used === "trim_transmission") {
    if (!listing.trim) return [];
    query = query.ilike("trim", literal(listing.trim));
  }
  const { data } = await query.order("price_usd").limit(80);
  const rows = (data ?? []).filter((r) => r.price_usd != null);
  const picks = rows.length <= 4 ? rows : [0, 1, 2, 3].map((i) => rows[Math.round((i * (rows.length - 1)) / 3)]);
  return picks.map((r) => ({
    id: r.id,
    name: vehicle(r),
    mileage: km(r.mileage_km),
    source: r.sources?.name ?? r.source,
    usd: r.price_usd as number,
  }));
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
  // Mixed currencies can't be compared line by line: fall back to USD.
  if (new Set(points.map((p) => p.currency)).size > 1) {
    return snapshots
      .filter((s) => s.price_usd != null)
      .map((s) => ({ at: s.observed_at, price: s.price_usd as number, currency: "USD" }))
      .filter((p, i, all) => i === 0 || all[i - 1].price !== p.price);
  }
  return points;
}

import { Car, MapPin, Star } from "lucide-react";
import Link from "next/link";

import { ageLine, firstImage, km, money, vehicle } from "@/lib/format";
import type { MatchCard } from "@/lib/types";
import { cn } from "@/lib/utils";

import { LevelBadge, StatusBadge } from "./badges";

/** The ruled list the rows below sit in: one column, two from `lg`. */
export const LISTING_ROWS = "grid grid-cols-1 border-t-2 border-foreground lg:grid-cols-2 lg:gap-x-10";

/**
 * A result row (§29), a dashboard opportunity (§28) or a saved listing (§30):
 * a line of the guide, price first, the score marked on the right.
 */
export function ListingCard({
  card,
  showProfile = false,
  footer,
}: {
  card: Pick<
    MatchCard,
    | "listing_id"
    | "make"
    | "model"
    | "trim"
    | "year"
    | "title"
    | "price"
    | "currency"
    | "mileage_km"
    | "location_text"
    | "published_at"
    | "first_seen_at"
    | "images"
    | "level"
    | "score"
    | "status"
    | "saved"
    | "profile_name"
    | "listing_status"
    | "probable_repost_of"
  > &
    Partial<Pick<MatchCard, "price_kind" | "financing_offered" | "price_usd">>;
  showProfile?: boolean;
  footer?: React.ReactNode;
}) {
  const image = firstImage(card.images);
  const name = vehicle(card);
  const gone = card.listing_status === "gone";
  const mileage = km(card.mileage_km);

  return (
    <article
      data-testid="listing-card"
      className="group relative grid grid-cols-[88px_minmax(0,1fr)] gap-x-4 gap-y-1 border-b py-3.5 hover:bg-[linear-gradient(90deg,transparent,var(--muted)_6%,var(--muted)_94%,transparent)] sm:grid-cols-[96px_minmax(0,1fr)_auto]"
    >
      <div className="relative row-span-3 h-16 w-full overflow-hidden rounded bg-muted sm:h-[66px]">
        {image ? (
          // eslint-disable-next-line @next/next/no-img-element -- listing photos live on each source's CDN
          <img src={image} alt="" loading="lazy" referrerPolicy="no-referrer" className="size-full object-cover" />
        ) : (
          <Car className="absolute inset-0 m-auto size-7 text-faint" aria-hidden />
        )}
      </div>

      <h3 className="min-w-0 text-base leading-snug font-bold">
        <Link href={`/app/listings/${card.listing_id}`} className="after:absolute after:inset-0 group-hover:underline">
          {name}
        </Link>
      </h3>

      <p className="type-figure text-lg leading-tight">
        {money(card.price, card.currency)}
        {card.price_kind === "cash" && card.price != null ? (
          <span className="ml-1.5 text-[13px] font-normal [font-stretch:100%] text-muted-foreground">de contado</span>
        ) : null}
        {card.currency === "ARS" && card.price_usd ? (
          <span className="ml-1.5 text-[13px] font-normal whitespace-nowrap [font-stretch:100%] text-muted-foreground">
            ≈ {money(card.price_usd, "USD")}
          </span>
        ) : null}
        {card.financing_offered ? (
          <span className="ml-1.5 rounded bg-muted px-1.5 py-0.5 align-[2px] text-[11px] font-semibold whitespace-nowrap [font-stretch:100%] text-muted-foreground">
            Financiable
          </span>
        ) : null}
      </p>

      <p className="flex min-w-0 flex-wrap gap-x-3.5 text-[13px] text-muted-foreground">
        {mileage ? <span>{mileage}</span> : null}
        {card.location_text ? (
          <span className="inline-flex min-w-0 items-center gap-1">
            <MapPin className="size-3 shrink-0" aria-hidden />
            <span className="truncate">{card.location_text}</span>
          </span>
        ) : null}
      </p>

      <div className="col-start-2 flex flex-wrap items-center gap-x-2.5 gap-y-1.5 pt-1 sm:col-start-3 sm:row-span-3 sm:row-start-1 sm:flex-col sm:items-end sm:pt-0 sm:text-right">
        {!gone ? <LevelBadge level={card.level} score={card.score} long className="max-sm:flex-row max-sm:items-baseline max-sm:gap-2" /> : null}
        <div className="flex flex-wrap items-center gap-1.5 sm:justify-end">
          {card.saved ? (
            <span className="inline-flex items-center gap-1 text-xs font-semibold">
              <Star className="size-3.5 fill-current" aria-hidden /> Guardado
            </span>
          ) : null}
          {!gone ? <StatusBadge status={card.status} /> : null}
        </div>
        <p className="flex flex-wrap gap-x-2 text-xs text-muted-foreground sm:flex-col sm:items-end">
          {gone ? <span className="font-medium text-destructive">Ya no está disponible</span> : null}
          {card.probable_repost_of ? <span>Re-publicado</span> : null}
          <span>{ageLine(card)}</span>
          {showProfile && card.profile_name ? <span>«{card.profile_name}»</span> : null}
        </p>
      </div>

      {footer ? <div className={cn("col-span-full sm:col-start-2")}>{footer}</div> : null}
    </article>
  );
}

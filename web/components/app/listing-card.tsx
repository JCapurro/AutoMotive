import { Car, MapPin, Star } from "lucide-react";
import Link from "next/link";

import { ageLine, firstImage, km, money, vehicle } from "@/lib/format";
import type { MatchCard } from "@/lib/types";

import { LevelBadge, StatusBadge } from "./badges";

/** A result row (§29), a dashboard opportunity (§28) or a saved listing (§30). */
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
    Partial<Pick<MatchCard, "price_kind" | "financing_offered">>;
  showProfile?: boolean;
  footer?: React.ReactNode;
}) {
  const image = firstImage(card.images);
  const name = vehicle(card);
  const gone = card.listing_status === "gone";
  const meta = [km(card.mileage_km), card.location_text].filter(Boolean);

  return (
    <article
      data-testid="listing-card"
      className="group relative flex gap-3 rounded-xl bg-card p-3 ring-1 ring-foreground/10 transition-shadow hover:shadow-sm"
    >
      <div className="relative size-20 shrink-0 overflow-hidden rounded-lg bg-muted sm:h-24 sm:w-32">
        {image ? (
          // eslint-disable-next-line @next/next/no-img-element -- listing photos live on each source's CDN
          <img src={image} alt="" loading="lazy" referrerPolicy="no-referrer" className="size-full object-cover" />
        ) : (
          <Car className="absolute inset-0 m-auto size-7 text-muted-foreground/60" aria-hidden />
        )}
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="flex items-start justify-between gap-2">
          <h3 className="min-w-0 text-sm leading-snug font-medium sm:text-base">
            <Link href={`/app/listings/${card.listing_id}`} className="after:absolute after:inset-0">
              {name}
            </Link>
          </h3>
          <LevelBadge level={card.level} score={card.score} />
        </div>
        <p className="text-base font-semibold tabular-nums">
          {money(card.price, card.currency)}
          {card.price_kind === "cash" && card.price != null ? (
            <span className="ml-1.5 text-xs font-normal text-muted-foreground">de contado</span>
          ) : null}
          {card.financing_offered ? (
            <span className="ml-1.5 rounded-full bg-muted px-1.5 py-0.5 text-[11px] font-normal text-muted-foreground">
              💳 financiable
            </span>
          ) : null}
        </p>
        {meta.length ? (
          <p className="flex min-w-0 items-center gap-1 truncate text-xs text-muted-foreground">
            {card.location_text ? <MapPin className="size-3 shrink-0" aria-hidden /> : null}
            <span className="truncate">{meta.join(" · ")}</span>
          </p>
        ) : null}
        <div className="mt-auto flex flex-wrap items-center gap-1.5 pt-1 text-xs text-muted-foreground">
          <StatusBadge status={card.status} />
          {card.saved ? (
            <span className="inline-flex items-center gap-0.5 text-amber-600">
              <Star className="size-3 fill-current" aria-hidden /> Guardado
            </span>
          ) : null}
          {gone ? <span className="text-destructive">Ya no está disponible</span> : null}
          {card.probable_repost_of ? <span>🔁 Re-publicado</span> : null}
          <span>{ageLine(card)}</span>
          {showProfile && card.profile_name ? <span>· {card.profile_name}</span> : null}
        </div>
        {footer}
      </div>
    </article>
  );
}

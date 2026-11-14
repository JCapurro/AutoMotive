import { LandingFeedPick } from "@/components/landing-feed-pick";
import { money } from "@/lib/format";
import { feedAgo, type LandingFeed, modelLabel } from "@/lib/landing-hero";

const number = new Intl.NumberFormat("es-AR");

/**
 * The new hero's proof (lib/landing-hero.ts): cars flagged in the last 24
 * hours, read like the old example (a price list with a highlighter), each
 * with a button that starts a search for one like it.
 */
export function LandingFeedList({ feed, now = new Date() }: { feed: LandingFeed; now?: Date }) {
  return (
    <section id="hoy" aria-labelledby="hoy-titulo" className="scroll-mt-24 rounded-[10px] bg-muted px-4 pt-5 pb-4.5 sm:px-6.5">
      <h2 id="hoy-titulo" className="type-heading text-[1.4rem] leading-tight text-balance">
        En las últimas 24 h marcamos {number.format(feed.flagged24h)} autos.
      </h2>
      <p className="mt-1 text-sm text-muted-foreground">Algunos de los que piden menos que otros parecidos.</p>
      <ol className="mt-3">
        {feed.rows.map((row, i) => (
          <li key={`${row.name}-${row.seenAt}`} className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-0.5 border-t py-3">
            <span className="leading-tight font-bold">
              <span className={i === 0 ? "mark" : undefined}>{row.name}</span>
            </span>
            <span className="type-figure row-span-2 text-right text-[17px] leading-tight font-bold">
              {money(row.usd, "USD")}
              <span className="block text-xs font-medium text-muted-foreground line-through [font-stretch:100%]">{money(row.median, "USD")}</span>
            </span>
            <span className="text-[13px] text-muted-foreground">
              {[`${number.format(row.km)} km`, row.where, row.source, feedAgo(row.seenAt, now)].filter(Boolean).join(" · ")}
            </span>
            <span className="col-span-2 mt-1.5 text-[14.5px] leading-snug">
              Pide <b>{money(row.median - row.usd, "USD")} menos</b> que la mediana de {number.format(row.n)} parecidos.
            </span>
            <span className="col-span-2 mt-2">
              <LandingFeedPick model={row.model} label={`Avisame de un ${modelLabel(row.model)} así`} />
            </span>
          </li>
        ))}
      </ol>
      <p className="border-t pt-3 text-[13px] leading-snug text-muted-foreground">
        Comparado con la mediana de autos del mismo modelo, año y caja publicados en el país. Precios en dólares al tipo de cambio del día.
      </p>
    </section>
  );
}

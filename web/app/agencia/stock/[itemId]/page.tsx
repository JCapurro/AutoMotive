import { ArrowLeft } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { ItemPrivateForm, ItemReview } from "@/components/agencia/item-private-form";
import { type ItemFormValues, StockItemForm } from "@/components/agencia/stock-item-form";
import { loadCatalog } from "@/lib/catalog";
import { webConfig } from "@/lib/config";
import {
  daysInStockText,
  demandCount,
  ITEM_STATUS,
  itemSending,
  margin,
  marketBasisText,
  parseDemand,
  parseMarket,
  parseModelDays,
  PRICE_CHECK_TEXT,
  priceCheck,
  priceVsMarketText,
  SUGGESTED_PRICE_NOTE,
  suggestedPrice,
} from "@/lib/dealer-insights";
import { PriceWhyBlock } from "@/components/agencia/price-why";
import { myDealer, priceContexts, stockInsights, whyOf } from "@/lib/dealer-server";
import { money, number, vehicle } from "@/lib/format";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = { title: "Auto" };

/** One car: edit it, its market detail (n, p25, median, p75), demand by level, what was paid and «¿Es este aviso tuyo?». */
export default async function ItemPage({ params }: PageProps<"/agencia/stock/[itemId]">) {
  const dealer = await myDealer();
  if (!dealer) redirect("/agencia");
  const { itemId: raw } = await params;
  if (!/^\d+$/.test(raw)) notFound();
  const itemId = Number(raw);
  const supabase = await createClient();
  const [{ data: item }, { data: priv }, insights, { dealerProgram }, catalog] = await Promise.all([
    supabase.from("dealer_stock_items").select("*").eq("id", itemId).eq("dealer_id", dealer.id).maybeSingle(),
    supabase.from("dealer_item_private").select("purchase_price, purchase_currency, notes").eq("item_id", itemId).maybeSingle(),
    stockInsights(),
    webConfig(),
    loadCatalog(supabase),
  ]);
  if (!item) notFound();
  const insight = insights.find((r) => r.item_id === itemId) ?? null;
  const duplicate = item.sync_state === "review" && item.duplicate_listing_id
    ? await supabase.from("listings").select("title, make, model, year, url, sources(name)").eq("id", item.duplicate_listing_id).maybeSingle().then(({ data }) => data)
    : null;

  const market = parseMarket(insight?.market);
  const why = insight && (item.status === "available" || item.status === "reserved") ? whyOf(insight, await priceContexts()) : null;
  const demand = parseDemand(insight?.demand);
  const check = priceCheck(market);
  const suggested = item.status === "sold" || item.status === "archived" ? null
    : suggestedPrice(market, parseModelDays(insight?.model_days_to_sell), item.currency);
  const own = margin(item.price, item.currency, priv?.purchase_price ?? null, priv?.purchase_currency ?? null, market?.blue);
  // No insight row for an archived car: its stock status, not «Lo estamos cargando».
  const sending = itemSending({ status: item.status, sync_state: item.sync_state, hidden_reason: insight ? insight.hidden_reason : undefined }, dealerProgram.manualConfirmDays);
  const name = vehicle({ make: insight?.make ?? item.make, model: insight?.model ?? item.model, trim: insight?.trim ?? item.trim, year: insight?.year ?? item.year });
  const images = Array.isArray(item.images) ? (item.images as unknown[]).filter((u): u is string => typeof u === "string") : [];
  const initial: ItemFormValues = {
    make: item.make ?? "", model: item.model ?? "", trim: item.trim ?? "", year: item.year ? String(item.year) : "",
    mileageKm: item.mileage_km != null ? String(item.mileage_km) : "", price: item.price != null ? String(item.price) : "",
    currency: item.currency === "USD" ? "USD" : "ARS", transmission: item.transmission === "manual" || item.transmission === "automatic" ? item.transmission : "",
    fuel: item.fuel ?? "", color: item.color ?? "", inStockSince: item.in_stock_since ?? "", title: item.title ?? "",
    description: item.description ?? "", images,
  };

  return (
    <div className="space-y-8">
      <Link href="/agencia/stock" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground hover:underline">
        <ArrowLeft className="size-4" aria-hidden /> Tu stock
      </Link>
      <header className="space-y-1">
        <h1 className="type-heading text-[1.9rem] leading-tight">{name}</h1>
        <p className="text-sm text-muted-foreground">
          {item.status === "archived" || item.status === "sold" ? sending.text : `${ITEM_STATUS[item.status] ?? item.status} · ${sending.text}`}
          {item.listing_id ? <> · <Link href={`/app/listings/${item.listing_id}`} className="underline underline-offset-2">Ver cómo lo ven los compradores</Link></> : null}
        </p>
      </header>

      {item.sync_state === "review" ? (
        <ItemReview
          itemId={itemId}
          duplicate={duplicate ? { title: vehicle(duplicate), source: duplicate.sources?.name ?? "otro sitio", url: duplicate.url?.startsWith("https://") ? duplicate.url : null } : null}
        />
      ) : null}

      <section className="space-y-3">
        <h2 className="type-heading text-[21px] leading-tight">Precio contra el mercado</h2>
        <p className="text-[15px]" data-testid="item-market">
          {priceVsMarketText(market)}
          {check ? <b className="ml-2 font-semibold text-warn">{PRICE_CHECK_TEXT}</b> : null}
        </p>
        {market && market.n > 0 ? (
          <dl className="grid max-w-xl grid-cols-2 gap-x-6 border-t sm:grid-cols-4">
            <Fact label="Comparables">{number(market.n)}</Fact>
            <Fact label="25 % piden menos de">{money(market.p25, "USD")}</Fact>
            <Fact label="Mediana">{money(market.median, "USD")}</Fact>
            <Fact label="25 % piden más de">{money(market.p75, "USD")}</Fact>
          </dl>
        ) : null}
        <p className="text-sm text-muted-foreground">
          {insight?.price_usd ? `Tu precio: ${money(insight.price_usd, "USD")}. ` : ""}
          {marketBasisText(market) ?? "Mismo modelo, año ±1."} Vistos en los últimos 30 días, todas las fuentes; pesos al blue{market?.blue ? ` (${money(market.blue, "ARS")})` : ""}.
        </p>
        {market && market.n > 0 ? (
          <p><Link href={`/agencia/stock/${itemId}/mercado`} className="text-sm font-semibold underline underline-offset-2">Ver el mercado: los {number(market.n)} avisos contra los que se compara</Link></p>
        ) : null}
        <p className="text-sm text-muted-foreground">{daysInStockText(insight?.days_in_stock ?? null, parseModelDays(insight?.model_days_to_sell))}</p>
      </section>

      <PriceWhyBlock why={why} />

      {suggested ? (
        <section className="space-y-2" data-testid="item-suggested">
          <h2 className="type-heading text-[21px] leading-tight">Precio para venderlo en unos 30 días</h2>
          <p className="text-[15px]"><b className="type-figure font-semibold">{suggested.label}</b>{suggested.currency === "ARS" ? <span className="text-muted-foreground"> ({money(suggested.usd, "USD")})</span> : null}</p>
          <p className="text-sm">{suggested.why}</p>
          <p className="text-sm text-muted-foreground">{SUGGESTED_PRICE_NOTE}</p>
        </section>
      ) : null}

      <section className="space-y-3">
        <h2 className="type-heading text-[21px] leading-tight">Cuánta gente lo busca</h2>
        {demand.approved ? (
          <>
            <dl className="grid max-w-xl grid-cols-2 gap-x-6 border-t sm:grid-cols-4" data-testid="item-demand">
              <Fact label="Buscan el modelo">{demandCount(demand.levels.model, demand.min_count)}</Fact>
              <Fact label="Entran en año y precio">{demandCount(demand.levels.fits, demand.min_count)}</Fact>
              <Fact label="En tu zona">{demandCount(demand.levels.zone, demand.min_count)}</Fact>
              <Fact label="Activas en tu zona">{demandCount(demand.levels.active_zone, demand.min_count)}</Fact>
            </dl>
            <p className="text-sm text-muted-foreground">
              Búsquedas guardadas en Ese Auto en los últimos {demand.window_days} días. Con menos de {demand.min_count} personas decimos «pocas». Nunca te mostramos quién busca.
            </p>
          </>
        ) : (
          <p className="text-[15px] text-muted-foreground">La demanda se ve con el plan Pro activo.</p>
        )}
      </section>

      {item.origin !== "sync" ? (
        <section className="space-y-3">
          <h2 className="type-heading text-[21px] leading-tight">Datos del auto</h2>
          <StockItemForm catalog={catalog} dealerId={dealer.id} itemId={itemId} initial={initial} />
        </section>
      ) : (
        <p className="text-sm text-muted-foreground">Este auto viene de tu publicación en otro sitio: sus datos se actualizan solos.</p>
      )}

      <section className="space-y-3">
        <h2 className="type-heading text-[21px] leading-tight">Solo para vos</h2>
        {own ? (
          <p className={own.amount < 0 ? "text-[15px] text-warn" : "text-[15px]"} data-testid="item-margin">
            Margen: <b className="font-semibold">{own.label}</b>
            {(priv?.purchase_currency ?? item.currency) !== item.currency ? <span className="text-sm text-muted-foreground"> · costo pasado al blue del día</span> : null}
          </p>
        ) : priv?.purchase_price != null ? (
          <p className="text-sm text-muted-foreground">Cargá el precio de venta para ver el margen.</p>
        ) : null}
        <ItemPrivateForm
          itemId={itemId}
          initial={{
            purchasePrice: priv?.purchase_price != null ? String(priv.purchase_price) : "",
            purchaseCurrency: priv?.purchase_currency === "ARS" || priv?.purchase_currency === "USD" ? priv.purchase_currency : "",
            notes: priv?.notes ?? "",
          }}
        />
      </section>
    </div>
  );
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0 border-b py-3">
      <dt className="text-[13px] text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 font-semibold">{children}</dd>
    </div>
  );
}

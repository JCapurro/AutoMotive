import { createElement, type ComponentProps } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/app/searches/7",
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/app/app/searches/actions", () => ({ saveSearch: vi.fn() }));
vi.mock("@/app/app/searches/margin-actions", () => ({ trackMarginSort: vi.fn() }));

import { OPPORTUNITY_TITLE } from "@/components/app/opportunity-threshold";
import { ProLockedSwitch } from "@/components/app/pro-locked";
import { SearchForm } from "@/components/app/search-form";
import { SortSelect } from "@/components/app/sort-select";
import { MARGIN, PRO_LOCKED, SELLER_STRICT } from "@/lib/copy";
import { SearchInput } from "@/lib/search-form";
import { sortsFor } from "@/lib/sorts";

/** Juan, 02/11: Pro's settings in view on the other plans, locked, with the way to the plans (lib/pro.ts proLocked). */
const v = (raw: SearchInput) => SearchInput.parse({ make: "Ford", model: "Fiesta", sources: ["mercadolibre"], ...raw });
// With the model-less search, whose upsell has its own «Ver planes».
const form = (props: Partial<ComponentProps<typeof SearchForm>>, raw: SearchInput = {}) => renderToStaticMarkup(createElement(SearchForm, {
  catalog: [], sources: [{ id: "mercadolibre", name: "MercadoLibre" }], profileId: 7, modelLessSearch: true, initial: v(raw), ...props,
}));
const all = { opportunity: true, margin: true, seller: true };

describe("the search form without Pro", () => {
  it("both instant alerts locked, with what they do and the plans", () => {
    const html = form({ lockedPro: all });
    expect(html).toContain('data-testid="opportunity-threshold-locked"');
    expect(html).toContain('data-testid="margin-threshold-locked"');
    expect(html).toContain(PRO_LOCKED.opportunity);
    expect(html).toContain(PRO_LOCKED.margin);
    expect(html.match(/href="\/app\/pro"/g)).toHaveLength(2);
    expect(html).not.toContain('type="range"');                       // nothing to set
  });

  it("the strict seller check, locked, once a type is chosen (as Pro sees it)", () => {
    expect(form({ lockedPro: all })).not.toContain("seller-strict-locked");
    const html = form({ lockedPro: all }, { seller_type: "private" });
    expect(html).toContain('data-testid="seller-strict-locked"');
    expect(html).toContain(SELLER_STRICT.check);
    expect(html).toContain(PRO_LOCKED.seller);
    expect(html).not.toContain('data-testid="seller-strict"');
  });

  it("a stored strict filter keeps its own note, not the lock", () => {
    const html = form({ lockedPro: all }, { seller_type: "private", seller_strict: true });
    expect(html).toContain(SELLER_STRICT.proOnly);
    expect(html).not.toContain("seller-strict-locked");
  });

  it("only what it's told: nothing by default, and Pro gets the real controls", () => {
    expect(form({}, { seller_type: "private" })).not.toContain(PRO_LOCKED.cta);
    const pro = form({ lockedPro: all, thresholdAlerts: true, sellerFilter: true, marginThreshold: { minThresholdUsd: 500 } }, { seller_type: "private" });
    expect(pro).not.toContain(PRO_LOCKED.cta);
    expect(pro).toContain('data-testid="seller-strict"');
  });
});

describe("ProLockedSwitch", () => {
  it("off and disabled, named by its setting, with the tag and the plans", () => {
    const html = renderToStaticMarkup(createElement(ProLockedSwitch, { id: "x", title: MARGIN.thresholdTitle, text: PRO_LOCKED.margin }));
    expect(html).toMatch(/^<fieldset disabled=""/);
    expect(html).toContain(`role="switch" aria-checked="false" aria-label="${MARGIN.thresholdTitle}" aria-describedby="x-hint"`);
    expect(html).toContain('<p id="x-hint"');
    expect(html).toContain(`>${PRO_LOCKED.badge}</span>`);
    expect(html).toMatch(/<span class="whitespace-nowrap">estimado <span[^>]*>Pro<\/span><\/span>/);   // with the last word
    expect(html).toContain(`href="/app/pro"`);
    expect(renderToStaticMarkup(createElement(ProLockedSwitch, { id: "y", title: OPPORTUNITY_TITLE, text: PRO_LOCKED.opportunity })))
      .toContain(`aria-label="${OPPORTUNITY_TITLE}"`);
  });
});

describe("the order", () => {
  const select = (props: Partial<ComponentProps<typeof SortSelect>>) => renderToStaticMarkup(createElement(SortSelect, { value: "score", ...props }));
  it("«Mayor margen estimado» in view and disabled without Pro", () => {
    expect(select({ locked: ["margin"] })).toMatch(/<option[^>]* value="margin" disabled="">Mayor margen estimado \(Pro\)<\/option>/);
    expect(select({})).not.toContain('value="margin"');
  });
  it("Pro picks it as any other", () => {
    const html = select({ options: sortsFor(true), locked: ["margin"] });
    expect(html).toContain(">Mayor margen estimado</option>");
    expect(html).not.toContain("(Pro)");
  });
});

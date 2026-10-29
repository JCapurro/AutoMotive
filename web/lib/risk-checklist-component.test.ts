import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/app/app/listings/actions", () => ({ trackRiskChecklist: vi.fn() }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { RiskChecklist } from "@/components/app/risk-checklist";
import { CHECKLIST_ITEMS, RISK_EMPHASIS, RISK_HEADER, type RiskConfig, riskConfig } from "@/lib/risk-checklist";

function render(config: RiskConfig, emphasized = false) {
  return renderToStaticMarkup(createElement(RiskChecklist, { listingId: 42, title: "Ford Fiesta Titanium 2017", config, emphasized }));
}
const anchors = (html: string) => html.match(/<a\b[^>]*>/g) ?? [];

describe("RiskChecklist (PAR-02)", () => {
  it("without links: header, the seven items, no <a>, closed", () => {
    const html = render(riskConfig(undefined));
    expect(html).toContain(RISK_HEADER);
    for (const item of CHECKLIST_ITEMS) expect(html).toContain(item.text);
    expect(anchors(html)).toEqual([]);
    expect(html).toMatch(/<details(?![^>]*\bopen\b)[^>]*data-testid="risk-checklist"/);
    expect(html).not.toContain(RISK_EMPHASIS);
    expect(html).toContain("Copiar checklist");
  });

  it("with links: «Ver sitio oficial» only where loaded, in a new tab, and the jurisdictions as sublists", () => {
    const html = render(
      riskConfig({
        links: {
          dnrpa: { label: "DNRPA", url: "https://dnrpa.example.test/" },
          patentes: [{ label: "CABA", url: "https://patentes.example.test/caba" }],
          infracciones: [{ label: "PBA", url: "https://infracciones.example.test/pba" }],
        },
      }),
    );
    const links = anchors(html);
    expect(links).toHaveLength(3);
    for (const a of links) {
      expect(a).toContain('target="_blank"');
      expect(a).toContain('rel="noopener noreferrer"');
    }
    expect(html.match(/Ver sitio oficial/g)).toHaveLength(1);
    expect(html).toContain("Patentes");
    expect(html).toContain("Infracciones");
    expect(html).toContain(">CABA<");
    expect(html).toContain(">PBA<");
  });

  it("with emphasis: open and with the emphasis line", () => {
    const html = render(riskConfig(undefined), true);
    expect(html).toMatch(/<details[^>]*\bopen=""[^>]*data-testid="risk-checklist"|<details[^>]*data-testid="risk-checklist"[^>]*\bopen=""/);
    expect(html).toContain(RISK_EMPHASIS);
  });

  it("never renders a link that is not https, even if one reaches it", () => {
    const config: RiskConfig = {
      checklistEnabled: true,
      links: {
        dnrpa: { label: "x", url: "javascript:alert(1)" },
        patentes: [{ label: "y", url: "http://example.test/" }],
        infracciones: [],
        vtv: null,
        form_08: null,
      },
    };
    const html = render(config);
    expect(anchors(html)).toEqual([]);
    expect(html).not.toContain("javascript:");
  });
});

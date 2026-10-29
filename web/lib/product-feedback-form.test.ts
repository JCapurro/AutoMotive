import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";
vi.mock("@/app/app/feedback/actions", () => ({ submitProductFeedback: vi.fn() }));

import { ProductFeedback } from "@/components/app/product-feedback";

it("keeps feedback in the page, with a bounded message and no extra email request", () => {
  const html = renderToStaticMarkup(createElement(ProductFeedback, { profileId: 12, onBack: vi.fn() }));
  expect(html).toContain("Tu comentario");
  expect(html).toContain('<textarea');
  expect(html).toContain('maxLength="2000"');
  expect(html).toContain("Enviar feedback");
  expect(html).toContain("Volver a los planes");
  expect(html).not.toContain('type="email"');
  expect(html).not.toContain('mailto:');
});

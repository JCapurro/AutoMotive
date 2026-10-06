import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";

vi.mock("@/lib/auth", () => ({ requireUser: vi.fn().mockResolvedValue({ id: "user" }) }));
vi.mock("@/lib/supabase/server", () => ({ createClient: async () => ({}) }));
vi.mock("@/app/app/searches/form-data", () => ({
  loadFormData: async () => ({ catalog: [], sources: [], defaultFrequency: "daily" }),
}));
vi.mock("@/components/app/search-form", () => ({ SearchForm: () => null }));
vi.mock("@/components/app/assisted-search", () => ({
  AssistedSearch: ({ initialText }: { initialText: string }) => createElement("textarea", { defaultValue: initialText }),
}));

import NewSearchPage from "@/app/app/searches/new/page";

it("hands the landing prompt to the assisted flow after authentication", async () => {
  const html = renderToStaticMarkup(await NewSearchPage({
    params: Promise.resolve({}), searchParams: Promise.resolve({ prompt: "Fiesta manual en Córdoba" }),
  }));
  expect(html).toContain("Fiesta manual en Córdoba");
});

it("keeps the empty assisted form for a visit without a prompt", async () => {
  const html = renderToStaticMarkup(await NewSearchPage({ params: Promise.resolve({}), searchParams: Promise.resolve({}) }));
  expect(html).toContain("<textarea></textarea>");
});

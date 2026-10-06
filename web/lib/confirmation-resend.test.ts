import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, expect, it, vi } from "vitest";
const hooks = vi.hoisted(() => ({ states: [] as unknown[] }));
vi.mock("react", async (original) => ({
  ...await original<typeof import("react")>(),
  useActionState: () => [hooks.states.shift(), () => {}, false],
  useEffect: () => {},
}));
vi.mock("@/app/login/actions", () => ({ authenticate: vi.fn(), resendConfirmation: vi.fn(), signInWithGoogle: vi.fn() }));
import { LoginForm } from "@/app/login/login-form";
beforeEach(() => { hooks.states = [{ next: "/app" }, { next: "/app" }, { next: "/app" }]; });
it("lets visitors request confirmation after an expired link without signing up again", () => {
  const html = renderToStaticMarkup(createElement(LoginForm, { next: "/app", mode: "login", linkError: true }));
  expect(html).toContain("Reenviar confirmación");
  expect(html).toContain("Email para reenviar la confirmación");
  expect(html).toContain("ya confirmaste tu cuenta");
});
it("lets users correct the recipient while waiting for a confirmation", () => {
  hooks.states = [{ next: "/app", email: "person@example.com", sent: true }, { next: "/app" }, { next: "/app" }];
  const html = renderToStaticMarkup(createElement(LoginForm, { next: "/app", mode: "signup", linkError: false }));
  expect(html).toContain('id="confirmation-email"');
  expect(html).not.toContain('type="hidden" name="email"');
});

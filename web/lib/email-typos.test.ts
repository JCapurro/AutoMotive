import { expect, it } from "vitest";

import { emailSuggestion } from "@/lib/email-typos";
import { isInAppBrowser } from "@/lib/in-app-browser";

it.each([
  ["juan@gmial.com", "juan@gmail.com"],
  ["juan@gmail.com.ar", "juan@gmail.com"],
  ["Juan@Gmail.con", "juan@gmail.com"],
  ["ana@hotmial.com", "ana@hotmail.com"],
  ["ana@hotmail.com.ra", "ana@hotmail.com.ar"],
  ["ana@outlok.com", "ana@outlook.com"],
  ["ana@yahooo.com.ar", "ana@yahoo.com.ar"],
  ["juan@gmali.com", "juan@gmail.com"],
  ["juan@gmail.cmo", "juan@gmail.com"],
  ["ana@hotamil.com", "ana@hotmail.com"],
])("suggests %s → %s", (typed, fixed) => {
  expect(emailSuggestion(typed)).toBe(fixed);
});

it.each(["juan@gmail.com", "ana@hotmail.com.ar", "ana@ymail.com", "ana@mail.com", "ana@yahoo.com.br", "ana@hotmail.com.", "ana@empresa.com.ar", "juan@", "juan", ""])(
  "leaves %j alone",
  (typed) => expect(emailSuggestion(typed)).toBeNull(),
);

it("spots the in-app browsers where Google refuses to sign in", () => {
  expect(isInAppBrowser("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Instagram 300.0")).toBe(true);
  expect(isInAppBrowser("Mozilla/5.0 (Linux; Android 14; wv) [FB_IAB/FB4A;FBAV/450.0]")).toBe(true);
  expect(isInAppBrowser("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0 Safari/537.36")).toBe(false);
  expect(isInAppBrowser(null)).toBe(false);
});

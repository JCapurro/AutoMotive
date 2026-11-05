/**
 * Argentine mobile numbers, stored in E.164 as mobiles are dialed: +54 9 + area code
 * + number, 10 digits after the 9 (profiles.phone). People type them every
 * way: with +54, with the 9 or without, with the 0 of the area code, with the
 * 15 after it, with spaces and dashes.
 */
export function normalizeArPhone(raw: string): string | null {
  let digits = String(raw ?? "").replace(/\D/g, "");
  if (digits.startsWith("00")) digits = digits.slice(2);
  if (digits.startsWith("54") && digits.length >= 12) {
    digits = digits.slice(2);
    if (digits.startsWith("9")) digits = digits.slice(1);
  }
  if (digits.startsWith("0")) digits = digits.slice(1);
  // «11 15 1234-5678»: the 15 goes after a 2-, 3- or 4-digit area code.
  if (digits.length === 12) {
    const at = [2, 3, 4].find((i) => digits.slice(i, i + 2) === "15");
    if (at === undefined) return null;
    digits = digits.slice(0, at) + digits.slice(at + 2);
  }
  // Area codes start with 1 (Buenos Aires), 2 or 3.
  if (!/^[1-3]\d{9}$/.test(digits)) return null;
  return `+549${digits}`;
}

/** «+54 9 11 1234-5678» for people; the stored value stays in E.164. */
export function formatArPhone(phone: string | null | undefined): string {
  const match = /^\+549(\d{10})$/.exec(phone ?? "");
  if (!match) return phone ?? "";
  const national = match[1];
  // Buenos Aires keeps the 11; the rest of the country, shown with the first 3 digits as area code.
  const area = national.startsWith("11") ? 2 : 3;
  const rest = national.slice(area);
  return `+54 9 ${national.slice(0, area)} ${rest.slice(0, rest.length - 4)}-${rest.slice(-4)}`;
}

export const PHONE_ERROR = "Ese celular no parece válido. Escribilo con el código de área, por ejemplo 11 2345-6789.";

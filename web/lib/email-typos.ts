/**
 * A non-blocking "¿Quisiste decir…?" for the free search's email: nobody
 * confirms it, so a typo means alerts that never arrive. Common Argentine
 * providers only; an unknown domain is left alone.
 */
const DOMAINS = ["gmail.com", "hotmail.com", "hotmail.com.ar", "outlook.com", "outlook.com.ar", "yahoo.com", "yahoo.com.ar", "live.com", "live.com.ar", "icloud.com"];

/** Real domains one edit away from a common one: never "correct" them. */
const REAL = [
  "mail.com", "ymail.com", "email.com", "gmx.com", "live.cl", "outlook.es", "hotmail.es", "yahoo.es",
  "yahoo.com.br", "hotmail.com.br", "outlook.com.br", "live.com.br", "yahoo.com.mx", "hotmail.com.mx", "outlook.com.mx",
];

const KNOWN: Record<string, string> = {
  "gmail.com.ar": "gmail.com",
  "gmail.co": "gmail.com",
  "gmail.con": "gmail.com",
  "gmail.cm": "gmail.com",
  "gmial.com": "gmail.com",
  "gmal.com": "gmail.com",
  "gamil.com": "gmail.com",
  "gmai.com": "gmail.com",
  "gnail.com": "gmail.com",
  "hotmial.com": "hotmail.com",
  "hotmal.com": "hotmail.com",
  "hotmai.com": "hotmail.com",
  "hotmail.con": "hotmail.com",
  "hotmail.co": "hotmail.com",
  "hotmail.com.ra": "hotmail.com.ar",
  "yahoo.con": "yahoo.com",
  "yaho.com": "yahoo.com",
  "yahoo.com.ra": "yahoo.com.ar",
  "outlok.com": "outlook.com",
  "outloo.com": "outlook.com",
  "icloud.con": "icloud.com",
};

/** The corrected address, or null when the domain looks right or unknown ("hotmail.com." is still being typed). */
export function emailSuggestion(value: string): string | null {
  const email = value.trim().toLowerCase();
  const at = email.lastIndexOf("@");
  if (at < 1 || at === email.length - 1) return null;
  const [user, domain] = [email.slice(0, at), email.slice(at + 1)];
  if (domain.endsWith(".") || DOMAINS.includes(domain) || REAL.includes(domain)) return null;
  const fixed = KNOWN[domain] ?? DOMAINS.find((known) => distance(domain, known) === 1);
  return fixed ? `${user}@${fixed}` : null;
}

/** Damerau-Levenshtein distance (a swap of two neighbours is one edit), cut short past 1. */
function distance(a: string, b: string): number {
  if (Math.abs(a.length - b.length) > 1) return 2;
  const rows = Array.from({ length: a.length + 1 }, (_, i) => Array.from({ length: b.length + 1 }, (_, j) => (i === 0 ? j : j === 0 ? i : 0)));
  for (let i = 1; i <= a.length; i++) {
    for (let j = 1; j <= b.length; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      rows[i][j] = Math.min(rows[i - 1][j] + 1, rows[i][j - 1] + 1, rows[i - 1][j - 1] + cost);
      if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) rows[i][j] = Math.min(rows[i][j], rows[i - 2][j - 2] + 1);
    }
  }
  return rows[a.length][b.length];
}

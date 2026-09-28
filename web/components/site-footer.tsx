import Link from "next/link";

/** Public pages' footer: who we are and the legal links (F7, punto 7). */
export function SiteFooter() {
  return (
    <footer className="border-t">
      <div className="mx-auto flex w-full max-w-5xl flex-wrap items-center justify-between gap-2 px-4 py-6 text-xs text-muted-foreground">
        <span>Automotive · Argentina</span>
        <span>Comparamos precios publicados contra publicaciones comparables del mercado observado.</span>
        <nav className="flex gap-4">
          <Link href="/privacidad" className="hover:underline">
            Privacidad
          </Link>
          <Link href="/terminos" className="hover:underline">
            Términos
          </Link>
        </nav>
      </div>
    </footer>
  );
}

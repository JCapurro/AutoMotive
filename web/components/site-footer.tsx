import Link from "next/link";

/** Public pages' footer: who we are and the legal links (F7, punto 7). */
export function SiteFooter() {
  return (
    <footer className="border-t">
      <div className="mx-auto flex w-full max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-6 text-sm text-muted-foreground sm:px-6 lg:px-10">
        <span>eseauto.com.ar · Argentina</span>
        <span className="basis-full sm:basis-auto">
          Comparamos precios publicados contra publicaciones comparables del mercado observado.
        </span>
        <nav className="flex gap-5 sm:ml-auto">
          <Link href="/privacidad" className="underline-offset-4 hover:underline">
            Privacidad
          </Link>
          <Link href="/terminos" className="underline-offset-4 hover:underline">
            Términos
          </Link>
        </nav>
      </div>
    </footer>
  );
}

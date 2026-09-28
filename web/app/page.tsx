import { BellRing, Clock, SearchCheck, TrendingDown } from "lucide-react";
import Link from "next/link";

import { Logo } from "@/components/logo";
import { SiteFooter } from "@/components/site-footer";
import { Button } from "@/components/ui/button";
import { currentUser } from "@/lib/auth";

// §50: hero, example card, the four benefits and the "Crear mi búsqueda" CTA.
const BENEFITS = [
  { icon: Clock, title: "No busques todo el día.", text: "Automotive monitorea por vos." },
  {
    icon: SearchCheck,
    title: "No revises cientos de publicaciones.",
    text: "Filtramos según lo que realmente buscás.",
  },
  {
    icon: TrendingDown,
    title: "Detectá oportunidades.",
    text: "Comparamos cada publicación contra vehículos similares.",
  },
  { icon: BellRing, title: "Llegá temprano.", text: "Recibí la alerta cuando aparece." },
];

export default async function Landing({ searchParams }: PageProps<"/">) {
  const [user, params] = await Promise.all([currentUser(), searchParams]);
  const start = user ? "/app/searches/new" : "/login?next=/app/searches/new";

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="mx-auto flex w-full max-w-5xl items-center justify-between px-4 py-4">
        <Logo />
        <Button asChild variant="ghost" size="sm">
          <Link href={user ? "/app" : "/login"}>{user ? "Mis búsquedas" : "Ingresar"}</Link>
        </Button>
      </header>

      <main className="flex-1">
        {params.cuenta === "borrada" ? (
          <p role="status" className="mx-auto w-full max-w-5xl px-4 text-sm text-muted-foreground">
            Borramos tu cuenta y todos tus datos.
          </p>
        ) : null}
        <section className="mx-auto grid w-full max-w-5xl items-center gap-10 px-4 pt-8 pb-16 md:grid-cols-[1.1fr_1fr] md:pt-16">
          <div className="space-y-6">
            <h1 className="text-4xl font-semibold tracking-tight text-balance md:text-5xl">
              Encontrá las oportunidades antes que los demás.
            </h1>
            <div className="space-y-2 text-lg text-muted-foreground">
              <p>Decinos qué auto estás buscando.</p>
              <p>
                Automotive monitorea las publicaciones y te avisa cuando aparece uno que vale la pena mirar.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <Button asChild size="lg" className="h-11 px-5 text-base">
                <Link href={start}>Crear mi búsqueda</Link>
              </Button>
              <span className="text-sm text-muted-foreground">Gratis durante el piloto.</span>
            </div>
          </div>
          <ExampleAlert />
        </section>

        <section className="border-t bg-muted/40">
          <div className="mx-auto grid w-full max-w-5xl gap-4 px-4 py-14 sm:grid-cols-2 lg:grid-cols-4">
            {BENEFITS.map(({ icon: Icon, title, text }) => (
              <div key={title} className="space-y-2 rounded-xl bg-background p-5 ring-1 ring-foreground/10">
                <Icon className="size-5 text-muted-foreground" aria-hidden />
                <p className="font-medium">{title}</p>
                <p className="text-sm text-muted-foreground">{text}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="mx-auto w-full max-w-5xl space-y-4 px-4 py-16 text-center">
          <h2 className="text-2xl font-semibold tracking-tight">Vos elegís qué auto querés. Automotive busca por vos.</h2>
          <Button asChild size="lg" className="h-11 px-5 text-base">
            <Link href={start}>Crear mi búsqueda</Link>
          </Button>
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}

/** The §50 example: what an opportunity alert looks like. */
function ExampleAlert() {
  return (
    <figure
      aria-label="Ejemplo de alerta"
      className="mx-auto w-full max-w-sm rounded-2xl bg-card p-5 shadow-sm ring-1 ring-foreground/10"
    >
      <p className="text-sm font-medium text-orange-700">🔥 Nueva oportunidad</p>
      <p className="mt-2 text-lg font-semibold">Ford Fiesta Titanium 2017</p>
      <dl className="mt-3 grid grid-cols-2 gap-y-1 text-sm">
        <dt className="text-muted-foreground">Kilometraje</dt>
        <dd className="text-right">112.000 km</dd>
        <dt className="text-muted-foreground">Precio publicado</dt>
        <dd className="text-right font-medium">USD 10.300</dd>
      </dl>
      <div className="mt-4 flex items-end justify-between">
        <div>
          <p className="text-3xl font-semibold tabular-nums">
            88<span className="text-base font-normal text-muted-foreground"> / 100</span>
          </p>
          <p className="text-xs text-muted-foreground">Opportunity Score</p>
        </div>
        <p className="max-w-[55%] text-right text-sm">8% debajo de publicaciones comparables.</p>
      </div>
      <figcaption className="mt-4 border-t pt-3 text-xs text-muted-foreground">Publicado hace 4 minutos.</figcaption>
    </figure>
  );
}

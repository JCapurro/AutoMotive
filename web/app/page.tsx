import Link from "next/link";

import { Logo } from "@/components/logo";
import { SiteFooter } from "@/components/site-footer";
import { Button } from "@/components/ui/button";
import { currentUser } from "@/lib/auth";
import { money } from "@/lib/format";
import { webConfig } from "@/lib/config";
import { PLAN_COPY, planPrice, WAITLIST_PLANS } from "@/lib/pro";

// §50: hero, an example of what we flag, how it works, the four benefits and
// the "Crear mi búsqueda" CTA. No chart to decode: a price list read with a
// highlighter, the way anyone reads a price guide.
const EXAMPLE = [
  { name: "Ford Focus 2.0 Trend 2014", km: "105.420 km", usd: 6949 },
  { name: "Ford Focus S 2014", km: "86.000 km", usd: 9523 },
  { name: "Ford Focus S 2015", km: "81.049 km", usd: 9723 },
  { name: "Ford Focus SE Plus 2016", km: "113.759 km", usd: 9994 },
  { name: "Ford Focus S 2016", km: "84.007 km", usd: 10258 },
];

const STEPS = [
  {
    title: "Decinos qué auto buscás.",
    text: "Marca, modelo, años, presupuesto y zona.",
    example: <Chips items={["Ford Focus", "2014 a 2017", "hasta 120.000 km", "AMBA"]} label="Ejemplo de búsqueda" />,
  },
  {
    title: "Revisamos las publicaciones por vos.",
    text: "Seguimos las fuentes disponibles y comparamos cada auto con otros parecidos. La frecuencia depende de cada portal.",
    example: <Chips items={["MercadoLibre", "Facebook Marketplace", "Kavak", "V6", "Autocosmos"]} label="Fuentes" />,
  },
  {
    title: "Te avisamos cuando aparece uno que vale la pena mirar.",
    text: "Por Telegram o email, con el precio comparado y las preguntas para hacerle al vendedor.",
    example: (
      <p className="inline-block rounded-md bg-muted px-3.5 py-3 text-[15px] leading-snug">
        <span className="block text-[13px] text-muted-foreground">Nueva oportunidad</span>
        <span className="mark">Ford Focus 2.0 Trend 2014, USD 6.949</span>
      </p>
    ),
  },
];

const BENEFITS = [
  { title: "No busques todo el día.", text: "Ese Auto monitorea por vos." },
  { title: "No revises cientos de publicaciones.", text: "Filtramos según lo que realmente buscás." },
  { title: "Detectá oportunidades.", text: "Comparamos cada publicación contra vehículos similares." },
  { title: "Llegá temprano.", text: "Recibí la alerta cuando aparece." },
];

const WRAP = "mx-auto w-full max-w-6xl px-4 sm:px-6 lg:px-10";

export default async function Landing({ searchParams }: PageProps<"/">) {
  const [user, params, cfg] = await Promise.all([currentUser(), searchParams, webConfig()]);
  const start = user ? "/app/searches/new" : "/login?next=/app/searches/new";

  return (
    <div className="flex min-h-dvh flex-col">
      <header className={`${WRAP} flex h-17 items-center justify-between`}>
        <Logo />
        <Link href={user ? "/app" : "/login"} className="px-1 py-2 text-[15px] font-medium underline-offset-4 hover:underline">
          {user ? "Mis búsquedas" : "Ingresar"}
        </Link>
      </header>

      <main className="flex-1">
        {params.cuenta === "borrada" ? (
          <p role="status" className={`${WRAP} text-sm text-muted-foreground`}>
            Borramos tu cuenta y todos tus datos.
          </p>
        ) : null}

        <section className={`${WRAP} pt-8 pb-14 md:pt-16`}>
          <h1 className="type-display max-w-[27ch] text-[2.4rem] leading-[1.02] text-balance md:text-[4.2rem] lg:text-[4.6rem]">
            Decinos cuál. Te avisamos cuando aparezca.
          </h1>
          <div className="mt-8 grid items-start gap-10 md:mt-12 md:grid-cols-[4fr_8fr] md:gap-14">
            <div>
              <div className="max-w-[34ch] space-y-2 text-[19px] leading-snug text-muted-foreground">
                <p>Decinos qué auto estás buscando.</p>
                <p>Ese Auto monitorea las publicaciones y te avisa cuando aparece uno que vale la pena mirar.</p>
              </div>
              <div className="mt-7 flex flex-wrap items-center gap-x-4 gap-y-3">
                <Button asChild className="h-11 px-4.5 text-[15px]">
                  <Link href={start}>Crear mi búsqueda</Link>
                </Button>
                <span className="text-sm text-muted-foreground">Prueba gratis por 3 días. Sin tarjeta.</span>
              </div>
            </div>
            <Example />
          </div>
        </section>

        <section className="border-t py-16">
          <div className={WRAP}>
            <h2 className="type-heading text-[1.75rem] leading-tight md:text-4xl">Cómo funciona</h2>
            <ol className="mt-8 border-t-2 border-foreground">
              {STEPS.map((step, i) => (
                <li
                  key={step.title}
                  className="grid grid-cols-[44px_minmax(0,1fr)] gap-x-4.5 gap-y-1.5 border-b py-5.5 md:grid-cols-[64px_minmax(0,5fr)_minmax(0,4fr)] md:gap-x-7"
                >
                  <span aria-hidden className="type-display row-span-3 text-4xl leading-none md:row-span-2 md:text-[44px]">
                    {i + 1}
                  </span>
                  <h3 className="text-xl leading-snug font-bold">{step.title}</h3>
                  <p className="max-w-[52ch] text-muted-foreground">{step.text}</p>
                  <div className="mt-1.5 md:col-start-3 md:row-span-2 md:row-start-1 md:mt-0.5">{step.example}</div>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section className="border-t py-16">
          <div className={WRAP}>
            <h2 className="type-heading max-w-[22ch] text-[1.75rem] leading-tight text-balance md:text-4xl">
              Lo que hacemos mientras hacés otra cosa.
            </h2>
            <dl className="mt-8 grid md:grid-cols-2 md:gap-x-12">
              {BENEFITS.map((b) => (
                <div key={b.title} className="space-y-1 border-b py-4.5">
                  <dt className="text-lg font-bold">{b.title}</dt>
                  <dd className="text-muted-foreground">{b.text}</dd>
                </div>
              ))}
            </dl>
          </div>
        </section>

        <section id="planes" className="border-t py-16">
          <div className={WRAP}>
            <h2 className="type-heading text-[1.75rem] leading-tight md:text-4xl">Un plan para tu forma de buscar</h2>
            <p className="mt-3 max-w-3xl text-muted-foreground">Empezá con una búsqueda gratis por 72 horas desde su primera activación.
              Incluye hasta 50 resultados y resumen diario. Pausar o reemplazarla no reinicia la prueba.</p>
            <div className="mt-8 grid gap-6 md:grid-cols-2">
              {WAITLIST_PLANS.map((plan) => <article key={plan} className="rounded-xl border p-6">
                <h3 className="text-xl font-bold">{PLAN_COPY[plan].name}</h3>
                <p className="mt-3 text-3xl font-bold">{planPrice(cfg.proOffer[plan].amount)} <span className="text-base font-normal">{PLAN_COPY[plan].period}</span></p>
                <p className="mt-2 text-muted-foreground">{PLAN_COPY[plan].pitch}</p>
                <p className="mt-3">{PLAN_COPY[plan].searches} búsquedas activas · una cuenta · pesos argentinos.</p>
                <p className="mt-2 text-sm text-muted-foreground">{plan === "pass_30" ? "Pago único, sin renovación automática." : "Durante el piloto: períodos de 30 días y renovación manual, sin débito automático."}</p>
                <Button asChild variant="outline" className="mt-5"><Link href={user ? `/app/pro?plan=${plan}` : `/login?next=${encodeURIComponent(`/app/pro?plan=${plan}`)}`}>
                  {plan === "pass_30" ? "Busco mi auto" : "Busco vehículos habitualmente"}
                </Link></Button>
              </article>)}
            </div>
            <p className="mt-5 text-sm text-muted-foreground">{cfg.commercialPilot ? "Las altas y la confirmación de pagos se coordinan con la administración." : "Las altas pagas están en lista de espera."}
              {" "}Al vencer el acceso se detienen nuevas coincidencias y alertas; conservamos historial y favoritos.
              Hasta 10 avisos inmediatos de nuevas coincidencias por día; los restantes van al resumen.
              Bajas de precio de favoritos: avisos inmediatos mientras el acceso siga vigente.</p>
          </div>
        </section>

        <section className="border-t pt-18 pb-22">
          <div className={WRAP}>
            <h2 className="type-display max-w-[20ch] text-[1.9rem] leading-[1.05] md:text-[2.8rem]">
              Vos elegís qué auto querés. Ese Auto busca por vos.
            </h2>
            <Button asChild className="mt-7 h-11 px-4.5 text-[15px]">
              <Link href={start}>Crear mi búsqueda</Link>
            </Button>
          </div>
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}

/** The example: a week of one model, cheapest first, the one we flag marked. */
function Example() {
  const [first, second] = EXAMPLE;
  return (
    <figure aria-label="Ejemplo de una oportunidad" className="rounded-[10px] bg-muted px-4 pt-5 pb-4.5 sm:px-6.5">
      <figcaption>
        <span className="block text-[17px] font-bold">Ejemplo: Ford Focus con caja manual en el AMBA</span>
        <span className="mt-0.5 block text-sm text-muted-foreground">Publicados en una semana, del más barato al más caro.</span>
      </figcaption>
      <ol className="mt-3">
        {EXAMPLE.map((row, i) => (
          <li
            key={row.name}
            className={
              i === 0
                ? "mark-row draw -mx-2.5 grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 px-2.5 py-2.5"
                : "-mx-2.5 grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 border-t px-2.5 py-2.5"
            }
          >
            <span className="min-w-0 leading-tight font-semibold">
              {row.name}
              <span className="mt-0.5 block text-[13px] font-normal text-muted-foreground">{row.km}</span>
            </span>
            <span className="type-figure text-right text-[17px] leading-tight font-bold">
              {money(row.usd, "USD")}
              {i === 0 ? <span className="block text-xs font-medium [font-stretch:100%]">Alta oportunidad</span> : null}
            </span>
          </li>
        ))}
      </ol>
      <p className="mt-3 border-t pt-3 text-[15px] leading-snug">
        Te avisamos del primero: <b>pide {money(second.usd - first.usd, "USD")} menos</b> que el que le sigue.
      </p>
    </figure>
  );
}

function Chips({ items, label }: { items: string[]; label: string }) {
  return (
    <ul aria-label={label} className="flex flex-wrap gap-1.5">
      {items.map((item) => (
        <li key={item} className="rounded bg-muted px-2.5 py-1 text-sm [font-stretch:92%]">
          {item}
        </li>
      ))}
    </ul>
  );
}

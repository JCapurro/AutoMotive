/**
 * GEO · the landing's structured data: who Ese Auto is (Organization), the
 * site (WebSite), what it does (Service) and the questions people ask before
 * signing up (FAQPage, the same text the landing shows). Pure: the landing
 * renders it into <script type="application/ld+json">.
 */
import { SITE_NAME } from "@/lib/guides";

/**
 * The landing's «Preguntas frecuentes», shown as they stand and repeated in
 * the FAQPage. Only what the landing already says elsewhere: no prices (they
 * live in the plans), no promise about a particular car.
 */
export const HOME_FAQ: { q: string; a: string }[] = [
  {
    q: "¿Qué es Ese Auto?",
    a: "Un servicio argentino para quien busca un auto usado. Nos decís qué auto querés (marca, modelo, años, presupuesto y zona) y te avisamos cuando aparece publicado uno que coincide.",
  },
  {
    q: "¿De dónde salen los autos?",
    a: "De las publicaciones de MercadoLibre, Facebook Marketplace, Kavak, V6 y Autocosmos. Cada cuánto revisamos cada portal depende del portal.",
  },
  {
    q: "¿Cómo me avisan?",
    a: "Por email, con el link a la publicación, su precio comparado con publicaciones parecidas y preguntas para hacerle al vendedor.",
  },
  {
    q: "¿Cómo saben si un precio es bueno?",
    a: "Comparamos cada publicación contra publicaciones comparables del mercado que observamos. Es una referencia para decidir qué mirar primero.",
  },
  {
    q: "¿Es gratis?",
    a: "Podés probar gratis por 3 días. Después elegís un plan según cuántas búsquedas querés seguir.",
  },
  {
    q: "¿Ese Auto vende autos o revisa los autos?",
    a: "No. No vendemos autos ni revisamos ninguno en particular: te avisamos de publicaciones de otros sitios y el contacto es directo con quien publica. Antes de comprar, conviene que lo revise un mecánico de confianza. Para saber qué mirar, están las guías orientativas por modelo.",
  },
];

export function homeJsonLd(site: string): Record<string, unknown> {
  const org = { "@type": "Organization", "@id": `${site}/#organization`, name: SITE_NAME, url: `${site}/`, logo: `${site}/icon.svg`, areaServed: { "@type": "Country", name: "Argentina" } };
  return {
    "@context": "https://schema.org",
    "@graph": [
      org,
      { "@type": "WebSite", "@id": `${site}/#website`, name: "eseauto.com.ar", alternateName: SITE_NAME, url: `${site}/`, inLanguage: "es-AR", publisher: { "@id": org["@id"] } },
      {
        "@type": "Service",
        name: "Alertas de autos usados",
        serviceType: "Alertas de publicaciones de autos usados",
        description: "Ese Auto revisa las publicaciones de autos usados por vos y te avisa cuando aparece uno que coincide con lo que buscás, con su precio comparado contra publicaciones parecidas.",
        provider: { "@id": org["@id"] },
        areaServed: { "@type": "Country", name: "Argentina" },
        url: `${site}/`,
      },
      {
        "@type": "FAQPage",
        url: `${site}/`,
        inLanguage: "es-AR",
        mainEntity: HOME_FAQ.map(({ q, a }) => ({ "@type": "Question", name: q, acceptedAnswer: { "@type": "Answer", text: a } })),
      },
    ],
  };
}

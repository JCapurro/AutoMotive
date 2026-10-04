import type { Metadata } from "next";
import Link from "next/link";

import { Contact, LegalPage } from "@/components/legal-page";
import { ConsentSettings } from "@/components/meta-pixel";
import { contactEmail } from "@/lib/env";

export const metadata: Metadata = { title: "Política de privacidad" };

// F7, punto 7 (Ley 25.326). A first version for the pilot: have it reviewed
// before a public launch.
export default function PrivacyPage() {
  return (
    <LegalPage title="Política de privacidad" updated="3 de octubre de 2026">
      <p>
        Ese Auto es un servicio en etapa de piloto que monitorea publicaciones de autos usados y te avisa cuando
        aparece una que coincide con tu búsqueda. Esta política explica qué datos tuyos usamos, para qué y cómo
        podés ejercer tus derechos.
      </p>

      <h2>Qué datos usamos</h2>
      <ul>
        <li>
          <strong>Tu email</strong>, para ingresar (te mandamos un link o un código) y, si lo elegís, para enviarte
          alertas.
        </li>
        <li>
          <strong>Tus búsquedas</strong>: vehículo, filtros, preferencias y un punto de referencia para el radio de
          búsqueda: una zona o ciudad que elijas o, si nos das permiso, la ubicación de tu dispositivo al crear la
          búsqueda, redondeada a alrededor de 1 km. No seguimos tu ubicación después.
        </li>
        <li>
          <strong>Tu cuenta de Telegram</strong>, solo si la vinculás: el identificador del chat, para mandarte las
          alertas.
        </li>
        <li>
          <strong>Cómo usás el servicio</strong>: publicaciones que abrís, guardás o descartás (y el motivo), estados
          como «contacté» o «compré», clics en las alertas y respuestas a encuestas. Lo usamos para mejorar las
          alertas y medir si el servicio es útil.
        </li>
        <li>
          <strong>Lo que escribís en el modo asistido</strong>, para convertirlo en filtros que después revisás.
        </li>
      </ul>
      <p>
        Las publicaciones de autos que mostramos son públicas y vienen de otros sitios; no forman parte de tus datos.
      </p>

      <h2>Para qué</h2>
      <p>
        Para prestarte el servicio: buscar, avisarte, mostrarte los resultados y mejorar cómo los priorizamos. Y
        para medir los anuncios con los que te llegamos (ver Cookies). No vendemos tus datos, no mostramos publicidad
        dentro del sitio y nunca contactamos a un vendedor en tu nombre.
      </p>

      <h2>Con quién se comparten</h2>
      <ul>
        <li>Mercado Pago procesa los cobros. Recibe el email indicado y una referencia de la contratación. Guardamos importes, fechas, estado e identificadores del pago para verificar tu acceso; no guardamos números de tarjeta ni códigos de seguridad.</li>
        <li>Resend, que envía los emails (tu dirección y el contenido de la alerta).</li>
        <li>Telegram, si elegís recibir alertas por ahí.</li>
        <li>
          Meta (Facebook e Instagram), solo si aceptás sus cookies: las páginas que visitás acá y las acciones que
          medimos (ver Cookies), sin tu email ni el contenido de tus búsquedas.
        </li>
        <li>
          Anthropic (Claude), que interpreta el texto del modo asistido. Solo recibe ese texto, sin tu email ni otros
          datos de tu cuenta.
        </li>
      </ul>

      <h2>Cuánto tiempo</h2>
      <p>
        Mientras tengas la cuenta. Si la borrás, eliminamos tu email, tus búsquedas, alertas y todo tu historial; solo
        queda un registro anónimo de que una cuenta se dio de baja.
      </p>

      <h2 id="cookies">Cookies</h2>
      <p>
        Usamos cookies propias para mantener tu sesión iniciada. Si las aceptás en el aviso de cookies, también usamos
        el Pixel de Meta (Facebook e Instagram), que guarda cookies de Meta para medir si nuestros anuncios
        funcionan: registra las páginas que visitás acá y acciones como pedir el link para entrar, crear la cuenta,
        crear una búsqueda, guardar una publicación o contratar un plan. Cuando un pago se aprueba, se lo informamos
        a Meta desde nuestro servidor con el plan, el importe, un identificador cifrado de tu cuenta, tu dirección IP,
        tu navegador y los identificadores de esas cookies. No le mandamos tu email, tus búsquedas ni otros datos de
        tu cuenta. Si las rechazás, no cargamos el Pixel ni le informamos nada a Meta.
      </p>
      <ConsentSettings />

      <h2>Tus derechos</h2>
      <p>
        Podés acceder, rectificar y suprimir tus datos en cualquier momento (Ley 25.326 de Protección de Datos
        Personales). Casi todo lo podés hacer vos desde <Link href="/app/settings">Ajustes</Link>: cambiar los
        canales, dejar de recibir emails (también con el link al pie de cada email) o borrar tu cuenta. Para
        cualquier otro pedido escribinos a <Contact email={contactEmail} /> y te respondemos dentro de los plazos
        que fija la ley.
      </p>
      <p>
        La Agencia de Acceso a la Información Pública, órgano de control de la Ley 25.326, atiende las denuncias y
        reclamos por incumplimiento de las normas sobre protección de datos personales.
      </p>
    </LegalPage>
  );
}

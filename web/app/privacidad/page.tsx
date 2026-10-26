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
    <LegalPage title="Política de privacidad" updated="16 de octubre de 2026">
      <p>
        Ese Auto es un servicio en etapa de piloto que monitorea publicaciones de autos usados y te avisa cuando
        aparece una que coincide con tu búsqueda. Esta política explica qué datos tuyos usamos, para qué y cómo
        podés ejercer tus derechos.
      </p>

      <h2>Qué datos usamos</h2>
      <ul>
        <li>
          <strong>Tu email</strong>. Para la búsqueda gratis te pedimos solo tu email, sin contraseña ni
          confirmación. Lo usamos para mandarte las alertas de tu búsqueda y los avisos sobre tu prueba gratis y tu
          plan (por ejemplo, cuando termina la prueba, o cuántos autos nuevos aparecieron para tu búsqueda en las 3
          semanas después de que venció). Para volver a entrar desde otro dispositivo te mandamos un link a ese
          email. Para contratar un plan te pedimos crear una cuenta: confirmar tu email y elegir una contraseña.
          También te escribimos para confirmar el registro o recuperar la contraseña. Las alertas y los avisos
          traen un link para dejar de recibirlos.
        </li>
        <li>
          <strong>Tus búsquedas</strong>: vehículo, filtros, preferencias y un punto de referencia para el radio de
          búsqueda: una zona o ciudad que elijas, una zona aproximada estimada a partir de tu conexión por nuestro
          proveedor de alojamiento (Vercel), o, si nos das permiso, la ubicación de tu dispositivo al crear la
          búsqueda. Podés cambiar la zona antes de guardar. Las coordenadas del dispositivo y de la zona aproximada
          se redondean a alrededor de 1 km. No guardamos tu dirección IP para obtener esta zona ni seguimos tu ubicación después.
        </li>
        <li>
          <strong>Cómo usás el servicio</strong>: publicaciones que abrís, guardás o descartás (y el motivo), estados
          como «contacté» o «compré», clics en las alertas, si abriste nuestros emails (cada email trae una imagen
          de 1 píxel que lo marca abierto cuando se cargan las imágenes) y respuestas a encuestas. Lo usamos para
          mejorar las alertas y medir si el servicio es útil.
        </li>
        <li>
          <strong>Lo que escribís en el modo asistido</strong>, para convertirlo en filtros que después revisás.
        </li>
        <li>
          <strong>Un identificador cifrado de tu IP</strong>: cuando dejás tu email para crear una búsqueda o pedís
          un link para entrar, guardamos un identificador cifrado (un hash) de tu dirección IP para prevenir abusos,
          como crear muchas búsquedas o pedir muchos links desde la misma conexión. Lo borramos a los 2 días como
          máximo y no guardamos la IP en sí.
        </li>
      </ul>
      <p>
        Las publicaciones de autos que mostramos son públicas y vienen de otros sitios; no forman parte de tus datos.
      </p>

      <h2>Si te llegan emails que no pediste</h2>
      <p>
        Para la búsqueda gratis no te pedimos confirmar el email antes de mandarte alertas (no hay doble opt-in).
        Por eso cada alerta y cada aviso de la prueba o del plan trae al pie un link para dejar de recibirlos. Si
        alguien escribió tu dirección y te llegan emails de Ese Auto que no pediste, tocá ese link y confirmá con
        un clic: no te mandamos más, sin que tengas que entrar ni tener contraseña. Si además querés que borremos
        esa búsqueda y tu email, escribinos a <Contact email={contactEmail} />.
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
        <li>Supabase, donde guardamos la base de datos y las cuentas (tu email, tus búsquedas y tu historial).</li>
        <li>Vercel, que aloja el sitio: procesa tus visitas, incluida tu dirección IP, para servir las páginas.</li>
        <li>Resend, que envía los emails (tu dirección y el contenido de la alerta).</li>
        <li>Google, si elegís «Continuar con Google» para entrar: nos comparte tu email y los datos básicos de tu perfil.</li>
        <li>
          Meta (Facebook e Instagram), salvo que rechaces las cookies de medición: las páginas que visitás acá y las acciones que
          medimos (ver Cookies), sin tu email ni el contenido de tus búsquedas.
        </li>
        <li>Google Analytics 4, salvo que rechaces las cookies de medición: páginas visitadas y eventos de uso como búsquedas, favoritos y contratación, sin el texto ni los filtros de tus búsquedas.</li>
        <li>Microsoft Clarity, salvo que rechaces las cookies de medición: mapas de calor y grabaciones de las interacciones con el sitio para detectar dificultades de uso. El contenido de los campos de los formularios se oculta en las grabaciones.</li>
        <li>
          OpenAI, que interpreta el texto del modo asistido. Recibe ese texto y las opciones del catálogo necesarias
          para convertirlo en filtros, sin tu email ni los identificadores de tu cuenta.
        </li>
      </ul>

      <h2>Cuánto tiempo</h2>
      <p>
        Mientras tengas la cuenta, también la que se crea con solo tu email al crear una búsqueda. Si la borrás,
        eliminamos tu email, tus búsquedas, alertas y todo tu historial; solo queda un registro anónimo de que una
        cuenta se dio de baja. El identificador cifrado de tu IP se borra a los 2 días como máximo.
      </p>

      <h2 id="cookies">Cookies</h2>
      <p>
        Usamos cookies propias para mantener tu sesión iniciada. Además usamos cookies de medición, en una sola
        categoría que se acepta o se rechaza junta en el aviso de cookies. Salvo que las rechaces, usamos
        Google Analytics 4 para medir visitas y acciones de uso, y el Pixel de Meta (Facebook e Instagram) para medir si nuestros anuncios
        funcionan: registra las páginas que visitás acá y acciones como dejar tu email para crear una búsqueda,
        crear una cuenta, guardar una búsqueda o una publicación, o iniciar la contratación de un plan. Google Analytics no recibe el texto ni los filtros de tus búsquedas. Cuando un pago se aprueba, se lo informamos
        a Meta desde nuestro servidor con el plan, el importe, un identificador cifrado de tu cuenta, tu dirección IP,
        tu navegador y los identificadores de esas cookies. No le mandamos tu email, tus búsquedas ni otros datos de
        tu cuenta. Estas cookies están activas desde que entrás al sitio. Un solo «Rechazar» las desactiva todas:
        el Pixel deja de enviarle datos a Meta, no le informamos los pagos, Google Analytics deja de medir tus visitas
        y no cargamos Microsoft Clarity.
      </p>
      <ConsentSettings />
      <p>
        Microsoft Clarity también se activa salvo que rechaces las cookies de medición. Nos permite ver clics,
        desplazamientos y recorridos por las páginas. No lo cargamos si las rechazaste ni en las páginas de
        confirmación y recuperación de acceso. Si cambiás tus preferencias y retirás el consentimiento, detenemos
        la grabación.
      </p>

      <h2>Tus derechos</h2>
      <p>
        Podés acceder, rectificar y suprimir tus datos en cualquier momento (Ley 25.326 de Protección de Datos
        Personales). Casi todo lo podés hacer vos desde <Link href="/app/settings">Ajustes</Link>: cambiar los
        canales, dejar de recibir emails (también con el link al pie de cada email) o borrar tu cuenta. Para
        borrar tus datos sin contraseña, en Ingresar pedí el link para entrar (te llega a tu email) y andá a
        Ajustes → «Borrar mi cuenta». Si no podés entrar, o para cualquier otro pedido, escribinos a{" "}
        <Contact email={contactEmail} /> y te respondemos dentro de los plazos que fija la ley.
      </p>
      <p>
        La Agencia de Acceso a la Información Pública, órgano de control de la Ley 25.326, atiende las denuncias y
        reclamos por incumplimiento de las normas sobre protección de datos personales.
      </p>
    </LegalPage>
  );
}

import type { Metadata } from "next";
import Link from "next/link";

import { Contact, LegalPage } from "@/components/legal-page";
import { contactEmail } from "@/lib/env";

export const metadata: Metadata = { title: "Términos de uso" };

// F7, punto 7. A first version for the pilot: have it reviewed before a
// public launch.
export default function TermsPage() {
  return (
    <LegalPage title="Términos de uso" updated="28 de septiembre de 2026">
      <p>
        Al crear una cuenta en Automotive aceptás estos términos. Si no estás de acuerdo, no uses el servicio.
      </p>

      <h2>El servicio</h2>
      <p>
        Automotive monitorea publicaciones de autos usados en sitios de terceros, te avisa cuando aparece una que
        coincide con tus búsquedas y te muestra información para evaluarla. Está en etapa de piloto: es gratuito,
        puede cambiar, tener interrupciones o dejar de funcionar, y te avisaremos por email antes de cobrar por
        cualquier parte.
      </p>

      <h2>La información que mostramos</h2>
      <ul>
        <li>
          Las publicaciones, sus precios, fotos y descripciones son de sus autores y de los sitios donde se
          publicaron. No verificamos que sean exactas ni que el vehículo siga disponible.
        </li>
        <li>
          El Opportunity Score y el análisis de precio comparan el precio publicado con otras publicaciones
          comparables que observamos. No son una valuación profesional del vehículo ni una recomendación de compra.
        </li>
        <li>
          Las señales de «conviene verificar» y las preguntas sugeridas son una ayuda: no reemplazan revisar el
          vehículo, la documentación ni una inspección profesional.
        </li>
      </ul>

      <h2>Tu compra es entre vos y el vendedor</h2>
      <p>
        Automotive no vende vehículos, no intermedia en la operación ni contacta a los vendedores. Cualquier trato,
        pago o reclamo es entre vos y el vendedor, por los canales del sitio donde está la publicación.
      </p>

      <h2>Tu cuenta</h2>
      <p>
        Usá un email que sea tuyo y no compartas los links de ingreso. No uses el servicio para fines ilegales ni
        intentes acceder a datos de otros usuarios o sobrecargar el sistema. Podemos suspender cuentas que lo hagan.
        Podés borrar tu cuenta cuando quieras desde <Link href="/app/settings">Ajustes</Link>.
      </p>

      <h2>Datos personales</h2>
      <p>
        Cómo usamos tus datos está en la <Link href="/privacidad">Política de privacidad</Link>.
      </p>

      <h2>Responsabilidad</h2>
      <p>
        El servicio se ofrece tal como está. En la medida en que la ley lo permita, no respondemos por decisiones de
        compra tomadas a partir de la información mostrada, por errores en las publicaciones de terceros ni por
        alertas que no lleguen o lleguen tarde.
      </p>

      <h2>Cambios y contacto</h2>
      <p>
        Si cambiamos estos términos, publicamos la nueva versión acá con su fecha y, si el cambio es importante, te
        avisamos por email. Consultas: <Contact email={contactEmail} />. Rigen las leyes de la República Argentina.
      </p>
    </LegalPage>
  );
}

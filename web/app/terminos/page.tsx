import type { Metadata } from "next";
import Link from "next/link";

import { Contact, LegalPage } from "@/components/legal-page";
import { contactEmail } from "@/lib/env";
import { webConfig } from "@/lib/config";
import { planPrice } from "@/lib/pro";

export const metadata: Metadata = { title: "Términos de uso" };
export const dynamic = "force-dynamic";

// F7, punto 7. A first version for the pilot: have it reviewed before a
// public launch.
export default async function TermsPage() {
  const { proOffer, automaticPayments } = await webConfig();
  return (
    <LegalPage title="Términos de uso" updated="5 de octubre de 2026">
      <p>
        Al crear una cuenta en Ese Auto aceptás estos términos. Si no estás de acuerdo, no uses el servicio.
      </p>

      <h2>El servicio</h2>
      <p>
        Ese Auto monitorea publicaciones de autos usados en sitios de terceros, te avisa cuando aparece una que
        coincide con tus búsquedas y te muestra información para evaluarla. La disponibilidad de las fuentes
        y la frecuencia de detección pueden variar. Los precios comparados corresponden a publicaciones observadas.
      </p>

      <h2>Prueba y planes</h2>
      <p>La prueba gratis permite una búsqueda activa durante 72 horas corridas desde su primera activación,
        una sola vez por cuenta, hasta 50 resultados y resumen diario. Editar, pausar o reemplazar la búsqueda no reinicia el plazo.</p>
      <p>Particular cuesta {planPrice(proOffer.pass_30.amount)} ARS por 30 días, permite 3 búsquedas activas y no se renueva automáticamente.
        Agencia cuesta {planPrice(proOffer.pro_monthly.amount)} ARS y permite 10 búsquedas activas en una cuenta.
        {automaticPayments ? " Agencia se cobra cada mes mediante una suscripción de Mercado Pago hasta que la canceles. El acceso corresponde al mes calendario de cada débito aprobado. No hay otra prueba gratis ni almacenamiento de tarjetas en S Auto." : " En el piloto asistido, Agencia se activa por 30 días con renovación manual. La administración confirma el pago externo antes de activar el período."}</p>
      <p>Al vencer el acceso se detienen nuevas coincidencias y alertas, incluidos los favoritos; se conserva el historial.
        Pausar una búsqueda libera capacidad. Cada modelo guardado consume una búsqueda.
        Los planes pagos incluyen hasta 10 avisos inmediatos de nuevas coincidencias por día y cuenta;
        los restantes van al resumen. Las bajas de precio de favoritos mantienen su aviso inmediato con acceso vigente.</p>
      <p>{automaticPayments ? "Podés cancelar la suscripción Agencia desde Ajustes. Mostramos la baja cuando Mercado Pago la confirma; se detienen las siguientes renovaciones y tu período ya pagado sigue vigente hasta su vencimiento." : "Podés avisar que no querés renovar desde Ajustes. Tu período ya pagado sigue vigente hasta su vencimiento."}
        {" "}Las suscripciones contratadas mediante enlaces genéricos se cancelan desde Mercado Pago; el aviso de no renovación en S Auto no detiene esos cobros.
        Para consultar un cobro o solicitar una devolución, contactá a <Contact email={contactEmail} />.
        Un pago pendiente o rechazado no activa acceso; una devolución total o contracargo revoca su período.
        Los cambios de precio se comunican antes de contratar otro período y no modifican un período ya comprado.</p>

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
        Ese Auto no vende vehículos, no intermedia en la operación ni contacta a los vendedores. Cualquier trato,
        pago o reclamo es entre vos y el vendedor, por los canales del sitio donde está la publicación.
      </p>

      <h2>Tu cuenta</h2>
      <p>
        Usá un email que sea tuyo y no compartas tu contraseña ni los links de confirmación o recuperación. No uses el servicio para fines ilegales ni
        intentes acceder a datos de otros usuarios o sobrecargar el sistema. Podemos suspender cuentas que lo hagan.
        Podés borrar tu cuenta desde <Link href="/app/settings">Ajustes</Link>, después de confirmar la baja de una suscripción activa.
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

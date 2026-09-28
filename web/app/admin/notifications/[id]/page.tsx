import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Inspector } from "@/components/admin/inspector";
import { PageHeader, TextLink } from "@/components/admin/ui";
import { inspectNotification } from "@/lib/admin-inspect";

export const metadata: Metadata = { title: "¿Por qué se envió?" };

// The inspector (sección 10, §45) for one alert.
export default async function NotificationInspector({ params }: PageProps<"/admin/notifications/[id]">) {
  const { id } = await params;
  if (!/^\d+$/.test(id)) notFound();
  const data = await inspectNotification(Number(id));
  if (!data?.notification) notFound();

  return (
    <>
      <PageHeader
        title={`¿Por qué se envió la alerta #${id}?`}
        description={`A ${data.email ?? data.notification.user_id}${data.match ? ` · match #${data.match.id}` : ""}`}
      >
        <TextLink href="/admin/notifications" className="text-sm">
          ← Notificaciones
        </TextLink>
      </PageHeader>
      <Inspector data={data} />
    </>
  );
}

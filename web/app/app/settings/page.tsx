import type { Metadata } from "next";

import { ChannelsForm, FrequencyForm, LocationForm, TelegramLink } from "@/components/app/settings-forms";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { requireUser } from "@/lib/auth";
import { telegramBot } from "@/lib/env";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = { title: "Ajustes" };

export default async function SettingsPage() {
  const user = await requireUser();
  const supabase = await createClient();
  const { data: profile } = await supabase
    .from("profiles")
    .select("email, telegram_chat_id, telegram_link_code, default_channels, default_notification_frequency, default_origin_label")
    .single();

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <h1 className="text-xl font-semibold tracking-tight">Ajustes</h1>

      <Card id="telegram">
        <CardHeader>
          <CardTitle>Telegram</CardTitle>
          <CardDescription>Recibí las alertas en Telegram y marcá «Me interesa» o «Descartar» desde el chat.</CardDescription>
        </CardHeader>
        <CardContent>
          <TelegramLink
            bot={telegramBot}
            code={profile?.telegram_link_code ?? ""}
            linked={Boolean(profile?.telegram_chat_id)}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Canales</CardTitle>
          <CardDescription>Por dónde te avisamos. Aplica a todas tus búsquedas.</CardDescription>
        </CardHeader>
        <CardContent>
          <ChannelsForm
            channels={profile?.default_channels ?? ["telegram", "web"]}
            email={profile?.email ?? user.email}
            telegram={Boolean(profile?.telegram_chat_id)}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Preferencias</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-5 sm:grid-cols-2">
          <FrequencyForm value={profile?.default_notification_frequency ?? "immediate"} />
          <LocationForm label={profile?.default_origin_label ?? null} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Cuenta</CardTitle>
          <CardDescription>{profile?.email ?? user.email}</CardDescription>
        </CardHeader>
        <CardContent>
          <form action="/auth/signout" method="post">
            <Button type="submit" variant="outline">
              Cerrar sesión
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

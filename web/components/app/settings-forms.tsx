"use client";

import { CheckCircle2, ExternalLink, Loader2, Send } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";
import { toast } from "sonner";

import {
  saveChannels,
  saveFrequency,
  telegramLinked,
  unlinkTelegram,
} from "@/app/app/settings/actions";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { FREQUENCY, type Frequency } from "@/lib/copy";

function useSave() {
  const [pending, start] = useTransition();
  const save = (fn: () => Promise<void>, ok = "Guardado") =>
    start(async () => {
      try {
        await fn();
        toast.success(ok);
      } catch {
        toast.error("No pudimos guardar. Probá de nuevo.");
      }
    });
  return [pending, save] as const;
}

/**
 * Link Telegram (sección 9): the deep link t.me/<bot>?start=<telegram_link_code>
 * opens the bot, which links the account and rotates the code. The page
 * polls until the bot has done it.
 */
export function TelegramLink({ bot, code, linked }: { bot: string; code: string; linked: boolean }) {
  const router = useRouter();
  const [waiting, setWaiting] = useState(false);
  const [pending, save] = useSave();

  useEffect(() => {
    if (!waiting || linked) return;
    let tries = 0;
    const timer = setInterval(async () => {
      tries += 1;
      if (await telegramLinked()) {
        clearInterval(timer);
        setWaiting(false);
        toast.success("¡Listo! Telegram quedó vinculado.");
        router.refresh();
      } else if (tries > 60) {
        clearInterval(timer);
        setWaiting(false);
      }
    }, 3000);
    return () => clearInterval(timer);
  }, [waiting, linked, router]);

  if (linked) {
    return (
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="flex items-center gap-2 text-sm" data-testid="telegram-status">
          <CheckCircle2 className="size-4 text-emerald-600" aria-hidden /> Telegram vinculado. Las alertas llegan a tu chat.
        </p>
        <Button variant="outline" size="sm" disabled={pending} onClick={() => save(unlinkTelegram, "Telegram desvinculado")}>
          Desvincular
        </Button>
      </div>
    );
  }
  if (!bot) {
    return <p className="text-sm text-muted-foreground">La vinculación con Telegram no está configurada en este entorno.</p>;
  }
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground" data-testid="telegram-status">
        Abrí el bot y tocá <span className="font-medium text-foreground">Iniciar</span>: te vinculamos al instante.
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <Button asChild>
          <a href={`https://t.me/${bot}?start=${code}`} target="_blank" rel="noopener noreferrer" onClick={() => setWaiting(true)}>
            <Send aria-hidden /> Vincular Telegram <ExternalLink aria-hidden />
          </a>
        </Button>
        {waiting ? (
          <span className="flex items-center gap-1.5 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" aria-hidden /> Esperando la confirmación del bot…
          </span>
        ) : null}
      </div>
    </div>
  );
}

export function ChannelsForm({ channels, email, telegram }: { channels: string[]; email: string | null; telegram: boolean }) {
  const [pending, save] = useSave();
  const toggle = (channel: string, on: boolean) => {
    const next = on ? [...new Set([...channels, channel])] : channels.filter((c) => c !== channel);
    save(() => saveChannels(next));
  };
  return (
    <div className="space-y-3">
      <label className="flex items-start gap-3 text-sm">
        <Checkbox checked disabled className="mt-0.5" />
        <span>
          <span className="font-medium">Web</span>
          <span className="block text-muted-foreground">Siempre: las alertas quedan en Alertas.</span>
        </span>
      </label>
      <label className="flex items-start gap-3 text-sm">
        <Checkbox
          className="mt-0.5"
          checked={channels.includes("telegram")}
          disabled={pending}
          onCheckedChange={(v) => toggle("telegram", v === true)}
        />
        <span>
          <span className="font-medium">Telegram</span>
          <span className="block text-muted-foreground">{telegram ? "Vinculado." : "Vinculalo arriba para recibirlas."}</span>
        </span>
      </label>
      <label className="flex items-start gap-3 text-sm">
        <Checkbox
          className="mt-0.5"
          checked={channels.includes("email")}
          disabled={pending || !email}
          onCheckedChange={(v) => toggle("email", v === true)}
        />
        <span>
          <span className="font-medium">Email</span>
          <span className="block text-muted-foreground">{email ?? "Sin email"}</span>
        </span>
      </label>
    </div>
  );
}

export function FrequencyForm({ value }: { value: Frequency }) {
  const [pending, save] = useSave();
  return (
    <div className="space-y-1.5">
      <Label htmlFor="default_frequency">Frecuencia de las alertas</Label>
      <NativeSelect
        id="default_frequency"
        value={value}
        disabled={pending}
        onChange={(e) => save(() => saveFrequency(e.target.value as Frequency), "Frecuencia actualizada en todas tus búsquedas")}
      >
        {(Object.keys(FREQUENCY) as Frequency[]).map((f) => (
          <NativeSelectOption key={f} value={f}>
            {FREQUENCY[f].label} — {FREQUENCY[f].hint}
          </NativeSelectOption>
        ))}
      </NativeSelect>
      <p className="text-xs text-muted-foreground">Se aplica a todas tus búsquedas; después podés cambiarla en cada una.</p>
    </div>
  );
}

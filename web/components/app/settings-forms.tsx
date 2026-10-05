"use client";

import { useTransition } from "react";
import { toast } from "sonner";

import {
  saveChannels,
  saveFrequency,
} from "@/app/app/settings/actions";
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

export function ChannelsForm({ channels, email }: { channels: string[]; email: string | null }) {
  const [pending, save] = useSave();
  const toggle = (channel: string, on: boolean) => {
    const next = on ? [...new Set([...channels, channel])] : channels.filter((c) => c !== channel);
    save(() => saveChannels(next));
  };
  return (
    <div className="space-y-3">
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

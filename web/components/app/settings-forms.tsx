"use client";

import { useState, useTransition } from "react";
import { toast } from "sonner";

import {
  saveChannels,
  saveContactTemplate,
  saveFrequency,
} from "@/app/app/settings/actions";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { renderContactMessage } from "@/lib/contact-message";
import { CONTACT_MESSAGE, CONTACT_TEMPLATE_ERROR, CONTACT_TEMPLATE_MAX_CHARS, FREQUENCY, type Frequency, lintContactTemplate } from "@/lib/copy";

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

/** The preview's car: a listing's catalog model, year and one specific question. */
const PREVIEW = { model: "Fiesta", year: 2017, questions: ["¿Tenés historial de services?"] };

/**
 * PRO-01: the template of the message for sellers, with a live preview. The
 * lint runs here as you type and again on the server; the error stays in the
 * form, not in a generic toast.
 */
export function ContactTemplateForm({ value }: { value: string | null }) {
  const [text, setText] = useState(value ?? "");
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const lint = lintContactTemplate(text);
  const preview = renderContactMessage(lint.error ? null : lint.value, PREVIEW.model, PREVIEW.year, PREVIEW.questions);
  const shown = error ?? (lint.error ? CONTACT_TEMPLATE_ERROR[lint.error] : null);
  const submit = (next: string | null, ok: string) =>
    start(async () => {
      const result = await saveContactTemplate(next).catch(() => ({ error: "No pudimos guardar. Probá de nuevo." }) as { error?: string; value?: string | null });
      if (result.error) {
        setError(result.error);
        return;
      }
      setError(null);
      setText(result.value ?? "");
      toast.success(ok);
    });
  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        <Label htmlFor="contact_template">{CONTACT_MESSAGE.field}</Label>
        <Textarea
          id="contact_template"
          value={text}
          rows={5}
          maxLength={CONTACT_TEMPLATE_MAX_CHARS * 2}
          placeholder={CONTACT_MESSAGE.default}
          aria-invalid={shown ? true : undefined}
          aria-describedby="contact_template_hint"
          onChange={(e) => {
            setText(e.target.value);
            setError(null);
          }}
        />
        <p id="contact_template_hint" className="text-xs text-muted-foreground">{CONTACT_MESSAGE.markers}</p>
        {shown ? <p role="alert" data-testid="contact-template-error" className="text-sm text-destructive">{shown}</p> : null}
      </div>
      <div className="space-y-1">
        <p className="text-xs font-medium text-muted-foreground">{CONTACT_MESSAGE.preview}</p>
        <p data-testid="contact-template-preview" className="whitespace-pre-line rounded-lg bg-muted p-3 text-sm [overflow-wrap:anywhere]">{preview}</p>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button type="button" disabled={pending || Boolean(lint.error)} onClick={() => submit(text, CONTACT_MESSAGE.saved)}>
          {CONTACT_MESSAGE.save}
        </Button>
        <Button type="button" variant="outline" disabled={pending} onClick={() => submit(null, CONTACT_MESSAGE.resetDone)}>
          {CONTACT_MESSAGE.reset}
        </Button>
      </div>
    </div>
  );
}

"use client";

import { useEffect, useId, useRef, useState, useTransition } from "react";
import { ArrowLeft, CheckCircle2, Send } from "lucide-react";
import { submitProductFeedback } from "@/app/app/feedback/actions";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

export function ProductFeedback({ profileId, onBack }: { profileId: number; onBack: () => void }) {
  const id = useId();
  const textarea = useRef<HTMLTextAreaElement>(null);
  const request = useRef<string | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  const [pending, start] = useTransition();
  useEffect(() => { textarea.current?.focus(); }, []);

  if (sent) return <div className="space-y-5 pb-6">
    <div role="status" className="space-y-2 rounded-xl bg-muted p-5">
      <CheckCircle2 className="size-6 text-primary" aria-hidden />
      <p className="font-medium">Gracias por contarnos.</p>
      <p className="text-sm leading-relaxed text-muted-foreground">Recibimos tu comentario. Nos ayuda a mejorar las búsquedas y los planes.</p>
    </div>
    <Button variant="outline" className="h-10 w-full md:h-10" onClick={onBack}><ArrowLeft aria-hidden /> Volver a los planes</Button>
  </div>;

  return <form className="space-y-4 pb-6" onSubmit={(event) => {
    event.preventDefault();
    setError(null);
    request.current ??= crypto.randomUUID();
    const requestId = request.current;
    start(async () => {
      try {
        const result = await submitProductFeedback({ message, profileId, requestId });
        if (result.ok) setSent(true);
        else setError(result.error ?? "No pudimos enviar tu comentario. Probá de nuevo.");
      } catch {
        setError("No pudimos enviar tu comentario. Tu texto sigue acá; probá de nuevo.");
      }
    });
  }}>
    <div className="space-y-2">
      <label htmlFor={id} className="text-sm font-medium">Tu comentario</label>
      <Textarea ref={textarea} id={id} value={message} minLength={10} maxLength={2000} required disabled={pending}
        aria-invalid={Boolean(error)} aria-describedby={`${id}-help${error ? ` ${id}-error` : ""}`}
        className="min-h-36 resize-y leading-relaxed" placeholder="¿Qué te faltó o qué mejorarías de tu experiencia?"
        onChange={(event) => { setMessage(event.target.value); setError(null); request.current = null; }} />
      <div id={`${id}-help`} className="flex items-start justify-between gap-3 text-xs text-muted-foreground">
        <p>Nos llega junto con tu cuenta y la búsqueda, para poder ayudarte.</p>
        <span className="shrink-0 tabular-nums">{message.length}/2000</span>
      </div>
    </div>
    {error ? <p id={`${id}-error`} role="alert" className="text-sm text-destructive">{error}</p> : null}
    <Button type="submit" disabled={pending || message.trim().length < 10} className="h-11 w-full md:h-11"><Send aria-hidden />{pending ? "Enviando…" : "Enviar feedback"}</Button>
    <Button type="button" variant="ghost" disabled={pending} className="h-10 w-full text-muted-foreground md:h-10" onClick={onBack}><ArrowLeft aria-hidden /> Volver a los planes</Button>
  </form>;
}

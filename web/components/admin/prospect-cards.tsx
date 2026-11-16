"use client";

import { useState, useTransition } from "react";
import { toast } from "sonner";

import { prospectAction, type ProspectActionResult } from "@/app/admin/prospeccion/actions";
import { Pill } from "@/components/admin/ui";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  greetingName, type Hook, HOOK_LABEL, HOOK_RECHECK_HOURS, hookOf, hoursSince, type MessageRow, phoneLabel, type ProspectRow, REGION_LABEL, REPLIES,
  SOURCE_LABEL, STATUS_LABEL, STEP_LABEL, waLink, waNumber,
} from "@/lib/admin-prospecting";

type Action = { prospectId: number; messageId: number | null; action: string; text: string | null };

function useAct() {
  const [pending, start] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const act = (input: Action, done?: string) => start(async () => {
    setError(null);
    let r: ProspectActionResult;
    try {
      r = await prospectAction(input);
    } catch {
      setError("No pudimos conectarnos. Probá de nuevo.");
      return;
    }
    if (r.error) setError(r.error);
    else if (done) toast.success(done);
  });
  return { pending, error, act };
}

function where(p: ProspectRow): string {
  return [p.locality, p.region ? REGION_LABEL[p.region] ?? p.region : null].filter(Boolean).join(" · ");
}

function Header({ p, extra }: { p: ProspectRow; extra?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-2">
      <div className="min-w-0">
        <p className="font-medium break-words">{p.display_name}</p>
        <p className="text-xs text-muted-foreground">
          {p.kind === "agencia" ? "Agencia" : "Persona"} · {p.listing_count ?? "?"} avisos · {p.sources.map((s) => SOURCE_LABEL[s] ?? s).join(", ")}
          {where(p) ? ` · ${where(p)}` : ""}
        </p>
        {mlButton(p) ? (
          <p className="text-xs text-muted-foreground">WhatsApp por el botón de su aviso de Mercado Libre</p>
        ) : <p className="text-xs text-muted-foreground">
          WhatsApp {phoneLabel(p.phone)}
          {p.phone_source ? ` (${p.phone_source === "aviso" ? "de su aviso" : p.phone_source === "pagina_aviso" ? "de la página del aviso" : p.phone_source === "web" ? "canal público del negocio" : p.phone_source})` : ""}
          {p.phone_evidence?.startsWith("http") ? <> · <a href={p.phone_evidence} target="_blank" rel="noreferrer" className="underline">dónde está</a></> : null}
        </p>}
      </div>
      <div className="flex flex-wrap gap-1">{extra}</div>
    </div>
  );
}

type Fact = Record<string, unknown>;

function FactsView({ facts }: { facts: Fact }) {
  const hooks = (facts.ganchos as Fact[] | undefined) ?? [];
  const stock = (facts.stock as Fact | undefined) ?? {};
  const age = (stock.antiguedad as Fact | undefined) ?? {};
  const positions = (facts.posicion_de_precios as Fact[] | undefined) ?? [];
  const demand = (facts.demanda_agregada as Fact[] | undefined) ?? [];
  const models = ((stock.modelos_principales as Fact[] | undefined) ?? []).map((m) => `${m.modelo} (${m.avisos})`).join(", ");
  return (
    <div className="space-y-2 text-xs">
      {hooks.map((h) => (
        <p key={String(h.id)}>
          <span className="font-medium">Gancho:</span> {String(h.auto)} en {String(h.lugar)} a {String(h.precio_publicado)},{" "}
          {String(h.porcentaje_abajo_de_comparables)} % abajo de {String(h.cantidad_de_comparables)} parecidos · {String(h.fuente)} · publicado {String(h.publicado ?? "")}
          {typeof h.url === "string" ? <> · <a className="underline" href={h.url} target="_blank" rel="noreferrer">ver aviso</a></> : null}
        </p>
      ))}
      <p><span className="font-medium">Stock:</span> {String(stock.avisos_activos ?? "?")} avisos · {models}</p>
      <p>
        <span className="font-medium">Antigüedad:</span> mediana {String(age.mediana_dias ?? "?")} días · {String(age.avisos_con_mas_de_45_dias ?? 0)} con más de 45 días ·{" "}
        {String((facts.dejaron_de_publicarse as Fact | undefined)?.avisos ?? 0)} dejaron de publicarse en 30 días
      </p>
      {positions.map((p, i) => (
        <p key={i}>
          <span className="font-medium">Precio:</span> {String(p.auto)} a {String(p.precio_publicado)}: {String(p.comparables_mas_baratos)} de{" "}
          {String(p.comparables_publicados_en_zona)} parecidos en {String(p.zona_de_comparacion)} están más baratos ({String(p.lectura)})
          {typeof p.url === "string" ? <> · <a className="underline" href={p.url} target="_blank" rel="noreferrer">su aviso</a></> : null}
        </p>
      ))}
      {demand.map((d, i) => (
        <p key={i}><span className="font-medium">Demanda:</span> {String(d.busquedas_activas_en_ese_auto)} búsquedas de {String(d.modelo)} a {String(d.radio_km)} km</p>
      ))}
      <details>
        <summary className="cursor-pointer text-muted-foreground">Todos los hechos (JSON)</summary>
        <pre className="mt-1 max-h-80 overflow-auto rounded bg-muted p-2 text-[11px] whitespace-pre-wrap">{JSON.stringify(facts, null, 1)}</pre>
      </details>
    </div>
  );
}

/** No number yet: the seller is reached through the WhatsApp button of their own ML listing. */
function mlButton(p: ProspectRow): boolean {
  return !p.phone && p.phone_source === "boton_ml" && !!p.phone_evidence?.startsWith("http");
}

/** Copy the text, open the listing (the ML app on the phone), tap WhatsApp, paste. */
function MlButtonSteps({ url, text, onCopy }: { url: string; text: string; onCopy: () => void }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      toast.success("Mensaje copiado");
      onCopy();
    } catch {
      toast.error("No se pudo copiar: seleccioná el texto y copialo a mano");
    }
  };
  return (
    <div className="w-full space-y-2 rounded-lg bg-muted/40 p-3">
      <p className="text-sm font-medium">Abrí su aviso y tocá WhatsApp</p>
      <ol className="list-decimal space-y-0.5 pl-5 text-xs text-muted-foreground">
        <li>Copiá el mensaje.</li>
        <li>Abrí el aviso (en el celular se abre en la app de Mercado Libre) y tocá «WhatsApp».</li>
        <li>Pegá el mensaje, mandalo y volvé a marcar «Enviado».</li>
      </ol>
      <div className="flex flex-wrap gap-2">
        <Button onClick={copy}>{copied ? "Copiado ✓" : "Copiar mensaje"}</Button>
        <Button asChild variant="outline">
          <a href={url} target="_blank" rel="noreferrer">Abrir su aviso en ML</a>
        </Button>
      </div>
    </div>
  );
}

/** The number WhatsApp showed after the ML button: the follow-ups then go by wa.me. */
function PhoneForm({ prospectId }: { prospectId: number }) {
  const [value, setValue] = useState("");
  const { pending, error, act } = useAct();
  const number = waNumber(value);
  return (
    <form className="flex flex-wrap items-center gap-2" onSubmit={(e) => {
      e.preventDefault();
      if (number) act({ prospectId, messageId: null, action: "phone_set", text: number }, "Número guardado");
    }}>
      <input value={value} onChange={(e) => setValue(e.target.value)} inputMode="tel" placeholder="Su número (ej. 341 512 3456)"
        aria-label="Número de WhatsApp que te apareció" className="h-8 min-w-0 flex-1 rounded-lg border bg-background px-2 text-sm" />
      <Button type="submit" size="sm" variant="secondary" disabled={pending || !number}>Guardar número</Button>
      {error ? <p role="alert" className="w-full text-xs text-destructive">{error}</p> : null}
    </form>
  );
}

/** The car the text offers, and how fresh the proof is that it is still published. */
function HookLine({ hook }: { hook: Hook }) {
  if (!hook.url) return null;
  const hours = hoursSince(hook.checkedAt, new Date());
  const stale = hours === null || hours > HOOK_RECHECK_HOURS;
  const how = hook.checkedBy === "colector" ? "visto por el colector" : "verificado en su aviso";
  return (
    <div className={`rounded-lg p-2 text-xs ${stale ? "bg-amber-500/10 text-amber-900 dark:text-amber-200" : "text-muted-foreground"}`}>
      <a href={hook.url} target="_blank" rel="noreferrer" className="font-medium underline underline-offset-2">{hook.car ?? "Auto del gancho"}</a>
      {" · "}
      <span suppressHydrationWarning>
        {hours === null ? "sin verificar que siga publicado" : hours === 0 ? `${how} hace menos de 1 h` : `${how} hace ${hours} h`}
      </span>
      {stale ? <span className="block">Abrí el aviso y fijate que siga publicado antes de mandarlo.</span> : null}
    </div>
  );
}

/** A message ready to send: editable, the other variant, the facts behind it, WhatsApp and the states. */
export function MessageCard({ message, prospect }: { message: MessageRow; prospect: ProspectRow }) {
  const saved = message.final_text ?? "";
  const [text, setText] = useState(saved);
  const { pending, error, act } = useAct();
  const dirty = text.trim() !== saved.trim();
  const link = waLink(prospect.phone, text);
  const other = message.chosen_index === null ? null : message.variants[1 - message.chosen_index];
  const review = (message.review?.decision ?? {}) as Record<string, unknown>;
  const base = { prospectId: prospect.id, messageId: message.id };

  return (
    <article className="space-y-3 rounded-xl bg-card p-4 ring-1 ring-foreground/10">
      <Header
        p={prospect}
        extra={<>
          <Pill tone={message.step === "first" ? "muted" : "warn"}>{STEP_LABEL[message.step]}</Pill>
          {message.hook_type ? <Pill>{HOOK_LABEL[message.hook_type]}</Pill> : null}
          {message.edited ? <Pill tone="warn">Editado</Pill> : null}
        </>}
      />
      <Textarea value={text} onChange={(e) => setText(e.target.value)} rows={8} className="text-sm" aria-label={`Mensaje para ${prospect.display_name}`} />
      <p className={`text-xs ${text.length > 450 ? "text-destructive" : "text-muted-foreground"}`}>{text.length} caracteres</p>
      <HookLine hook={hookOf({ facts: message.facts, final_text: text })} />
      <div className="flex flex-wrap gap-2">
        {link ? (
          <Button asChild>
            <a href={link} target="_blank" rel="noreferrer" onClick={() => { if (dirty) act({ ...base, action: "edited", text }); }}>
              Abrir en WhatsApp
            </a>
          </Button>
        ) : mlButton(prospect) ? (
          <MlButtonSteps url={prospect.phone_evidence!} text={text}
            onCopy={() => { if (dirty) act({ ...base, action: "edited", text }); }} />
        ) : <Pill tone="bad">Sin número válido</Pill>}
        <Button variant="secondary" disabled={pending} onClick={() => act({ ...base, action: dirty ? "edited" : "sent", text: dirty ? text : null }, dirty ? "Guardado" : "Marcado como enviado")}>
          {dirty ? "Guardar cambios" : "Marcar enviado"}
        </Button>
        {dirty ? null : (
          <>
            <Button variant="outline" disabled={pending} onClick={() => act({ ...base, action: "not_interested", text: null }, "Marcado")}>No le interesa</Button>
            <Button variant="outline" disabled={pending} onClick={() => act({ ...base, action: "wrong_number", text: null }, "Marcado")}>Número equivocado</Button>
            <Button variant="ghost" disabled={pending} onClick={() => act({ ...base, action: "skipped", text: null }, "Descartado")}>Descartar</Button>
          </>
        )}
      </div>
      {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}
      {mlButton(prospect) ? <PhoneForm prospectId={prospect.id} /> : null}

      {other ? (
        <details className="rounded-lg bg-muted/40 p-3">
          <summary className="cursor-pointer text-sm font-medium">La otra variante · {HOOK_LABEL[other.hook_type] ?? other.hook_type}</summary>
          <p className="mt-2 text-sm whitespace-pre-wrap">{other.text}</p>
          <Button className="mt-2" size="sm" variant="outline" disabled={pending}
            onClick={() => { act({ ...base, action: "chose_variant", text: String(1 - (message.chosen_index ?? 0)) }, "Cambiada"); setText(other.text); }}>
            Usar esta
          </Button>
        </details>
      ) : null}
      <details className="rounded-lg bg-muted/40 p-3">
        <summary className="cursor-pointer text-sm font-medium">Datos que lo respaldan</summary>
        <div className="mt-2 space-y-2">
          {typeof review.por_que === "string" && review.por_que ? <p className="text-xs"><span className="font-medium">Revisión:</span> {review.por_que}</p> : null}
          <FactsView facts={message.facts} />
        </div>
      </details>
    </article>
  );
}

/** A prospect already written to: mark the answer or close it. */
export function WaitingRow({ p }: { p: ProspectRow }) {
  const { pending, error, act } = useAct();
  const base = { prospectId: p.id, messageId: null };
  return (
    <li className="space-y-2 rounded-xl bg-card p-3 ring-1 ring-foreground/10">
      <Header p={p} extra={<Pill>{STATUS_LABEL[p.status]}</Pill>} />
      <p className="text-xs text-muted-foreground">
        Último envío {p.last_sent_at ? new Date(p.last_sent_at).toLocaleDateString("es-AR", { timeZone: "America/Argentina/Buenos_Aires" }) : "—"}
        {p.next_due_on ? ` · próximo mensaje el ${p.next_due_on.split("-").reverse().join("/")}` : ""}
      </p>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" disabled={pending} onClick={() => act({ ...base, action: "replied", text: null }, "Marcado: respondió")}>Respondió</Button>
        <Button size="sm" variant="outline" disabled={pending} onClick={() => act({ ...base, action: "not_interested", text: null }, "Marcado")}>No le interesa</Button>
        <Button size="sm" variant="outline" disabled={pending} onClick={() => act({ ...base, action: "wrong_number", text: null }, "Marcado")}>Número equivocado</Button>
        <Button size="sm" variant="ghost" disabled={pending} onClick={() => act({ ...base, action: "closed", text: null }, "Cerrado")}>Cerrar</Button>
      </div>
      {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}
      {mlButton(p) ? <PhoneForm prospectId={p.id} /> : null}
    </li>
  );
}

/** Someone who answered: the ready-made replies, each straight into their WhatsApp. */
export function RepliedRow({ p, hook }: { p: ProspectRow; hook: { car: string | null; url: string | null } | null }) {
  const { pending, error, act } = useAct();
  const ctx = { name: greetingName(p), hookUrl: hook?.url ?? null, hookCar: hook?.car ?? null, zone: p.locality };
  return (
    <li className="space-y-2 rounded-xl bg-card p-3 ring-1 ring-foreground/10">
      <Header p={p} extra={<Pill tone="ok">Respondió</Pill>} />
      <div className="flex flex-wrap gap-1.5">
        {REPLIES.map((r) => {
          const link = waLink(p.phone, r.text(ctx));
          return link ? (
            <a key={r.key} href={link} target="_blank" rel="noreferrer"
              className="inline-flex h-7 items-center rounded-lg bg-muted px-2.5 text-xs hover:bg-muted/70">{r.label}</a>
          ) : null;
        })}
      </div>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="outline" disabled={pending} onClick={() => act({ prospectId: p.id, messageId: null, action: "not_interested", text: null }, "Marcado")}>No le interesa</Button>
        <Button size="sm" variant="ghost" disabled={pending} onClick={() => act({ prospectId: p.id, messageId: null, action: "closed", text: null }, "Cerrado")}>Cerrar</Button>
        <Button size="sm" variant="ghost" disabled={pending} onClick={() => act({ prospectId: p.id, messageId: null, action: "reopened", text: null }, "Reabierto")}>No respondió (deshacer)</Button>
      </div>
      {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}
    </li>
  );
}

/** Every ready-made reply, to copy. */
export function RepliesList() {
  const ctx = { name: "", hookUrl: null, hookCar: null, zone: null };
  return (
    <ul className="grid gap-3 md:grid-cols-2">
      {REPLIES.map((r) => {
        const text = r.text(ctx);
        return (
          <li key={r.key} className="space-y-2 rounded-xl bg-card p-3 ring-1 ring-foreground/10">
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm font-medium">{r.label}</p>
              <Button size="sm" variant="outline" onClick={() => { void navigator.clipboard.writeText(text).then(() => toast.success("Copiado")); }}>Copiar</Button>
            </div>
            <p className="text-xs whitespace-pre-wrap text-muted-foreground">{text}</p>
          </li>
        );
      })}
    </ul>
  );
}

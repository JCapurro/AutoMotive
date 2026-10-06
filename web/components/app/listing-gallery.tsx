"use client";

import { Car, ChevronLeft, ChevronRight, RotateCcw, X, ZoomIn, ZoomOut } from "lucide-react";
import { Dialog } from "radix-ui";
import { useRef, useState, type PointerEvent } from "react";

import { cn } from "@/lib/utils";

const control = "inline-flex size-11 shrink-0 items-center justify-center rounded-md hover:bg-white/15 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white disabled:opacity-35";

/** Source photos stay in the app; the publication link remains a separate action. */
export function ListingGallery({ images, name }: { images: string[]; name: string }) {
  const [open, setOpen] = useState(false);
  const [index, setIndex] = useState(0);
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [failed, setFailed] = useState<string | null>(null);
  const pointers = useRef(new Map<number, { x: number; y: number }>());
  const gesture = useRef({ distance: 0, zoom: 1 });
  const viewport = useRef<HTMLDivElement>(null);
  const opener = useRef<HTMLButtonElement | null>(null);

  function reset() {
    setZoom(1);
    setOffset({ x: 0, y: 0 });
    pointers.current.clear();
  }

  function changePhoto(next: number) {
    setIndex((next + images.length) % images.length);
    setFailed(null);
    reset();
  }

  function changeZoom(value: number) {
    const next = Math.max(1, Math.min(5, value));
    setZoom(next);
    if (next === 1) setOffset({ x: 0, y: 0 });
    else {
      const bounds = viewport.current?.getBoundingClientRect();
      if (bounds) setOffset((position) => ({
        x: Math.max(-bounds.width * (next - 1) / 2, Math.min(bounds.width * (next - 1) / 2, position.x)),
        y: Math.max(-bounds.height * (next - 1) / 2, Math.min(bounds.height * (next - 1) / 2, position.y)),
      }));
    }
  }

  function distance() {
    const [a, b] = Array.from(pointers.current.values());
    return a && b ? Math.hypot(a.x - b.x, a.y - b.y) : 0;
  }

  function pointerDown(event: PointerEvent<HTMLDivElement>) {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    pointers.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (pointers.current.size === 2) gesture.current = { distance: distance(), zoom };
  }

  function pointerMove(event: PointerEvent<HTMLDivElement>) {
    const previous = pointers.current.get(event.pointerId);
    if (!previous) return;
    pointers.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (pointers.current.size === 2 && gesture.current.distance > 0) {
      changeZoom(gesture.current.zoom * distance() / gesture.current.distance);
    } else if (zoom > 1) {
      const bounds = event.currentTarget.getBoundingClientRect();
      setOffset((position) => ({
        x: Math.max(-bounds.width * (zoom - 1) / 2, Math.min(bounds.width * (zoom - 1) / 2, position.x + event.clientX - previous.x)),
        y: Math.max(-bounds.height * (zoom - 1) / 2, Math.min(bounds.height * (zoom - 1) / 2, position.y + event.clientY - previous.y)),
      }));
    }
  }

  if (!images.length) return (
    <div className="mt-6 grid h-40 place-items-center rounded-md bg-muted" aria-label="Sin fotos disponibles">
      <Car className="size-10 text-faint" aria-hidden />
    </div>
  );

  const shown = images.slice(0, 5);
  return (
    <Dialog.Root open={open} onOpenChange={(value) => { setOpen(value); if (!value) reset(); }}>
      <div className="mt-6 grid grid-cols-4 gap-1.5 md:grid-cols-[2fr_1fr_1fr] md:grid-rows-2">
        {shown.map((src, i) => (
          <button
            key={`${src}-${i}`}
            type="button"
            aria-label={`Ampliar foto ${i + 1} de ${images.length}`}
            aria-haspopup="dialog"
            onClick={(event) => { opener.current = event.currentTarget; changePhoto(i); setOpen(true); }}
            className={cn("group relative cursor-zoom-in overflow-hidden rounded bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring", i === 0 ? "col-span-full aspect-video md:col-span-1 md:row-span-2 md:aspect-auto" : "aspect-[4/3] md:aspect-auto md:min-h-36")}
          >
            {/* eslint-disable-next-line @next/next/no-img-element -- source CDN photos */}
            <img src={src} alt={`${name}, foto ${i + 1}`} loading={i < 2 ? "eager" : "lazy"} referrerPolicy="no-referrer" className="size-full object-cover" />
            {i === shown.length - 1 && images.length > shown.length ? (
              <span className="absolute inset-0 grid place-items-center bg-[#14213d]/60 text-sm font-semibold text-white group-hover:bg-[#14213d]/70">+{images.length - shown.length} fotos</span>
            ) : (
              <span className="absolute bottom-2 right-2 rounded bg-black/60 p-1.5 text-white"><ZoomIn className="size-4" aria-hidden /></span>
            )}
          </button>
        ))}
      </div>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/90" />
        <Dialog.Content
          className="fixed inset-0 z-50 flex flex-col bg-[#0a101c] text-white outline-none"
          onCloseAutoFocus={(event) => { event.preventDefault(); opener.current?.focus(); }}
          onKeyDown={(event) => {
            if (event.target instanceof HTMLButtonElement && ["Enter", " "].includes(event.key)) return;
            if (event.key === "ArrowLeft" && images.length > 1) { event.preventDefault(); changePhoto(index - 1); }
            if (event.key === "ArrowRight" && images.length > 1) { event.preventDefault(); changePhoto(index + 1); }
            if (["+", "="].includes(event.key)) { event.preventDefault(); changeZoom(zoom + 0.5); }
            if (event.key === "-") { event.preventDefault(); changeZoom(zoom - 0.5); }
          }}
        >
          <header className="flex shrink-0 items-center gap-2 border-b border-white/15 px-3 py-2 sm:px-5">
            <Dialog.Title className="min-w-0 flex-1 truncate text-sm font-semibold">Fotos de {name}</Dialog.Title>
            <span className="shrink-0 text-sm" aria-live="polite">{index + 1} / {images.length}</span>
            <Dialog.Close className={control} aria-label="Cerrar visor"><X aria-hidden className="size-5" /></Dialog.Close>
          </header>
          <div className="relative min-h-0 flex-1">
            <div
              ref={(node) => {
                viewport.current = node;
                if (!node) return;
                const wheel = (event: WheelEvent) => {
                  event.preventDefault();
                  changeZoom(zoom + (event.deltaY < 0 ? 0.25 : -0.25));
                };
                node.addEventListener("wheel", wheel, { passive: false });
                return () => node.removeEventListener("wheel", wheel);
              }}
              className={cn("absolute inset-0 touch-none overflow-hidden", zoom > 1 ? "cursor-grab active:cursor-grabbing" : "cursor-zoom-in")}
              onDoubleClick={() => changeZoom(zoom > 1 ? 1 : 2)}
              onPointerDown={pointerDown}
              onPointerMove={pointerMove}
              onPointerUp={(event) => pointers.current.delete(event.pointerId)}
              onPointerCancel={(event) => pointers.current.delete(event.pointerId)}
              onLostPointerCapture={(event) => pointers.current.delete(event.pointerId)}
            >
              {failed === images[index] ? (
                <p role="status" className="grid h-full place-items-center p-6 text-center">No pudimos cargar esta foto. Probá con otra.</p>
              ) : (
                /* eslint-disable-next-line @next/next/no-img-element -- source CDN photos */
                <img key={images[index]} src={images[index]} alt={`${name}, foto ${index + 1}`} referrerPolicy="no-referrer" draggable={false} onError={() => setFailed(images[index])} className="size-full select-none object-contain" style={{ transform: `translate(${offset.x}px, ${offset.y}px) scale(${zoom})` }} />
              )}
            </div>
            {images.length > 1 && <>
              <button type="button" className={cn(control, "absolute top-1/2 left-2 -translate-y-1/2 bg-black/50")} aria-label="Foto anterior" onClick={() => changePhoto(index - 1)}><ChevronLeft aria-hidden /></button>
              <button type="button" className={cn(control, "absolute top-1/2 right-2 -translate-y-1/2 bg-black/50")} aria-label="Foto siguiente" onClick={() => changePhoto(index + 1)}><ChevronRight aria-hidden /></button>
            </>}
          </div>
          <footer className="shrink-0 border-t border-white/15 px-3 pt-2 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
            <div className="flex items-center justify-center gap-2">
              <button type="button" className={control} aria-label="Reducir zoom" disabled={zoom <= 1} onClick={() => changeZoom(zoom - 0.5)}><ZoomOut aria-hidden className="size-5" /></button>
              <output aria-label="Nivel de zoom" className="w-14 text-center text-sm tabular-nums">{Math.round(zoom * 100)}%</output>
              <button type="button" className={control} aria-label="Aumentar zoom" disabled={zoom >= 5} onClick={() => changeZoom(zoom + 0.5)}><ZoomIn aria-hidden className="size-5" /></button>
              <button type="button" className={control} aria-label="Restablecer zoom" onClick={reset}><RotateCcw aria-hidden className="size-5" /></button>
            </div>
            <Dialog.Description className="text-center text-xs text-white/65">Usá + y − o pellizcá para ampliar. Arrastrá la foto para ver los detalles.</Dialog.Description>
          </footer>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

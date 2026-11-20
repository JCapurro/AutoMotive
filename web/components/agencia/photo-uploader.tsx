"use client";

import { ImagePlus, Star, X } from "lucide-react";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { createClient } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";

export const MAX_PHOTOS = 10;
export const BUCKET = "dealer-photos";
const MAX_SIDE = 1600;

/** Shrinks a photo in the browser (longest side 1600 px, JPEG) so a phone picture weighs ~300 KB instead of 5 MB. */
export async function shrink(file: File, maxSide = MAX_SIDE, quality = 0.82): Promise<Blob> {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext("2d")!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  return new Promise((resolve, reject) => canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("toBlob"))), "image/jpeg", quality));
}

/**
 * The car's photos: upload from the device (to the dealer-photos bucket, under
 * the agency's folder) or paste a link. The first one is the cover buyers see.
 * It only edits the list of URLs; the form saves it with the rest of the car.
 */
export function PhotoUploader({ dealerId, value, onChange }: { dealerId: number; value: string[]; onChange: (urls: string[]) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [link, setLink] = useState("");
  const room = MAX_PHOTOS - value.length;

  async function upload(files: FileList | null) {
    if (!files?.length) return;
    setError(null);
    const picked = Array.from(files).filter((f) => f.type.startsWith("image/")).slice(0, room);
    if (picked.length < files.length) setError(room <= 0 ? `Ya hay ${MAX_PHOTOS} fotos.` : `Subimos solo ${picked.length}: el máximo es ${MAX_PHOTOS} fotos y solo imágenes.`);
    if (!picked.length) return;
    setUploading(picked.length);
    const supabase = createClient();
    const added: string[] = [];
    for (const file of picked) {
      try {
        const blob = await shrink(file);
        const path = `${dealerId}/${crypto.randomUUID()}.jpg`;
        const { error: failed } = await supabase.storage.from(BUCKET).upload(path, blob, { contentType: "image/jpeg", cacheControl: "31536000" });
        if (failed) throw failed;
        added.push(supabase.storage.from(BUCKET).getPublicUrl(path).data.publicUrl);
      } catch {
        setError("No pudimos subir alguna foto. Probá de nuevo con JPG o PNG.");
      }
      setUploading((n) => n - 1);
    }
    setUploading(0);
    if (added.length) onChange([...value, ...added]);
    if (input.current) input.current.value = "";
  }

  function addLink() {
    const url = link.trim();
    if (!/^https:\/\/\S+$/.test(url)) return setError("El link tiene que empezar con https://");
    if (room <= 0) return setError(`Ya hay ${MAX_PHOTOS} fotos.`);
    setError(null);
    onChange([...value, url]);
    setLink("");
  }

  return (
    <div className="space-y-3" data-testid="photo-uploader">
      {value.length ? (
        <ul className="grid grid-cols-3 gap-2 sm:grid-cols-5">
          {value.map((url, i) => (
            <li key={url} className={cn("group relative aspect-[4/3] overflow-hidden rounded-lg border bg-muted", i === 0 && "ring-2 ring-foreground")}>
              {/* eslint-disable-next-line @next/next/no-img-element -- the agency's own uploads and links, any host */}
              <img src={url} alt={`Foto ${i + 1}`} className="size-full object-cover" loading="lazy" />
              {i === 0 ? (
                <span className="absolute bottom-1 left-1 rounded bg-foreground px-1.5 py-0.5 text-[10px] font-semibold text-background">Portada</span>
              ) : (
                <button type="button" onClick={() => onChange([url, ...value.filter((u) => u !== url)])} aria-label={`Usar la foto ${i + 1} de portada`}
                  className="absolute bottom-1 left-1 inline-flex items-center gap-1 rounded bg-background/90 px-1.5 py-0.5 text-[10px] font-medium hover:bg-background">
                  <Star className="size-3" aria-hidden /> Portada
                </button>
              )}
              <button type="button" onClick={() => onChange(value.filter((u) => u !== url))} aria-label={`Sacar la foto ${i + 1}`}
                className="absolute top-1 right-1 rounded-full bg-background/90 p-1 hover:bg-background">
                <X className="size-3.5" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      <div className="flex flex-wrap items-center gap-2">
        <input ref={input} type="file" accept="image/jpeg,image/png,image/webp" multiple hidden onChange={(e) => upload(e.target.files)} data-testid="photo-input" />
        <Button type="button" variant="outline" className="h-9" disabled={uploading > 0 || room <= 0} onClick={() => input.current?.click()}>
          <ImagePlus aria-hidden /> {uploading > 0 ? `Subiendo ${uploading}…` : "Subir fotos"}
        </Button>
        <span className="text-xs text-muted-foreground">{value.length} de {MAX_PHOTOS}. La primera es la portada que ven los compradores.</span>
      </div>
      <div className="flex gap-2">
        <Input aria-label="Link de una foto" placeholder="o pegá un link https://…" value={link} maxLength={1000} onChange={(e) => setLink(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addLink(); } }} className="h-9 max-w-sm" />
        <Button type="button" variant="ghost" className="h-9" disabled={!link.trim()} onClick={addLink}>Agregar</Button>
      </div>
      {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}
    </div>
  );
}

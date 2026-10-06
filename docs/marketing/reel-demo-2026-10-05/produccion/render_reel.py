"""Render local de un reel a partir de capturas reales y una banda sonora original.

Las capturas deben venir del navegador autorizado. Este script no navega ni
accede a cuentas, no simula interfaces y no modifica imágenes originales.
"""
from pathlib import Path
import json
import math
import subprocess
import sys
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE / "dependencias"))
import imageio_ffmpeg

W, H, FPS, SECONDS = 1080, 1920, 30, 24
NAVY, YELLOW, PAPER, MUTED = "#14283e", "#f4d447", "#fbfbf8", "#637487"
FONT_PATH = "C:/Windows/Fonts/bahnschrift.ttf"

def font(size, weight=700):
    f = ImageFont.truetype(FONT_PATH, size)
    f.set_variation_by_axes([weight, 100])
    return f

FONTS = {size: font(size) for size in (28, 32, 36, 42, 48, 54, 62, 70, 82, 94, 112)}
def text(draw, xy, value, size=62, fill=NAVY):
    draw.text(xy, value, font=FONTS[size], fill=fill, stroke_width=0)

def wrapped(draw, value, x, y, size=82, maxwidth=860, gap=10, fill=NAVY):
    words = value.split()
    line = ""
    for word in words:
        proposed = (line + " " + word).strip()
        if line and draw.textlength(proposed, font=FONTS[size]) > maxwidth:
            text(draw, (x, y), line, size, fill)
            y += size + gap
            line = word
        else:
            line = proposed
    if line:
        text(draw, (x, y), line, size, fill)
        y += size + gap
    return y

def ease(t):
    t = min(1, max(0, t))
    return 1 - (1 - t) ** 3

def brand(draw, y=282):
    draw.rectangle((78, y, 295, y + 70), fill=YELLOW)
    text(draw, (92, y + 4), "S Auto", 54)
    text(draw, (319, y + 12), "Ese Auto", 42)

def make_audio():
    sr = 48000
    samples = int(SECONDS * sr)
    audio = np.zeros(samples, np.float64)
    rng = np.random.default_rng(20261005)
    beat = 60 / 112
    def add(at, signal, amp):
        start = int(at * sr)
        stop = min(samples, start + len(signal))
        if 0 <= start < samples:
            audio[start:stop] += signal[:stop-start] * amp
    for n in range(math.ceil(SECONDS / beat)):
        at = n * beat
        t = np.arange(int(sr * .28)) / sr
        pitch = 45 + 95 * np.exp(-t * 26)
        kick = np.sin(2 * np.pi * np.cumsum(pitch) / sr) * np.exp(-t * 16)
        add(at, kick, .28)
        if n % 2:
            t = np.arange(int(sr * .14)) / sr
            noise = rng.standard_normal(len(t))
            clap = (noise - np.roll(noise, 1)) * np.exp(-t * 40)
            add(at, clap, .055)
        for sub in (0, .5):
            t = np.arange(int(sr * .065)) / sr
            noise = rng.standard_normal(len(t))
            hat = (noise - np.roll(noise, 1)) * np.exp(-t * 85)
            add(at + sub * beat, hat, .025)
        notes = [130.813, 130.813, 164.814, 195.998, 110.0, 110.0, 146.832, 164.814]
        f = notes[n % len(notes)]
        t = np.arange(int(sr * .34)) / sr
        bass = (np.sin(2*np.pi*f*t) + .25*np.sin(4*np.pi*f*t)) * np.exp(-t*9)
        add(at + beat*.5, bass, .115)
    for n, at in enumerate(np.arange(2*beat, SECONDS, 2*beat)):
        melody = [523.251, 659.255, 587.33, 783.991, 659.255, 587.33, 523.251, 440.0]
        f = melody[n % len(melody)]
        t = np.arange(int(sr * .42)) / sr
        pluck = (np.sin(2*np.pi*f*t) + .2*np.sin(4*np.pi*f*t)) * np.exp(-t*11)
        add(at, pluck, .04)
    fade = np.minimum(np.arange(samples)/(sr*.08), 1)
    fade *= np.minimum(np.arange(samples)[::-1]/(sr*.25), 1)
    audio *= fade
    audio = np.tanh(audio * 1.3) * .7
    stereo = np.column_stack((audio, np.roll(audio, 80)*.97))
    path = ROOT / "audio-original.wav"
    with wave.open(str(path), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(sr)
        out.writeframes((stereo * 32767).astype("<i2").tobytes())
    return path

def intro_frame(t):
    frame = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(frame)
    text(d, (82, 292), "POV:", 62, YELLOW)
    offset = int((1 - ease(t / .25)) * 45)
    wrapped(d, "buscar un usado ya parece un trabajo", 78, 392 + offset, 94, 865, 8, PAPER)
    labels = ["MODELO", "PRECIO", "ZONA"]
    for i, label in enumerate(labels):
        y = 955 + i * 94
        d.rounded_rectangle((78, y, 930, y + 76), 13, fill="#263d55")
        text(d, (112, y + 14), label, 42, PAPER)
        angle = int(t*240 + i*85)
        d.arc((838, y+20, 878, y+60), angle, angle+290, fill=YELLOW, width=5)
    if t >= 1.65:
        d.rounded_rectangle((75, 810, 935, 912), 12, fill=YELLOW)
        text(d, (110, 829), "Otra vez los mismos filtros.", 48)
    return frame

def closing_frame(t):
    frame = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(frame)
    brand(d)
    y = wrapped(d, "Probá una búsqueda", 78, 440, 94, 860, 10)
    d.rectangle((76, y + 14, 936, y + 132), fill=YELLOW)
    text(d, (95, y + 22), "gratis por 3 días.", 82)
    text(d, (81, 838), "Con resumen diario.", 54)
    text(d, (81, 944), "Enlace en el perfil", 54)
    text(d, (81, 1043), "@eseauto.ar", 48)
    text(d, (81, 1150), "eseauto.com.ar", 42)
    return frame

def capture_frame(segment, local_t, elapsed):
    frame = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(frame)
    text(d, (78, 284), segment["step"], 32, MUTED)
    wrapped(d, segment["heading"], 78, 350, 70, 855, 4)
    src = segment["_image"]
    panels = segment.get("panels", [{"crop":segment.get("crop"),"bounds":[78,573,850,640]}])
    for info in panels:
        crop = info.get("crop")
        view = src.crop(tuple(crop)) if crop else src
        panel_x, panel_y, panel_w, panel_h = info["bounds"]
        fit = min(panel_w / view.width, panel_h / view.height)
        scale = fit * (.955 + .025 * ease(local_t / max(.5, segment["end"]-segment["start"])))
        sw, sh = round(view.width*scale), round(view.height*scale)
        resized = view.resize((sw, sh), Image.Resampling.LANCZOS)
        panel = Image.new("RGB", (panel_w, panel_h), "#f0f3f5")
        px, py = (panel_w-sw)//2, (panel_h-sh)//2
        panel.paste(resized, (px, py))
        frame.paste(panel, (panel_x, panel_y))
        d.rounded_rectangle((panel_x, panel_y, panel_x+panel_w, panel_y+panel_h), 14, outline="#bcc8d2", width=3)
        # Se señalan controles reales; no se simula un resultado ni una acción.
        focus = segment.get("focus")
        if focus and .6 < local_t < 2:
            fx, fy, fw, fh = focus
            ox = crop[0] if crop else 0
            oy = crop[1] if crop else 0
            rect = (panel_x+px+(fx-ox)*scale, panel_y+py+(fy-oy)*scale,
                    panel_x+px+(fx+fw-ox)*scale, panel_y+py+(fy+fh-oy)*scale)
            d.rounded_rectangle(rect, 8, outline=YELLOW, width=5)
    text(d, (78, 1222), segment.get("note",""), 28, MUTED)
    d.rectangle((78, 1260, 928, 1267), fill="#e3e8ed")
    d.rectangle((78, 1260, 78+int(850*elapsed/SECONDS), 1267), fill=YELLOW)
    return frame

def cover():
    frame = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(frame)
    brand(d, 480)
    wrapped(d, "Dejá de repetir la búsqueda.", 78, 680, 112, 850, 10)
    d.rectangle((78, 1080, 931, 1167), fill=YELLOW)
    text(d, (98, 1095), "Así funciona Ese Auto", 54)
    text(d, (81, 1240), "eseauto.com.ar", 42)
    frame.save(ROOT / "PORTADA_REEL.png")

if __name__ == "__main__":
    audio = make_audio()
    cover()
    if "--prepare-only" in sys.argv:
        print(json.dumps({"audio": str(audio), "cover": str(ROOT / "PORTADA_REEL.png"), "status": "awaiting_real_captures"}))
        sys.exit(0)
    manifest_path = ROOT / "ESCENAS.json"
    if not manifest_path.exists():
        raise SystemExit("Faltan capturas reales y ESCENAS.json; no se renderiza un recorrido inventado.")
    segments = json.loads(manifest_path.read_text(encoding="utf-8"))
    for segment in segments:
        assert segment["end"] > segment["start"]
        segment["_image"] = Image.open(ROOT / segment["file"]).convert("RGB")
    assert segments[0]["start"] == 3 and segments[-1]["end"] == 20
    for current, nxt in zip(segments, segments[1:]):
        assert current["end"] == nxt["start"]
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    target = ROOT / "ESE_AUTO_REEL_DEMO_1080x1920.mp4"
    assert not target.exists(), "El video ya existe; usar una nueva versión."
    cmd = [ffmpeg, "-y", "-f", "rawvideo", "-vcodec", "rawvideo", "-s", f"{W}x{H}",
           "-pix_fmt", "rgb24", "-r", str(FPS), "-i", "-", "-i", str(audio),
           "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-t", str(SECONDS), str(target)]
    with (ROOT / "RENDER.log").open("wb") as log:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=log, stderr=log)
        try:
            for frame_number in range(FPS * SECONDS):
                t = frame_number / FPS
                if t < 3:
                    frame = intro_frame(t)
                elif t >= 20:
                    frame = closing_frame(t - 20)
                else:
                    seg = next(x for x in segments if x["start"] <= t < x["end"])
                    frame = capture_frame(seg, t-seg["start"], t)
                proc.stdin.write(frame.tobytes())
                if frame_number % 90 == 0:
                    print(f"Render {frame_number}/{FPS*SECONDS}", flush=True)
            proc.stdin.close()
            assert proc.wait() == 0, "Revisar RENDER.log"
        except:
            proc.kill()
            raise
    print(json.dumps({"video": str(target), "duration": SECONDS, "fps": FPS, "dimensions": [W, H], "bytes": target.stat().st_size}))

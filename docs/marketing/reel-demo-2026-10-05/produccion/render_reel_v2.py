"""Segunda edición: movimiento de marca y música original de 120 BPM.

Reutiliza capturas y guion de la primera edición. No accede a cuentas ni
representa clics o resultados que no hayan ocurrido. Conserva la edición V1.
"""
from pathlib import Path
import json
import math
import subprocess
import sys
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import render_reel as base

ROOT, HERE = base.ROOT, base.HERE
W, H, FPS, SECONDS = base.W, base.H, base.FPS, base.SECONDS
NAVY, YELLOW, PAPER, MUTED = base.NAVY, base.YELLOW, base.PAPER, base.MUTED
FFMPEG = base.imageio_ffmpeg.get_ffmpeg_exe()
BOUNDARIES = [0, 3, 5, 8, 10, 12, 16, 20, 24]
TRANSITIONS = {1: "diagonal", 2: "push", 3: "vertical", 4: "zoom", 5: "diagonal", 6: "zoom", 7: "vertical"}
TRANSITION_LENGTH = .3
SCENES = json.loads((ROOT / "ESCENAS.json").read_text(encoding="utf-8"))
for scene in SCENES:
    scene["_image"] = Image.open(ROOT / scene["file"]).convert("RGB")
# Un poco más de margen arriba del rótulo Kilometraje, sin modificar la captura.
SCENES[2]["panels"][2]["crop"][1] = 631


def progress(value):
    return min(1.0, max(0.0, value))


def smooth(value):
    p = progress(value)
    return p * p * (3 - 2 * p)


def reveal(canvas, layer, at, duration=.3, offset=32):
    p = base.ease(at / duration)
    if p <= 0:
        return
    shifted = Image.new("RGBA", (W, H))
    shifted.alpha_composite(layer, (0, round(offset * (1 - p))))
    shifted.putalpha(shifted.getchannel("A").point(lambda a: round(a * p)))
    canvas.alpha_composite(shifted)


def layer_text(canvas, value, xy, size, at, fill=NAVY, duration=.3, offset=30):
    layer = Image.new("RGBA", (W, H))
    base.text(ImageDraw.Draw(layer), xy, value, size, fill)
    reveal(canvas, layer, at, duration, offset)


def make_audio():
    """Instrumental propio: house ligero, bajo sincopado y cortes a negras.

    Las transiciones duran 300 ms y empiezan en segundos enteros, que coinciden
    con negras a 120 BPM. Los efectos son síntesis original, no música bajada.
    """
    sr = 48000
    count = SECONDS * sr
    mix = np.zeros((count, 2), np.float64)
    rng = np.random.default_rng(202610052)
    beat = .5

    def add(at, signal, amp=1, pan=0):
        start = round(at * sr)
        if start < 0:
            signal = signal[-start:]
            start = 0
        end = min(count, start + len(signal))
        if end <= start:
            return
        signal = signal[:end - start]
        if signal.ndim == 1:
            gains = np.array([math.sqrt((1 - pan) / 2), math.sqrt((1 + pan) / 2)])
            mix[start:end] += signal[:, None] * gains * amp
        else:
            mix[start:end] += signal * amp

    def clock(duration):
        return np.arange(round(sr * duration)) / sr

    def envelope(t, attack=.005, decay=8):
        return np.minimum(t / attack, 1) * np.exp(-t * decay)

    def midi(note):
        return 440 * 2 ** ((note - 69) / 12)

    def bright_noise(duration, decay, smoothing=5):
        t = clock(duration)
        noise = rng.standard_normal(len(t))
        low = np.convolve(noise, np.ones(smoothing) / smoothing, mode="same")
        high = low - np.convolve(low, np.ones(51) / 51, mode="same")
        return t, high * np.exp(-t * decay)

    # Dm - Bb - F - C, cuatro compases por vuelta. Instrumentos por separado.
    roots = [38, 34, 41, 36]
    chords = [[62, 65, 69], [58, 62, 65], [60, 65, 69], [60, 64, 67]]
    for n in range(48):
        at = n * beat
        bar, slot = n // 4, n % 4
        energy = .68 if at < 3 else 1
        # Bombo con cuerpo grave, caída de tono y ataque corto.
        t = clock(.39)
        freq = 49 + 105 * np.exp(-t * 38)
        phase = 2 * np.pi * np.cumsum(freq) / sr
        kick = np.sin(phase) * np.exp(-t * 13)
        kick += .16 * np.sin(2 * phase) * np.exp(-t * 42)
        add(at, np.tanh(kick * 1.5), .68 * energy)
        if slot in (1, 3):
            t, noise = bright_noise(.2, 24, 3)
            clap = noise * 1.1
            for shift in (.009, .018):
                moved = np.zeros(len(noise))
                lag = round(shift * sr)
                moved[lag:] = noise[:-lag]
                clap += moved * .45
            clap += .12 * np.sin(2 * np.pi * 180 * t) * np.exp(-t * 38)
            add(at, clap, .31 * energy)
        for half in (0, .5):
            _, hat = bright_noise(.085, 65, 2)
            add(at + half * beat, hat, (.12 if half else .07) * energy, -.3 if n % 2 else .3)
        if at >= 3:
            _, hat = bright_noise(.19, 19, 3)
            add(at + beat * .5, hat, .065, .35)
            # Dos notas sincopadas, con huecos para el bombo.
            root = roots[bar % 4]
            for sub, note, length in ((.33, root, .20), (.77, root + (12 if slot == 3 else 0), .13)):
                t = clock(length)
                f = midi(note)
                bass = sum(np.sin(2 * np.pi * f * harmonic * t) / harmonic ** 1.55 for harmonic in range(1, 7))
                bass *= envelope(t, .007, 9)
                add(at + sub * beat, np.tanh(bass * 1.35), .30)
            # Acordes cortos con dos osciladores levemente desafinados y apertura estéreo.
            if slot in (0, 2, 3):
                t = clock(.33)
                left = np.zeros(len(t))
                right = np.zeros(len(t))
                for note in chords[bar % 4]:
                    f = midi(note)
                    for h in range(1, 5):
                        left += np.sin(2 * np.pi * f * h * .998 * t) / h ** 1.8
                        right += np.sin(2 * np.pi * f * h * 1.002 * t + .08) / h ** 1.8
                stab = np.column_stack((left, right)) * envelope(t, .013, 13)[:, None] / 3
                add(at + .25, stab, .22)
            if slot in (1, 3):
                t = clock(.24)
                f = midi(chords[bar % 4][(bar + slot) % 3] + 12)
                pluck = (np.sin(2 * np.pi * f * t) + .23 * np.sin(4 * np.pi * f * t)) * envelope(t, .006, 17)
                add(at + .125, pluck, .11, -.45 if slot == 1 else .45)
        # Pequeños fills antes de cambios de sección, sin saturar el tutorial.
        if at in (7.5, 11.5, 19.5):
            for sub in (.5, .75):
                _, snare = bright_noise(.1, 34, 4)
                add(at + sub * beat, snare, .15, -.15 if sub == .5 else .15)

    # Barridos cortos e impactos sincronizados con los siete cambios de escena.
    for boundary in BOUNDARIES[1:-1]:
        t = clock(.29)
        noise = rng.standard_normal(len(t))
        noise = np.convolve(noise, np.ones(13) / 13, mode="same")
        sweep = noise * np.sin(np.pi * t / .29) ** 1.2
        stereo = np.column_stack((sweep * np.linspace(1, .3, len(t)), sweep * np.linspace(.3, 1, len(t))))
        add(boundary - .11, stereo, .23)
        t = clock(.22)
        impact = np.sin(2 * np.pi * (110 * t - 85 * t * t)) * np.exp(-t * 24)
        add(boundary, impact, .10)

    fade = np.minimum(np.arange(count) / (sr * .025), 1)
    fade *= np.minimum(np.arange(count)[::-1] / (sr * .14), 1)
    mix *= fade[:, None]
    mix = np.tanh(mix * 1.2)
    mix *= .88 / np.max(np.abs(mix))
    raw = ROOT / "audio-v2-mezcla.wav"
    normalized = ROOT / "audio-v2-120bpm.wav"
    with wave.open(str(raw), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(sr)
        out.writeframes((mix * 32767).astype("<i2").tobytes())
    # Dos pasadas para que la base tenga volumen consistente sin picos saturados.
    measured = subprocess.run([FFMPEG, "-hide_banner", "-i", str(raw), "-af",
        "loudnorm=I=-16:TP=-1.5:LRA=7:print_format=json", "-f", "null", "-"], capture_output=True, text=True, check=True)
    info = json.JSONDecoder().raw_decode(measured.stderr[measured.stderr.rfind("{"):])[0]
    filtering = ("loudnorm=I=-16:TP=-1.5:LRA=7:linear=true:"
        f"measured_I={info['input_i']}:measured_TP={info['input_tp']}:"
        f"measured_LRA={info['input_lra']}:measured_thresh={info['input_thresh']}:"
        f"offset={info['target_offset']}:print_format=json")
    result = subprocess.run([FFMPEG, "-hide_banner", "-y", "-i", str(raw), "-af", filtering,
        "-ar", str(sr), "-c:a", "pcm_s16le", str(normalized)], capture_output=True, text=True, check=True)
    output_info = json.JSONDecoder().raw_decode(result.stderr[result.stderr.rfind("{"):])[0]
    (ROOT / "AUDIO_V2_MEDICION.json").write_text(json.dumps(output_info, indent=2) + "\n", encoding="utf-8")
    return normalized


def intro_frame(t):
    frame = Image.new("RGBA", (W, H), NAVY)
    d = ImageDraw.Draw(frame)
    # Marcas geométricas suaves: el texto sigue llevando el foco.
    drift = round(18 * math.sin(t * .7))
    d.ellipse((840 + drift, 185, 1270 + drift, 615), outline="#294057", width=2)
    d.line((54, 1290, 1010, 1290), fill="#294057", width=2)
    layer_text(frame, "POV:", (82, 292), 62, t, YELLOW, .18, 15)
    lines = ["buscar un usado", "ya parece", "un trabajo"]
    for i, value in enumerate(lines):
        layer_text(frame, value, (78, 392 + i * 102), 94, t - .10 - i * .13, PAPER, .32, 44)
    under = round(530 * base.ease((t - .80) / .28))
    if under:
        ImageDraw.Draw(frame).rectangle((81, 699, 81 + under, 706), fill=YELLOW)
    for i, label in enumerate(("MODELO", "PRECIO", "ZONA")):
        p = base.ease((t - .60 - i * .14) / .35)
        if p <= 0:
            continue
        layer = Image.new("RGBA", (W, H))
        ld = ImageDraw.Draw(layer)
        x, y = 78 + round((1 - p) * 100), 955 + i * 94
        ld.rounded_rectangle((x, y, x + 852, y + 76), 13, fill="#263d55")
        base.text(ld, (x + 34, y + 14), label, 42, PAPER)
        angle = round(t * 300 + i * 85)
        ld.arc((x + 760, y + 20, x + 800, y + 60), angle, angle + 280, fill=YELLOW, width=5)
        layer.putalpha(layer.getchannel("A").point(lambda a: round(a * p)))
        frame.alpha_composite(layer)
    if t > 1.65:
        layer = Image.new("RGBA", (W, H))
        ld = ImageDraw.Draw(layer)
        ld.rounded_rectangle((75, 810, 935, 912), 12, fill=YELLOW)
        base.text(ld, (110, 829), "Otra vez los mismos filtros.", 48)
        reveal(frame, layer, t - 1.65, .24, 28)
    return frame.convert("RGB")


def capture_frame(scene, local, elapsed):
    frame = Image.new("RGBA", (W, H), PAPER)
    header = Image.new("RGBA", (W, H))
    d = ImageDraw.Draw(header)
    base.text(d, (78, 284), scene["step"], 32, MUTED)
    d.rounded_rectangle((78, 337, 185, 343), 3, fill=YELLOW)
    base.wrapped(d, scene["heading"], 78, 366, 70, 855, 4)
    reveal(frame, header, local - .06, .28, 20)
    panels = scene.get("panels", [{"crop": scene["crop"], "bounds": [78, 573, 850, 640]}]) if "panels" not in scene else scene["panels"]
    src = scene["_image"]
    duration = scene["end"] - scene["start"]
    for i, info in enumerate(panels):
        p = base.ease((local - .15 - i * .085) / .34)
        if p <= 0:
            continue
        crop = info["crop"]
        view = src.crop(tuple(crop))
        x, y, width, height = info["bounds"]
        y += round(42 * (1 - p))
        fit = min(width / view.width, height / view.height)
        scale = fit * (.956 + .025 * smooth(local / duration))
        sw, sh = round(view.width * scale), round(view.height * scale)
        px, py = (width - sw) // 2, (height - sh) // 2
        resized = view.resize((sw, sh), Image.Resampling.LANCZOS)
        panel = Image.new("RGBA", (width, height), "#f0f3f5")
        panel.paste(resized, (px, py))
        layer = Image.new("RGBA", (W, H))
        ld = ImageDraw.Draw(layer)
        ld.rounded_rectangle((x + 3, y + 9, x + width + 3, y + height + 9), 15, fill="#e6ebef")
        layer.alpha_composite(panel, (x, y))
        ld.rounded_rectangle((x, y, x + width, y + height), 14, outline="#c0ccd5", width=2)
        focus = scene.get("focus")
        if focus and 1.0 < local < 2.7:
            fx, fy, fw, fh = focus
            padding = 3 + 3 * math.sin((local - 1) * 2 * math.pi)
            rect = (x + px + (fx - crop[0]) * scale - padding, y + py + (fy - crop[1]) * scale - padding,
                    x + px + (fx + fw - crop[0]) * scale + padding, y + py + (fy + fh - crop[1]) * scale + padding)
            ld.rounded_rectangle(rect, 9, outline=YELLOW, width=5)
        layer.putalpha(layer.getchannel("A").point(lambda a: round(a * p)))
        frame.alpha_composite(layer)
    layer_text(frame, scene["note"], (78, 1222), 28, local - .45, MUTED, .25, 12)
    d = ImageDraw.Draw(frame)
    d.rounded_rectangle((78, 1260, 928, 1267), 3, fill="#e3e8ed")
    d.rounded_rectangle((78, 1260, 78 + max(4, round(850 * elapsed / SECONDS)), 1267), 3, fill=YELLOW)
    return frame.convert("RGB")


def closing_frame(t):
    frame = Image.new("RGBA", (W, H), PAPER)
    layer = Image.new("RGBA", (W, H))
    base.brand(ImageDraw.Draw(layer))
    reveal(frame, layer, t - .07, .28, 25)
    layer_text(frame, "Probá una", (78, 440), 94, t - .14, duration=.3, offset=35)
    layer_text(frame, "búsqueda", (78, 544), 94, t - .24, duration=.3, offset=35)
    p = base.ease((t - .46) / .36)
    if p:
        layer = Image.new("RGBA", (W, H))
        d = ImageDraw.Draw(layer)
        d.rounded_rectangle((76, 666, 936, 776), 10, fill=YELLOW)
        base.text(d, (95, 683), "gratis por 3 días.", 82)
        mask = Image.new("L", (W, H))
        ImageDraw.Draw(mask).rectangle((0, 0, 76 + round(860 * p), H), fill=255)
        layer.putalpha(Image.composite(layer.getchannel("A"), Image.new("L", (W, H)), mask))
        frame.alpha_composite(layer)
    layer_text(frame, "Con resumen diario.", (81, 838), 54, t - .80, offset=22)
    layer = Image.new("RGBA", (W, H))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle((78, 944, 928, 1040), 15, fill=NAVY)
    base.text(d, (103, 962), "Enlace en el perfil", 54, PAPER)
    d.line((856, 1007, 889, 974), fill=YELLOW, width=6)
    d.line((865, 974, 889, 974, 889, 998), fill=YELLOW, width=6)
    reveal(frame, layer, t - 1.02, .32, 25)
    layer_text(frame, "@eseauto.ar", (81, 1083), 48, t - 1.20, offset=18)
    layer_text(frame, "eseauto.com.ar", (81, 1162), 42, t - 1.37, offset=18)
    d = ImageDraw.Draw(frame)
    p = base.ease((t - 1.7) / .45)
    if p:
        d.rectangle((81, 1222, 81 + round(298 * p), 1226), fill=YELLOW)
    # Respiración suave del borde del CTA al beat, sin hacer parpadear el texto.
    if t >= 1.7:
        pulse = .5 + .5 * math.cos(t * 4 * math.pi)
        color = (round(199 + 45 * pulse), round(176 + 36 * pulse), 71)
        d.rounded_rectangle((78, 944, 928, 1040), 15, outline=color, width=2)
    return frame.convert("RGB")


def scene_frame(index, local):
    if index == 0:
        return intro_frame(local)
    if index == 7:
        return closing_frame(local)
    return capture_frame(SCENES[index - 1], local, BOUNDARIES[index] + local)


def zoom(frame, factor):
    if abs(factor - 1) < .001:
        return frame
    sw, sh = round(W * factor), round(H * factor)
    large = frame.resize((sw, sh), Image.Resampling.BICUBIC)
    # El anclaje sigue al centro del contenido, no al centro vacío del formato.
    x = round((sw - W) * .47)
    y = round((sh - H) * .43)
    return large.crop((x, y, x + W, y + H))


def transition(old, new, p, style):
    q = smooth(p)
    if style == "zoom":
        old = zoom(old, 1 + .065 * q)
        new = zoom(new, 1 + .055 * (1 - q))
        blur = 1.5 * math.sin(math.pi * q)
        if blur > .25:
            old = old.filter(ImageFilter.GaussianBlur(blur))
        return Image.blend(old, new, q)
    if style == "push":
        move = round(W * q)
        frame = Image.new("RGB", (W, H), PAPER)
        frame.paste(old, (-move, 0))
        frame.paste(new, (W - move, 0))
        if 0 < move < W:
            ImageDraw.Draw(frame).rectangle((W - move - 12, 0, W - move, H), fill=YELLOW)
        return frame
    if style == "vertical":
        edge = round((H + 65) * (1 - q))
        frame = old.copy()
        if edge < H:
            frame.paste(new.crop((0, max(0, edge), W, H)), (0, max(0, edge)))
        ImageDraw.Draw(frame).rectangle((0, edge - 34, W, edge - 9), fill=YELLOW)
        ImageDraw.Draw(frame).rectangle((0, edge - 9, W, edge), fill=NAVY)
        return frame
    # Barrido diagonal con borde amarillo breve; no se tapa el contenido al final.
    edge = -260 + (W + 520) * q
    slope = 210
    mask = Image.new("L", (W, H))
    md = ImageDraw.Draw(mask)
    md.polygon([(0, 0), (edge + slope, 0), (edge - slope, H), (0, H)], fill=255)
    frame = Image.composite(new, old, mask)
    d = ImageDraw.Draw(frame)
    d.polygon([(edge + slope, 0), (edge + slope + 24, 0), (edge - slope + 24, H), (edge - slope, H)], fill=YELLOW)
    return frame


def frame_at(t):
    index = next(i for i in range(8) if BOUNDARIES[i] <= t < BOUNDARIES[i + 1])
    local = t - BOUNDARIES[index]
    incoming = scene_frame(index, local)
    if index and local < TRANSITION_LENGTH:
        prior_duration = BOUNDARIES[index] - BOUNDARIES[index - 1]
        outgoing = scene_frame(index - 1, prior_duration - 1 / FPS)
        return transition(outgoing, incoming, local / TRANSITION_LENGTH, TRANSITIONS[index])
    return incoming


if __name__ == "__main__":
    if "--preview-only" in sys.argv:
        directory = HERE / "revision-v2"
        directory.mkdir(exist_ok=True)
        moments = [1.0, 2.5, 3.1333, 5.1333, 6.5, 8.1333, 9.0, 10.1333, 11.0, 12.1333, 14.0, 16.1333, 18.0, 20.1333, 21.0, 22.5]
        thumbs = []
        for t in moments:
            frame = frame_at(t)
            frame.save(directory / f"{t:05.2f}.png")
            thumb = frame.resize((270, 480), Image.Resampling.LANCZOS)
            tile = Image.new("RGB", (270, 515), "#dce3e9")
            tile.paste(thumb)
            ImageDraw.Draw(tile).text((12, 483), f"{t:.2f} s", font=base.FONTS[28], fill=NAVY)
            thumbs.append(tile)
        contact = Image.new("RGB", (270 * 4, 515 * 4), "#dce3e9")
        for n, tile in enumerate(thumbs):
            contact.paste(tile, ((n % 4) * 270, (n // 4) * 515))
        contact.save(directory / "CONTACTO.png")
        print(json.dumps({"preview": str(directory / "CONTACTO.png"), "frames": len(moments)}))
        sys.exit(0)
    audio = make_audio()
    target = ROOT / "ESE_AUTO_REEL_DEMO_V2_1080x1920.mp4"
    assert not target.exists(), "La versión V2 ya existe; no sobrescribir sin revisar."
    cmd = [FFMPEG, "-y", "-f", "rawvideo", "-vcodec", "rawvideo", "-s", f"{W}x{H}",
           "-pix_fmt", "rgb24", "-r", str(FPS), "-i", "-", "-i", str(audio),
           "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-t", str(SECONDS), str(target)]
    with (ROOT / "RENDER_V2.log").open("wb") as log:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=log, stderr=log)
        try:
            for number in range(FPS * SECONDS):
                proc.stdin.write(frame_at(number / FPS).tobytes())
                if number % 90 == 0:
                    print(f"Render V2 {number}/{FPS * SECONDS}", flush=True)
            proc.stdin.close()
            assert proc.wait() == 0, "Revisar RENDER_V2.log"
        except BaseException:
            proc.kill()
            raise
    print(json.dumps({"video": str(target), "duration": SECONDS, "fps": FPS, "dimensions": [W, H], "bytes": target.stat().st_size}))

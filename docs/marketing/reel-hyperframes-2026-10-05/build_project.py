"""Author the HyperFrames project from frozen, authentic screenshots.

No rasterized replacement renderer: HyperFrames owns seeking and export.
UI images are native 3x renders of frozen, authentic DOM, fonts, and photos.
Phone and camera choreography adapts official registry motion primitives.
"""
from pathlib import Path
import json
from PIL import Image

ROOT = Path(__file__).resolve().parent
COMPS = ROOT / "compositions"
COMMON = """
*{box-sizing:border-box}h1,h2,p{margin:0}
.scene{position:absolute;inset:0;width:100%;height:100%;overflow:hidden;perspective:1800px;color:#fbfbf8}
.world{position:absolute;inset:0;transform-style:preserve-3d}
.eyebrow{position:absolute;left:78px;top:315px;font-size:32px;letter-spacing:2px;font-weight:650;color:#f4d447}
.headline{position:absolute;left:78px;top:370px;width:850px;font-size:94px;line-height:1.04;font-weight:750;letter-spacing:-2px}
.line{display:block;position:relative;width:100%;min-height:102px}
.note{position:absolute;left:78px;top:1350px;width:850px;font-size:28px;line-height:1.25;color:#cad4dd}
.view{position:relative;overflow:hidden;background:#fbfbf8;border-radius:18px}
.view img{display:block;width:100%;height:100%;object-fit:contain;image-rendering:auto}
.panel{position:absolute;transform-style:flat;border:3px solid #a5b5c5;border-radius:21px;box-shadow:0 28px 70px #07132188}
.underline{position:absolute;height:8px;background:#f4d447;transform-origin:0 50%}
"""


def capture(name, width, id="", extra=""):
    image_path = ROOT / 'assets' / 'capturas-hd' / f'{name}.png'
    with Image.open(image_path) as source:
        source_width, source_height = source.size
    assert source_width >= width * 1.12, 'Capture must stay sharp during camera zooms'
    height = source_height * width / source_width
    ident = f' id="{id}"' if id else ""
    return (f'<div{ident} class="view" style="width:{width}px;height:{height:.2f}px;{extra}">'
            f'<img id="capture-{name}" src="assets/capturas-hd/{name}.png" '
            f'alt="Componente completo de Ese Auto, capturado en alta definicion"></div>')


def scene(name, duration, css, markup, js):
    text = f'''<!doctype html><html lang="es"><head><meta charset="utf-8"></head><body><template>
<style>#{name}{{position:absolute;inset:0;width:100%;height:100%;overflow:hidden}}{COMMON}{css}</style>
<div id="{name}" data-composition-id="{name}" data-duration="{duration}" data-width="1080" data-height="1920">
<section id="{name}-clip" class="scene clip" data-start="0" data-duration="{duration}" data-track-index="1"><div class="world">{markup}</div></section>
</div><script>(function(){{const root=document.getElementById('{name}');const tl=gsap.timeline({{paused:true}});
const q=s=>root.querySelectorAll(s);{js}window.__timelines['{name}']=tl;}})();</script>
</template></body></html>'''
    (COMPS / f"{name}.html").write_text(text, encoding="utf-8")


def build():
    COMPS.mkdir(exist_ok=True)
    scene("ea-problema", 3, """
    .hook{position:absolute;left:78px;top:365px;width:850px;font-size:110px;line-height:1.02;font-weight:750;letter-spacing:-3px}
    .hook-line{display:block;width:850px;height:120px}.hook-line:last-child{color:#f4d447}
    .loop-card{position:absolute;left:95px;top:885px;width:790px;height:126px;border:2px solid #879bb0;border-radius:18px;background:#263d55;display:flex;align-items:center;padding:28px 42px;font-size:46px;font-weight:650}
    .loop-card:nth-child(2){top:1045px;left:130px}.loop-card:nth-child(3){top:1205px;left:78px}
    .loop-card svg{margin-left:auto;width:48px;height:48px;flex:none}.card-stack{position:absolute;inset:0;transform-style:preserve-3d}
    """, """
    <div class="eyebrow" id="problem-label">¿BUSCANDO UN USADO?</div>
    <h1 class="hook"><span class="hook-line">Otra vez</span><span class="hook-line">los mismos</span><span class="hook-line">filtros.</span></h1>
    <div class="card-stack">
    """ + "".join(f'''<div class="loop-card"><span>{label}</span><svg viewBox="0 0 48 48" aria-hidden="true"><path d="M38 19A15 15 0 1 0 38 30M38 8v12H26" fill="none" stroke="#f4d447" stroke-width="4" stroke-linecap="round"/></svg></div>''' for label in ("MODELO", "PRESUPUESTO", "ZONA")) + "</div>", """
    tl.fromTo(q('.hook-line'),{y:180,rotationX:-45,opacity:0},{y:0,rotationX:0,opacity:1,duration:.56,stagger:.13,ease:'power4.out'},.02);
    tl.fromTo(q('.eyebrow'),{x:-180,opacity:0},{x:0,opacity:1,duration:.35,ease:'power2.out'},0);
    tl.fromTo(q('.loop-card'),{x:1000,z:-600,rotationY:-50,opacity:0},{x:0,z:0,rotationY:-7,opacity:1,duration:.65,stagger:.16,ease:'back.out(1.2)'},.40);
    tl.to(q('.loop-card'),{x:-35,y:-20,rotationY:5,duration:1.4,stagger:.08,ease:'sine.inOut'},1.05);
    tl.to(q('.loop-card svg'),{rotation:270,duration:1.75,ease:'none'},.7);
    tl.to(q('.eyebrow'),{opacity:0,duration:.16},2.05);
    tl.to(q('.hook'),{scale:1.08,y:-50,duration:.7,ease:'power2.in'},2.25);
    tl.to(q('.world'),{z:-800,rotationY:30,x:-900,opacity:0,duration:.45,ease:'power3.in'},2.55);
    """);

    phone = capture("01-formulario-vacio", 440, "search-empty")
    written = capture("02-busqueda-escrita", 840, "search-written")
    scene("ea-busqueda", 5, """
    .phone-stage{position:absolute;left:266px;top:570px;width:480px;height:780px;transform-style:preserve-3d;transform-origin:50% 40%}
    .hardware{position:absolute;inset:0;border:4px solid #91a2b4;border-radius:68px;background:#263d55;box-shadow:45px 50px 90px #071321bb,inset 0 0 0 9px #0e1d30}
    .phone-surface{position:absolute;left:20px;top:55px;width:440px;height:655px;border-radius:46px;background:#fbfbf8;overflow:hidden}
    #search-empty{position:absolute;left:0;top:55px}
    .cutout{position:absolute;left:177px;top:21px;width:125px;height:20px;border-radius:20px;background:#0b1728}
    .written-panel{left:78px;top:635px;width:846px;transform-origin:50% 50%}
    .search-focus{position:absolute;left:43px;top:516px;width:244px;height:78px;border:7px solid #f4d447;border-radius:16px;pointer-events:none}
    """, f'''
    <div class="eyebrow">01 · TU BÚSQUEDA</div><h2 class="headline"><span class="line">Contá qué auto</span><span class="line">buscás.</span></h2>
    <div class="phone-stage"><div class="hardware"></div><div class="phone-surface">{phone}</div><div class="cutout"></div></div>
    <div class="panel written-panel">{written}<div class="search-focus"></div></div>
    <p class="note">Modelo, presupuesto y zona · revisá antes de guardar.</p>
    ''', """
    // Adaptación del recurso oficial parallax-device-dive con pantalla auténtica.
    tl.fromTo(q('.phone-stage'),{y:480,z:-600,scale:.76,rotationX:22,rotationY:-38,opacity:0},{y:0,z:0,scale:1,rotationX:5,rotationY:-13,opacity:1,duration:.75,ease:'power3.out'},0);
    tl.fromTo(q('.headline .line'),{x:-400,opacity:0},{x:0,opacity:1,duration:.48,stagger:.12,ease:'power4.out'},.12);
    tl.fromTo(q('.eyebrow'),{y:-50,opacity:0},{y:0,opacity:1,duration:.3},.1);
    tl.to(q('.phone-stage'),{scale:1.32,y:125,rotationX:0,rotationY:0,duration:.65,ease:'power2.inOut'},1.05);
    tl.to(q('.phone-stage'),{x:-560,scale:.75,rotationY:45,opacity:0,duration:.42,ease:'power3.inOut'},1.8);
    tl.fromTo(q('.written-panel'),{x:190,y:130,z:-300,scale:.64,rotationY:-35,opacity:0},{x:0,y:0,z:0,scale:1,rotationY:0,opacity:1,duration:.55,ease:'power4.out'},2.1);
    tl.to(q('.written-panel'),{scale:1.045,y:-14,duration:1.4,ease:'sine.inOut'},2.65);
    tl.fromTo(q('.search-focus'),{opacity:0,scale:1.14},{opacity:1,scale:1,duration:.35,ease:'power2.out'},3.0);
    tl.to(q('.search-focus'),{opacity:0,duration:.25},4.15);
    tl.fromTo(q('.note'),{x:150,opacity:0},{x:0,opacity:1,duration:.4},2.65);
    tl.to(q('.written-panel'),{x:1000,rotationY:35,opacity:0,duration:.45,ease:'power3.in'},4.55);
    tl.to(q('.headline,.note,.eyebrow'),{opacity:0,y:-45,duration:.3},4.7);
    """);

    model = capture("03-modelo", 820)
    year = capture("03-anio", 820)
    km = capture("03-kilometraje", 820)
    money = capture("04-precio", 840)
    zone = capture("04-zona", 840)
    scene("ea-filtros", 4, """
    .filter-model{left:78px;top:630px}.filter-year{left:78px;top:945px}.filter-km{left:78px;top:1130px}
    .filter-group,.zone-group{position:absolute;inset:0;transform-style:flat;perspective:1800px}
    .money{left:78px;top:680px}.zone{left:78px;top:910px}
    #zone-title{position:absolute;left:78px;top:370px;width:850px;font-size:94px;line-height:1.04;font-weight:750;letter-spacing:-2px}
    """, f'''
    <div class="eyebrow">02 · LOS FILTROS</div><h2 class="headline" id="filters-title"><span class="line">Revisá lo que</span><span class="line">entendimos.</span></h2>
    <h2 id="zone-title"><span class="line">Ajustá presupuesto</span><span class="line">y zona.</span></h2>
    <div class="filter-group"><div class="panel filter-model">{model}</div><div class="panel filter-year">{year}</div><div class="panel filter-km">{km}</div></div>
    <div class="zone-group"><div class="panel money">{money}</div><div class="panel zone">{zone}</div></div>
    <p class="note">Podés corregir los filtros antes de guardar.</p>
    ''', """
    tl.fromTo(q('#filters-title,.eyebrow'),{x:-180,opacity:0},{x:0,opacity:1,duration:.4,ease:'power3.out'},.05);
    tl.fromTo(q('.filter-group .panel'),{x:-850,z:-450,rotationY:48,opacity:0},{x:0,z:0,rotationY:0,opacity:1,duration:.6,stagger:.19,ease:'power4.out'},.05);
    tl.to(q('.filter-model'),{y:-18,rotationY:-4,duration:.9,ease:'sine.inOut'},.8);
    tl.to(q('.filter-year,.filter-km'),{y:12,rotationY:4,duration:.8,ease:'sine.inOut'},1.05);
    tl.to(q('.filter-group'),{x:-1150,rotationY:-25,opacity:0,duration:.4,ease:'power3.in'},1.75);
    tl.to(q('#filters-title'),{x:-350,opacity:0,duration:.24},1.8);
    tl.fromTo(q('#zone-title'),{y:100,opacity:0},{y:0,opacity:1,duration:.45,ease:'power3.out'},2.0);
    tl.fromTo(q('.zone-group .panel'),{x:850,rotationY:-42,z:-300,opacity:0},{x:0,rotationY:0,z:0,opacity:1,duration:.6,stagger:.15,ease:'power4.out'},1.98);
    tl.to(q('.zone-group'),{y:-12,scale:1.02,duration:.8,ease:'sine.inOut'},2.7);
    tl.fromTo(q('.note'),{opacity:0},{opacity:1,duration:.3},.9);
    tl.to(q('.zone-group'),{y:-500,scale:.9,opacity:0,duration:.38,ease:'power3.in'},3.62);
    tl.to(q('#zone-title,.eyebrow,.note'),{opacity:0,duration:.25},3.75);
    """);

    result1 = capture("05-opcion-1", 780)
    result2 = capture("05-opcion-2", 780)
    scene("ea-opciones", 4, """
    .result-one{left:78px;top:630px}.result-two{left:78px;top:1000px}
    .results-stage{position:absolute;inset:0;transform-style:flat;perspective:1800px}
    """, f'''
    <div class="eyebrow">03 · LAS OPCIONES</div><h2 class="headline"><span class="line">Revisá las</span><span class="line">coincidencias.</span></h2>
    <div class="results-stage"><div class="panel result-one">{result1}</div><div class="panel result-two">{result2}</div></div>
    <p class="note" style="top:1390px">Búsqueda existente · datos del 5/10.</p>
    ''', """
    tl.fromTo(q('.headline .line'),{x:-450,skewX:8,opacity:0},{x:0,skewX:0,opacity:1,duration:.55,stagger:.1,ease:'power4.out'},0);
    tl.fromTo(q('.eyebrow'),{opacity:0},{opacity:1,duration:.3},.05);
    // Dos opciones auténticas, cada una con entrada y profundidad propias.
    tl.fromTo(q('.result-one'),{x:-1050,rotationY:38,z:-250,opacity:0},{x:0,rotationY:4,z:0,opacity:1,duration:.7,ease:'power4.out'},.1);
    tl.fromTo(q('.result-two'),{x:1050,rotationY:-38,z:-350,opacity:0},{x:0,rotationY:-4,z:0,opacity:1,duration:.7,ease:'power4.out'},.75);
    tl.to(q('.result-one'),{y:-40,x:-15,scale:.96,rotationY:0,duration:1.2,ease:'sine.inOut'},1.5);
    tl.to(q('.result-two'),{y:-30,x:8,scale:1.025,rotationY:0,duration:1.2,ease:'sine.inOut'},1.5);
    tl.fromTo(q('.note'),{opacity:0},{opacity:1,duration:.3},1.3);
    tl.to(q('.result-one'),{x:-1000,y:-120,opacity:0,duration:.35,ease:'power3.in'},3.3);
    tl.to(q('.result-two'),{y:-330,scale:1.32,opacity:0,duration:.5,ease:'power3.in'},3.5);
    tl.to(q('.headline,.eyebrow,.note'),{opacity:0,duration:.25},3.75);
    """);

    price = capture("06-precio-contexto", 840)
    scene("ea-precio", 4, """
    .price-stage{position:absolute;left:78px;top:650px;width:846px;transform-style:preserve-3d;transform-origin:50% 30%}
    .price-corner{position:absolute;inset:-13px;border:6px solid #f4d447;border-radius:28px;pointer-events:none}
    """, f'''
    <div class="eyebrow">04 · EL PRECIO</div><h2 class="headline"><span class="line">Mirá el precio</span><span class="line">en contexto.</span></h2>
    <div class="panel price-stage">{price}<div class="price-corner"></div></div>
    <p class="note">Comparamos precios publicados de autos parecidos.</p>
    ''', """
    tl.fromTo(q('.headline .line'),{y:120,opacity:0},{y:0,opacity:1,duration:.5,stagger:.12,ease:'power3.out'},.05);
    tl.fromTo(q('.eyebrow'),{opacity:0},{opacity:1,duration:.3},.05);
    // Cámara hacia el precio pedido; después abre para mostrar los comparables.
    // Geometría de enfoque adaptada de ui-focus-zoom, ancla medida en la captura.
    tl.fromTo(q('.price-stage'),{y:220,scale:.8,rotationX:28,opacity:0},{y:0,scale:1,rotationX:0,opacity:1,duration:.6,ease:'power4.out'},0);
    tl.to(q('.price-stage'),{scale:1.12,y:-36,duration:.9,ease:'power2.inOut'},.7);
    tl.to(q('.price-stage'),{scale:1,y:0,rotationY:-3,duration:.8,ease:'power2.inOut'},1.7);
    tl.fromTo(q('.price-corner'),{opacity:0,scale:1.04},{opacity:1,scale:1,duration:.4,ease:'power2.out'},.7);
    tl.to(q('.price-corner'),{opacity:0,duration:.35},1.65);
    tl.fromTo(q('.note'),{x:220,opacity:0},{x:0,opacity:1,duration:.4},1.1);
    tl.to(q('.price-stage'),{scale:.45,rotationY:55,x:-500,z:-500,opacity:0,duration:.5,ease:'power3.in'},3.5);
    tl.to(q('.headline,.eyebrow,.note'),{opacity:0,duration:.25},3.75);
    """);

    scene("ea-cierre", 4, """
    .close-copy{position:absolute;left:78px;top:370px;width:850px;font-size:100px;line-height:1.04;font-weight:750;letter-spacing:-2px}
    .free{position:absolute;left:72px;top:640px;width:880px;height:190px;font-size:158px;font-weight:800;color:#f4d447;letter-spacing:-5px;line-height:1}
    .days{position:absolute;left:78px;top:825px;width:850px;font-size:90px;font-weight:750;line-height:1}
    .daily{position:absolute;left:78px;top:945px;width:850px;font-size:42px}
    .cta{position:absolute;left:78px;top:1055px;width:850px;height:112px;display:flex;align-items:center;justify-content:space-between;background:#f4d447;border-radius:20px;padding:24px 36px;color:#14283e;font-size:52px;font-weight:700}
    .cta svg{width:55px;height:55px;flex:none}.handle{position:absolute;left:78px;top:1210px;width:850px;font-size:48px;font-weight:700}
    .domain{position:absolute;left:78px;top:1290px;width:850px;font-size:42px;color:#cad4dd}
    .finish-rule{left:78px;top:1380px;width:840px;height:5px}
    """, """
    <div class="eyebrow">ESE AUTO · ARGENTINA</div><h2 class="close-copy"><span class="line">Probá una</span><span class="line">búsqueda</span></h2>
    <div class="free">GRATIS</div><div class="days">por 3 días.</div><p class="daily">Con resumen diario.</p>
    <div class="cta"><span>Enlace en el perfil</span><svg viewBox="0 0 60 60" aria-hidden="true"><path d="M10 50L50 10M15 10H50V45" stroke="#14283e" stroke-width="6" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg></div>
    <p class="handle">@eseauto.ar</p><p class="domain">eseauto.com.ar</p><div class="underline finish-rule"></div>
    """, """
    tl.fromTo(q('.close-copy .line'),{y:200,rotationX:-60,opacity:0},{y:0,rotationX:0,opacity:1,duration:.6,stagger:.13,ease:'power4.out'},0);
    tl.fromTo(q('.eyebrow'),{x:-150,opacity:0},{x:0,opacity:1,duration:.35},.05);
    tl.fromTo(q('.free'),{x:1000,rotationY:-65,scale:1.3,opacity:0},{x:0,rotationY:0,scale:1,opacity:1,duration:.7,ease:'back.out(1.05)'},.40);
    tl.fromTo(q('.days'),{y:140,opacity:0},{y:0,opacity:1,duration:.45,ease:'power3.out'},.85);
    tl.fromTo(q('.daily'),{x:-200,opacity:0},{x:0,opacity:1,duration:.4},1.1);
    tl.fromTo(q('.cta'),{y:200,scale:.8,rotationX:35,opacity:0},{y:0,scale:1,rotationX:0,opacity:1,duration:.6,ease:'back.out(1.15)'},1.25);
    tl.fromTo(q('.handle,.domain'),{y:60,opacity:0},{y:0,opacity:1,duration:.4,stagger:.13,ease:'power2.out'},1.65);
    tl.fromTo(q('.finish-rule'),{scaleX:0},{scaleX:1,duration:.55,ease:'power3.out'},1.9);
    tl.to(q('.cta svg'),{x:8,y:-8,duration:.5,repeat:3,yoyo:true,ease:'sine.inOut'},2);
    """);

    slots = [("ea-problema",0,3),("ea-busqueda",3,5),("ea-filtros",8,4),("ea-opciones",12,4),("ea-precio",16,4),("ea-cierre",20,4)]
    hosts = "\n".join(f'<div id="host-{name}" data-composition-id="{name}" data-composition-src="compositions/{name}.html" data-start="{start}" data-duration="{duration}" data-track-index="1" data-width="1080" data-height="1920"></div>' for name,start,duration in slots)
    index = f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Ese Auto · Reel HyperFrames</title>
<script src="vendor/gsap.min.js"></script><style>
@font-face{{font-family:'Ese';src:url('assets/bahnschrift.ttf') format('truetype');font-weight:100 900;font-display:block}}
*{{box-sizing:border-box}}html,body{{margin:0;width:100%;height:100%;background:#14283e;font-family:'Ese',sans-serif}}
#ea-root{{position:relative;width:100%;height:100%;overflow:hidden}}
#ea-root>div[data-composition-src]{{position:absolute;inset:0}}
.backdrop{{position:absolute;inset:0;background:#14283e;overflow:hidden}}
.route-art{{position:absolute;left:-100px;top:-100px;width:1300px;height:2150px;opacity:.7}}
.brand{{position:absolute;left:78px;top:230px;display:flex;gap:28px;align-items:center;color:#fbfbf8;font-size:40px;font-weight:750}}
.brand-mark{{color:#14283e;background:#f4d447;padding:2px 16px;font-size:50px;line-height:1.2;font-weight:750}}
.brand-name{{width:210px}}.glow{{position:absolute;left:560px;top:650px;width:850px;height:850px;border-radius:50%;background:radial-gradient(circle,#f4d44724 0%,#f4d44700 65%)}}
</style></head><body><div id="ea-root" data-composition-id="ea-main" data-start="0" data-duration="24" data-width="1080" data-height="1920">
<div class="backdrop" data-layout-ignore><div class="glow"></div><svg class="route-art" viewBox="0 0 1300 2150" aria-hidden="true"><g fill="none" stroke="#3c5269" stroke-width="3"><path d="M1300 100C260 160 1360 820 500 1370S240 2100 0 2150"/><path d="M1400 160C360 210 1460 880 600 1430S340 2160 100 2210"/><path d="M1200 40C160 100 1260 760 400 1310S140 2040 -100 2090"/></g><path class="route-dash" d="M1350 130C310 185 1410 850 550 1400S290 2130 50 2180" fill="none" stroke="#f4d447" stroke-width="4" stroke-dasharray="16 66" opacity=".5"/></svg></div>
<div class="brand"><span class="brand-mark">S Auto</span><span class="brand-name">Ese Auto</span></div>
{hosts}
<audio id="ea-music" src="assets/musica-120bpm.wav" data-start="0" data-duration="24" data-track-index="2" data-volume="1"></audio>
</div><script>const tl=gsap.timeline({{paused:true}});tl.to('.route-art',{{x:-30,y:55,rotation:3,duration:24,ease:'none'}},0);tl.to('.route-dash',{{strokeDashoffset:-1800,duration:24,ease:'none'}},0);tl.fromTo('.glow',{{scale:.85,opacity:.55}},{{scale:1.2,opacity:1,duration:4,repeat:5,yoyo:true,ease:'sine.inOut'}},0);window.__timelines['ea-main']=tl;</script></body></html>'''
    (ROOT / "index.html").write_text(index, encoding="utf-8")
    (ROOT / "index.motion.json").write_text(json.dumps({"duration":24,"assertions":[{"kind":"keepsMoving","withinSelector":"#ea-root","maxStaticSec":1.3}]}),encoding="utf-8")
    print(json.dumps({"framework":"HyperFrames 0.8.134","scenes":len(slots),"duration":24,"project":str(ROOT)}))


if __name__ == "__main__":
    build()

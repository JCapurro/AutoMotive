"""Freeze the live 2026-10-06 landing as native 3x HyperFrames assets.

Keep the measured hero and complete primary controls. The separate fine-print
paragraph lies outside the selected region; no text or control is cut in half.
"""
from pathlib import Path
import json
import math
import shutil
import sys
from PIL import Image

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / 'assets/landing-2026-10-06'
PRODUCTION = ROOT / 'produccion/landing-2026-10-06'


def clean(value):
    # The browser DOM export transports accented UTF-8 through Latin-1.
    if isinstance(value, str) and ('\u00c3' in value or '\u00c2' in value):
        try:
            return value.encode('latin1').decode('utf8')
        except (UnicodeEncodeError, UnicodeDecodeError):
            return value
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean(v) for v in value]
    return value


def source(name):
    value = clean(json.loads((ASSETS / 'dom-src' / f'{name}.json').read_text(encoding='utf8')))
    assert '[Truncated]' not in value['html']
    return value


def prepare():
    PRODUCTION.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / 'assets/capturas-hd/fonts', PRODUCTION / 'fonts', dirs_exist_ok=True)
    shutil.copyfile(ROOT / 'vendor/gsap.min.js', PRODUCTION / 'gsap.min.js')
    fonts = json.loads((ROOT / 'assets/capturas-hd/fuentes-activos.json').read_text(encoding='utf8'))['fonts']
    font = next(f for f in fonts if f['name'].startswith('21ca8f3f56c22ca2'))
    faces = f"@font-face{{font-family:Archivo;src:url('fonts/{Path(font['path']).name}') format('woff2');font-weight:100 900;font-stretch:62% 125%;font-style:normal;font-display:block}}"
    faces += "@font-face{font-family:'Archivo Fallback';src:local('Arial');ascent-override:88.96%;descent-override:21.28%;line-gap-override:0%;size-adjust:98.7%}"
    title, description, empty, written = [source(n) for n in ['hero-titulo','hero-descripcion','landing-vacia','landing-escrita']]
    primary = next(c for c in empty['controls'] if c['text'] == 'Crear mi búsqueda')
    hero_origin = title['rect']['top'] - 24
    hero_width = title['width'] + 32
    hero_height = primary['rect']['bottom'] + 8 - hero_origin
    parts = ''.join(f'<div style="position:absolute;left:16px;top:{d["rect"]["top"]-hero_origin}px">{d["html"]}</div>' for d in [title, description, empty])
    hero = f'<div style="position:relative;width:{hero_width}px;height:{hero_height}px;overflow:hidden;background:white">{parts}</div>'
    button = next(c for c in written['controls'] if c['text'] == 'Crear mi búsqueda')
    form_height = button['rect']['bottom'] - written['rect']['top'] + 8
    form_width = written['width'] + 16
    form = f'<div style="padding:8px;width:{form_width}px;height:{form_height+16}px;overflow:hidden;background:white;box-sizing:border-box">{written["html"]}</div>'
    ledger = [
        {'name':'00-landing-hero','x':16,'y':16,'width':math.ceil(hero_width*3),'height':math.ceil(hero_height*3),'source':'public landing 2026-10-06','scale':3},
        {'name':'01-landing-escrita','x':1296,'y':16,'width':math.ceil(form_width*3),'height':math.ceil((form_height+16)*3),'source':'public landing draft 2026-10-06','scale':3,
         'focus':{'left':(button['rect']['left']-written['rect']['left']+8)*840/form_width-6,'top':(button['rect']['top']-written['rect']['top']+8)*840/form_width-6,'width':button['rect']['width']*840/form_width+12,'height':button['rect']['height']*840/form_width+12}}
    ]
    slots = ''.join(f'<div style="position:absolute;left:{d["x"]}px;top:{d["y"]}px;transform:scale(3);transform-origin:0 0">{html}</div>' for d,html in zip(ledger,[hero,form]))
    height = max(d['height'] for d in ledger)+32
    html = f'<!doctype html><html><head><meta charset="utf-8"><script src="gsap.min.js"></script><style>{faces}html,body{{margin:0;background:white}}#landing-root{{position:relative;width:100%;height:100%;overflow:hidden}}</style></head><body><div id="landing-root" data-composition-id="landing-captures" data-width="2560" data-height="{height}" data-duration="1">{slots}</div><script>const tl=gsap.timeline({{paused:true}});tl.to("#landing-root",{{opacity:1,duration:1}},0);window.__timelines["landing-captures"]=tl;</script></body></html>'
    (PRODUCTION/'index.html').write_text(html,encoding='utf8')
    (ASSETS/'CAPTURAS_LANDING.json').write_text(json.dumps(ledger,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'assets':len(ledger),'native_scale':3,'atlas_height':height,'focus':ledger[1]['focus']}))


def extract():
    ledger = json.loads((ASSETS/'CAPTURAS_LANDING.json').read_text(encoding='utf8'))
    with Image.open(ASSETS/'atlas/frame-00-at-0.5s.png') as atlas:
        for d in ledger:
            x,y,w,h = (d[k] for k in ['x','y','width','height'])
            assert x+w <= atlas.width and y+h <= atlas.height
            atlas.crop((x,y,x+w,y+h)).save(ASSETS/(d['name']+'.png'))
    print(json.dumps({'extracted':len(ledger),'resampled':False}))


if __name__ == '__main__':
    extract() if '--extract' in sys.argv else prepare()

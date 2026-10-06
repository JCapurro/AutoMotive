"""Rasterize frozen visible DOM components, never upscale the old JPEGs.

Source HTML, computed styles, values, fonts, and photos were exported from
the authenticated platform using CUA. HyperFrames owns native 3x rendering.
"""
from pathlib import Path
import json
import re
import shutil
import math
import sys
from PIL import Image, ImageOps, ImageDraw

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / 'assets' / 'capturas-hd'
PRODUCTION = ROOT / 'produccion' / 'capturas-hd'


def prepare():
    PRODUCTION.mkdir(parents=True, exist_ok=True)
    for dirname in ['fonts', 'photos']:
        shutil.copytree(ASSETS / dirname, PRODUCTION / dirname, dirs_exist_ok=True)
    shutil.copyfile(ROOT / 'vendor/gsap.min.js', PRODUCTION / 'gsap.min.js')
    sources = json.loads((ASSETS / 'fuentes-activos.json').read_text(encoding='utf-8'))
    archivo = next(font for font in sources['fonts'] if font['name'].startswith('21ca8f3f56c22ca2'))
    faces = f"@font-face{{font-family:'Archivo';src:url('fonts/{Path(archivo['path']).name}') format('woff2');font-weight:100 900;font-stretch:62% 125%;font-style:normal;font-display:block}}"
    faces += "@font-face{font-family:'Archivo Fallback';src:local('Arial');ascent-override:88.96%;descent-override:21.28%;line-gap-override:0%;size-adjust:98.7%}"
    groups = [
        ('01-formulario-vacio', ['01-formulario-vacio'], 0),
        ('02-busqueda-escrita', ['02-busqueda-escrita'], 0),
        ('03-modelo', ['03-marca', '03-modelo'], 16),
        ('03-anio', ['03-anio'], 0),
        ('03-kilometraje', ['03-kilometraje'], 0),
        ('04-precio', ['04-precio'], 0),
        ('04-zona', ['04-zona', '04-radio'], 16),
        ('05-opcion-1', ['05-opcion-1'], 0),
        ('05-opcion-2', ['05-opcion-2'], 0),
        ('06-precio-contexto', ['06-precios', '06-comparables'], 12),
    ]
    slots, ledger, offset, row_height = [], [], 24, 0
    for idx, (name, ids, gap) in enumerate(groups):
        entries = [json.loads((ASSETS/'dom-src'/f'{key}.json').read_text(encoding='utf-8')) for key in ids]
        width = max(entry['width'] for entry in entries)
        height = sum(entry['height'] for entry in entries) + gap * (len(entries)-1)
        contents = []
        for entry in entries:
            assert '[Truncated]' not in entry['html'], 'Visible DOM export must be complete'
            # Quotes in computed font-family must remain inside the style attribute.
            markup = entry['html'].replace('"Archivo Fallback"', '&quot;Archivo Fallback&quot;')
            markup = re.sub(r'style="([^"]*)"', lambda m: 'style="'+m.group(1)+'margin:0!important;"', markup, count=1)
            for photo in sources['photos']:
                markup = markup.replace(photo['url'].replace('&', '&amp;'), 'photos/'+Path(photo['path']).name)
            # Preserve the complete original car photo inside its thumbnail box.
            markup = re.sub(r'<img[^>]*>',lambda m:m.group().replace('object-fit:cover;','object-fit:contain;'),markup)
            contents.append('<div style="flex:none">'+markup+'</div>')
        body = f'<div style="display:flex;flex-direction:column;gap:{gap}px;width:{width}px">'+''.join(contents)+'</div>'
        # Full component + 8 CSS px on each edge. Scale actual vectors to 3x.
        x = 24 + (idx % 2) * 1280
        out_height = math.ceil((height+16)*3)
        slots.append(f'<div id="asset-{idx}" style="position:absolute;left:{x}px;top:{offset}px;transform:scale(3);transform-origin:0 0;background:#fff;padding:8px;width:{width+16}px;height:{height+16}px;box-sizing:border-box">{body}</div>')
        ledger.append({'name':name,'x':x,'y':offset,'width':math.ceil((width+16)*3),'height':out_height,'scale':3,'source_components':ids})
        row_height = max(row_height, out_height)
        if idx % 2 == 1:
            offset += row_height + 24
            row_height = 0
    html = '<!doctype html><html><head><meta charset="utf-8"><script src="gsap.min.js"></script><style>'+faces+'html,body{margin:0;background:#fff}#captures-root{position:relative;width:100%;height:100%;overflow:hidden}</style></head><body><div id="captures-root" data-composition-id="captures" data-width="2560" data-height="'+str(offset)+'" data-duration="1">'+''.join(slots)+'</div><script>const tl=gsap.timeline({paused:true});tl.to("#captures-root",{opacity:1,duration:1},0);window.__timelines["captures"]=tl;</script></body></html>'
    (PRODUCTION/'index.html').write_text(html,encoding='utf-8')
    (ASSETS/'CAPTURAS_HD.json').write_text(json.dumps(ledger,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'components':len(ledger),'native_scale':3,'max_width':max(x['width'] for x in ledger),'max_height':max(x['height'] for x in ledger)}))


def extract():
    ledger = json.loads((ASSETS/'CAPTURAS_HD.json').read_text(encoding='utf-8'))
    with Image.open(ASSETS/'atlas/frame-00-at-0.5s.png') as atlas:
        board = Image.new('RGB', (1240, 1400), '#dce0e4')
        for index, row in enumerate(ledger):
            x, y, width, height = (row[key] for key in ['x','y','width','height'])
            assert x+width <= atlas.width and y+height <= atlas.height
            component = atlas.crop((x,y,x+width,y+height))
            component.save(ASSETS/(row['name']+'.png'))
            thumb = ImageOps.contain(component, (290,430))
            column, line = index % 4, index // 4
            board.paste(thumb, (column*310+10,line*460+25))
            ImageDraw.Draw(board).text((column*310+10,line*460+5),row['name'],fill='black')
        (ROOT/'revision').mkdir(exist_ok=True)
        board.save(ROOT/'revision/CAPTURAS_HD_REVISION.jpg',quality=94)
    print(json.dumps({'extracted':len(ledger),'resampled':False}))


if __name__ == '__main__':
    extract() if '--extract' in sys.argv else prepare()

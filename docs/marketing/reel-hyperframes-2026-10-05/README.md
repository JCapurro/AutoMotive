# Ese Auto · proyecto HyperFrames

Composición de 24 segundos, 1080 × 1920, 30 fps. Exportada con HyperFrames 0.8.134 y animaciones GSAP 3.14.2. Cada una de las seis escenas tiene una línea de tiempo que se puede recorrer y editar.

## Editar

El editor local está en http://localhost:3019/#project/reel-hyperframes-2026-10-05 mientras el servidor esté encendido.

Desde PowerShell, en esta carpeta:

```powershell
.\hf.ps1 preview --background --port 3019
```

`index.html` monta las seis escenas de `compositions/`. El fondo y la música se mantienen durante toda la composición. `STORYBOARD_HD.md` describe el guion; `frame.md` fija la dirección visual. `build_project.py` contiene el generador de la composición: ejecutarlo vuelve a escribir los HTML, por lo que conviene elegir entre editar el generador o editar directamente las escenas.

## Verificar y exportar

```powershell
.\hf.ps1 check --help
.\hf.ps1 render --output ESE_AUTO_REEL_HYPERFRAMES_HD_1080x1920.mp4 --fps 30 --quality delivery --workers 4
```

`CHECK_HD.json` guarda el control de ejecución, diseño, movimiento y contraste. Las capturas revisadas están en `snapshots-hd/`.

`hf.ps1` está configurado para los runtimes y FFmpeg de esta computadora. En otra máquina, instalá las dependencias de `package-lock.json`, usá el CLI de HyperFrames y configurá las rutas de FFmpeg/FFprobe si no están disponibles en PATH. La fuente Bahnschrift se tomó de la instalación local de Windows.

## Material y alcance

La versión HD usa diez PNG de componentes completos de la plataforma, sin ampliación de los JPEG originales. Se congelaron el DOM visible, los estilos, los valores y la fuente Archivo; HyperFrames los renderiza a 3x con las fotos originales de los avisos. Las fotos se muestran completas dentro de su marco (object-fit:contain). No se inventaron resultados. La música, los textos y los tiempos del montaje aprobado se conservan. El teléfono es un marco de presentación animado.

`assets/capturas-hd/dom-src/` guarda los componentes exportados. `prepare_hd_captures.py` crea un atlas local renderizable; después de capturarlo con HyperFrames en `assets/capturas-hd/atlas/`, ejecutar el generador con `--extract` recupera los diez PNG sin cambiar su resolución. `CAPTURAS_HD.json` documenta las dimensiones y componentes de origen. `ARCHIVOS_HD.json` y `PUBLICAR_REEL_HD.md` corresponden a la entrega corregida. Los MP4 anteriores y su paquete ZIP se conservan.

El diagnóstico opcional de keyframes por selector no pudo identificar el teléfono dentro de la subcomposición de plantilla. La revisión se hizo con capturas del proyecto completo y del video exportado; el control de movimiento de HyperFrames sí pasó.

El helper oficial de animación produjo `.hyperframes/anim-map/animation-map.json` con 186 tweens. Su diagnóstico incluye las líneas de tiempo locales de escenas inactivas y las del montaje: por ejemplo, marca el teléfono antes de los 3 segundos y el subrayado del cierre antes de los 20 segundos. Por eso sus señales de colisión o invisibilidad se contrastaron con las capturas en los tiempos reales del montaje. El recorrido del teléfono se corrigió para conservar el título despejado durante el acercamiento.

Los videos anteriores se conservaron en `../reel-demo-2026-10-05/`.

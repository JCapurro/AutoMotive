# Autocity, Car One y Grupo Randazzo

Solicitud: implementar las tres agencias en la rama existente `codex/nuevas-fuentes-usados`.

## Contrato

Collectors `autocity`, `carone`, `gruporandazzo` sobre los catálogos públicos de usados. Un target de inventario por fuente, sin hints de marca/modelo. Preservar IDs estables, URL de ficha propia, precio final y moneda, año/km, ubicación, fotos, descripción y atributos explícitos. Evitar planes, 0 km y anuncios vendidos; mantener precios de consulta como desconocidos. Reservados y a ingresar requieren una decisión documentada acorde al estado publicado. No tomar recomendaciones ni precios sin impuestos como precio total.

## Trabajo

- [x] Implementar los tres collectors, fixtures públicos recortados y pruebas de parser/transporte/paginación/identidad/raw slim; probar cada catálogo y una ficha real sin ingesta. Autocity 220, Car One 199, Randazzo 190 usados leídos en los últimos recorridos. Randazzo usa REST público filtrado y comprobado con rangos `Resources` y estado de cada unidad; no los contadores SSR cacheados.
- [x] Registrar fuentes en worker, CLI, configuración, seed y migración idempotente; validar targets y configuración sin sobrescribir ajustes existentes. Capacidad `STRICT_DETAIL_ID` para las tres agencias: se valida identidad antes de aplicar detalle o replay.
- [x] Revisar contrato y calidad, corregir hallazgos, correr suite offline y PostgreSQL aislado, actualizar documentación y grafo. 592 pruebas offline y 16 PostgreSQL aprobadas; 34 tests propios de agencias. Grafo AST actualizado (4.570 nodos/11.151 relaciones), diff válido, checkout principal preservado.

El checkout principal conserva sus cambios. Esta entrega es local: no aplicar migraciones ni ingesta en producción ni publicar código sin una solicitud posterior.

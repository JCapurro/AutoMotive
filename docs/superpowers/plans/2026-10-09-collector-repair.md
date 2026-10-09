# Collector repair Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development for implementation and review. Steps use checkbox syntax for tracking.

**Goal:** Abrir un chat por incidente de collector en Revisar, diagnosticar y corregir con pruebas y conservar pendientes mientras la PC no esté disponible.

**Architecture:** Un trigger privado registra transiciones del snapshot existente sin instalar un nuevo daemon en el VPS. Un repositorio Python reserva incidentes y un CLI entrega contexto saneado a una automatización nativa de Codex que crea y registra chats.

**Tech Stack:** PostgreSQL/Supabase, psycopg 3, Python unittest/pytest, Codex app tools.

---

## Task 1: Cola privada y reservas

Files: nueva migración `collector_repair_incidents`, `worker/db/repos/collector_repairs.py`, `worker/tests/test_collector_repairs_postgres.py`.

- [ ] Generar la migración con Supabase CLI y mantenerla después de las migraciones ya existentes que referencian el snapshot.
- [ ] Escribir pruebas DB de Revisar->pending, fallo persistente sin duplicar, OK->resolved, retiro->cancelled, snapshot vencido desconocido, permisos sin acceso de anon/authenticated.
- [ ] Implementar trigger SECURITY INVOKER con search_path fijo y privilegios explícitos; índice único parcial por source donde resolved_at es null.
- [ ] Implementar `claim(cx, owner, lease_seconds=900)`, `attach(cx, incident_id, token, thread_id)` y `needs_input(cx, incident_id, note)`; probar reservas concurrentes, token vencido y registro idempotente.
- [ ] Ejecutar `python -m pytest tests/test_collector_repairs_postgres.py -q` con TEST_DATABASE_URL apuntando exclusivamente a una base local nueva terminada en `_test`.

## Task 2: Contexto y herramienta para Codex

Files: `worker/tools/collector_repairs.py`, `worker/tests/test_collector_repairs.py`, `docs/COLLECTOR_REPAIR.md`.

- [ ] Escribir pruebas de redacción, inclusión de corridas y targets y exclusión de credenciales/perfiles; snapshot stale no despacha.
- [ ] Implementar comandos `claim --owner <nombre>`, `attach <id> --token <uuid> --thread <id>`, `context <id>`, `needs-input <id> --note <texto>` y `list`, JSON por stdout y errores saneados por stderr.
- [ ] Construir prompt que identifica el incidente con UUID, delimita contexto no confiable, pide reproducir, arreglo mínimo, pruebas y validación real; preservar checkout ajeno y pedir captcha/SSH solo si requerido.
- [ ] Documentar despacho y reconciliación por título exacto tras interrupciones, silencio sin novedades, límites de la autenticación actual del VPS.
- [ ] Ejecutar `python -m pytest tests/test_collector_repairs.py tests/test_platform_health.py -q`.

## Task 3: Revisión y activación

- [ ] Revisar conformidad con diseño, luego calidad del código con agente independiente; resolver los hallazgos y repetir las pruebas afectadas.
- [ ] Ejecutar `graphify update .` y guardar solo cambios propios en un commit de la rama codex/collector-repair.
- [ ] Integrar archivos propios al checkout principal preservando sus cambios ajenos. No hacer push sin necesidad.
- [ ] Aplicar solamente la nueva migración en producción dentro de una transacción, guardar su versión y comprobar privilegios y trigger.
- [ ] Probar CLI contra el snapshot real; crear la automatización heartbeat nativa cada cinco minutos y despachar un incidente real pendiente si existe. Registrar el identificador del chat y comprobar que la segunda reserva no duplique.
- [ ] Informar qué quedó implementado, activado y observado, y cualquier autenticación pendiente para desplegar arreglos futuros.

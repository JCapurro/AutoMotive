# Puesta en producción del piloto (F7)

Runbook para dejar AutoMotive abierto a usuarios reales con la **opción B** del
[plan técnico](TECHNICAL_PLAN.md) (F7): todo corre en esta PC (Supabase local,
web y worker) y Cloudflare Tunnel lo publica en tu dominio con https.

```
Internet ──https──▶ Cloudflare ──túnel──▶ cloudflared (esta PC)
                                             ├─ automotive.<dominio>      → 127.0.0.1:3000  (web)
                                             └─ api.automotive.<dominio>  → 127.0.0.1:54321 (Supabase: solo /auth, /rest, /realtime)
```

Los pasos 1 a 6 se hacen en páginas web y consolas de terceros: solo los podés
hacer vos. Del 7 en adelante es esta PC. Tiempo total: 1 a 2 horas, más lo que
tarde en propagarse el DNS.

> En los ejemplos, `automotive.tudominio.com.ar` es la web y
> `api.automotive.tudominio.com.ar` la API. Cambialos por los tuyos.

---

## Checklist

- [ ] 1. Dominio en Cloudflare
- [ ] 2. Túnel de Cloudflare con los dos hostnames (y la API restringida)
- [ ] 3. Resend: dominio verificado y API key
- [ ] 4. API key de Anthropic (modo asistido)
- [ ] 5. Chat de Telegram para las alertas operativas
- [ ] 6. Sesiones de MercadoLibre y Facebook renovadas
- [ ] 7. Archivos de configuración completos
- [ ] 8. Windows preparado (energía, Docker, firewall)
- [ ] 9. Tareas programadas instaladas
- [ ] 10. Prueba de aceptación desde un celular con datos móviles

---

## 1. Dominio en Cloudflare

1. Si no tenés dominio, comprá uno. Opciones: un `.com.ar` en [NIC Argentina](https://nic.ar)
   (barato, requiere CUIT/CUIL y clave fiscal) o un `.com` directamente en
   Cloudflare (Dashboard → *Domain Registration → Register Domains*), que se
   configura solo.
2. En [dash.cloudflare.com](https://dash.cloudflare.com), *Add a domain* → plan
   **Free**.
3. Si el dominio no se compró en Cloudflare, cambiá los *nameservers* donde lo
   compraste (en NIC Argentina: *Mis dominios → Delegar*) por los dos que te da
   Cloudflare. Esperá el mail «Your domain is now active» (de minutos a 24 h).

## 2. Túnel de Cloudflare

`cloudflared` ya está instalado en esta PC (`C:\Program Files (x86)\cloudflared`).

1. Cloudflare → **Zero Trust** (la primera vez pide elegir un nombre de equipo y
   el plan Free; puede pedir una tarjeta aunque no cobre) → *Networks → Tunnels →
   Create a tunnel* → **Cloudflared** → nombre `automotive-pc`.
2. En *Install and run a connector* elegí **Windows** y copiá el comando
   `cloudflared.exe service install <TOKEN>`. Correlo en una **PowerShell como
   administrador**. Queda como servicio de Windows: arranca solo con la PC.
3. *Public Hostnames* → agregá **dos**:

   | Subdomain | Domain | Path | Service |
   |---|---|---|---|
   | `automotive` | `tudominio.com.ar` | *(vacío)* | `HTTP` · `127.0.0.1:3000` |
   | `api.automotive` | `tudominio.com.ar` | `^/(auth\|rest\|realtime)/v1/` | `HTTP` · `127.0.0.1:54321` |

   **El Path del segundo es obligatorio.** En el puerto 54321 también están pgMeta
   (`/pg/*`, SQL sin autenticación) y Storage: sin el filtro, cualquiera podría
   leer y borrar la base. Con el filtro, todo lo demás de ese hostname da 404.
4. Comprobá, desde el navegador:
   - `https://api.automotive.tudominio.com.ar/auth/v1/health` → un JSON.
   - `https://api.automotive.tudominio.com.ar/pg/tables` → **404**. Si no da 404,
     revisá el Path antes de seguir.

## 3. Resend (emails de login y de alertas)

1. Creá la cuenta en [resend.com](https://resend.com) (el plan gratis alcanza:
   100 emails por día, 3.000 por mes).
2. *Domains → Add domain* → `tudominio.com.ar` (o un subdominio, por ejemplo
   `mail.tudominio.com.ar`) → región **São Paulo**. Resend ofrece cargar los
   registros DNS en Cloudflare automáticamente; si no, copiá los registros MX,
   SPF y DKIM en Cloudflare → *DNS*. Esperá a que el dominio quede **Verified**.
3. *API Keys → Create API key* con permiso **Sending access**. Guardala: se
   usa en dos lugares (paso 7).
4. Elegí el remitente, por ejemplo `alertas@tudominio.com.ar`.

## 4. API key de Anthropic (modo asistido)

`claude -p` usa tu suscripción personal de Claude Code; para usuarios del
piloto conviene la API.

1. [console.anthropic.com](https://console.anthropic.com) → *Billing*: cargá
   crédito (con US$5 sobra para el piloto: cada búsqueda asistida con Haiku 4.5
   cuesta menos de medio centavo de dólar) y poné un **límite de gasto mensual**.
2. *API Keys → Create key* → nombre `automotive-pilot`.

## 5. Chat de Telegram para las alertas operativas

Ahí te avisan el worker (una fuente que falla 3 veces seguidas) y el watchdog
(el worker, la base o la web caídos).

1. Escribile a [@userinfobot](https://t.me/userinfobot): te responde tu `Id`
   (un número). Ese es `TELEGRAM_ADMIN_CHAT_ID`.
2. Mandale cualquier mensaje a tu bot de AutoMotive (tiene que haber un chat
   abierto para que pueda escribirte).

## 6. Sesiones de MercadoLibre y Facebook

En la prueba de fuentes del 28/09, Kavak, V6 y Autocosmos funcionaron.
MercadoLibre pedía verificación y Facebook devolvía 0 resultados (la sesión es
de mayo). Desde `worker\`:

```powershell
python -m collectors.mercadolibre   # se abre Chromium: iniciá sesión o completá la verificación, volvé y Enter
python -m collectors.facebook       # idem con Facebook (conviene una cuenta secundaria)
python -m tools.scraper_cli mercadolibre marca=Ford modelo=Fiesta
python -m tools.scraper_cli facebook marca=Ford modelo=Fiesta
```

Las dos últimas tienen que listar publicaciones.

## 7. Archivos de configuración

Ninguno de estos archivos va a git.

**`supabase\.env`** (lo lee `supabase\config.toml`). Ya existe con valores de
desarrollo y las claves propias del stack. Cambiá **solo** estas líneas:

```ini
SITE_URL=https://automotive.tudominio.com.ar
AUTH_REDIRECT_URLS=https://automotive.tudominio.com.ar/**
AUTH_EXTERNAL_URL=https://api.automotive.tudominio.com.ar/auth/v1
SMTP_ENABLED=true
RESEND_API_KEY=re_...                       # la del paso 3
EMAIL_FROM_ADDRESS=alertas@tudominio.com.ar
```

No toques `JWT_SECRET`, `SUPABASE_PUBLISHABLE_KEY` ni `SUPABASE_SECRET_KEY`:
reemplazan las claves de demo de la CLI, que son iguales en todas las
instalaciones y con la API pública dejarían entrar a cualquiera.

**`.env`** (raíz, el worker):

```ini
WEB_BASE_URL=https://automotive.tudominio.com.ar
RESEND_API_KEY=re_...
EMAIL_FROM=Automotive <alertas@tudominio.com.ar>
TELEGRAM_ADMIN_CHAT_ID=123456789            # el del paso 5
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...                # la del paso 4
```

**`web\.env.local`**:

```ini
NEXT_PUBLIC_SUPABASE_URL=https://api.automotive.tudominio.com.ar
SITE_URL=https://automotive.tudominio.com.ar
NEXT_PUBLIC_CONTACT_EMAIL=vos@tudominio.com.ar   # aparece en /privacidad y /terminos
```

(`NEXT_PUBLIC_SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` y
`NEXT_PUBLIC_TELEGRAM_BOT_USERNAME` ya están.)

Aplicalo, desde la raíz del repo:

```powershell
npx supabase stop; npx supabase start       # toma supabase\.env
cd worker; python -m tools.supabase_keys sync; cd ..
```

Probá el modo asistido contra la API real (unas 20 llamadas, menos de 10 centavos de dólar):

```powershell
$env:LLM_SMOKE = "1"; $env:LLM_PROVIDER = "anthropic"; pytest worker/tests/test_llm_contract.py -k smoke
```

## 8. Windows

En una PowerShell **como administrador**:

```powershell
# Que la PC no se suspenda enchufada (la pantalla sí puede apagarse).
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0

# Docker Desktop publica los puertos de Supabase en todas las interfaces: que
# nadie de tu red local llegue a la base, a Studio ni a pgMeta. El túnel entra
# por 127.0.0.1 y no se ve afectado.
New-NetFirewallRule -DisplayName "AutoMotive: Supabase solo local" -Direction Inbound `
  -Protocol TCP -LocalPort 54321-54329 -RemoteAddress Any -Action Block
```

En Docker Desktop → *Settings → General*, activá **Start Docker Desktop when
you sign in**.

Las tareas arrancan al iniciar sesión. Si se corta la luz, la PC vuelve a
funcionar recién cuando alguien inicia sesión. Si querés que arranque sola:
activá en el BIOS «Restore on AC power loss» y el inicio de sesión automático
con [Autologon de Sysinternals](https://learn.microsoft.com/sysinternals/downloads/autologon).
Ojo: cualquiera con acceso físico a la PC entra a tu sesión.

## 9. Tareas programadas

1. Cerrá lo que esté corriendo a mano: el `npm run dev` de la web y el
   `python main.py` del worker (si no, choca el puerto 3000 y hay dos bots).
2. En una PowerShell **como administrador**, desde la raíz del repo:

   ```powershell
   powershell -ExecutionPolicy Bypass -File ops\install-tasks.ps1 -BackupDest "$env:OneDrive\AutoMotive\backups"
   Get-ScheduledTask -TaskPath \AutoMotive\ | Start-ScheduledTask
   ```

   Usá una carpeta sincronizada (OneDrive, Google Drive) para `-BackupDest`,
   así los backups no mueren con la PC. El script compila la web (`npm ci` +
   `npm run build`) y registra cinco tareas en *Programador de tareas →
   AutoMotive*:

   | Tarea | Cuándo | Qué hace |
   |---|---|---|
   | Supabase | al iniciar sesión | espera Docker y hace `npx supabase start` |
   | Web | al iniciar sesión | `next start` en 127.0.0.1:3000, se reinicia si se cae |
   | Worker | al iniciar sesión | `python main.py`, se reinicia si se cae |
   | Watchdog | cada 5 min | te avisa por Telegram si el worker, la base o la web dejan de responder, y cuando vuelven |
   | Backup | 03:30 todos los días | `pg_dump` de la base, guarda los últimos 14 |

3. Verificá:

   ```powershell
   cd worker; python -m tools.watchdog --dry   # base OK · worker OK · web OK
   ```

   Y en `https://automotive.tudominio.com.ar/admin/sources`, «Worker: late ahora».

Para darte acceso a `/admin`, primero ingresá una vez en la web con tu email y después:

```powershell
docker exec supabase_db_automotive psql -U postgres -c "update public.profiles set role = 'admin' where email = 'vos@tudominio.com.ar'"
```

## 10. Prueba de aceptación

Hacela desde un celular **con datos móviles** (no desde el wifi de tu casa), así
probás el camino de un usuario real:

1. Entrá a `https://automotive.tudominio.com.ar`: la landing carga con candado.
2. Ingresá con un email tuyo: el link llega por Resend (revisá spam la primera
   vez) y te deja adentro.
3. En *Ajustes* vinculá Telegram y activá el email.
4. Creá una búsqueda amplia de un modelo con volumen (por ejemplo, Ford Fiesta,
   sin precio máximo, frecuencia inmediata, nivel mínimo 🟡).
5. Esperá a que el worker encuentre una publicación nueva (minutos a horas):
   tiene que llegar por Telegram y por email. Tocá el link: en
   `/admin/notifications` la alerta figura como clickeada.
6. Tocá «Dejar de recibir estos emails» al pie del email: el email se apaga en *Ajustes*.
7. En `/admin/sources`, las 5 fuentes tienen una corrida `ok` en las últimas 24 h.

---

## Operación del día a día

**Dónde mirar:**

| Qué | Dónde |
|---|---|
| Log del worker (UTF-8, rota a medianoche, 14 días) | `logs\worker.log` |
| Salida cruda de cada proceso (tracebacks de arranque) | `logs\worker.out.log`, `logs\web.out.log` |
| Arranques y reinicios de los procesos | `logs\supervisor.log` |
| Watchdog | `logs\watchdog.log` |
| Estado de fuentes, errores y métricas | `/admin` |

**Actualizar a una versión nueva** (después de `git pull`, desde la raíz):

```powershell
powershell -ExecutionPolicy Bypass -File ops\update.ps1
```

El script hace un backup, aplica las migraciones, instala las dependencias,
compila la web y reinicia las tareas Web y Worker. Si el build falla, la versión
anterior sigue corriendo.

**Tests con el piloto andando.**
- `pytest` con `TEST_DATABASE_URL` apunta a `automotive_test`: no toca el piloto.
  Después de cada migración, recreá esa base con `python -m tools.test_db`.
- `npx supabase test db` corre en transacciones que se descartan.
- **No corras `npm run e2e` con `SMTP_ENABLED=true`**: mandaría emails reales a
  direcciones inventadas, lo que perjudica la reputación del dominio. Además, el
  e2e necesita el worker **parado** (si no, el worker real toma los pedidos del
  modo asistido que el test simula) y el puerto 3000 libre (compila y sirve la
  web de producción: el overlay de `next dev` tapa la barra de navegación del
  celular).

**Restaurar un backup** (pisa la base actual):

```powershell
Get-ScheduledTask -TaskPath \AutoMotive\ | Stop-ScheduledTask
docker cp "$env:OneDrive\AutoMotive\backups\automotive-AAAAMMDD-HHMM.dump" supabase_db_automotive:/tmp/r.dump
docker exec supabase_db_automotive pg_restore -U supabase_admin -d postgres --clean --if-exists /tmp/r.dump
Get-ScheduledTask -TaskPath \AutoMotive\ | Start-ScheduledTask
```

Probalo una vez en una base aparte, reemplazando `-d postgres --clean --if-exists`
por `-d restore_check`, después de
`docker exec supabase_db_automotive psql -U supabase_admin -c "create database restore_check"`.

**Rotar las claves de Supabase** (si se filtró alguna; cierra todas las sesiones):

```powershell
cd worker; python -m tools.supabase_keys generate --rotate; cd ..
npx supabase stop; npx supabase start
cd worker; python -m tools.supabase_keys sync; cd ..
powershell -ExecutionPolicy Bypass -File ops\update.ps1   # recompila la web con la clave nueva
```

**Desinstalar las tareas:** `powershell -ExecutionPolicy Bypass -File ops\uninstall-tasks.ps1`.

# Puesta en producción del piloto (F7)

Runbook para dejar AutoMotive abierto a usuarios reales con la **opción B** del
[plan técnico](TECHNICAL_PLAN.md) (F7), con la base en la nube: la web y el
worker corren en esta PC y Cloudflare Tunnel publica la web en tu dominio con
https. La base, el login y la API son un proyecto de **Supabase en la nube**
(plan Free, US$0).

```
Internet ──https──▶ Cloudflare ──túnel──▶ cloudflared (esta PC) ── automotive.<dominio> → 127.0.0.1:3000 (web)

Navegador, web y worker ──https / Postgres──▶ Supabase (proyecto dnqyravczgcpuowijbja, São Paulo)
```

| Proyecto de Supabase | |
|---|---|
| Organización | `automotive` (plan **Free**) |
| Ref | `dnqyravczgcpuowijbja` · región `sa-east-1` |
| API | `https://dnqyravczgcpuowijbja.supabase.co` |
| Postgres | pooler de sesión `aws-0-sa-east-1.pooler.supabase.com:5432`, usuario `postgres.dnqyravczgcpuowijbja` |

La conexión directa (`db.dnqyravczgcpuowijbja.supabase.co`) es solo IPv6 y desde
esta PC no conecta: usá siempre el pooler. Límites del plan Free: 500 MB de base
y el proyecto se pausa tras 7 días sin actividad (el worker lo mantiene activo).
No crees proyectos en otra organización sin mirar el plan: una organización Pro
cobra US$10 por mes por proyecto.

Los pasos 1 a 6 se hacen en páginas web y consolas de terceros: solo los podés
hacer vos. Del 7 en adelante es esta PC y el dashboard de Supabase. Tiempo
total: 1 a 2 horas, más lo que tarde en propagarse el DNS.

> En los ejemplos, `automotive.tudominio.com.ar` es la web. Cambialo por el tuyo.

---

## Checklist

- [x] 0. Proyecto de Supabase en la nube con las migraciones y el seed (29/09)
- [ ] 1. Dominio en Cloudflare
- [ ] 2. Túnel de Cloudflare para la web
- [ ] 3. Resend: dominio verificado y API key
- [ ] 4. API key de Anthropic (modo asistido)
- [ ] 5. Chat de Telegram para las alertas operativas
- [ ] 6. Sesiones de MercadoLibre y Facebook renovadas
- [ ] 7. Archivos de configuración y ajustes de Auth en Supabase
- [ ] 8. Windows preparado (energía, Docker)
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
3. *Public Hostnames* → agregá **uno**, solo la web (la API es la de Supabase en
   la nube, no pasa por el túnel):

   | Subdomain | Domain | Path | Service |
   |---|---|---|---|
   | `automotive` | `tudominio.com.ar` | *(vacío)* | `HTTP` · `127.0.0.1:3000` |

4. Comprobá, desde el navegador: `https://automotive.tudominio.com.ar` carga la
   landing (con la web andando).

## 3. Resend (emails de login y de alertas)

1. Creá la cuenta en [resend.com](https://resend.com) (el plan gratis alcanza:
   100 emails por día, 3.000 por mes).
2. *Domains → Add domain* → `tudominio.com.ar` (o un subdominio, por ejemplo
   `mail.tudominio.com.ar`) → región **São Paulo**. Resend ofrece cargar los
   registros DNS en Cloudflare automáticamente; si no, copiá los registros MX,
   SPF y DKIM en Cloudflare → *DNS*. Esperá a que el dominio quede **Verified**.
3. *API Keys → Create API key* con permiso **Sending access**. Guardala: se
   usa en dos lugares (paso 7: el `.env` del worker y el SMTP de Supabase).
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

## 7. Configuración

### Supabase (dashboard)

El proyecto en la nube **no lee** `supabase\config.toml` ni `supabase\.env`
(eso es solo para el stack local de desarrollo): Auth se configura en
[supabase.com/dashboard](https://supabase.com/dashboard/project/dnqyravczgcpuowijbja).

1. *Authentication → URL Configuration*:
   - **Site URL**: `https://automotive.tudominio.com.ar`
   - **Redirect URLs**: `https://automotive.tudominio.com.ar/**` y, para probar
     con la web local, `http://127.0.0.1:3000/**`.
2. *Authentication → Emails → SMTP Settings* → **Enable custom SMTP**. El email
   que trae Supabase manda muy pocos por hora y solo a miembros del equipo: sin
   esto los usuarios del piloto no reciben el link.

   | Campo | Valor |
   |---|---|
   | Sender email | `alertas@tudominio.com.ar` |
   | Sender name | `Automotive` |
   | Host | `smtp.resend.com` |
   | Port | `465` |
   | Username | `resend` |
   | Password | la API key de Resend (paso 3) |

3. *Authentication → Rate Limits*: **emails por hora** en `60`.
4. *Authentication → Emails → Templates*: en **Magic Link** y en **Confirm
   signup**, asunto `Tu link para entrar a Automotive` y como cuerpo el contenido
   de `supabase\templates\magic_link.html`. (El primer ingreso de un email nuevo
   manda el de *Confirm signup*; así los dos se ven igual).

Las claves (`anon` y `service_role`) están en *Project Settings → API Keys →
Legacy API keys*. La `service_role` saltea RLS: solo va en los `.env`, nunca en
el navegador ni en git.

### Archivos

Ninguno de estos archivos va a git. Los valores de la base local quedaron
comentados con `# local:` para volver a ella si hace falta.

**`.env`** (raíz, el worker). Ya tiene la base de la nube:

```ini
DATABASE_URL=postgresql://postgres.dnqyravczgcpuowijbja:<contraseña>@aws-0-sa-east-1.pooler.supabase.com:5432/postgres
SUPABASE_URL=https://dnqyravczgcpuowijbja.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJ...            # la service_role
```

Si la contraseña tiene caracteres especiales, van codificados (`@` → `%40`);
más simple: resetearla en *Project Settings → Database* por una solo con letras
y números. Completá además:

```ini
WEB_BASE_URL=https://automotive.tudominio.com.ar
RESEND_API_KEY=re_...
EMAIL_FROM=Automotive <alertas@tudominio.com.ar>
TELEGRAM_ADMIN_CHAT_ID=123456789            # el del paso 5
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...                # la del paso 4
```

**`web\.env.local`**. Ya tiene `NEXT_PUBLIC_SUPABASE_URL`
(`https://dnqyravczgcpuowijbja.supabase.co`), `NEXT_PUBLIC_SUPABASE_ANON_KEY`
(la `anon`), `SUPABASE_SERVICE_ROLE_KEY` y `NEXT_PUBLIC_TELEGRAM_BOT_USERNAME`.
Completá:

```ini
SITE_URL=https://automotive.tudominio.com.ar
NEXT_PUBLIC_CONTACT_EMAIL=vos@tudominio.com.ar   # aparece en /privacidad y /terminos
```

Las variables `NEXT_PUBLIC_*` quedan fijas al compilar: después de cambiarlas,
`ops\update.ps1` (o `npm run build` en `web\` y reiniciar la tarea Web).

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
```

Docker solo hace falta para el backup diario (corre `pg_dump` en la imagen
`postgres:17`; el script abre Docker Desktop si está cerrado). Si alguna vez
levantás el stack local de desarrollo (`npx supabase start`), Docker publica sus
puertos en todas las interfaces: bloquealos para tu red local con

```powershell
New-NetFirewallRule -DisplayName "AutoMotive: Supabase solo local" -Direction Inbound `
  -Protocol TCP -LocalPort 54321-54329 -RemoteAddress Any -Action Block
```

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
   `npm run build`) y registra cuatro tareas en *Programador de tareas →
   AutoMotive* (si quedó la tarea *Supabase* de cuando la base era local, la
   borra):

   | Tarea | Cuándo | Qué hace |
   |---|---|---|
   | Web | al iniciar sesión | `next start` en 127.0.0.1:3000, se reinicia si se cae |
   | Worker | al iniciar sesión | `python main.py`, se reinicia si se cae |
   | Watchdog | cada 5 min | te avisa por Telegram si el worker, la base o la web dejan de responder, y cuando vuelven |
   | Backup | 03:30 todos los días | `pg_dump` de la base de la nube (esquemas `public`, `auth` y el historial de migraciones), guarda los últimos 14 |

   El plan Free de Supabase no incluye backups descargables: el de esta tarea
   es el único.

3. Verificá:

   ```powershell
   cd worker; python -m tools.watchdog --dry   # base OK · worker OK · web OK
   ```

   Y en `https://automotive.tudominio.com.ar/admin/sources`, «Worker: late ahora».

Para darte acceso a `/admin`, primero ingresá una vez en la web con tu email y
después, en el dashboard de Supabase → *SQL Editor*:

```sql
update public.profiles set role = 'admin' where email = 'vos@tudominio.com.ar';
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

El script hace un backup, aplica las migraciones pendientes a la base de la
nube (`npx supabase db push` con el `DATABASE_URL` del `.env`), instala las
dependencias, compila la web y reinicia las tareas Web y Worker. Si el build
falla, la versión anterior sigue corriendo.

**Tests.** Corren contra el stack **local** (`npx supabase start` a mano, con
Docker), nunca contra la nube:
- `pytest` con `TEST_DATABASE_URL` apunta a `automotive_test` del stack local.
  Después de cada migración, recreá esa base con `python -m tools.test_db`.
- `npx supabase test db` corre en transacciones que se descartan.
- `npm run e2e` usa `web\.env.local`, que ahora apunta a la nube: antes de
  correrlo, volvé a los valores `# local:` de ese archivo (y después
  restauralos y recompilá). El e2e además necesita el worker **parado** (si no,
  el worker real toma los pedidos del modo asistido que el test simula) y el
  puerto 3000 libre (compila y sirve la web de producción: el overlay de
  `next dev` tapa la barra de navegación del celular).

**Restaurar un backup** (pisa las tablas de `public`; pensado para un proyecto
recién creado o para volver atrás el mismo). Con Docker abierto, desde la raíz:

```powershell
Get-ScheduledTask -TaskPath \AutoMotive\ | Stop-ScheduledTask
$env:PGURL = ((Get-Content .env | Select-String '^DATABASE_URL=') -replace '^DATABASE_URL=', '').Trim()
$dir = "$env:OneDrive\AutoMotive\backups"; $f = "automotive-AAAAMMDD-HHMM.dump"
# 1) usuarios (auth.users...): antes que public, que los referencia
docker run --rm -e PGURL -v "${dir}:/in" postgres:17 sh -c "set -f; pg_restore -d `$PGURL --data-only -n auth /in/$f"
# 2) public y el historial de migraciones
docker run --rm -e PGURL -v "${dir}:/in" postgres:17 sh -c "set -f; pg_restore -d `$PGURL --clean --if-exists --no-owner -n public -n supabase_migrations /in/$f"
Get-ScheduledTask -TaskPath \AutoMotive\ | Start-ScheduledTask
```

Unos pocos errores de `default privileges` y «schema public already exists» son
esperables. Si en el paso 1 los usuarios ya existen, da claves duplicadas y se
puede ignorar. Para ensayar sin tocar nada, restaurá en un proyecto Free nuevo
de la organización `automotive`.

**Rotar las claves de Supabase** (si se filtró la `service_role`, la contraseña
de la base o la clave JWT):
- Contraseña de la base: *Project Settings → Database → Reset database
  password*, y actualizá `DATABASE_URL` en `.env`.
- Claves de la API: *Project Settings → JWT Keys* (rotar cierra todas las
  sesiones). Copiá la `anon` y la `service_role` nuevas a `.env` y
  `web\.env.local`, y corré `ops\update.ps1` para recompilar la web.

**Desinstalar las tareas:** `powershell -ExecutionPolicy Bypass -File ops\uninstall-tasks.ps1`.

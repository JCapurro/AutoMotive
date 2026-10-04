# Graph Report - AutoMotive  (2026-10-04)

## Corpus Check
- 370 files · ~267,996 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 3359 nodes · 8507 edges · 186 communities (167 shown, 19 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 483 edges (avg confidence: 0.53)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `dd36d73f`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Links
- description_facts.py
- service.py
- billing/page.tsx
- requireUser
- createAdminClient
- crawl.py
- meta-pixel.tsx
- TelegramActionTests
- parse
- app/listings/[id]/page.tsx
- ListingFacts
- test_llm_jobs_postgres.py
- connection
- database.ts
- ingest.py
- normalize_text
- settings/page.tsx
- enrich.py
- keyword_partial
- search-form.tsx
- db.ts
- facebook.py
- Listing
- fiesta_listing
- pipeline/llm_jobs.py
- test_llm_drafts.py
- watchdog.py
- format.ts
- ClaudeCliProvider
- PRD — Automotive
- listing-actions.tsx
- scraper_cli.py
- ingest
- test_llm_claude_cli.py
- PriceRef
- listings.py
- matching.py
- templates.py
- browser_context
- red_flags.py
- geo.py
- Migration
- 20260927120000_core_schema.sql
- test_parsers.py
- devDependencies
- dependencies
- compilerOptions
- [notificationId]/route.ts
- IntelligenceConfig
- PRDCopyTests
- test_ingest_postgres.py
- Page
- mercadopago-server.ts
- 20261007120000_ese_auto_commercial.sql
- createClient
- scheduler.py
- PostgresTestCase
- 20261003120000_f6_backoffice_metrics.sql
- SourceAlerts
- components.json
- 20260927120100_rls.sql
- ResolvePriceTests
- test_db_postgres.py
- matches.py
- .listing
- Automotive — web
- AutoCosmosScraper
- startup_warnings
- .rows
- metrics/page.tsx
- patch
- 7 Textos y piezas listos para preparar
- CommercialTests
- Ese Auto · propuesta comercial y proyección
- Estrategia de lanzamiento de Ese Auto
- test_handlers.py
- Comunes a cualquier ruta
- Puesta en producción del piloto (F7)
- Automotive — Plan técnico del MVP
- mercadolibre.py
- MercadoPagoTests
- rescore.py
- v6.py
- LLMProvider
- saved/page.tsx
- 20261001120000_f4_web.sql
- test_intelligence.py
- render_all
- Configuración de cuentas de Ese Auto
- 11 Conversaciones y soporte
- PROPUESTA_COMERCIAL.md
- Setup
- prompts/__init__.py
- app/app/layout.tsx
- 13. Roadmap por fases
- scripts
- 40. Modelo conceptual de datos
- toggle-group.tsx
- 8 Anuncios de Meta
- test_notifications_templates.py
- 5. Pipeline de ingesta (§14, §15, §42)
- db/__init__.py
- Amount
- RedFlagTests
- to_profile
- 6. Intelligence (§16–20, §24, §25, §44)
- 4. Modelo de datos (Postgres / Supabase)
- test_db.py
- 47. Riesgos principales
- 58. Definición final del producto
- AmountTests
- 20261002120000_f5_llm.sql
- 20261004120000_f7_pilot.sql
- 10. Propuesta de valor
- 12. Flujo principal
- 15. Detección de publicación nueva
- 21. Alertas
- 22. Tipos de alertas
- 28. Dashboard principal
- 48. Feature prioritization
- 50. Home / landing propuesta
- 20260927120200_telegram_bot_compat.sql
- 20260928120000_f1_ingest.sql
- 20261006120000_description_facts.sql
- loading.tsx
- package.json
- kavak.py
- test_notifications_channels.py
- 16. Matching Engine
- 23. Página de resultado
- 33. Freemium inicial
- 36. Métricas de activación
- 20260930120000_f3_notifications.sql
- opengraph-image.tsx
- main.py
- 9 Presupuesto y reglas para invertir
- 20261009120000_meta_conversions.sql
- raw_pages.py
- TelegramChannel
- pgcase.py
- assess
- ResendEmailChannelTests
- sonner
- 20261005120000_f7_ops.sql
- AGENTS.md
- eslint.config.mjs
- next.config.ts
- postcss.config.mjs
- 8. Capa LLM (§43, §44)
- automotive-worker
- 20261008120000_mercadopago.sql
- test_description_facts.py
- Mercado Pago · cobro y acceso automático
- 7. Motor de notificaciones (§21, §22, §32, §47)
- .__init__
- vercel.json

## God Nodes (most connected - your core abstractions)
1. `Links` - 88 edges
2. `createClient()` - 74 edges
3. `Listing` - 72 edges
4. `connection()` - 70 edges
5. `PRD — Automotive` - 59 edges
6. `requireUser()` - 54 edges
7. `createAdminClient()` - 51 edges
8. `Page` - 48 edges
9. `PostgresTestCase` - 45 edges
10. `Notifier` - 44 edges

## Surprising Connections (you probably didn't know these)
- `DigestItem` --uses--> `Links`  [INFERRED]
  worker/notifications/templates.py → worker/notifications/links.py
- `ResetPasswordPage()` --calls--> `createClient()`  [EXTRACTED]
  web/app/auth/reset-password/page.tsx → web/lib/supabase/server.ts
- `LoginForm()` --indirect_call--> `resendConfirmation()`  [INFERRED]
  web/app/login/login-form.tsx → web/app/login/actions.ts
- `LoginPage()` --calls--> `safeNext()`  [EXTRACTED]
  web/app/login/page.tsx → web/lib/navigation.ts
- `EXAMPLE` --calls--> `money()`  [EXTRACTED]
  web/app/page.tsx → web/lib/format.ts

## Import Cycles
- None detected.

## Communities (186 total, 19 thin omitted)

### Community 0 - "Links"
Cohesion: 0.12
Nodes (18): CallbackQueryHandler, Update, _allowed(), help_(), invalid_code_text(), linked_text(), The Telegram bot after F4: it links the account and answers alert buttons.…, register() (+10 more)

### Community 1 - "description_facts.py"
Cohesion: 0.17
Nodes (18): _after_label(), _amounts(), _before_label(), _close(), _currency(), _distinct(), _km(), _plausible() (+10 more)

### Community 2 - "service.py"
Cohesion: 0.06
Nodes (52): at_least(), rank(), Opportunity levels (§20, sección 6.4), thresholds from…, build_items(), digest_loop(), Any, datetime, Daily digest (§32, sección 7.2). Every day at app_config.digest_hour (ART,… (+44 more)

### Community 3 - "billing/page.tsx"
Cohesion: 0.08
Nodes (37): ActionResult, shape(), SourceInput, updateConfig(), updateSource(), confirmPayment(), launchCommercialPilot(), recordRefund() (+29 more)

### Community 4 - "requireUser"
Cohesion: 0.07
Nodes (54): Dashboard(), metadata, joinWaitlist(), reportVisibleResults(), trackProCta(), checkPayment(), ownedCheckout(), startPayment() (+46 more)

### Community 5 - "createAdminClient"
Cohesion: 0.12
Nodes (44): ConfigPage(), HINTS, metadata, ErrorsPage(), metadata, metadata, metadata, MatchesPage() (+36 more)

### Community 6 - "crawl.py"
Cohesion: 0.12
Nodes (24): log_error(), Record a pipeline error. Never raises: observability must not break the…, crawl_due(), derive_targets(), Any, BatchHandler, HealthHandler, SourceHealth (+16 more)

### Community 7 - "meta-pixel.tsx"
Cohesion: 0.06
Nodes (38): markSeen(), metadata, mono, sans, viewport, LoginForm(), metadata, metadata (+30 more)

### Community 9 - "parse"
Cohesion: 0.18
Nodes (8): parse(), _plain(), _published_is(), Lowercase, no accents, no invisible characters; line breaks kept., The facts a listing's title and description state. None without text. The title…, _year(), FinancingTests, KmAndYearTests

### Community 10 - "app/listings/[id]/page.tsx"
Cohesion: 0.07
Nodes (39): markFor(), metadata, plain(), priceHistory(), SAME, SCORE_PART, ScoreInWords(), Similar (+31 more)

### Community 11 - "ListingFacts"
Cohesion: 0.13
Nodes (24): AsyncAnthropic, AnthropicApiProvider, CatalogModel, M, The Claude API with an API key (F7, punto 6): the provider for serving the…, `claude -p` as the pilot's LLM (sección 8.2). claude -p --output-format json…, The LLM layer (sección 8): providers behind one interface. provider.py…, LocalProvider (+16 more)

### Community 12 - "test_llm_jobs_postgres.py"
Cohesion: 0.16
Nodes (6): LlmJobsCase, QueueTests, The llm_jobs queue against the local Supabase Postgres (sección 8.4): what the…, What the web can do with the user's session (sección 4.4)., Run `sql` as the signed-in web user (role authenticated, RLS on)., WebAccessTests

### Community 13 - "connection"
Cohesion: 0.08
Nodes (46): connection(), AsyncConnection, get_geocode_cache(), has_fresh_geocode_failure(), Cache that this query failed to geocode, so we don't keep retrying., True if the query was tried and failed within the past `max_age_days`., set_geocode_cache(), set_geocode_cache_failure() (+38 more)

### Community 14 - "database.ts"
Cohesion: 0.10
Nodes (22): MatchInspector(), metadata, metadata, NotificationInspector(), context(), Inspection, inspectMatch(), inspectNotification() (+14 more)

### Community 15 - "ingest.py"
Cohesion: 0.13
Nodes (30): load_models(), Model-level rows with their trims, aliases and production years., DescriptionFacts, _empty(), _facts(), _geocode_rows(), ingest_rows(), IngestConfig (+22 more)

### Community 16 - "normalize_text"
Cohesion: 0.09
Nodes (32): vehicle_catalog: canonical make/model/trim names. The catalog is small (a few…, normalize_brand(), normalize_model(), normalize_text(), Brand/model normalization so comparables match across sources. Used both at…, Model names — strip extra trim qualifiers leaving only the base model., _strip_accents(), _classify() (+24 more)

### Community 17 - "settings/page.tsx"
Cohesion: 0.14
Nodes (18): RFC-8058, POST(), metadata, metadata, ResetPasswordPage(), unsubscribe(), metadata, UnsubscribePage() (+10 more)

### Community 18 - "enrich.py"
Cohesion: 0.10
Nodes (35): Refresher, mark_detail_checked(), DescriptionLLM, drain(), enrich_pass(), ingest_detail(), Any, Listing (+27 more)

### Community 19 - "keyword_partial"
Cohesion: 0.15
Nodes (12): Run keyword detection over the title and tag the listing. Statistical detection…, is_suspicious_discount(), keyword_partial(), Detect listings whose advertised price isn't the real total. In AR auto…, Return a reason string if title/description looks like an anticipo/plan, else…, Return a reason if the price is implausibly low relative to median., Discount > SUSPICIOUS but < ALMOST_CERTAIN — worth flagging in the notification…, statistical_partial() (+4 more)

### Community 20 - "search-form.tsx"
Cohesion: 0.04
Nodes (81): AssistedStart, canonical(), enabledSources(), escapeLike(), jobText(), Preview, PreviewListing, previewSearch() (+73 more)

### Community 21 - "db.ts"
Cohesion: 0.11
Nodes (25): SEARCH_FILTERS, alertedUser(), signIn(), ask(), setHeartbeat(), signIn(), globalSetup(), main() (+17 more)

### Community 22 - "facebook.py"
Cohesion: 0.10
Nodes (28): CollectorBlocked, The source answered with a login wall, a security challenge or no session. The…, _after_colon(), _city_slug(), _city_slug_from_origin(), _extract_location(), FacebookMarketplaceScraper, _looks_like_location() (+20 more)

### Community 23 - "Listing"
Cohesion: 0.08
Nodes (31): NamedTuple, Listing, One ad as a collector read it, before normalization. `marca`/`modelo`/`version`…, FxQuote, attrs_hash(), fingerprint(), _hash(), listing_facts() (+23 more)

### Community 24 - "fiesta_listing"
Cohesion: 0.15
Nodes (14): evaluate(), match(), The reasons if every hard filter is ok or unknown; None if one fails., CurrencyTests, fiesta_listing(), fiesta_profile(), GoldenFixtureTests, GuardAndLevelTests (+6 more)

### Community 25 - "pipeline/llm_jobs.py"
Cohesion: 0.13
Nodes (22): claim(), expire(), finish(), Any, AsyncConnection, llm_jobs: the queue between the web and the LLM layer (sección 8.4). The web…, The oldest queued job of `kinds`, now 'running'; None if there is none., done' with its output, or 'failed' with the error (never both). (+14 more)

### Community 26 - "test_llm_drafts.py"
Cohesion: 0.11
Nodes (33): _km(), _money(), normalize_draft(), normalize_drafts(), _positive(), Any, CatalogModel, date (+25 more)

### Community 27 - "watchdog.py"
Cohesion: 0.09
Nodes (30): timedelta, beat(), last_beat(), datetime, The worker's heartbeat (F7, punto 8): one row in worker_heartbeat, updated…, started_now(), EnvFileTests, F7, punto 8: the watchdog's decisions (tools/watchdog.py), without network or… (+22 more)

### Community 28 - "format.ts"
Cohesion: 0.11
Nodes (34): AdminListingPage(), escapeLike(), ListingsPage(), DIGEST_SECTION, DigestItem, InboxPage(), metadata, WebPayload (+26 more)

### Community 29 - "ClaudeCliProvider"
Cohesion: 0.09
Nodes (24): Runner, ClaudeCliProvider, parse_envelope(), Any, CatalogModel, M, The structured answer inside `--output-format json`'s envelope., load_recordings() (+16 more)

### Community 30 - "PRD — Automotive"
Cohesion: 0.04
Nodes (51): 11. Principios de producto, 13. Concepto de Search Profile, 14. Ingesta de publicaciones, 17. Opportunity Score, 18. Componentes iniciales del Opportunity Score, 19. Price Intelligence, 1. Resumen ejecutivo, 20. Niveles de oportunidad (+43 more)

### Community 31 - "listing-actions.tsx"
Cohesion: 0.07
Nodes (53): answerInfluence(), currentStatus(), Purchase, recordPurchase(), setDiscardReason(), setSaved(), setStatus(), Supabase (+45 more)

### Community 32 - "scraper_cli.py"
Cohesion: 0.09
Nodes (30): shutdown(), _collector_loop(), AbstractEventLoop, Any, T, Run collector coroutines on an event loop that can start subprocesses.…, run_collector(), AsyncConnection (+22 more)

### Community 33 - "ingest"
Cohesion: 0.18
Nodes (8): ingest(), Listing, normalize → geocode → upsert. The whole batch is one transaction., CanonicalUpsertTests, card(), DescriptionFactsTests, EnrichmentTests, Normalization v3: the description as a source of the price.

### Community 34 - "test_llm_claude_cli.py"
Cohesion: 0.16
Nodes (26): BaseModel, Run the CLI once and return its stdout. Raises LLMTimeout / LLMError., run_cli(), json_schema(), Any, The model's JSON Schema, self-contained: `$defs` inlined and titles dropped.…, envelope(), FakeRunner (+18 more)

### Community 35 - "PriceRef"
Cohesion: 0.13
Nodes (16): AST, fetch(), PriceRef, Any, public.comparables() for one listing. `cfg` overrides app_config.comparables., _merge(), Any, ConfigTests (+8 more)

### Community 36 - "listings.py"
Cohesion: 0.09
Nodes (34): enrichment_queue(), find_repost_of(), insert_listing(), insert_snapshot(), llm_facts_last_day(), lock_existing(), mark_gone(), matched_recheck_queue() (+26 more)

### Community 37 - "matching.py"
Cohesion: 0.13
Nodes (25): Result, _choice(), distance_km(), evaluate(), filter_currency(), _km(), _location(), MatchResult (+17 more)

### Community 38 - "templates.py"
Cohesion: 0.14
Nodes (29): age_line(), ago_long(), before_after(), Button, Content, _digest(), DigestItem, email() (+21 more)

### Community 39 - "browser_context"
Cohesion: 0.33
Nodes (6): Browser, BrowserContext, browser_context(), _ensure_browser(), Shared Playwright helpers — reuse a single browser instance across scrapers., Yield a fresh browser context. Closes context on exit; browser is reused.

### Community 40 - "red_flags.py"
Cohesion: 0.19
Nodes (16): ago(), money(), number(), Every user-facing string of the intelligence layer (§19, §24, §25). Kept in one…, USD 10.300 · ARS 12.500.000 (Argentine thousands separator)., _age_years(), description_known(), description_mismatches() (+8 more)

### Community 41 - "geo.py"
Cohesion: 0.12
Nodes (20): Coords, _fallback_can_stand_alone(), filter_listings_by_radius(), geocode_location(), _geocode_nominatim(), haversine_km(), _looks_like_non_location_query(), _lookup_known_location() (+12 more)

### Community 42 - "Migration"
Cohesion: 0.13
Nodes (11): Row, LoadEmailsTests, _make_sqlite(), MigrateSqliteTests, Path, load_emails(), main(), Migration (+3 more)

### Community 43 - "20260927120000_core_schema.sql"
Cohesion: 0.13
Nodes (29): app_config_set_updated_at, crawl_targets_set_updated_at, matches_set_updated_at, on_auth_user_created, owned_vehicles_set_updated_at, profiles_set_updated_at, public.app_config, public.collector_runs (+21 more)

### Community 44 - "test_parsers.py"
Cohesion: 0.09
Nodes (9): AutoCosmosParserTests, FacebookParserTests, html(), KavakParserTests, MercadoLibreParserTests, Search and detail parsers against saved HTML (tests/fixtures/html). The…, raw_pages keep a slimmed page: every parser reads the same from it., RawPageTests (+1 more)

### Community 45 - "devDependencies"
Cohesion: 0.07
Nodes (29): babel-plugin-react-compiler, eslint, eslint-config-next, pg, @playwright/test, tailwindcss, @tailwindcss/postcss, tsx (+21 more)

### Community 46 - "dependencies"
Cohesion: 0.07
Nodes (29): class-variance-authority, cn, lucide-react, next, next-themes, radix-ui, react-dom, recharts (+21 more)

### Community 47 - "compilerOptions"
Cohesion: 0.07
Nodes (28): dom, dom.iterable, esnext, **/*.mts, .next/dev/types/**/*.ts, next-env.d.ts, .next/types/**/*.ts, node_modules (+20 more)

### Community 48 - "[notificationId]/route.ts"
Cohesion: 0.33
Nodes (10): GET(), handle(), HEAD(), peek(), Row, track(), ClickTarget, destination() (+2 more)

### Community 49 - "IntelligenceConfig"
Cohesion: 0.19
Nodes (23): diff_pct(), How far below the median the published price is, in % (negative = above)., IntelligenceConfig, level_for(), 🔥 high ≥ 85 · 🟢 good ≥ 70 · 🟡 match ≥ 50 · ⚪ low. `cap` is the highest level…, age_hours(), clamp(), completeness_component() (+15 more)

### Community 50 - "PRDCopyTests"
Cohesion: 0.24
Nodes (3): notification(), PRDCopyTests, The §22 lines, in order, at the top of the Telegram message and the email text.

### Community 51 - "test_ingest_postgres.py"
Cohesion: 0.15
Nodes (12): ListingDetail, What fetch_detail() found at a listing's URL (sección 5.5). `gone` means the…, fake(), FakeSource, IngestCase, MatchedRecheckTests, Listing, F1 ingestion against the local Supabase Postgres (docs/TECHNICAL_PLAN.md,… (+4 more)

### Community 52 - "Page"
Cohesion: 0.11
Nodes (14): BaseScraper, Apply user filters that the source could not enforce server-side., Download the ad's own page, with the source's login-wall and session checks,…, Read the ad's page: description, version, transmission, seller type, every…, What raw_pages keeps of a detail page: enough for parse_detail()., _expand(), fetch_page(), fetch_rendered() (+6 more)

### Community 53 - "mercadopago-server.ts"
Cohesion: 0.08
Nodes (49): GET(), POST(), reply(), checkoutUrl(), paymentPeriod(), sameSecret(), api(), applyPayment() (+41 more)

### Community 54 - "20261007120000_ese_auto_commercial.sql"
Cohesion: 0.09
Nodes (8): llm_jobs_guard_commercial, matches_guard_commercial, public.commercial_payments, public.guard_assisted_commercial_access(), public.guard_match_access(), public.plan_limits_for(), public.profiles, public.refund_commercial_payment()

### Community 55 - "createClient"
Cohesion: 0.14
Nodes (24): declineRenewal(), GET(), GET(), PasswordState, updatePassword(), PasswordForm(), POST(), authenticate() (+16 more)

### Community 56 - "scheduler.py"
Cohesion: 0.09
Nodes (29): Price Intelligence (§19, sección 6.2). The statistics come from the SQL…, Weights, curves and thresholds of the intelligence layer (sección 6, Apéndice…, Evaluation, One listing × one profile → everything a match row stores. Pure.…, Backfill one profile. Returns how many listings it matched., rematch_profile(), batch_handler(), _key() (+21 more)

### Community 57 - "PostgresTestCase"
Cohesion: 0.14
Nodes (24): build_notifier(), The channels this worker can deliver on (sección 7.2)., ResendEmailChannel, WebChannel, MatchCandidate, Notifier, A new, non-backfill match the crawl just stored., PostgresTestCase (+16 more)

### Community 58 - "20261003120000_f6_backoffice_metrics.sql"
Cohesion: 0.10
Nodes (16): pro_waitlist_set_updated_at, public.admin_notification_daily, public.admin_score_histogram, public.admin_searches, public.admin_source_health, public.admin_users, public.join_waitlist(), public.pro_waitlist (+8 more)

### Community 59 - "SourceAlerts"
Cohesion: 0.10
Nodes (26): get_config(), Any, finish_run(), Observability (sección 10, §46): collector_runs, pipeline_errors and source…, A source's failure streak after a run (the admin alert reads it)., Close a run and keep the source's health counters in step. Returns the source's…, SourceHealth, start_run() (+18 more)

### Community 60 - "components.json"
Cohesion: 0.09
Nodes (21): aliases, components, hooks, lib, ui, utils, iconLibrary, menuAccent (+13 more)

### Community 61 - "20260927120100_rls.sql"
Cohesion: 0.10
Nodes (20): public.app_config, public.collector_runs, public.crawl_targets, public.enforce_plan_limits(), public.events, public.fx_rates, public.geocode_cache, public.listing_snapshots (+12 more)

### Community 63 - "test_db_postgres.py"
Cohesion: 0.13
Nodes (8): AlertRepoTests, GeocodeAndConfigTests, _listing(), The bot's data layer against a real Postgres with the supabase/ migrations. Run…, /start <code> (public.link_telegram, F4)., SeenMatchesTests, store(), TelegramLinkTests

### Community 64 - "matches.py"
Cohesion: 0.11
Nodes (26): AsyncConnectionPool, close_pool(), connection_kwargs(), open_pool(), Any, Async Postgres connection pool (psycopg 3), one per worker process. The worker…, Open the process-wide pool (idempotent)., _existing() (+18 more)

### Community 65 - ".listing"
Cohesion: 0.22
Nodes (6): ComparablesCascadeTests, IntelligenceCase, PriceRef, Insert a listing row directly: comparables are about stored columns., Sección 6.2: trim+transmission → transmission → model, first with n ≥ min_n., ScoredMatchesTests

### Community 66 - "Automotive — web"
Cohesion: 0.22
Nodes (7): Configuración del proyecto alojado antes de publicar, Desarrollo, Registro y acceso con Supabase Auth, Automotive — web, Correrla, Rutas (plan técnico, sección 9), Tests

### Community 67 - "AutoCosmosScraper"
Cohesion: 0.12
Nodes (19): range, AutoCosmosScraper, _price(), AsyncClient, Listing, Response, GET, retried on a network error or a 5xx; the last answer or error wins., (price, currency, partial reason) from the price blocks of a card or detail. A… (+11 more)

### Community 68 - "startup_warnings"
Cohesion: 0.14
Nodes (10): What this configuration leaves off (F7, punto 5): one line per channel, metric…, startup_warnings(), _database(), db_test_skip_reason(), Why the DB tests can't run here, or None. They TRUNCATE tables, so they only…, ConfigTests, F7, punto 4: the DB tests TRUNCATE, so they never touch the pilot's database., F7, punto 5: every channel or metric the .env leaves off is logged at startup. (+2 more)

### Community 69 - ".rows"
Cohesion: 0.25
Nodes (6): RuntimeError, CrawlTargetsTests, _FakeBot, One crawl-loop tick with every target due, no jitter., The crawl feeds the notification engine (sección 7): silent first run, one…, TelegramAlertsTests

### Community 70 - "metrics/page.tsx"
Cohesion: 0.15
Nodes (16): CTA_EVENTS, day(), levelLabel(), median(), metadata, MetricsPage(), Rate(), WAITLIST (+8 more)

### Community 71 - "patch"
Cohesion: 0.33
Nodes (5): patch, _is_recent(), Drop listings published more than `max_age_days` ago. If the source doesn't say…, _is_recent reads stored listing rows (published_at is a timestamptz)., SchedulerRecencyTests

### Community 72 - "7 Textos y piezas listos para preparar"
Cohesion: 0.13
Nodes (15): 7 Textos y piezas listos para preparar, P01 Qué es Ese Auto, P02 Cómo funciona, P03 Qué incluye la prueba, P04 Presentación de Juan, P05 Volver a buscar lo mismo, P06 Mirar un precio con contexto, P07 En qué parte estás (+7 more)

### Community 74 - "Ese Auto · propuesta comercial y proyección"
Cohesion: 0.12
Nodes (16): 1. Qué vender, 2. Qué ya existe y qué falta, 3. Referencias de mercado, 4. Alternativas iniciales conservadas como referencia, 5. Oferta seleccionada en pesos: B, 6. Proyección a seis meses, 7. Validación y salida comercial, 8. Decisión a registrar (+8 more)

### Community 76 - "Estrategia de lanzamiento de Ese Auto"
Cohesion: 0.15
Nodes (13): 10 Medición y decisiones, 12 Trabajo semanal y siguiente decisión, 13 Fuentes y estado de la evidencia, 1 La apuesta comercial, 2 Oferta y límites de lo que vamos a comunicar, 3 Desde qué cuentas y herramientas, 4 Preparación antes del día 0, 5 Dirección visual y producción (+5 more)

### Community 77 - "test_handlers.py"
Cohesion: 0.21
Nodes (9): start(), _ctx(), _FakeChat, _FakeMessage, _FakeUpdate, _FakeUser, The bot after F4: /start <code> links the account, the old wizard commands…, RetiredWizardTests (+1 more)

### Community 78 - "Comunes a cualquier ruta"
Cohesion: 0.12
Nodes (16): COM-02 · Una oferta coherente, COM-03 · Límites que siguen vigentes al vencer, COM-04 y COM-05 · Cobro y ciclo de vida, COM-06 · Autogestión, COM-07 · Producto que se puede prometer, COM-08 · Medir rentabilidad, no solo intención, COM-09 · Operación comercial, COM-10 · Salida controlada (+8 more)

### Community 79 - "Puesta en producción del piloto (F7)"
Cohesion: 0.13
Nodes (15): 10. Prueba de aceptación, 1. Dominio en Cloudflare, 2. Túnel de Cloudflare, 3. Resend (emails de login y de alertas), 4. API key de Anthropic (modo asistido), 5. Chat de Telegram para las alertas operativas, 6. Sesiones de MercadoLibre y Facebook, 7. Configuración (+7 more)

### Community 80 - "Automotive — Plan técnico del MVP"
Cohesion: 0.18
Nodes (11): 10. Backoffice y observabilidad (§45, §46), 11. Métricas y eventos (§35–38, §53), 12. Freemium (§33, §34), 14. Riesgos y decisiones abiertas, 15. Trazabilidad PRD → plan, 1. Punto de partida y gaps, 2. Arquitectura objetivo, 3. Estructura del repo (+3 more)

### Community 81 - "mercadolibre.py"
Cohesion: 0.14
Nodes (19): _blocked(), _browser_storage_state(), _build_url(), _extract_id(), _looks_like_login_wall(), _page_looks_like_login_wall(), _parse_card(), parse_search() (+11 more)

### Community 83 - "rescore.py"
Cohesion: 0.18
Nodes (16): purge_older_than(), nightly_loop(), Any, datetime, Re-scoring existing matches (sección 6.1). * After enrichment: transmission or…, Re-score (search_profile_id, listing_id) pairs. Returns rows updated., Seconds from `now` to the next `hour` ("HH:MM", ART)., Re-score matches once a night, then purge stale listings; also, once at… (+8 more)

### Community 84 - "v6.py"
Cohesion: 0.13
Nodes (30): BeautifulSoup, AutoCosmos AR scraper. AutoCosmos exposes a public listings page at…, parse_relative_date(), Parse Spanish relative date strings shown by AR car classifieds. Examples…, Return a unix timestamp inferred from a Spanish relative-date string., _strip_accents(), dedupe(), json_ld() (+22 more)

### Community 85 - "LLMProvider"
Cohesion: 0.08
Nodes (36): fixture, skipif, build_provider(), LLMProvider, CatalogModel, Protocol, Modo asistido (§12): one draft per vehicle the text asks for. `catalog` lets…, Optional: facts stated in a listing's free text (red flags, sección 6.5). (+28 more)

### Community 86 - "saved/page.tsx"
Cohesion: 0.18
Nodes (13): FOLLOWED, metadata, SavedPage(), Snapshot, watchEvents(), LevelBadge(), STATUS_STYLE, StatusBadge() (+5 more)

### Community 87 - "20261001120000_f4_web.sql"
Cohesion: 0.24
Nodes (7): public.dashboard_summary(), public.link_telegram(), public.match_cards, public.profiles, public.recent_opportunities(), public.search_result_counts(), public.search_results()

### Community 88 - "test_intelligence.py"
Cohesion: 0.24
Nodes (9): RedFlag, Any, datetime, question_keys(), Questions for the seller (§25, sección 6.6). Deterministic templates. Always:…, One message ready to copy: "Hola, ¿cómo estás? ¿Lo seguís teniendo? …"., seller_questions(), F2 intelligence, pure (docs/TECHNICAL_PLAN.md, sección 6): no network, no… (+1 more)

### Community 89 - "render_all"
Cohesion: 0.29
Nodes (5): CopyLintTests, Notification, §19: no "vale", "precio real", "tasación" in any alert., render_all(), TemplateSnapshotTests

### Community 90 - "Configuración de cuentas de Ese Auto"
Cohesion: 0.18
Nodes (9): Aplicación desde el celular o navegador habitual, Cierre de la configuración, Configuración de cuentas de Ese Auto, Estado comprobado, Instagram, Qué debe ver alguien al entrar al perfil, Referencias, Revisión de Meta (+1 more)

### Community 91 - "11 Conversaciones y soporte"
Cohesion: 0.29
Nodes (7): 11 Conversaciones y soporte, Consulta que llega al Twitter personal, Pedido de opinión después de usar la prueba, Persona que pregunta cómo empezar, Pregunta sobre el precio, Pregunta sobre si un auto está garantizado, Profesional que escribe DEMO

### Community 92 - "PROPUESTA_COMERCIAL.md"
Cohesion: 0.24
Nodes (4): Comprobaciones reproducibles, Ese Auto · implementación del lanzamiento comercial, Habilitación del entorno destino, Límites de esta entrega

### Community 93 - "Setup"
Cohesion: 0.10
Nodes (20): Agregar una nueva fuente, AutoMotive, Backoffice y métricas (F6), Base de datos (Supabase), Comandos del bot, Correr el bot, Correr la web, Cómo funciona (+12 more)

### Community 95 - "prompts/__init__.py"
Cohesion: 0.24
Nodes (8): catalog_text(), load(), parse_search_system(), parse_search_user(), CatalogModel, date, System prompts and user messages of the LLM layer, shared by every provider.…, One line per make: "Ford: Fiesta [S, SE, Titanium]; Focus [...]".

### Community 96 - "app/app/layout.tsx"
Cohesion: 0.16
Nodes (16): markOpened(), AppLayout(), active(), BottomNav(), ITEMS, MobileInboxLink(), TopNav(), Inbox (+8 more)

### Community 97 - "13. Roadmap por fases"
Cohesion: 0.20
Nodes (10): 13. Roadmap por fases, F0 · Fundaciones (M), F1 · Ingesta centrada en la publicación (L), F2 · Intelligence (M), F3 · Motor de notificaciones (M), F4 · Web MVP (L), F5 · Modo asistido con LLM (S–M), F6 · Backoffice, métricas y monetización (M) (+2 more)

### Community 98 - "scripts"
Cohesion: 0.20
Nodes (10): scripts, build, dev, e2e, e2e:seed, gen:types, lint, start (+2 more)

### Community 99 - "40. Modelo conceptual de datos"
Cohesion: 0.22
Nodes (9): 40. Modelo conceptual de datos, Listing, ListingSnapshot, Match, OwnedVehicle, SearchProfile, User, UserListingInteraction (+1 more)

### Community 100 - "toggle-group.tsx"
Cohesion: 0.31
Nodes (6): react, ToggleGroupContext, ToggleGroupItem(), Toggle(), toggleVariants, react

### Community 101 - "8 Anuncios de Meta"
Cohesion: 0.40
Nodes (5): 8 Anuncios de Meta, A01 El tiempo de búsqueda, A02 La búsqueda concreta, A03 Mostrar la prueba, Retorno a visitantes y campaña profesional

### Community 102 - "test_notifications_templates.py"
Cohesion: 0.14
Nodes (15): Channel, Notification, Protocol, The channel interface (sección 7.2): the engine never knows how an alert…, A notifications row, with the user's contact data, ready to send., SendResult, Notification, Email through Resend (§21, obligatorio): immediate alerts and the daily digest,… (+7 more)

### Community 103 - "5. Pipeline de ingesta (§14, §15, §42)"
Cohesion: 0.25
Nodes (8): 5.1 Crawl targets, 5.2 Normalización, 5.3 Upsert, snapshots y detección de cambios, 5.4 Re-publicaciones (§15, heurística imperfecta aceptada), 5.5 Enrichment de la ficha, 5.6 Watchlist refresher (§30), 5.7 Bootstrap (evita el diluvio inicial; se conserva la idea actual), 5. Pipeline de ingesta (§14, §15, §42)

### Community 104 - "db/__init__.py"
Cohesion: 0.09
Nodes (36): Postgres (Supabase) data access for the worker. Replaces the old SQLite module.…, search_profiles column values → the wizard dict the scheduler and handlers…, to_legacy(), AsyncConnection, resolve_make_model(), alerts_for_target(), _canonical(), create_alert() (+28 more)

### Community 105 - "Amount"
Cohesion: 0.23
Nodes (8): Amount, Financing, from_llm(), PriceResolution, Any, What resolve_price() concluded, stored in description_facts.price_check. The…, Facts from the LLM's ListingFacts (llm/schemas.py), on top of the rules'. The…, JsonTests

### Community 107 - "to_profile"
Cohesion: 0.13
Nodes (13): _put(), Any, Translate between the Telegram wizard's filter dict and search_profiles. The…, (marca, modelo) combinations of a wizard filter: one search profile each., Wizard dict + one (make, model) → search_profiles column values., split_vehicles(), to_profile(), match_model() (+5 more)

### Community 108 - "6. Intelligence (§16–20, §24, §25, §44)"
Cohesion: 0.29
Nodes (7): 6.1 Matching, 6.2 Comparables y Price Intelligence (§19), 6.3 Opportunity Score 0–100 (§17–18), 6.4 Niveles (§20), 6.5 Red flags (§24), 6.6 Preguntas al vendedor (§25), 6. Intelligence (§16–20, §24, §25, §44)

### Community 109 - "4. Modelo de datos (Postgres / Supabase)"
Cohesion: 0.33
Nodes (6): 4.1 Tablas, 4.2 DDL de las tablas centrales (boceto), 4.3 Forma de `filters` y `preferences`, 4.4 RLS y seguridad, 4.5 Migración desde SQLite (`worker/tools/migrate_sqlite.py`), 4. Modelo de datos (Postgres / Supabase)

### Community 110 - "test_db.py"
Cohesion: 0.47
Nodes (5): container(), main(), (Re)create the database the Postgres tests run on (F7, punto 4). The DB tests…, The local stack's Postgres container: supabase_db_<project_id>., script()

### Community 111 - "47. Riesgos principales"
Cohesion: 0.40
Nodes (5): 47. Riesgos principales, Datos incompletos, Demasiadas alertas, Dependencia de fuentes externas, Falsas oportunidades

### Community 112 - "58. Definición final del producto"
Cohesion: 0.40
Nodes (5): 58. Definición final del producto, Automotive, Evolución inmediata, Promesa MVP, Visión

### Community 114 - "20261002120000_f5_llm.sql"
Cohesion: 0.60
Nodes (4): llm_jobs_enforce_rate_limit, public.enforce_llm_rate_limit(), public.llm_job_stats, public.llm_jobs

### Community 115 - "20261004120000_f7_pilot.sql"
Cohesion: 0.60
Nodes (3): public.delete_my_account(), public.profiles, public.unsubscribe_email()

### Community 116 - "10. Propuesta de valor"
Cohesion: 0.50
Nodes (4): 10. Propuesta de valor, Diferenciación, Mensaje alternativo, Propuesta principal

### Community 117 - "12. Flujo principal"
Cohesion: 0.50
Nodes (4): 12. Flujo principal, Modo asistido, Modo estructurado, Onboarding

### Community 118 - "15. Detección de publicación nueva"
Cohesion: 0.50
Nodes (4): 15. Detección de publicación nueva, Nueva publicación, Publicación actualizada, Re-publicación

### Community 119 - "21. Alertas"
Cohesion: 0.50
Nodes (4): 21. Alertas, Futuro, Obligatorio, Prioridad alta

### Community 120 - "22. Tipos de alertas"
Cohesion: 0.50
Nodes (4): 22. Tipos de alertas, Baja de precio, Match normal, Oportunidad

### Community 121 - "28. Dashboard principal"
Cohesion: 0.50
Nodes (4): 28. Dashboard principal, Header, Mis búsquedas, Oportunidades recientes

### Community 122 - "48. Feature prioritization"
Cohesion: 0.50
Nodes (4): 48. Feature prioritization, P0 — indispensable, P1 — MVP fuerte, P2 — después de validar

### Community 123 - "50. Home / landing propuesta"
Cohesion: 0.50
Nodes (4): 50. Home / landing propuesta, Beneficios, Ejemplo visual, Hero

### Community 124 - "20260927120200_telegram_bot_compat.sql"
Cohesion: 0.67
Nodes (3): public.ensure_telegram_profile(), public.profiles, public.search_profiles

### Community 125 - "20260928120000_f1_ingest.sql"
Cohesion: 0.50
Nodes (3): public.listings, public.search_profiles, public.sources

### Community 126 - "20261006120000_description_facts.sql"
Cohesion: 0.83
Nodes (3): public.listings, public.match_cards, public.raw_pages

### Community 128 - "package.json"
Cohesion: 0.50
Nodes (3): name, private, version

### Community 129 - "kavak.py"
Cohesion: 0.19
Nodes (13): KavakScraper, _parse_card(), parse_detail(), parse_search(), Listing, Kavak Argentina scraper. Kavak is a SPA — search results render via JS only, so…, The page's data names the car it shows: …"car_id":549997,… (JSON, maybe…, _shows_car() (+5 more)

### Community 130 - "test_notifications_channels.py"
Cohesion: 0.22
Nodes (7): InlineKeyboardMarkup, parse(), Inline buttons of a Telegram alert (sección 7.2): ⭐ Me interesa · ✖ Descartar.…, keyboard(), Notification, CallbackDataTests, Channel adapters against fakes: a fake Telegram bot and a mocked Resend API.

### Community 132 - "16. Matching Engine"
Cohesion: 0.67
Nodes (3): 16. Matching Engine, Hard filters, Soft preferences

### Community 133 - "23. Página de resultado"
Cohesion: 0.67
Nodes (3): 23. Página de resultado, Análisis de precio, ¿Por qué apareció?

### Community 134 - "33. Freemium inicial"
Cohesion: 0.67
Nodes (3): 33. Freemium inicial, Free, Pro

### Community 135 - "36. Métricas de activación"
Cohesion: 0.67
Nodes (3): 36. Métricas de activación, First Value, Search Profile Creation Rate

### Community 139 - "main.py"
Cohesion: 0.09
Nodes (24): AbstractEventLoop, Any, T, Entry-point helper: run the worker's coroutines on a loop psycopg supports.…, run(), selector_loop(), amain(), _every() (+16 more)

### Community 140 - "9 Presupuesto y reglas para invertir"
Cohesion: 0.67
Nodes (3): 9 Presupuesto y reglas para invertir, Economía que debe cerrar, Reglas operativas

### Community 142 - "raw_pages.py"
Cohesion: 0.27
Nodes (9): compress(), decompress(), iter_for_reparse(), mark_parsed(), raw_pages: the last detail page of each listing, compressed (normalization v3).…, Stored detail pages, oldest listing first. `below_version`: per source, only…, The stored page was read again with this parser version (tools/reprocess.py)., RawPage (+1 more)

### Community 143 - "TelegramChannel"
Cohesion: 0.38
Nodes (4): TelegramChannel, FakeBot, Exception, TelegramChannelTests

### Community 144 - "pgcase.py"
Cohesion: 0.12
Nodes (13): Business rules from the app_config table (Apéndice A), cached briefly so edits…, due_targets(), enabled_sources(), finish_target(), Any, crawl_targets and the source cadence they run on (sección 5.1)., Make crawl_targets mirror `specs` (pipeline.crawl.TargetSpec): upsert the…, Active targets of enabled sources whose next_run_at has come (or never ran). (+5 more)

### Community 145 - "assess"
Cohesion: 0.25
Nodes (6): assess(), Any, datetime, PriceRef, The columns of `matches` this evaluation fills., Match, score, flags and questions whether or not it matches (explain_match).

### Community 146 - "ResendEmailChannelTests"
Cohesion: 0.39
Nodes (3): Request, F7, punto 7: a footer link and List-Unsubscribe one-click (RFC 8058)., ResendEmailChannelTests

### Community 160 - "8. Capa LLM (§43, §44)"
Cohesion: 0.40
Nodes (5): 8.1 Interfaz, 8.2 `ClaudeCliProvider` (piloto), 8.3 `LocalProvider` (lanzamiento), 8.4 Flujo del modo asistido en la web, 8. Capa LLM (§43, §44)

### Community 180 - "20261008120000_mercadopago.sql"
Cohesion: 0.39
Nodes (5): profiles_guard_billing_delete, public.apply_mercadopago_payment(), public.billing_checkouts, public.commercial_payments, public.guard_billing_account_delete()

### Community 181 - "test_description_facts.py"
Cohesion: 0.40
Nodes (3): trim_page_noise(), NumberTests, The description as a source of facts: price kinds, financing, km, year (pure).

### Community 182 - "Mercado Pago · cobro y acceso automático"
Cohesion: 0.17
Nodes (12): Acceso confirmado y preferencia Particular recuperada, Alta inicial con el MCP · 2/10/2026, Compra bloqueada por mezcla de participantes reales y de prueba, Configuración pendiente del entorno destino, Ensayo aislado · 3/10/2026, Estado actual · 3/10/2026, Implementación, Mercado Pago · cobro y acceso automático (+4 more)

### Community 183 - "7. Motor de notificaciones (§21, §22, §32, §47)"
Cohesion: 0.50
Nodes (4): 7.1 Decisión, 7.2 Canales, 7.3 Tracking de aperturas y clics, 7. Motor de notificaciones (§21, §22, §32, §47)

## Knowledge Gaps
- **537 isolated node(s):** `public.vehicle_catalog`, `public.pipeline_errors`, `public.app_config`, `public.geocode_cache`, `public.fx_rates` (+532 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **19 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Listing` connect `Listing` to `kavak.py`, `ingest`, `AutoCosmosScraper`, `.rows`, `crawl.py`, `geo.py`, `Migration`, `ingest.py`, `normalize_text`, `mercadolibre.py`, `enrich.py`, `keyword_partial`, `v6.py`, `Page`, `facebook.py`, `test_ingest_postgres.py`, `test_db_postgres.py`?**
  _High betweenness centrality (0.030) - this node is a cross-community bridge._
- **Why does `Links` connect `Links` to `render_all`, `ingest`, `test_notifications_channels.py`, `.rows`, `test_notifications_templates.py`, `templates.py`, `TelegramActionTests`, `main.py`, `test_handlers.py`, `TelegramChannel`, `ResendEmailChannelTests`, `test_ingest_postgres.py`, `PRDCopyTests`, `.__init__`, `PostgresTestCase`?**
  _High betweenness centrality (0.026) - this node is a cross-community bridge._
- **Why does `PostgresTestCase` connect `PostgresTestCase` to `ingest`, `.listing`, `.rows`, `patch`, `TelegramActionTests`, `CommercialTests`, `Migration`, `test_llm_jobs_postgres.py`, `pgcase.py`, `MercadoPagoTests`, `test_ingest_postgres.py`, `Listing`, `scheduler.py`, `test_db_postgres.py`?**
  _High betweenness centrality (0.020) - this node is a cross-community bridge._
- **Are the 41 inferred relationships involving `Links` (e.g. with `ResendEmailChannel` and `TelegramChannel`) actually correct?**
  _`Links` has 41 INFERRED edges - model-reasoned connections that need verification._
- **Are the 35 inferred relationships involving `Listing` (e.g. with `AutoCosmosScraper` and `Page`) actually correct?**
  _`Listing` has 35 INFERRED edges - model-reasoned connections that need verification._
- **What connects `public.vehicle_catalog`, `public.pipeline_errors`, `public.app_config` to the rest of the system?**
  _537 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Links` be split into smaller, more focused modules?**
  _Cohesion score 0.11904761904761904 - nodes in this community are weakly interconnected._
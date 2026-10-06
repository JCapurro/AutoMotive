# Graph Report - AutoMotive  (2026-10-06)

## Corpus Check
- 414 files · ~281,522 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 3653 nodes · 9243 edges · 212 communities (181 shown, 31 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 534 edges (avg confidence: 0.55)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `b3fe8efe`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Links
- description_facts.py
- Event
- admin/actions.ts
- pro.ts
- inspector.tsx
- crawl.py
- meta-pixel.tsx
- test_notifications_postgres.py
- app/listings/[id]/page.tsx
- copy.ts
- ListingFacts
- QueueTests
- notifications.py
- connection
- ingest.py
- CatalogModel
- settings/page.tsx
- enrich.py
- button.tsx
- search-form.tsx
- db.ts
- facebook.py
- resolve_price
- fiesta_listing
- LLMProvider
- test_llm_drafts.py
- platform_health.py
- Page
- test_llm_contract.py
- PRD — Automotive
- createClient
- geo.py
- test_ingest_postgres.py
- test_llm_claude_cli.py
- PriceRef
- listings.py
- matching.py
- templates.py
- service.py
- scraper_cli.py
- searches/[id]/page.tsx
- migrate_sqlite.py
- 20260927120000_core_schema.sql
- Page
- devDependencies
- dependencies
- compilerOptions
- createAdminClient
- intelligence/scoring.py
- channels/base.py
- rescore.py
- test_llm_openai_api.py
- mercadopago-server.ts
- 20261007120000_ese_auto_commercial.sql
- login-form.tsx
- scheduler.py
- metrics/page.tsx
- 20261003120000_f6_backoffice_metrics.sql
- SourceAlerts
- components.json
- 20260927120100_rls.sql
- telegram.py
- Listing
- CollectorChecksTests
- test_intelligence_postgres.py
- Automotive — web
- autocosmos.py
- startup_warnings
- load_models
- matches.py
- Comparación de modelos para búsqueda asistida
- test_handlers.py
- CommercialTests
- Ese Auto · propuesta comercial y proyección
- database.ts
- patch
- Comunes a cualquier ruta
- Puesta en producción del piloto (F7)
- Automotive — Plan técnico del MVP
- kavak.py
- MercadoPagoTests
- main.py
- to_profile
- test_description_intelligence.py
- types.ts
- 20261001120000_f4_web.sql
- IntelligenceConfig
- RuntimeError
- AvailabilityTests
- mercadolibre.py
- PROPUESTA_COMERCIAL.md
- Setup
- prompts/__init__.py
- server.ts
- 13. Roadmap por fases
- scripts
- 40. Modelo conceptual de datos
- toggle-group.tsx
- listing.py
- test_notifications_templates.py
- 5. Pipeline de ingesta (§14, §15, §42)
- seller_questions
- DeliveryTests
- RedFlagTests
- raw_pages.py
- test_ops.py
- 4. Modelo de datos (Postgres / Supabase)
- test_mvp_worker.py
- 47. Riesgos principales
- 58. Definición final del producto
- AutoMotive
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
- BaseScraper
- Description Intelligence Implementation Plan
- 16. Matching Engine
- 23. Página de resultado
- 33. Freemium inicial
- 36. Métricas de activación
- 20260930120000_f3_notifications.sql
- opengraph-image.tsx
- description_claims.py
- MVP del 6 de octubre de 2026
- 20261009120000_meta_conversions.sql
- explain_match.py
- Descripciones como fuente de datos
- 8. Capa LLM (§43, §44)
- TelegramActionTests
- sonner
- 20261005120000_f7_ops.sql
- AGENTS.md
- eslint.config.mjs
- next.config.ts
- postcss.config.mjs
- 20261010120000_mvp_email_free_trial.sql
- automotive-worker
- 20261008120000_mercadopago.sql
- 20261011120000_mvp_email_only_published.sql
- Mercado Pago · cobro y acceso automático
- insert_profiles
- _is_recent
- pgcase.py
- PLATFORM_HEALTH.md
- sync-locations.py
- vercel.json
- 34. Alternativa de pricing
- 35. Métricas principales
- 38. Métricas de outcome
- 49. MVP final recomendado
- 7. Público objetivo
- 8. Persona principal
- 9. Persona secundaria futura
- 20261012121500_private_platform_health.sql
- 20261014120000_description_intelligence.sql
- GPT-6 Luna en el worker
- 6. Intelligence (§16–20, §24, §25, §44)
- ResendEmailChannelTests
- run
- IA sobre descripciones
- simulate_alert.py
- Confirmación consumida por una vista previa
- heartbeat.py
- Ingreso con Google
- 7. Motor de notificaciones (§21, §22, §32, §47)
- .__init__

## God Nodes (most connected - your core abstractions)
1. `Links` - 89 edges
2. `Listing` - 83 edges
3. `connection()` - 73 edges
4. `createClient()` - 70 edges
5. `PRD — Automotive` - 59 edges
6. `createAdminClient()` - 53 edges
7. `PostgresTestCase` - 51 edges
8. `requireUser()` - 48 edges
9. `ListingDetail` - 45 edges
10. `Notifier` - 45 edges

## Surprising Connections (you probably didn't know these)
- `DigestItem` --uses--> `Links`  [INFERRED]
  worker/notifications/templates.py → worker/notifications/links.py
- `setStatus()` --references--> `STATUSES`  [EXTRACTED]
  web/app/app/listings/actions.ts → web/lib/copy.ts
- `ResetPasswordPage()` --calls--> `createClient()`  [EXTRACTED]
  web/app/auth/reset-password/page.tsx → web/lib/supabase/server.ts
- `EXAMPLE` --calls--> `money()`  [EXTRACTED]
  web/app/page.tsx → web/lib/format.ts
- `insertListing()` --indirect_call--> `ago()`  [INFERRED]
  web/e2e/support/db.ts → web/lib/format.ts

## Import Cycles
- None detected.

## Communities (212 total, 31 thin omitted)

### Community 0 - "Links"
Cohesion: 0.16
Nodes (15): CallbackQueryHandler, Update, _allowed(), help_(), invalid_code_text(), linked_text(), The Telegram bot after F4: it links the account and answers alert buttons.…, register() (+7 more)

### Community 1 - "description_facts.py"
Cohesion: 0.07
Nodes (37): _after_label(), Amount, _amounts(), _before_label(), _close(), _currency(), DescriptionFacts, _distinct() (+29 more)

### Community 2 - "Event"
Cohesion: 0.11
Nodes (24): at_least(), rank(), Opportunity levels (§20, sección 6.4), thresholds from…, classify(), decide(), decide_all(), Decision, Event (+16 more)

### Community 3 - "admin/actions.ts"
Cohesion: 0.12
Nodes (22): ActionResult, shape(), SourceInput, updateConfig(), updateSource(), confirmPayment(), launchCommercialPilot(), recordRefund() (+14 more)

### Community 4 - "pro.ts"
Cohesion: 0.10
Nodes (38): BillingPage(), metadata, joinWaitlist(), checkPayment(), ownedCheckout(), startPayment(), stopSubscription(), metadata (+30 more)

### Community 5 - "inspector.tsx"
Cohesion: 0.13
Nodes (31): metadata, metadata, metadata, metadata, metadata, metadata, Filters, metadata (+23 more)

### Community 6 - "crawl.py"
Cohesion: 0.10
Nodes (30): start_run(), due_targets(), enabled_sources(), finish_target(), Any, crawl_targets and the source cadence they run on (sección 5.1)., Make crawl_targets mirror `specs` (pipeline.crawl.TargetSpec): upsert the…, Active targets of enabled sources whose next_run_at has come (or never ran). (+22 more)

### Community 7 - "meta-pixel.tsx"
Cohesion: 0.06
Nodes (37): metadata, mono, sans, viewport, metadata, ListingActions(), ViewTracker(), Consent (+29 more)

### Community 8 - "test_notifications_postgres.py"
Cohesion: 0.21
Nodes (8): ListingEvent, AlertTypesTests, DailyCapAndDigestTests, DedupeTests, NotificationsCase, F3 notification engine against the local Supabase Postgres…, Acceptance: the three types of §22 reach Telegram and email with the right copy., Acceptance: the same listing never generates two alerts of the same type.

### Community 9 - "app/listings/[id]/page.tsx"
Cohesion: 0.08
Nodes (50): AdminListingPage(), escapeLike(), ListingsPage(), ListingPage(), markFor(), metadata, plain(), priceHistory() (+42 more)

### Community 10 - "copy.ts"
Cohesion: 0.10
Nodes (21): STATUS_STYLE, StatusBadge(), COMPARABLE_LEVEL, COMPONENT, COMPONENTS, Enums, FORBIDDEN_TERMS, InteractionStatus (+13 more)

### Community 11 - "ListingFacts"
Cohesion: 0.09
Nodes (32): AsyncAnthropic, AnthropicApiProvider, CatalogModel, M, The Claude API with an API key (F7, punto 6): the provider for serving the…, `claude -p` as the pilot's LLM (sección 8.2). claude -p --output-format json…, The LLM layer (sección 8): providers behind one interface. provider.py…, LocalProvider (+24 more)

### Community 12 - "QueueTests"
Cohesion: 0.17
Nodes (5): LlmJobsCase, QueueTests, What the web can do with the user's session (sección 4.4)., Run `sql` as the signed-in web user (role authenticated, RLS on)., WebAccessTests

### Community 13 - "notifications.py"
Cohesion: 0.08
Nodes (38): apply_telegram_action(), delivery_payload(), digest_users(), existing_keys(), insert_decisions(), insert_digest(), insert_event(), interactions() (+30 more)

### Community 14 - "connection"
Cohesion: 0.10
Nodes (35): Postgres (Supabase) data access for the worker. Replaces the old SQLite module.…, close_pool(), connection(), AsyncConnection, Async Postgres connection pool (psycopg 3), one per worker process. The worker…, get_config(), Any, Business rules from the app_config table (Apéndice A), cached briefly so edits… (+27 more)

### Community 15 - "ingest.py"
Cohesion: 0.10
Nodes (36): The crawl target a card was found through: a hint, never the truth., Target, One target crawled: what the collector returned and what ingest made of it., TargetRun, _empty(), _facts(), _geocode_rows(), ingest_rows() (+28 more)

### Community 16 - "CatalogModel"
Cohesion: 0.09
Nodes (36): vehicle_catalog: canonical make/model/trim names. The catalog is small (a few…, _km(), _money(), normalize_draft(), _positive(), Any, CatalogModel, date (+28 more)

### Community 17 - "settings/page.tsx"
Cohesion: 0.15
Nodes (18): RFC-8058, POST(), metadata, metadata, metadata, ResetPasswordPage(), unsubscribe(), metadata (+10 more)

### Community 18 - "enrich.py"
Cohesion: 0.08
Nodes (39): Refresher, mark_detail_checked(), money(), USD 10.300 · ARS 12.500.000 (Argentine thousands separator)., input_hash(), DescriptionLLM, drain(), enrich_pass() (+31 more)

### Community 19 - "button.tsx"
Cohesion: 0.16
Nodes (18): deleteAccount(), PasswordState, updatePassword(), PasswordForm(), DeleteAccount(), Props, Button(), buttonVariants (+10 more)

### Community 20 - "search-form.tsx"
Cohesion: 0.05
Nodes (75): AssistedStart, canonical(), enabledSources(), escapeLike(), jobText(), Preview, PreviewListing, previewSearch() (+67 more)

### Community 21 - "db.ts"
Cohesion: 0.11
Nodes (25): SEARCH_FILTERS, alertedUser(), signIn(), ask(), setHeartbeat(), signIn(), globalSetup(), main() (+17 more)

### Community 22 - "facebook.py"
Cohesion: 0.09
Nodes (30): _after_colon(), _city_slug(), _city_slug_from_origin(), _extract_location(), FacebookMarketplaceScraper, _looks_like_location(), _matches_query_text(), _own_images() (+22 more)

### Community 23 - "resolve_price"
Cohesion: 0.15
Nodes (7): PriceResolution, What resolve_price() concluded, stored in description_facts.price_check. The…, The listing's effective price (sección 5.2, v3). `published`/`currency`: the…, resolve_price(), _usd(), _resolve(), ResolvePriceTests

### Community 24 - "fiesta_listing"
Cohesion: 0.13
Nodes (14): evaluate(), match(), The reasons if every hard filter is ok or unknown; None if one fails., CurrencyTests, fiesta_listing(), fiesta_profile(), GoldenFixtureTests, GuardAndLevelTests (+6 more)

### Community 25 - "LLMProvider"
Cohesion: 0.09
Nodes (30): claim(), expire(), finish(), Any, AsyncConnection, llm_jobs: the queue between the web and the LLM layer (sección 8.4). The web…, The oldest queued job of `kinds`, now 'running'; None if there is none., done' with its output, or 'failed' with the error (never both). (+22 more)

### Community 26 - "test_llm_drafts.py"
Cohesion: 0.11
Nodes (35): trim_envelope(), normalize_drafts(), One search per resolved model, with all its requested versions., _items(), CatalogModel, vehicle_catalog as supabase/seed.sql inserts it, without a database. The LLM…, seed_catalog(), _year() (+27 more)

### Community 27 - "platform_health.py"
Cohesion: 0.15
Nodes (24): timedelta, last_beat(), collector_checks(), exclusive_check(), inspect_database(), load_state(), main(), notify_changes() (+16 more)

### Community 28 - "Page"
Cohesion: 0.20
Nodes (3): CollectorTransportTests, Page, Tecc transport contract: persistent Chrome, shared search/detail state, real…

### Community 29 - "test_llm_contract.py"
Cohesion: 0.10
Nodes (29): fixture, skipif, load_recordings(), Any, Path, Recorded `claude -p` answers, replayed without the CLI. tools/record_llm.py…, {user text: trimmed envelope}., replay_provider() (+21 more)

### Community 30 - "PRD — Automotive"
Cohesion: 0.05
Nodes (37): 11. Principios de producto, 13. Concepto de Search Profile, 14. Ingesta de publicaciones, 17. Opportunity Score, 18. Componentes iniciales del Opportunity Score, 19. Price Intelligence, 1. Resumen ejecutivo, 20. Niveles de oportunidad (+29 more)

### Community 31 - "createClient"
Cohesion: 0.14
Nodes (29): answerInfluence(), currentStatus(), markSeen(), Purchase, recordPurchase(), setDiscardReason(), setSaved(), setStatus() (+21 more)

### Community 32 - "geo.py"
Cohesion: 0.12
Nodes (20): Coords, _fallback_can_stand_alone(), filter_listings_by_radius(), geocode_location(), _geocode_nominatim(), haversine_km(), _looks_like_non_location_query(), _lookup_known_location() (+12 more)

### Community 33 - "test_ingest_postgres.py"
Cohesion: 0.07
Nodes (32): ListingDetail, What fetch_detail() found at a listing's URL (sección 5.5). `gone` means the…, TelegramChannel, WebChannel, Notifier, ingest(), normalize → geocode → upsert. The whole batch is one transaction., CanonicalUpsertTests (+24 more)

### Community 34 - "test_llm_claude_cli.py"
Cohesion: 0.09
Nodes (37): BaseModel, Runner, ClaudeCliProvider, parse_envelope(), Any, CatalogModel, M, Run the CLI once and return its stdout. Raises LLMTimeout / LLMError. (+29 more)

### Community 35 - "PriceRef"
Cohesion: 0.15
Nodes (14): AST, fetch(), PriceRef, Any, Price Intelligence (§19, sección 6.2). The statistics come from the SQL…, public.comparables() for one listing. `cfg` overrides app_config.comparables., CopyLintTests, _docstring_nodes() (+6 more)

### Community 36 - "listings.py"
Cohesion: 0.08
Nodes (36): enrichment_queue(), find_repost_of(), finish_description_run(), insert_listing(), insert_snapshot(), llm_facts_last_day(), lock_existing(), mark_gone() (+28 more)

### Community 37 - "matching.py"
Cohesion: 0.12
Nodes (26): Result, number(), _choice(), distance_km(), evaluate(), filter_currency(), _km(), _location() (+18 more)

### Community 38 - "templates.py"
Cohesion: 0.12
Nodes (31): age_line(), ago_long(), before_after(), Button, Content, _digest(), DigestItem, email() (+23 more)

### Community 39 - "service.py"
Cohesion: 0.12
Nodes (28): log_error(), Record a pipeline error. Never raises: observability must not break the…, build_items(), Any, datetime, Daily digest (§32, sección 7.2). Every day at app_config.digest_hour (ART,…, Digest items from waiting rows and the day's top matches: waiting rows always…, Build today's digests. Returns how many were created (then delivered). (+20 more)

### Community 40 - "scraper_cli.py"
Cohesion: 0.11
Nodes (25): shutdown(), _collector_loop(), AbstractEventLoop, Any, T, Run collector coroutines on an event loop that can start subprocesses.…, run_collector(), Return the current USD→ARS rate (see `usd_ars_quote`). (+17 more)

### Community 41 - "searches/[id]/page.tsx"
Cohesion: 0.09
Nodes (31): Dashboard(), metadata, reportVisibleResults(), trackProCta(), COUNT_KEY, EMPTY, Filter, FILTERS (+23 more)

### Community 42 - "migrate_sqlite.py"
Cohesion: 0.11
Nodes (17): AsyncConnectionPool, connection_kwargs(), open_pool(), Any, Open the process-wide pool (idempotent)., LoadEmailsTests, _make_sqlite(), MigrateSqliteTests (+9 more)

### Community 43 - "20260927120000_core_schema.sql"
Cohesion: 0.13
Nodes (29): app_config_set_updated_at, crawl_targets_set_updated_at, matches_set_updated_at, on_auth_user_created, owned_vehicles_set_updated_at, profiles_set_updated_at, public.app_config, public.collector_runs (+21 more)

### Community 44 - "Page"
Cohesion: 0.11
Nodes (10): Page, AutoCosmosParserTests, FacebookParserTests, html(), KavakParserTests, MercadoLibreParserTests, Search and detail parsers against saved HTML (tests/fixtures/html). The…, raw_pages keep a slimmed page: every parser reads the same from it. (+2 more)

### Community 45 - "devDependencies"
Cohesion: 0.07
Nodes (29): babel-plugin-react-compiler, eslint, eslint-config-next, pg, @playwright/test, tailwindcss, @tailwindcss/postcss, tsx (+21 more)

### Community 46 - "dependencies"
Cohesion: 0.07
Nodes (29): class-variance-authority, cn, lucide-react, next, next-themes, radix-ui, react-dom, recharts (+21 more)

### Community 47 - "compilerOptions"
Cohesion: 0.07
Nodes (28): dom, dom.iterable, esnext, **/*.mts, .next/dev/types/**/*.ts, next-env.d.ts, .next/types/**/*.ts, node_modules (+20 more)

### Community 48 - "createAdminClient"
Cohesion: 0.11
Nodes (26): MatchInspector(), NotificationInspector(), HealthPage(), metadata, NAMES, GET(), handle(), HEAD() (+18 more)

### Community 49 - "intelligence/scoring.py"
Cohesion: 0.20
Nodes (22): diff_pct(), How far below the median the published price is, in % (negative = above)., level_for(), 🔥 high ≥ 85 · 🟢 good ≥ 70 · 🟡 match ≥ 50 · ⚪ low. `cap` is the highest level…, age_hours(), clamp(), completeness_component(), completeness_fields() (+14 more)

### Community 50 - "channels/base.py"
Cohesion: 0.15
Nodes (16): Channel, Notification, Protocol, The channel interface (sección 7.2): the engine never knows how an alert…, A notifications row, with the user's contact data, ready to send., SendResult, datetime, Notification (+8 more)

### Community 51 - "rescore.py"
Cohesion: 0.17
Nodes (16): purge_older_than(), nightly_loop(), Any, datetime, Re-scoring existing matches (sección 6.1). * After enrichment: transmission or…, Re-score (search_profile_id, listing_id) pairs. Returns rows updated., Seconds from `now` to the next `hour` ("HH:MM", ART)., Re-score matches once a night, then purge stale listings; also, once at… (+8 more)

### Community 52 - "test_llm_openai_api.py"
Cohesion: 0.16
Nodes (24): build_provider(), The provider `LLM_PROVIDER` names., test_build_provider(), answer(), provider(), parametrize, Responses wire contract and failure handling, with no live API calls. Replays…, replay() (+16 more)

### Community 53 - "mercadopago-server.ts"
Cohesion: 0.09
Nodes (48): GET(), POST(), reply(), checkoutUrl(), paymentPeriod(), sameSecret(), api(), applyPayment() (+40 more)

### Community 54 - "20261007120000_ese_auto_commercial.sql"
Cohesion: 0.09
Nodes (8): llm_jobs_guard_commercial, matches_guard_commercial, public.commercial_payments, public.guard_assisted_commercial_access(), public.guard_match_access(), public.plan_limits_for(), public.profiles, public.refund_commercial_payment()

### Community 55 - "login-form.tsx"
Cohesion: 0.12
Nodes (26): GET(), HEAD(), ConfirmEmailPage(), GET(), HEAD(), POST(), tokenTypes, POST() (+18 more)

### Community 56 - "scheduler.py"
Cohesion: 0.10
Nodes (26): MatchCandidate, A new, non-backfill match the crawl just stored., Bootstrap of new or edited profiles (sección 5.7). A profile that was never…, Backfill one profile. Returns how many listings it matched., Bootstrap every profile that needs it. Returns how many were processed., rematch_profile(), run_pending(), batch_handler() (+18 more)

### Community 57 - "metrics/page.tsx"
Cohesion: 0.09
Nodes (36): ConfigPage(), HINTS, metadata, ErrorsPage(), MatchesPage(), CTA_EVENTS, day(), levelLabel() (+28 more)

### Community 58 - "20261003120000_f6_backoffice_metrics.sql"
Cohesion: 0.10
Nodes (16): pro_waitlist_set_updated_at, public.admin_notification_daily, public.admin_score_histogram, public.admin_searches, public.admin_source_health, public.admin_users, public.join_waitlist(), public.pro_waitlist (+8 more)

### Community 59 - "SourceAlerts"
Cohesion: 0.12
Nodes (22): finish_run(), Observability (sección 10, §46): collector_runs, pipeline_errors and source…, A source's failure streak after a run (the admin alert reads it)., Close a run and keep the source's health counters in step. Returns the source's…, SourceHealth, failing_text(), last_error_line(), Any (+14 more)

### Community 60 - "components.json"
Cohesion: 0.09
Nodes (21): aliases, components, hooks, lib, ui, utils, iconLibrary, menuAccent (+13 more)

### Community 61 - "20260927120100_rls.sql"
Cohesion: 0.10
Nodes (20): public.app_config, public.collector_runs, public.crawl_targets, public.enforce_plan_limits(), public.events, public.fx_rates, public.geocode_cache, public.listing_snapshots (+12 more)

### Community 62 - "telegram.py"
Cohesion: 0.12
Nodes (13): InlineKeyboardMarkup, parse(), Inline buttons of a Telegram alert (sección 7.2): ⭐ Me interesa · ✖ Descartar.…, keyboard(), Any, datetime, Notification, Telegram (§21, canal existente): the §22 copy in HTML plus the inline buttons ⭐… (+5 more)

### Community 63 - "Listing"
Cohesion: 0.09
Nodes (13): Listing, One ad as a collector read it, before normalization. `marca`/`modelo`/`version`…, PostgresTestCase, Opens the worker pool on TEST_DATABASE_URL over a clean slate., AlertRepoTests, GeocodeAndConfigTests, _listing(), The bot's data layer against a real Postgres with the supabase/ migrations. Run… (+5 more)

### Community 65 - "test_intelligence_postgres.py"
Cohesion: 0.19
Nodes (7): ComparablesCascadeTests, IntelligenceCase, PriceRef, F2 intelligence against the local Supabase Postgres (docs/TECHNICAL_PLAN.md,…, Insert a listing row directly: comparables are about stored columns., Sección 6.2: trim+transmission → transmission → model, first with n ≥ min_n., ScoredMatchesTests

### Community 66 - "Automotive — web"
Cohesion: 0.22
Nodes (7): Configuración del proyecto alojado antes de publicar, Desarrollo, Registro y acceso con Supabase Auth, Automotive — web, Correrla, Rutas (plan técnico, sección 9), Tests

### Community 67 - "autocosmos.py"
Cohesion: 0.11
Nodes (20): range, AutoCosmosScraper, _price(), AsyncClient, Listing, Response, AutoCosmos AR scraper. AutoCosmos exposes a public listings page at…, GET, retried on a network error or a 5xx; the last answer or error wins. (+12 more)

### Community 68 - "startup_warnings"
Cohesion: 0.13
Nodes (10): What this configuration leaves off (F7, punto 5): one line per channel, metric…, startup_warnings(), _database(), db_test_skip_reason(), Why the DB tests can't run here, or None. They TRUNCATE tables, so they only…, ConfigTests, F7, punto 4: the DB tests TRUNCATE, so they never touch the pilot's database., F7, punto 5: every channel or metric the .env leaves off is logged at startup. (+2 more)

### Community 69 - "load_models"
Cohesion: 0.24
Nodes (8): load_models(), match_model(), AsyncConnection, CatalogModel, Model-level rows with their trims, aliases and production years., Canonical (make, model), or None if it isn't in the catalog. The model matches…, resolve_make_model(), CatalogMatchTests

### Community 70 - "matches.py"
Cohesion: 0.17
Nodes (19): _existing(), filter_unseen(), insert_legacy_matches(), _keys(), mark_seen(), matched_by_other_profiles(), matches_of_listings(), Any (+11 more)

### Community 71 - "Comparación de modelos para búsqueda asistida"
Cohesion: 0.17
Nodes (12): APIs: estructura de salida y razonamiento, APIs: precios comparables, Comparación de modelos para búsqueda asistida, Decisión económica provisional, DeepSeek y Kimi locales, Estado del trabajo en el proyecto, Hardware local y otros modelos abiertos, Jev aplicado al contrato (+4 more)

### Community 72 - "test_handlers.py"
Cohesion: 0.21
Nodes (9): start(), _ctx(), _FakeChat, _FakeMessage, _FakeUpdate, _FakeUser, The bot after F4: /start <code> links the account, the old wizard commands…, RetiredWizardTests (+1 more)

### Community 74 - "Ese Auto · propuesta comercial y proyección"
Cohesion: 0.12
Nodes (16): 1. Qué vender, 2. Qué ya existe y qué falta, 3. Referencias de mercado, 4. Alternativas iniciales conservadas como referencia, 5. Oferta seleccionada en pesos: B, 6. Proyección a seis meses, 7. Validación y salida comercial, 8. Decisión a registrar (+8 more)

### Community 76 - "database.ts"
Cohesion: 0.09
Nodes (24): loadFormData(), metadata, Tabs(), TabsContent(), TabsList(), tabsListVariants, TabsTrigger(), Catalog (+16 more)

### Community 77 - "patch"
Cohesion: 0.18
Nodes (22): patch, parse_publication_date(), parse_relative_date(), publication_date(), Any, Parse Spanish relative date strings shown by AR car classifieds. Examples…, Read only publication-specific fields of the current ad/card. The caller…, Return a unix timestamp inferred from a Spanish relative-date string. (+14 more)

### Community 78 - "Comunes a cualquier ruta"
Cohesion: 0.12
Nodes (16): COM-02 · Una oferta coherente, COM-03 · Límites que siguen vigentes al vencer, COM-04 y COM-05 · Cobro y ciclo de vida, COM-06 · Autogestión, COM-07 · Producto que se puede prometer, COM-08 · Medir rentabilidad, no solo intención, COM-09 · Operación comercial, COM-10 · Salida controlada (+8 more)

### Community 79 - "Puesta en producción del piloto (F7)"
Cohesion: 0.13
Nodes (15): 10. Prueba de aceptación, 1. Dominio en Cloudflare, 2. Túnel de Cloudflare, 3. Resend (emails de login y de alertas), 4. API key de Anthropic (modo asistido), 5. Chat de Telegram para las alertas operativas, 6. Sesiones de MercadoLibre y Facebook, 7. Configuración (+7 more)

### Community 80 - "Automotive — Plan técnico del MVP"
Cohesion: 0.18
Nodes (11): 10. Backoffice y observabilidad (§45, §46), 11. Métricas y eventos (§35–38, §53), 12. Freemium (§33, §34), 14. Riesgos y decisiones abiertas, 15. Trazabilidad PRD → plan, 1. Punto de partida y gaps, 2. Arquitectura objetivo, 3. Estructura del repo (+3 more)

### Community 81 - "kavak.py"
Cohesion: 0.09
Nodes (43): BeautifulSoup, Browser, browser_context(), _ensure_browser(), BrowserContext, Shared Playwright helpers — reuse a single browser instance across scrapers., Yield a fresh browser context. Closes context on exit; browser is reused., dedupe() (+35 more)

### Community 83 - "main.py"
Cohesion: 0.14
Nodes (16): amain(), build_notifier(), _every(), notifying(), stdout, plus LOG_FILE (UTF-8, rotated at midnight, LOG_KEEP_DAYS kept)., Run `job(stop)` now and then every `seconds` until stopped; errors are logged., The channels this worker can deliver on (sección 7.2)., A refresh pass whose price_drop / listing_gone events go to the engine. (+8 more)

### Community 84 - "to_profile"
Cohesion: 0.20
Nodes (11): _put(), Any, Translate between the Telegram wizard's filter dict and search_profiles. The…, (marca, modelo) combinations of a wizard filter: one search profile each., Wizard dict + one (make, model) → search_profiles column values., search_profiles column values → the wizard dict the scheduler and handlers…, split_vehicles(), to_legacy() (+3 more)

### Community 85 - "test_description_intelligence.py"
Cohesion: 0.35
Nodes (10): answer(), read(), test_an_anticipo_cannot_become_the_cash_price(), test_changed_description_invalidates_old_claims_even_when_new_text_has_no_facts(), test_cropped_quotes_cannot_hide_negations_or_maintenance_mileage(), test_negations_do_not_become_positive_claims(), test_preserves_seller_claims_and_literal_evidence_round_trip(), test_price_and_mileage_need_matching_numbers_in_evidence() (+2 more)

### Community 86 - "types.ts"
Cohesion: 0.14
Nodes (20): DescriptionPriceContext(), SellerDescription(), FUEL, TRANSMISSION, BOOL, DescriptionListing, folded(), LABEL (+12 more)

### Community 87 - "20261001120000_f4_web.sql"
Cohesion: 0.24
Nodes (7): public.dashboard_summary(), public.link_telegram(), public.match_cards, public.profiles, public.recent_opportunities(), public.search_result_counts(), public.search_results()

### Community 88 - "IntelligenceConfig"
Cohesion: 0.10
Nodes (26): IntelligenceConfig, _merge(), Any, Weights, curves and thresholds of the intelligence layer (sección 6, Apéndice…, assess(), Evaluation, Any, datetime (+18 more)

### Community 89 - "RuntimeError"
Cohesion: 0.18
Nodes (3): RuntimeError, Page, PersistentChromeTests

### Community 91 - "mercadolibre.py"
Cohesion: 0.09
Nodes (37): CollectorBlocked, The source answered with a login wall, a security challenge or no session. The…, _blocked(), _ensure_context(), mercadolibre_context(), BrowserContext, Tecc's Mercado Libre transport: installed Chrome with a dedicated profile. The…, Serialize page operations on one Chrome context for the worker lifetime. (+29 more)

### Community 92 - "PROPUESTA_COMERCIAL.md"
Cohesion: 0.24
Nodes (4): Comprobaciones reproducibles, Ese Auto · implementación del lanzamiento comercial, Habilitación del entorno destino, Límites de esta entrega

### Community 93 - "Setup"
Cohesion: 0.18
Nodes (11): Backoffice y métricas (F6), Base de datos (Supabase), Correr el bot, Correr la web, Login de Facebook (una vez), MercadoLibre: sesion web, Migrar la base SQLite vieja, Modo asistido (LLM) (+3 more)

### Community 95 - "prompts/__init__.py"
Cohesion: 0.24
Nodes (8): catalog_text(), load(), parse_search_system(), parse_search_user(), CatalogModel, date, System prompts and user messages of the LLM layer, shared by every provider.…, One line per make: "Ford: Fiesta [S, SE, Titanium]; Focus [...]".

### Community 96 - "server.ts"
Cohesion: 0.13
Nodes (20): AppLayout(), BENEFITS, EXAMPLE, Landing(), STEPS, active(), BottomNav(), ITEMS (+12 more)

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

### Community 101 - "listing.py"
Cohesion: 0.06
Nodes (45): NamedTuple, AsyncConnection, date, quote_for_today(), fx_rates: the day's USD/ARS quote, frozen so price_usd can be reproduced…, The quote stored for today (blue, else oficial), fetching and storing it on…, today_ar(), _fetch_quote() (+37 more)

### Community 102 - "test_notifications_templates.py"
Cohesion: 0.12
Nodes (8): Notification engine (sección 7): decide → queue → channels, plus the daily…, notification(), CopyLintTests, PRDCopyTests, Snapshots of the three alert types of §22 (+ the digest) on every channel. The…, §19: no "vale", "precio real", "tasación" in any alert., The §22 lines, in order, at the top of the Telegram message and the email text., TemplateSnapshotTests

### Community 103 - "5. Pipeline de ingesta (§14, §15, §42)"
Cohesion: 0.25
Nodes (8): 5.1 Crawl targets, 5.2 Normalización, 5.3 Upsert, snapshots y detección de cambios, 5.4 Re-publicaciones (§15, heurística imperfecta aceptada), 5.5 Enrichment de la ficha, 5.6 Watchlist refresher (§30), 5.7 Bootstrap (evita el diluvio inicial; se conserva la idea actual), 5. Pipeline de ingesta (§14, §15, §42)

### Community 104 - "seller_questions"
Cohesion: 0.21
Nodes (11): RedFlag, Any, datetime, question_keys(), Questions for the seller (§25, sección 6.6). Deterministic templates. Always:…, One message ready to copy: "Hola, ¿cómo estás? ¿Lo seguís teniendo? …"., seller_questions(), claim() (+3 more)

### Community 107 - "raw_pages.py"
Cohesion: 0.27
Nodes (9): compress(), decompress(), iter_for_reparse(), mark_parsed(), raw_pages: the last detail page of each listing, compressed (normalization v3).…, Stored detail pages, oldest listing first. `below_version`: per source, only…, The stored page was read again with this parser version (tools/reprocess.py)., RawPage (+1 more)

### Community 108 - "test_ops.py"
Cohesion: 0.15
Nodes (15): EnvFileTests, F7, punto 8: the watchdog's decisions (tools/watchdog.py), without network or…, tools/supabase_keys.py rewrites .env files in place., TransitionTests, WebCheckTests, WorkerHeartbeatTests, generate(), main() (+7 more)

### Community 109 - "4. Modelo de datos (Postgres / Supabase)"
Cohesion: 0.33
Nodes (6): 4.1 Tablas, 4.2 DDL de las tablas centrales (boceto), 4.3 Forma de `filters` y `preferences`, 4.4 RLS y seguridad, 4.5 Migración desde SQLite (`worker/tools/migrate_sqlite.py`), 4. Modelo de datos (Postgres / Supabase)

### Community 110 - "test_mvp_worker.py"
Cohesion: 0.22
Nodes (7): MvpWorkerTests, The web/email worker must start without a Telegram token or API connection., container(), main(), (Re)create the database the Postgres tests run on (F7, punto 4). The DB tests…, The local stack's Postgres container: supabase_db_<project_id>., script()

### Community 111 - "47. Riesgos principales"
Cohesion: 0.40
Nodes (5): 47. Riesgos principales, Datos incompletos, Demasiadas alertas, Dependencia de fuentes externas, Falsas oportunidades

### Community 112 - "58. Definición final del producto"
Cohesion: 0.40
Nodes (5): 58. Definición final del producto, Automotive, Evolución inmediata, Promesa MVP, Visión

### Community 113 - "AutoMotive"
Cohesion: 0.22
Nodes (9): Agregar una nueva fuente, AutoMotive, Comandos del bot, Cómo funciona, Estructura, Fuentes, Limitaciones, Matching y Opportunity Score (+1 more)

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

### Community 129 - "BaseScraper"
Cohesion: 0.12
Nodes (11): BaseScraper, Page, Run keyword detection over the title and tag the listing. Statistical detection…, Apply user filters that the source could not enforce server-side., Download the ad's own page, with the source's login-wall and session checks,…, Read the ad's page: description, version, transmission, seller type, every…, What raw_pages keeps of a detail page: enough for parse_detail()., KavakScraper (+3 more)

### Community 130 - "Description Intelligence Implementation Plan"
Cohesion: 0.25
Nodes (7): Description Intelligence Implementation Plan, Resultados de verificación, Task 1: Contrato y conservación, Task 2: Análisis de todas las descripciones y caché, Task 3: Señales y preguntas, Task 4: Ficha y explicación, Task 5: Verificación y entrega

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

### Community 139 - "description_claims.py"
Cohesion: 0.42
Nodes (8): _bool_supported(), folded(), grounded_values(), _negative(), quote_contexts(), Ground seller statements in the actual text before keeping them. No I/O., Include preceding clause context so a quote cannot crop off a negation/service…, Reject missing/invented citations, invented string values and inverted…

### Community 140 - "MVP del 6 de octubre de 2026"
Cohesion: 0.33
Nodes (5): Configuración, MercadoLibre, MVP del 6 de octubre de 2026, Prueba gratuita, Verificación

### Community 143 - "explain_match.py"
Cohesion: 0.25
Nodes (9): ago(), Every user-facing string of the intelligence layer (§19, §24, §25). Kept in one…, explain(), load(), main(), Any, Explain why a listing matches (or not) a search profile, and its score.…, Everything the tool prints, as data (also the --json output). (+1 more)

### Community 144 - "Descripciones como fuente de datos"
Cohesion: 0.40
Nodes (4): Datos y procedencia, Descripciones como fuente de datos, Flujo, Validación y operación

### Community 145 - "8. Capa LLM (§43, §44)"
Cohesion: 0.40
Nodes (5): 8.1 Interfaz, 8.2 `ClaudeCliProvider` (piloto), 8.3 `LocalProvider` (lanzamiento), 8.4 Flujo del modo asistido en la web, 8. Capa LLM (§43, §44)

### Community 146 - "TelegramActionTests"
Cohesion: 0.31
Nodes (3): public.track_notification_click, what the web's /r/<id> calls (sección 7.3):…, TelegramActionTests, TrackingTests

### Community 160 - "20261010120000_mvp_email_free_trial.sql"
Cohesion: 0.83
Nodes (3): public.enable_free_trial(), public.profiles, public.search_profiles

### Community 180 - "20261008120000_mercadopago.sql"
Cohesion: 0.39
Nodes (5): profiles_guard_billing_delete, public.apply_mercadopago_payment(), public.billing_checkouts, public.commercial_payments, public.guard_billing_account_delete()

### Community 182 - "Mercado Pago · cobro y acceso automático"
Cohesion: 0.14
Nodes (14): Acceso confirmado y preferencia Particular recuperada, Alta inicial con el MCP · 2/10/2026, Cobertura del ensayo que continúa pendiente, Compra bloqueada por mezcla de participantes reales y de prueba, Ensayo aislado · 3/10/2026, Estado actual · 5/10/2026, Historial de preparación · 3/10/2026, Implementación (+6 more)

### Community 183 - "insert_profiles"
Cohesion: 0.29
Nodes (10): _canonical(), create_alert(), ensure_telegram_profile(), insert_profiles(), _profile_name(), AsyncConnection, Insert one search profile per (marca, modelo) of a wizard filter. Names are…, Create the alert for a Telegram user. Returns the new profile ids. (+2 more)

### Community 184 - "_is_recent"
Cohesion: 0.38
Nodes (4): _is_recent(), Drop old listings, using first detection when publication is unknown., _is_recent reads stored listing rows (published_at is a timestamptz)., SchedulerRecencyTests

### Community 185 - "pgcase.py"
Cohesion: 0.22
Nodes (4): Helpers for tests that need Postgres (see conftest.py for the event loop)., Commercial access and payment boundaries against an isolated local database., Real isolated PostgreSQL checks for automatic access and hostile/repeated money…, HealthDatabaseTests

### Community 200 - "GPT-6 Luna en el worker"
Cohesion: 0.29
Nodes (5): Completar la clave, Comprobar y arrancar, GPT-6 Luna en el worker, Parámetros y fallos, Validación disponible

### Community 201 - "6. Intelligence (§16–20, §24, §25, §44)"
Cohesion: 0.29
Nodes (7): 6.1 Matching, 6.2 Comparables y Price Intelligence (§19), 6.3 Opportunity Score 0–100 (§17–18), 6.4 Niveles (§20), 6.5 Red flags (§24), 6.6 Preguntas al vendedor (§25), 6. Intelligence (§16–20, §24, §25, §44)

### Community 202 - "ResendEmailChannelTests"
Cohesion: 0.39
Nodes (3): Request, F7, punto 7: a footer link and List-Unsubscribe one-click (RFC 8058)., ResendEmailChannelTests

### Community 203 - "run"
Cohesion: 0.33
Nodes (6): AbstractEventLoop, Any, T, Entry-point helper: run the worker's coroutines on a loop psycopg supports.…, run(), selector_loop()

### Community 204 - "IA sobre descripciones"
Cohesion: 0.33
Nodes (5): Activación y reproceso, Comportamiento, IA sobre descripciones, Presupuesto y caché, Verificación

### Community 205 - "simulate_alert.py"
Cohesion: 0.38
Nodes (5): main(), Simulate the arrival of a listing: what the crawl does with a new listing of a…, Returns the notifications the listing produced., simulate(), SimulatedEmail

### Community 206 - "Confirmación consumida por una vista previa"
Cohesion: 0.40
Nodes (4): Confirmación consumida por una vista previa, Corrección, Evidencia de producción, Validación y alcance

### Community 207 - "heartbeat.py"
Cohesion: 0.60
Nodes (4): beat(), datetime, The worker's heartbeat (F7, punto 8): one row in worker_heartbeat, updated…, started_now()

### Community 209 - "Ingreso con Google"
Cohesion: 0.40
Nodes (4): Activación en Supabase Cloud, Ingreso con Google, Supabase local (opcional), Verificación de aceptación

### Community 210 - "7. Motor de notificaciones (§21, §22, §32, §47)"
Cohesion: 0.50
Nodes (4): 7.1 Decisión, 7.2 Canales, 7.3 Tracking de aperturas y clics, 7. Motor de notificaciones (§21, §22, §32, §47)

## Knowledge Gaps
- **547 isolated node(s):** `public.vehicle_catalog`, `public.pipeline_errors`, `public.app_config`, `public.geocode_cache`, `public.fx_rates` (+542 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **31 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Listing` connect `Listing` to `geo.py`, `BaseScraper`, `test_ingest_postgres.py`, `autocosmos.py`, `listing.py`, `crawl.py`, `test_notifications_postgres.py`, `migrate_sqlite.py`, `Page`, `ingest.py`, `CatalogModel`, `kavak.py`, `enrich.py`, `test_description_intelligence.py`, `facebook.py`, `mercadolibre.py`?**
  _High betweenness centrality (0.036) - this node is a cross-community bridge._
- **Why does `PostgresTestCase` connect `Listing` to `test_ingest_postgres.py`, `test_intelligence_postgres.py`, `listing.py`, `test_notifications_postgres.py`, `CommercialTests`, `migrate_sqlite.py`, `QueueTests`, `channels/base.py`, `MercadoPagoTests`, `TelegramActionTests`, `pgcase.py`, `AvailabilityTests`, `test_llm_contract.py`?**
  _High betweenness centrality (0.020) - this node is a cross-community bridge._
- **Why does `Links` connect `Links` to `test_ingest_postgres.py`, `templates.py`, `test_notifications_templates.py`, `test_handlers.py`, `test_notifications_postgres.py`, `ResendEmailChannelTests`, `test_mvp_worker.py`, `channels/base.py`, `main.py`, `TelegramActionTests`, `telegram.py`?**
  _High betweenness centrality (0.019) - this node is a cross-community bridge._
- **Are the 42 inferred relationships involving `Links` (e.g. with `ResendEmailChannel` and `TelegramChannel`) actually correct?**
  _`Links` has 42 INFERRED edges - model-reasoned connections that need verification._
- **Are the 36 inferred relationships involving `Listing` (e.g. with `AutoCosmosScraper` and `Page`) actually correct?**
  _`Listing` has 36 INFERRED edges - model-reasoned connections that need verification._
- **What connects `public.vehicle_catalog`, `public.pipeline_errors`, `public.app_config` to the rest of the system?**
  _547 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `description_facts.py` be split into smaller, more focused modules?**
  _Cohesion score 0.07192460317460317 - nodes in this community are weakly interconnected._
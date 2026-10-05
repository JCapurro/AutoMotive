# Graph Report - AutoMotive  (2026-10-05)

## Corpus Check
- 375 files · ~264,134 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 3379 nodes · 8638 edges · 183 communities (157 shown, 26 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 493 edges (avg confidence: 0.53)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `9f3877a2`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Links
- description_facts.py
- service.py
- Listing
- pro.ts
- createAdminClient
- Target
- pro-plans.tsx
- PostgresTestCase
- format.ts
- app/listings/[id]/page.tsx
- ListingFacts
- test_llm_jobs_postgres.py
- connection
- database.ts
- ingest.py
- CatalogModel
- baja/page.tsx
- enrich.py
- listing-actions.tsx
- search-form.tsx
- db.ts
- facebook.py
- listing.py
- fiesta_listing
- LLMProvider
- test_llm_drafts.py
- watchdog.py
- new/page.tsx
- ClaudeCliProvider
- PRD — Automotive
- createClient
- scraper_cli.py
- ingest
- test_llm_claude_cli.py
- PriceRef
- listings.py
- matching.py
- templates.py
- db/__init__.py
- AutoCosmosScraper
- geo.py
- migrate_sqlite.py
- 20260927120000_core_schema.sql
- test_parsers.py
- devDependencies
- dependencies
- compilerOptions
- [notificationId]/route.ts
- IntelligenceConfig
- PRDCopyTests
- ListingDetail
- test_llm_openai_api.py
- mercadopago-server.ts
- 20261007120000_ese_auto_commercial.sql
- login/actions.ts
- scheduler.py
- TelegramChannel
- 20261003120000_f6_backoffice_metrics.sql
- SourceAlerts
- components.json
- 20260927120100_rls.sql
- resolve_price
- test_db_postgres.py
- matches.py
- .listing
- Automotive — web
- Site
- startup_warnings
- searches/[id]/page.tsx
- metrics/page.tsx
- Comparación de modelos para búsqueda asistida
- test_llm_anthropic_api.py
- CommercialTests
- Ese Auto · propuesta comercial y proyección
- match_model
- patch
- Comunes a cualquier ruta
- Puesta en producción del piloto (F7)
- Automotive — Plan técnico del MVP
- parse_detail
- MercadoPagoTests
- OpenAIApiProvider
- v6.py
- test_llm_contract.py
- inspector.tsx
- 20261001120000_f4_web.sql
- test_intelligence.py
- TemplateSnapshotTests
- .evaluate
- .__init__
- PROPUESTA_COMERCIAL.md
- Setup
- prompts/__init__.py
- app/app/layout.tsx
- 13. Roadmap por fases
- scripts
- 40. Modelo conceptual de datos
- toggle-group.tsx
- telegram.py
- 5. Pipeline de ingesta (§14, §15, §42)
- profiles.py
- RedFlagTests
- 6. Intelligence (§16–20, §24, §25, §44)
- 4. Modelo de datos (Postgres / Supabase)
- test_db.py
- 47. Riesgos principales
- 58. Definición final del producto
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
- .matches_filters
- 16. Matching Engine
- 23. Página de resultado
- 33. Freemium inicial
- 36. Métricas de activación
- 20260930120000_f3_notifications.sql
- opengraph-image.tsx
- 20261009120000_meta_conversions.sql
- raw_pages.py
- intelligence/engine.py
- ResendEmailChannelTests
- sonner
- 20261005120000_f7_ops.sql
- AGENTS.md
- eslint.config.mjs
- next.config.ts
- postcss.config.mjs
- automotive-worker
- 20261008120000_mercadopago.sql
- Mercado Pago · cobro y acceso automático
- Notifier
- .from_app_config
- sync-locations.py
- vercel.json
- 34. Alternativa de pricing
- 35. Métricas principales
- 38. Métricas de outcome
- 49. MVP final recomendado
- 7. Público objetivo
- 8. Persona principal
- 9. Persona secundaria futura

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
- `PurchasedBanner()` --calls--> `answerInfluence()`  [EXTRACTED]
  web/components/app/listing-actions.tsx → web/app/app/listings/actions.ts
- `ResetPasswordPage()` --calls--> `createClient()`  [EXTRACTED]
  web/app/auth/reset-password/page.tsx → web/lib/supabase/server.ts
- `LoginForm()` --indirect_call--> `resendConfirmation()`  [INFERRED]
  web/app/login/login-form.tsx → web/app/login/actions.ts
- `LoginPage()` --calls--> `safeNext()`  [EXTRACTED]
  web/app/login/page.tsx → web/lib/navigation.ts

## Import Cycles
- None detected.

## Communities (183 total, 26 thin omitted)

### Community 0 - "Links"
Cohesion: 0.11
Nodes (24): CallbackQueryHandler, Update, _allowed(), help_(), invalid_code_text(), linked_text(), The Telegram bot after F4: it links the account and answers alert buttons.…, register() (+16 more)

### Community 1 - "description_facts.py"
Cohesion: 0.07
Nodes (37): _after_label(), Amount, _amounts(), _before_label(), _close(), _currency(), DescriptionFacts, _distinct() (+29 more)

### Community 2 - "service.py"
Cohesion: 0.07
Nodes (43): at_least(), rank(), Opportunity levels (§20, sección 6.4), thresholds from…, Audience, classify(), decide(), decide_all(), Decision (+35 more)

### Community 3 - "Listing"
Cohesion: 0.09
Nodes (35): AutoCosmos AR scraper. AutoCosmos exposes a public listings page at…, BaseScraper, CollectorBlocked, Listing, Run keyword detection over the title and tag the listing. Statistical detection…, One ad as a collector read it, before normalization. `marca`/`modelo`/`version`…, Apply user filters that the source could not enforce server-side., The source answered with a login wall, a security challenge or no session. The… (+27 more)

### Community 4 - "pro.ts"
Cohesion: 0.05
Nodes (54): ActionResult, shape(), SourceInput, updateConfig(), updateSource(), confirmPayment(), launchCommercialPilot(), recordRefund() (+46 more)

### Community 5 - "createAdminClient"
Cohesion: 0.10
Nodes (47): ConfigPage(), HINTS, metadata, ErrorsPage(), metadata, metadata, metadata, MatchesPage() (+39 more)

### Community 6 - "Target"
Cohesion: 0.08
Nodes (35): due_targets(), finish_target(), Any, crawl_targets and the source cadence they run on (sección 5.1)., Make crawl_targets mirror `specs` (pipeline.crawl.TargetSpec): upsert the…, Active targets of enabled sources whose next_run_at has come (or never ran)., next_run_at = now + the source's interval (sección 5.1). A failed run retries…, sync_targets() (+27 more)

### Community 7 - "pro-plans.tsx"
Cohesion: 0.07
Nodes (40): checkPayment(), ownedCheckout(), startPayment(), stopSubscription(), metadata, mono, sans, viewport (+32 more)

### Community 8 - "PostgresTestCase"
Cohesion: 0.12
Nodes (19): ResendEmailChannel, Build today's digests. Returns how many were created (then delivered)., run_digest(), MatchCandidate, A new, non-backfill match the crawl just stored., ListingEvent, PostgresTestCase, Opens the worker pool on TEST_DATABASE_URL over a clean slate. (+11 more)

### Community 9 - "format.ts"
Cohesion: 0.11
Nodes (34): AdminListingPage(), escapeLike(), ListingsPage(), DIGEST_SECTION, DigestItem, InboxPage(), metadata, WebPayload (+26 more)

### Community 10 - "app/listings/[id]/page.tsx"
Cohesion: 0.07
Nodes (36): ListingPage(), markFor(), metadata, plain(), priceHistory(), SAME, SCORE_PART, ScoreInWords() (+28 more)

### Community 11 - "ListingFacts"
Cohesion: 0.12
Nodes (26): AsyncAnthropic, AnthropicApiProvider, CatalogModel, M, The Claude API with an API key (F7, punto 6): the provider for serving the…, `claude -p` as the pilot's LLM (sección 8.2). claude -p --output-format json…, The LLM layer (sección 8): providers behind one interface. provider.py…, LocalProvider (+18 more)

### Community 12 - "test_llm_jobs_postgres.py"
Cohesion: 0.16
Nodes (6): LlmJobsCase, QueueTests, The llm_jobs queue against the local Supabase Postgres (sección 8.4): what the…, What the web can do with the user's session (sección 4.4)., Run `sql` as the signed-in web user (role authenticated, RLS on)., WebAccessTests

### Community 13 - "connection"
Cohesion: 0.10
Nodes (38): connection(), AsyncConnection, apply_telegram_action(), digest_users(), existing_keys(), insert_decisions(), insert_digest(), insert_event() (+30 more)

### Community 14 - "database.ts"
Cohesion: 0.10
Nodes (21): MatchInspector(), NotificationInspector(), context(), Inspection, inspectMatch(), inspectNotification(), ListingRow, MatchRow (+13 more)

### Community 15 - "ingest.py"
Cohesion: 0.13
Nodes (32): attrs_hash(), _empty(), _facts(), _geocode_rows(), ingest_rows(), IngestConfig, merge(), normalize_items() (+24 more)

### Community 16 - "CatalogModel"
Cohesion: 0.08
Nodes (38): load_models(), vehicle_catalog: canonical make/model/trim names. The catalog is small (a few…, Model-level rows with their trims, aliases and production years., _km(), _money(), _positive(), The LLM's search drafts, checked against vehicle_catalog (sección 8.4, paso 4).…, normalize_brand() (+30 more)

### Community 17 - "baja/page.tsx"
Cohesion: 0.15
Nodes (17): RFC-8058, POST(), metadata, ResetPasswordPage(), unsubscribe(), metadata, UnsubscribePage(), LoginForm() (+9 more)

### Community 18 - "enrich.py"
Cohesion: 0.10
Nodes (36): Refresher, mark_detail_checked(), enabled_sources(), DescriptionLLM, drain(), enrich_pass(), ingest_detail(), Any (+28 more)

### Community 19 - "listing-actions.tsx"
Cohesion: 0.14
Nodes (20): PasswordState, updatePassword(), PasswordForm(), Props, PurchasedBanner(), PurchaseDialog(), TODAY(), SellerQuestions() (+12 more)

### Community 20 - "search-form.tsx"
Cohesion: 0.05
Nodes (73): AssistedStart, canonical(), enabledSources(), escapeLike(), jobText(), Preview, PreviewListing, previewSearch() (+65 more)

### Community 21 - "db.ts"
Cohesion: 0.11
Nodes (25): SEARCH_FILTERS, alertedUser(), signIn(), ask(), setHeartbeat(), signIn(), globalSetup(), main() (+17 more)

### Community 22 - "facebook.py"
Cohesion: 0.09
Nodes (30): parse_relative_date(), Parse Spanish relative date strings shown by AR car classifieds. Examples…, Return a unix timestamp inferred from a Spanish relative-date string., _strip_accents(), _after_colon(), _city_slug(), _city_slug_from_origin(), _extract_location() (+22 more)

### Community 23 - "listing.py"
Cohesion: 0.10
Nodes (19): NamedTuple, FxQuote, fingerprint(), _hash(), listing_facts(), normalize_listing(), price_usd(), Any (+11 more)

### Community 24 - "fiesta_listing"
Cohesion: 0.14
Nodes (13): match(), The reasons if every hard filter is ok or unknown; None if one fails., CurrencyTests, fiesta_listing(), fiesta_profile(), GoldenFixtureTests, GuardAndLevelTests, PriceRef (+5 more)

### Community 25 - "LLMProvider"
Cohesion: 0.08
Nodes (34): claim(), expire(), finish(), Any, AsyncConnection, llm_jobs: the queue between the web and the LLM layer (sección 8.4). The web…, The oldest queued job of `kinds`, now 'running'; None if there is none., done' with its output, or 'failed' with the error (never both). (+26 more)

### Community 26 - "test_llm_drafts.py"
Cohesion: 0.10
Nodes (39): normalize_draft(), normalize_drafts(), Any, CatalogModel, date, One search per resolved model, with all its requested versions., The catalog model the draft names, or the make alone, or nothing., _trim() (+31 more)

### Community 27 - "watchdog.py"
Cohesion: 0.09
Nodes (30): timedelta, beat(), last_beat(), datetime, The worker's heartbeat (F7, punto 8): one row in worker_heartbeat, updated…, started_now(), EnvFileTests, F7, punto 8: the watchdog's decisions (tools/watchdog.py), without network or… (+22 more)

### Community 28 - "new/page.tsx"
Cohesion: 0.16
Nodes (15): loadFormData(), EditSearchPage(), metadata, metadata, DeleteSearchButton(), Tabs(), TabsContent(), TabsList() (+7 more)

### Community 29 - "ClaudeCliProvider"
Cohesion: 0.17
Nodes (10): Runner, ClaudeCliProvider, parse_envelope(), Any, CatalogModel, M, The structured answer inside `--output-format json`'s envelope., parametrize (+2 more)

### Community 30 - "PRD — Automotive"
Cohesion: 0.05
Nodes (37): 11. Principios de producto, 13. Concepto de Search Profile, 14. Ingesta de publicaciones, 17. Opportunity Score, 18. Componentes iniciales del Opportunity Score, 19. Price Intelligence, 1. Resumen ejecutivo, 20. Niveles de oportunidad (+29 more)

### Community 31 - "createClient"
Cohesion: 0.11
Nodes (45): markOpened(), AppLayout(), answerInfluence(), currentStatus(), markSeen(), Purchase, recordPurchase(), setDiscardReason() (+37 more)

### Community 32 - "scraper_cli.py"
Cohesion: 0.07
Nodes (36): shutdown(), _collector_loop(), AbstractEventLoop, Any, T, Run collector coroutines on an event loop that can start subprocesses.…, run_collector(), AsyncConnection (+28 more)

### Community 33 - "ingest"
Cohesion: 0.11
Nodes (18): RuntimeError, ingest(), Listing, normalize → geocode → upsert. The whole batch is one transaction., CanonicalUpsertTests, card(), CrawlTargetsTests, DescriptionFactsTests (+10 more)

### Community 34 - "test_llm_claude_cli.py"
Cohesion: 0.16
Nodes (26): BaseModel, Run the CLI once and return its stdout. Raises LLMTimeout / LLMError., run_cli(), json_schema(), Any, The model's JSON Schema, self-contained: `$defs` inlined and titles dropped.…, envelope(), FakeRunner (+18 more)

### Community 35 - "PriceRef"
Cohesion: 0.15
Nodes (14): AST, fetch(), PriceRef, Any, Price Intelligence (§19, sección 6.2). The statistics come from the SQL…, public.comparables() for one listing. `cfg` overrides app_config.comparables., CopyLintTests, _docstring_nodes() (+6 more)

### Community 36 - "listings.py"
Cohesion: 0.09
Nodes (33): enrichment_queue(), find_repost_of(), insert_listing(), insert_snapshot(), llm_facts_last_day(), lock_existing(), mark_gone(), matched_recheck_queue() (+25 more)

### Community 37 - "matching.py"
Cohesion: 0.12
Nodes (26): Result, _choice(), distance_km(), evaluate(), filter_currency(), _km(), _location(), MatchResult (+18 more)

### Community 38 - "templates.py"
Cohesion: 0.09
Nodes (37): money(), Every user-facing string of the intelligence layer (§19, §24, §25). Kept in one…, USD 10.300 · ARS 12.500.000 (Argentine thousands separator)., Operational alerts for the admin (sección 10, §46). A source that fails…, age_line(), ago_long(), before_after(), Button (+29 more)

### Community 39 - "db/__init__.py"
Cohesion: 0.09
Nodes (24): AsyncConnectionPool, Postgres (Supabase) data access for the worker. Replaces the old SQLite module.…, close_pool(), open_pool(), Async Postgres connection pool (psycopg 3), one per worker process. The worker…, Open the process-wide pool (idempotent)., get_config(), Any (+16 more)

### Community 40 - "AutoCosmosScraper"
Cohesion: 0.25
Nodes (9): AutoCosmosScraper, _price(), AsyncClient, Listing, Response, GET, retried on a network error or a 5xx; the last answer or error wins., (price, currency, partial reason) from the price blocks of a card or detail. A…, _slug() (+1 more)

### Community 41 - "geo.py"
Cohesion: 0.13
Nodes (18): Coords, _fallback_can_stand_alone(), filter_listings_by_radius(), geocode_location(), _geocode_nominatim(), _looks_like_non_location_query(), _lookup_known_location(), normalize_location_query() (+10 more)

### Community 42 - "migrate_sqlite.py"
Cohesion: 0.12
Nodes (15): Row, connection_kwargs(), Any, LoadEmailsTests, _make_sqlite(), MigrateSqliteTests, Path, load_emails() (+7 more)

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
Cohesion: 0.18
Nodes (24): diff_pct(), How far below the median the published price is, in % (negative = above)., IntelligenceConfig, ago(), level_for(), 🔥 high ≥ 85 · 🟢 good ≥ 70 · 🟡 match ≥ 50 · ⚪ low. `cap` is the highest level…, age_hours(), clamp() (+16 more)

### Community 50 - "PRDCopyTests"
Cohesion: 0.24
Nodes (3): notification(), PRDCopyTests, The §22 lines, in order, at the top of the Telegram message and the email text.

### Community 51 - "ListingDetail"
Cohesion: 0.16
Nodes (8): ListingDetail, What fetch_detail() found at a listing's URL (sección 5.5). `gone` means the…, Download the ad's own page, with the source's login-wall and session checks,…, Read the ad's page: description, version, transmission, seller type, every…, FakeSource, Listing, Stands in for a collector: returns `results[name]`, serves `details[url]` (an…, WatchlistTests

### Community 52 - "test_llm_openai_api.py"
Cohesion: 0.19
Nodes (21): check_contract(), answer(), provider(), parametrize, Responses wire contract and failure handling, with no live API calls. Replays…, replay(), test_connection_error_is_retried_once_and_sanitized(), test_golden_wire_contract() (+13 more)

### Community 53 - "mercadopago-server.ts"
Cohesion: 0.08
Nodes (50): GET(), POST(), reply(), checkoutUrl(), paymentPeriod(), sameSecret(), api(), applyPayment() (+42 more)

### Community 54 - "20261007120000_ese_auto_commercial.sql"
Cohesion: 0.09
Nodes (8): llm_jobs_guard_commercial, matches_guard_commercial, public.commercial_payments, public.guard_assisted_commercial_access(), public.guard_match_access(), public.plan_limits_for(), public.profiles, public.refund_commercial_payment()

### Community 55 - "login/actions.ts"
Cohesion: 0.19
Nodes (17): GET(), GET(), POST(), authenticate(), callbackUrl(), Email, emailError(), resendConfirmation() (+9 more)

### Community 56 - "scheduler.py"
Cohesion: 0.06
Nodes (56): profiles_by_ids(), Profiles (alert dicts with their "profile" row) by id, enabled or not., log_error(), Observability (sección 10, §46): collector_runs, pipeline_errors and source…, Record a pipeline error. Never raises: observability must not break the…, start_run(), Weights, curves and thresholds of the intelligence layer (sección 6, Apéndice…, build_items() (+48 more)

### Community 57 - "TelegramChannel"
Cohesion: 0.26
Nodes (6): Any, datetime, TelegramChannel, FakeBot, Exception, TelegramChannelTests

### Community 58 - "20261003120000_f6_backoffice_metrics.sql"
Cohesion: 0.10
Nodes (16): pro_waitlist_set_updated_at, public.admin_notification_daily, public.admin_score_histogram, public.admin_searches, public.admin_source_health, public.admin_users, public.join_waitlist(), public.pro_waitlist (+8 more)

### Community 59 - "SourceAlerts"
Cohesion: 0.11
Nodes (21): finish_run(), A source's failure streak after a run (the admin alert reads it)., Close a run and keep the source's health counters in step. Returns the source's…, SourceHealth, failing_text(), last_error_line(), Any, datetime (+13 more)

### Community 60 - "components.json"
Cohesion: 0.09
Nodes (21): aliases, components, hooks, lib, ui, utils, iconLibrary, menuAccent (+13 more)

### Community 61 - "20260927120100_rls.sql"
Cohesion: 0.10
Nodes (20): public.app_config, public.collector_runs, public.crawl_targets, public.enforce_plan_limits(), public.events, public.fx_rates, public.geocode_cache, public.listing_snapshots (+12 more)

### Community 62 - "resolve_price"
Cohesion: 0.15
Nodes (7): PriceResolution, What resolve_price() concluded, stored in description_facts.price_check. The…, The listing's effective price (sección 5.2, v3). `published`/`currency`: the…, resolve_price(), _usd(), _resolve(), ResolvePriceTests

### Community 63 - "test_db_postgres.py"
Cohesion: 0.13
Nodes (8): AlertRepoTests, GeocodeAndConfigTests, _listing(), The bot's data layer against a real Postgres with the supabase/ migrations. Run…, /start <code> (public.link_telegram, F4)., SeenMatchesTests, store(), TelegramLinkTests

### Community 64 - "matches.py"
Cohesion: 0.17
Nodes (19): _existing(), filter_unseen(), insert_legacy_matches(), _keys(), mark_seen(), matched_by_other_profiles(), matches_of_listings(), Any (+11 more)

### Community 65 - ".listing"
Cohesion: 0.22
Nodes (6): ComparablesCascadeTests, IntelligenceCase, PriceRef, Insert a listing row directly: comparables are about stored columns., Sección 6.2: trim+transmission → transmission → model, first with n ≥ min_n., ScoredMatchesTests

### Community 66 - "Automotive — web"
Cohesion: 0.22
Nodes (7): Configuración del proyecto alojado antes de publicar, Desarrollo, Registro y acceso con Supabase Auth, Automotive — web, Correrla, Rutas (plan técnico, sección 9), Tests

### Community 67 - "Site"
Cohesion: 0.20
Nodes (10): range, AutoCosmosSearchTests, card(), page(), Request, Response, AutoCosmos search: every page of the model, `?pidx=N`, retried on 503 (no…, Serves `pages[pidx]`; `fail[pidx]` is a list of statuses (or exceptions) to… (+2 more)

### Community 68 - "startup_warnings"
Cohesion: 0.14
Nodes (10): What this configuration leaves off (F7, punto 5): one line per channel, metric…, startup_warnings(), _database(), db_test_skip_reason(), Why the DB tests can't run here, or None. They TRUNCATE tables, so they only…, ConfigTests, F7, punto 4: the DB tests TRUNCATE, so they never touch the pilot's database., F7, punto 5: every channel or metric the .env leaves off is logged at startup. (+2 more)

### Community 69 - "searches/[id]/page.tsx"
Cohesion: 0.09
Nodes (28): Dashboard(), metadata, COUNT_KEY, EMPTY, Filter, FILTERS, metadata, SearchResultsPage() (+20 more)

### Community 70 - "metrics/page.tsx"
Cohesion: 0.17
Nodes (13): CTA_EVENTS, day(), levelLabel(), median(), metadata, MetricsPage(), Rate(), WAITLIST (+5 more)

### Community 71 - "Comparación de modelos para búsqueda asistida"
Cohesion: 0.11
Nodes (17): Completar la clave, Comprobar y arrancar, GPT-6 Luna en el worker, Parámetros y fallos, Validación disponible, APIs: estructura de salida y razonamiento, APIs: precios comparables, Comparación de modelos para búsqueda asistida (+9 more)

### Community 72 - "test_llm_anthropic_api.py"
Cohesion: 0.27
Nodes (12): message(), provider(), parametrize, Request, Response, F7, punto 6: the Claude API provider (llm/anthropic_api.py) against a mocked…, replay(), test_golden_phrases() (+4 more)

### Community 74 - "Ese Auto · propuesta comercial y proyección"
Cohesion: 0.12
Nodes (16): 1. Qué vender, 2. Qué ya existe y qué falta, 3. Referencias de mercado, 4. Alternativas iniciales conservadas como referencia, 5. Oferta seleccionada en pesos: B, 6. Proyección a seis meses, 7. Validación y salida comercial, 8. Decisión a registrar (+8 more)

### Community 76 - "match_model"
Cohesion: 0.36
Nodes (4): match_model(), CatalogModel, Canonical (make, model), or None if it isn't in the catalog. The model matches…, CatalogMatchTests

### Community 77 - "patch"
Cohesion: 0.33
Nodes (5): patch, _is_recent(), Drop listings published more than `max_age_days` ago. If the source doesn't say…, _is_recent reads stored listing rows (published_at is a timestamptz)., SchedulerRecencyTests

### Community 78 - "Comunes a cualquier ruta"
Cohesion: 0.12
Nodes (16): COM-02 · Una oferta coherente, COM-03 · Límites que siguen vigentes al vencer, COM-04 y COM-05 · Cobro y ciclo de vida, COM-06 · Autogestión, COM-07 · Producto que se puede prometer, COM-08 · Medir rentabilidad, no solo intención, COM-09 · Operación comercial, COM-10 · Salida controlada (+8 more)

### Community 79 - "Puesta en producción del piloto (F7)"
Cohesion: 0.13
Nodes (15): 10. Prueba de aceptación, 1. Dominio en Cloudflare, 2. Túnel de Cloudflare, 3. Resend (emails de login y de alertas), 4. API key de Anthropic (modo asistido), 5. Chat de Telegram para las alertas operativas, 6. Sesiones de MercadoLibre y Facebook, 7. Configuración (+7 more)

### Community 80 - "Automotive — Plan técnico del MVP"
Cohesion: 0.10
Nodes (20): 10. Backoffice y observabilidad (§45, §46), 11. Métricas y eventos (§35–38, §53), 12. Freemium (§33, §34), 14. Riesgos y decisiones abiertas, 15. Trazabilidad PRD → plan, 1. Punto de partida y gaps, 2. Arquitectura objetivo, 3. Estructura del repo (+12 more)

### Community 81 - "parse_detail"
Cohesion: 0.11
Nodes (23): BeautifulSoup, json_ld(), json_ld_of_type(), Any, Every schema.org object in the page's JSON-LD blocks (flattening @graph)., _browser_storage_state(), _build_url(), _extract_id() (+15 more)

### Community 83 - "OpenAIApiProvider"
Cohesion: 0.29
Nodes (5): OpenAIApiProvider, AsyncClient, CatalogModel, M, Response

### Community 84 - "v6.py"
Cohesion: 0.17
Nodes (19): Browser, BrowserContext, browser_context(), _ensure_browser(), Yield a fresh browser context. Closes context on exit; browser is reused., multiline_text(), Text with paragraph breaks kept (descriptions)., text_of() (+11 more)

### Community 85 - "test_llm_contract.py"
Cohesion: 0.09
Nodes (26): fixture, skipif, AbstractEventLoop, Any, T, Entry-point helper: run the worker's coroutines on a loop psycopg supports.…, run(), selector_loop() (+18 more)

### Community 86 - "inspector.tsx"
Cohesion: 0.11
Nodes (23): metadata, CASCADE, Inspector(), LEVEL_RANK, STATUS_TONE, Json(), LevelBadge(), STATUS_STYLE (+15 more)

### Community 87 - "20261001120000_f4_web.sql"
Cohesion: 0.24
Nodes (7): public.dashboard_summary(), public.link_telegram(), public.match_cards, public.profiles, public.recent_opportunities(), public.search_result_counts(), public.search_results()

### Community 88 - "test_intelligence.py"
Cohesion: 0.14
Nodes (20): RedFlag, number(), _age_years(), description_known(), description_mismatches(), Any, datetime, Red flags (§24, sección 6.5). Pure, deterministic rules. Each flag has an id, a… (+12 more)

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
Cohesion: 0.20
Nodes (13): active(), BottomNav(), ITEMS, MobileInboxLink(), TopNav(), Inbox, InboxContext, InboxProvider() (+5 more)

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

### Community 102 - "telegram.py"
Cohesion: 0.09
Nodes (27): InlineKeyboardMarkup, parse(), Inline buttons of a Telegram alert (sección 7.2): ⭐ Me interesa · ✖ Descartar.…, Channel, Notification, Protocol, The channel interface (sección 7.2): the engine never knows how an alert…, A notifications row, with the user's contact data, ready to send. (+19 more)

### Community 103 - "5. Pipeline de ingesta (§14, §15, §42)"
Cohesion: 0.25
Nodes (8): 5.1 Crawl targets, 5.2 Normalización, 5.3 Upsert, snapshots y detección de cambios, 5.4 Re-publicaciones (§15, heurística imperfecta aceptada), 5.5 Enrichment de la ficha, 5.6 Watchlist refresher (§30), 5.7 Bootstrap (evita el diluvio inicial; se conserva la idea actual), 5. Pipeline de ingesta (§14, §15, §42)

### Community 104 - "profiles.py"
Cohesion: 0.08
Nodes (36): _put(), Any, Translate between the Telegram wizard's filter dict and search_profiles. The…, (marca, modelo) combinations of a wizard filter: one search profile each., Wizard dict + one (make, model) → search_profiles column values., search_profiles column values → the wizard dict the scheduler and handlers…, split_vehicles(), to_legacy() (+28 more)

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

### Community 129 - ".matches_filters"
Cohesion: 0.24
Nodes (7): _parse_card(), parse_search(), Listing, _slug(), _to_int(), KavakFilterTests, Listing

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

### Community 142 - "raw_pages.py"
Cohesion: 0.24
Nodes (10): compress(), decompress(), iter_for_reparse(), mark_parsed(), purge_older_than(), raw_pages: the last detail page of each listing, compressed (normalization v3).…, Stored detail pages, oldest listing first. `below_version`: per source, only…, The stored page was read again with this parser version (tools/reprocess.py). (+2 more)

### Community 145 - "intelligence/engine.py"
Cohesion: 0.29
Nodes (9): assess(), evaluate(), Evaluation, Any, datetime, PriceRef, One listing × one profile → everything a match row stores. Pure.…, The columns of `matches` this evaluation fills. (+1 more)

### Community 146 - "ResendEmailChannelTests"
Cohesion: 0.39
Nodes (3): Request, F7, punto 7: a footer link and List-Unsubscribe one-click (RFC 8058)., ResendEmailChannelTests

### Community 180 - "20261008120000_mercadopago.sql"
Cohesion: 0.39
Nodes (5): profiles_guard_billing_delete, public.apply_mercadopago_payment(), public.billing_checkouts, public.commercial_payments, public.guard_billing_account_delete()

### Community 182 - "Mercado Pago · cobro y acceso automático"
Cohesion: 0.17
Nodes (12): Acceso confirmado y preferencia Particular recuperada, Alta inicial con el MCP · 2/10/2026, Compra bloqueada por mezcla de participantes reales y de prueba, Configuración pendiente del entorno destino, Ensayo aislado · 3/10/2026, Estado actual · 3/10/2026, Implementación, Mercado Pago · cobro y acceso automático (+4 more)

### Community 184 - "Notifier"
Cohesion: 0.10
Nodes (23): amain(), build_notifier(), _every(), notifying(), stdout, plus LOG_FILE (UTF-8, rotated at midnight, LOG_KEEP_DAYS kept)., Run `job(stop)` now and then every `seconds` until stopped; errors are logged., The channels this worker can deliver on (sección 7.2)., A refresh pass whose price_drop / listing_gone events go to the engine. (+15 more)

### Community 185 - ".from_app_config"
Cohesion: 0.40
Nodes (3): _merge(), Any, ConfigTests

## Knowledge Gaps
- **507 isolated node(s):** `public.vehicle_catalog`, `public.pipeline_errors`, `public.app_config`, `public.geocode_cache`, `public.fx_rates` (+502 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **26 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Listing` connect `Listing` to `.matches_filters`, `ingest`, `Target`, `AutoCosmosScraper`, `PostgresTestCase`, `geo.py`, `migrate_sqlite.py`, `ingest.py`, `CatalogModel`, `parse_detail`, `enrich.py`, `ListingDetail`, `v6.py`, `facebook.py`, `listing.py`, `test_db_postgres.py`?**
  _High betweenness centrality (0.030) - this node is a cross-community bridge._
- **Why does `PostgresTestCase` connect `PostgresTestCase` to `ingest`, `.listing`, `Listing`, `db/__init__.py`, `CommercialTests`, `migrate_sqlite.py`, `test_llm_jobs_postgres.py`, `patch`, `MercadoPagoTests`, `ListingDetail`, `listing.py`, `scheduler.py`, `test_db_postgres.py`?**
  _High betweenness centrality (0.025) - this node is a cross-community bridge._
- **Why does `connection()` connect `connection` to `matches.py`, `ingest`, `listings.py`, `Target`, `db/__init__.py`, `profiles.py`, `raw_pages.py`, `enrich.py`, `scheduler.py`, `SourceAlerts`?**
  _High betweenness centrality (0.023) - this node is a cross-community bridge._
- **Are the 41 inferred relationships involving `Links` (e.g. with `ResendEmailChannel` and `TelegramChannel`) actually correct?**
  _`Links` has 41 INFERRED edges - model-reasoned connections that need verification._
- **Are the 35 inferred relationships involving `Listing` (e.g. with `AutoCosmosScraper` and `Page`) actually correct?**
  _`Listing` has 35 INFERRED edges - model-reasoned connections that need verification._
- **What connects `public.vehicle_catalog`, `public.pipeline_errors`, `public.app_config` to the rest of the system?**
  _507 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Links` be split into smaller, more focused modules?**
  _Cohesion score 0.10520487264673312 - nodes in this community are weakly interconnected._
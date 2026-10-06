# Graph Report - AutoMotive  (2026-10-05)

## Corpus Check
- 403 files · ~276,911 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 3620 nodes · 9172 edges · 208 communities (174 shown, 34 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 533 edges (avg confidence: 0.55)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `0f348a8f`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Links
- description_facts.py
- Event
- BaseScraper
- pro.ts
- createAdminClient
- Target
- pro-plans.tsx
- WebChannel
- app/listings/[id]/page.tsx
- inspector.tsx
- ListingFacts
- QueueTests
- notifications.py
- normalize_text
- ingest.py
- CatalogModel
- settings/page.tsx
- log_error
- button.tsx
- search-form.tsx
- db.ts
- facebook.py
- listing.py
- fiesta_listing
- LLMProvider
- test_llm_drafts.py
- platform_health.py
- Page
- ClaudeCliProvider
- PRD — Automotive
- createClient
- scraper_cli.py
- test_ingest_postgres.py
- test_llm_claude_cli.py
- PriceRef
- listings.py
- matching.py
- templates.py
- Notifier
- AutoCosmosScraper
- geo.py
- migrate_sqlite.py
- 20260927120000_core_schema.sql
- html
- devDependencies
- dependencies
- compilerOptions
- [notificationId]/route.ts
- IntelligenceConfig
- PRDCopyTests
- rescore.py
- test_llm_openai_api.py
- mercadopago-server.ts
- 20261007120000_ese_auto_commercial.sql
- login-form.tsx
- scheduler.py
- TelegramChannel
- 20261003120000_f6_backoffice_metrics.sql
- SourceAlerts
- components.json
- 20260927120100_rls.sql
- SearchDraft
- Listing
- CollectorChecksTests
- .listing
- Automotive — web
- Site
- startup_warnings
- new/page.tsx
- matches.py
- Comparación de modelos para búsqueda asistida
- test_llm_anthropic_api.py
- CommercialTests
- Ese Auto · propuesta comercial y proyección
- database.ts
- Page
- Comunes a cualquier ruta
- Puesta en producción del piloto (F7)
- Automotive — Plan técnico del MVP
- mercadolibre.py
- MercadoPagoTests
- billing/page.tsx
- v6.py
- test_description_intelligence.py
- searches/[id]/page.tsx
- 20261001120000_f4_web.sql
- test_intelligence.py
- TemplateSnapshotTests
- AvailabilityTests
- RuntimeError
- PROPUESTA_COMERCIAL.md
- Setup
- prompts/__init__.py
- web/app/page.tsx
- 13. Roadmap por fases
- scripts
- 40. Modelo conceptual de datos
- toggle-group.tsx
- merge
- telegram.py
- 5. Pipeline de ingesta (§14, §15, §42)
- connection
- DeliveryTests
- RedFlagTests
- AmountTests
- test_ops.py
- 4. Modelo de datos (Postgres / Supabase)
- test_db.py
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
- .matches_filters
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
- assess
- Descripciones como fuente de datos
- 8. Capa LLM (§43, §44)
- raw_pages.py
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
- simulate_alert.py
- targets.py
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
- _is_recent
- LocalProvider
- ResendEmailChannelTests
- run
- IA sobre descripciones
- heartbeat.py
- open_pool
- .__init__

## God Nodes (most connected - your core abstractions)
1. `Links` - 89 edges
2. `Listing` - 83 edges
3. `connection()` - 73 edges
4. `createClient()` - 69 edges
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
- `TermsPage()` --calls--> `planPrice()`  [EXTRACTED]
  web/app/terminos/page.tsx → web/lib/pro.ts

## Import Cycles
- None detected.

## Communities (208 total, 34 thin omitted)

### Community 0 - "Links"
Cohesion: 0.09
Nodes (26): CallbackQueryHandler, Update, _allowed(), help_(), invalid_code_text(), linked_text(), The Telegram bot after F4: it links the account and answers alert buttons.…, register() (+18 more)

### Community 1 - "description_facts.py"
Cohesion: 0.06
Nodes (45): input_hash(), _after_label(), Amount, _amounts(), _before_label(), _close(), _currency(), DescriptionFacts (+37 more)

### Community 2 - "Event"
Cohesion: 0.10
Nodes (28): at_least(), level_for(), rank(), Opportunity levels (§20, sección 6.4), thresholds from…, 🔥 high ≥ 85 · 🟢 good ≥ 70 · 🟡 match ≥ 50 · ⚪ low. `cap` is the highest level…, Audience, classify(), decide() (+20 more)

### Community 3 - "BaseScraper"
Cohesion: 0.12
Nodes (10): BaseScraper, Page, Run keyword detection over the title and tag the listing. Statistical detection…, Download the ad's own page, with the source's login-wall and session checks,…, Read the ad's page: description, version, transmission, seller type, every…, What raw_pages keeps of a detail page: enough for parse_detail()., FakeSource, Listing (+2 more)

### Community 4 - "pro.ts"
Cohesion: 0.07
Nodes (42): ActionResult, shape(), SourceInput, updateConfig(), updateSource(), confirmPayment(), launchCommercialPilot(), recordRefund() (+34 more)

### Community 5 - "createAdminClient"
Cohesion: 0.09
Nodes (60): ConfigPage(), HINTS, metadata, ErrorsPage(), metadata, metadata, metadata, MatchesPage() (+52 more)

### Community 6 - "Target"
Cohesion: 0.10
Nodes (27): The crawl target a card was found through: a hint, never the truth., Target, crawl_due(), derive_targets(), Any, BatchHandler, HealthHandler, SourceHealth (+19 more)

### Community 7 - "pro-plans.tsx"
Cohesion: 0.08
Nodes (33): metadata, mono, sans, viewport, ListingActions(), ProPlans(), ViewTracker(), Consent (+25 more)

### Community 8 - "WebChannel"
Cohesion: 0.13
Nodes (17): ResendEmailChannel, WebChannel, MatchCandidate, A new, non-backfill match the crawl just stored., ListingEvent, WebChannelTests, AlertTypesTests, DailyCapAndDigestTests (+9 more)

### Community 9 - "app/listings/[id]/page.tsx"
Cohesion: 0.08
Nodes (47): AdminListingPage(), escapeLike(), ListingsPage(), ListingPage(), markFor(), metadata, plain(), priceHistory() (+39 more)

### Community 10 - "inspector.tsx"
Cohesion: 0.06
Nodes (44): MatchInspector(), metadata, metadata, NotificationInspector(), CASCADE, Decision(), Inspector(), LEVEL_RANK (+36 more)

### Community 11 - "ListingFacts"
Cohesion: 0.09
Nodes (32): AsyncAnthropic, BaseModel, AnthropicApiProvider, CatalogModel, M, The Claude API with an API key (F7, punto 6): the provider for serving the…, `claude -p` as the pilot's LLM (sección 8.2). claude -p --output-format json…, The LLM layer (sección 8): providers behind one interface. provider.py… (+24 more)

### Community 12 - "QueueTests"
Cohesion: 0.17
Nodes (5): LlmJobsCase, QueueTests, What the web can do with the user's session (sección 4.4)., Run `sql` as the signed-in web user (role authenticated, RLS on)., WebAccessTests

### Community 13 - "notifications.py"
Cohesion: 0.07
Nodes (41): apply_telegram_action(), delivery_payload(), digest_users(), existing_keys(), insert_decisions(), insert_digest(), insert_event(), interactions() (+33 more)

### Community 14 - "normalize_text"
Cohesion: 0.11
Nodes (19): _put(), Any, Translate between the Telegram wizard's filter dict and search_profiles. The…, Wizard dict + one (make, model) → search_profiles column values., search_profiles column values → the wizard dict the scheduler and handlers…, to_legacy(), to_profile(), match_model() (+11 more)

### Community 15 - "ingest.py"
Cohesion: 0.08
Nodes (49): load_models(), AsyncConnection, CatalogModel, Model-level rows with their trims, aliases and production years., resolve_make_model(), money(), USD 10.300 · ARS 12.500.000 (Argentine thousands separator)., Re-score the matches of the listings a detail pass updated. (+41 more)

### Community 16 - "CatalogModel"
Cohesion: 0.16
Nodes (17): _best_by_name(), _brands_in(), CatalogModel, _finish(), _fuzzy(), _has_phrase(), _pick(), Make, model and trim of a listing, resolved against vehicle_catalog (sección… (+9 more)

### Community 17 - "settings/page.tsx"
Cohesion: 0.14
Nodes (18): RFC-8058, POST(), metadata, metadata, ResetPasswordPage(), unsubscribe(), metadata, UnsubscribePage() (+10 more)

### Community 18 - "log_error"
Cohesion: 0.12
Nodes (23): Refresher, mark_detail_checked(), matched_recheck_queue(), Saved or followed listings still active and not checked in the last day…, Active listings with a match (above 'low') that the crawl stopped seeing: past…, watchlist_queue(), log_error(), Record a pipeline error. Never raises: observability must not break the… (+15 more)

### Community 19 - "button.tsx"
Cohesion: 0.10
Nodes (27): PasswordState, updatePassword(), PasswordForm(), SourceForm(), Props, FrequencySelect(), PauseButton(), ChannelsForm() (+19 more)

### Community 20 - "search-form.tsx"
Cohesion: 0.05
Nodes (72): AssistedStart, canonical(), enabledSources(), escapeLike(), jobText(), Preview, PreviewListing, previewSearch() (+64 more)

### Community 21 - "db.ts"
Cohesion: 0.11
Nodes (25): SEARCH_FILTERS, alertedUser(), signIn(), ask(), setHeartbeat(), signIn(), globalSetup(), main() (+17 more)

### Community 22 - "facebook.py"
Cohesion: 0.09
Nodes (30): CollectorBlocked, The source answered with a login wall, a security challenge or no session. The…, _after_colon(), _city_slug(), _city_slug_from_origin(), _extract_location(), FacebookMarketplaceScraper, _looks_like_location() (+22 more)

### Community 23 - "listing.py"
Cohesion: 0.11
Nodes (23): attrs_hash(), fingerprint(), _hash(), listing_facts(), normalize_listing(), price_usd(), Any, CatalogModel (+15 more)

### Community 24 - "fiesta_listing"
Cohesion: 0.13
Nodes (15): timedelta, evaluate(), match(), The reasons if every hard filter is ok or unknown; None if one fails., CurrencyTests, fiesta_listing(), fiesta_profile(), GoldenFixtureTests (+7 more)

### Community 25 - "LLMProvider"
Cohesion: 0.09
Nodes (29): claim(), expire(), finish(), Any, AsyncConnection, llm_jobs: the queue between the web and the LLM layer (sección 8.4). The web…, The oldest queued job of `kinds`, now 'running'; None if there is none., done' with its output, or 'failed' with the error (never both). (+21 more)

### Community 26 - "test_llm_drafts.py"
Cohesion: 0.13
Nodes (28): _items(), CatalogModel, vehicle_catalog as supabase/seed.sql inserts it, without a database. The LLM…, seed_catalog(), _year(), draft(), norm(), normalization/drafts.py: the deterministic step after the LLM (sección 8.4,… (+20 more)

### Community 27 - "platform_health.py"
Cohesion: 0.13
Nodes (26): last_beat(), HealthDatabaseTests, collector_checks(), exclusive_check(), inspect_database(), load_state(), main(), notify_changes() (+18 more)

### Community 29 - "ClaudeCliProvider"
Cohesion: 0.10
Nodes (20): fixture, Runner, ClaudeCliProvider, CatalogModel, M, load_recordings(), Any, Path (+12 more)

### Community 30 - "PRD — Automotive"
Cohesion: 0.05
Nodes (37): 11. Principios de producto, 13. Concepto de Search Profile, 14. Ingesta de publicaciones, 17. Opportunity Score, 18. Componentes iniciales del Opportunity Score, 19. Price Intelligence, 1. Resumen ejecutivo, 20. Niveles de oportunidad (+29 more)

### Community 31 - "createClient"
Cohesion: 0.11
Nodes (40): AppLayout(), answerInfluence(), currentStatus(), markSeen(), Purchase, recordPurchase(), setDiscardReason(), setSaved() (+32 more)

### Community 32 - "scraper_cli.py"
Cohesion: 0.07
Nodes (40): NamedTuple, shutdown(), _collector_loop(), AbstractEventLoop, Any, T, Run collector coroutines on an event loop that can start subprocesses.…, run_collector() (+32 more)

### Community 33 - "test_ingest_postgres.py"
Cohesion: 0.10
Nodes (21): ListingDetail, What fetch_detail() found at a listing's URL (sección 5.5). `gone` means the…, ingest(), normalize → geocode → upsert. The whole batch is one transaction., CanonicalUpsertTests, card(), CrawlTargetsTests, DescriptionFactsTests (+13 more)

### Community 34 - "test_llm_claude_cli.py"
Cohesion: 0.15
Nodes (27): parse_envelope(), Any, Run the CLI once and return its stdout. Raises LLMTimeout / LLMError., The structured answer inside `--output-format json`'s envelope., run_cli(), envelope(), FakeRunner, provider() (+19 more)

### Community 35 - "PriceRef"
Cohesion: 0.13
Nodes (16): AST, fetch(), PriceRef, Any, public.comparables() for one listing. `cfg` overrides app_config.comparables., _merge(), Any, ConfigTests (+8 more)

### Community 36 - "listings.py"
Cohesion: 0.10
Nodes (32): enrichment_queue(), find_repost_of(), finish_description_run(), insert_listing(), insert_snapshot(), llm_facts_last_day(), lock_existing(), mark_gone() (+24 more)

### Community 37 - "matching.py"
Cohesion: 0.13
Nodes (25): Result, _choice(), distance_km(), evaluate(), filter_currency(), _km(), _location(), MatchResult (+17 more)

### Community 38 - "templates.py"
Cohesion: 0.11
Nodes (33): age_line(), ago_long(), before_after(), Button, Content, _digest(), DigestItem, email() (+25 more)

### Community 39 - "Notifier"
Cohesion: 0.08
Nodes (42): amain(), build_notifier(), _every(), notifying(), stdout, plus LOG_FILE (UTF-8, rotated at midnight, LOG_KEEP_DAYS kept)., Run `job(stop)` now and then every `seconds` until stopped; errors are logged., The channels this worker can deliver on (sección 7.2)., A refresh pass whose price_drop / listing_gone events go to the engine. (+34 more)

### Community 40 - "AutoCosmosScraper"
Cohesion: 0.25
Nodes (9): AutoCosmosScraper, _price(), AsyncClient, Listing, Response, GET, retried on a network error or a 5xx; the last answer or error wins., (price, currency, partial reason) from the price blocks of a card or detail. A…, _slug() (+1 more)

### Community 41 - "geo.py"
Cohesion: 0.14
Nodes (19): Coords, _fallback_can_stand_alone(), filter_listings_by_radius(), geocode_location(), _geocode_nominatim(), haversine_km(), _looks_like_non_location_query(), _lookup_known_location() (+11 more)

### Community 42 - "migrate_sqlite.py"
Cohesion: 0.12
Nodes (15): connection_kwargs(), Any, ensure_telegram_profile(), LoadEmailsTests, _make_sqlite(), MigrateSqliteTests, Path, load_emails() (+7 more)

### Community 43 - "20260927120000_core_schema.sql"
Cohesion: 0.13
Nodes (29): app_config_set_updated_at, crawl_targets_set_updated_at, matches_set_updated_at, on_auth_user_created, owned_vehicles_set_updated_at, profiles_set_updated_at, public.app_config, public.collector_runs (+21 more)

### Community 44 - "html"
Cohesion: 0.10
Nodes (6): AutoCosmosParserTests, FacebookParserTests, html(), KavakParserTests, MercadoLibreParserTests, V6ParserTests

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
Cohesion: 0.21
Nodes (22): diff_pct(), How far below the median the published price is, in % (negative = above)., IntelligenceConfig, ago(), age_hours(), clamp(), completeness_component(), completeness_fields() (+14 more)

### Community 50 - "PRDCopyTests"
Cohesion: 0.24
Nodes (3): notification(), PRDCopyTests, The §22 lines, in order, at the top of the Telegram message and the email text.

### Community 51 - "rescore.py"
Cohesion: 0.19
Nodes (15): nightly_loop(), Any, datetime, Re-scoring existing matches (sección 6.1). * After enrichment: transmission or…, Re-score (search_profile_id, listing_id) pairs. Returns rows updated., Seconds from `now` to the next `hour` ("HH:MM", ART)., Re-score matches once a night, then purge stale listings; also, once at…, rescore() (+7 more)

### Community 52 - "test_llm_openai_api.py"
Cohesion: 0.16
Nodes (24): build_provider(), The provider `LLM_PROVIDER` names., test_build_provider(), answer(), provider(), parametrize, Responses wire contract and failure handling, with no live API calls. Replays…, replay() (+16 more)

### Community 53 - "mercadopago-server.ts"
Cohesion: 0.12
Nodes (39): GET(), POST(), reply(), checkoutUrl(), paymentPeriod(), sameSecret(), api(), applyPayment() (+31 more)

### Community 54 - "20261007120000_ese_auto_commercial.sql"
Cohesion: 0.09
Nodes (8): llm_jobs_guard_commercial, matches_guard_commercial, public.commercial_payments, public.guard_assisted_commercial_access(), public.guard_match_access(), public.plan_limits_for(), public.profiles, public.refund_commercial_payment()

### Community 55 - "login-form.tsx"
Cohesion: 0.19
Nodes (17): GET(), GET(), POST(), authenticate(), AuthMode, callbackUrl(), Email, emailError() (+9 more)

### Community 56 - "scheduler.py"
Cohesion: 0.10
Nodes (22): Price Intelligence (§19, sección 6.2). The statistics come from the SQL…, Evaluation, Bootstrap of new or edited profiles (sección 5.7). A profile that was never…, Backfill one profile. Returns how many listings it matched., Bootstrap every profile that needs it. Returns how many were processed., rematch_profile(), run_pending(), _key() (+14 more)

### Community 57 - "TelegramChannel"
Cohesion: 0.26
Nodes (6): Any, datetime, TelegramChannel, FakeBot, Exception, TelegramChannelTests

### Community 58 - "20261003120000_f6_backoffice_metrics.sql"
Cohesion: 0.10
Nodes (16): pro_waitlist_set_updated_at, public.admin_notification_daily, public.admin_score_histogram, public.admin_searches, public.admin_source_health, public.admin_users, public.join_waitlist(), public.pro_waitlist (+8 more)

### Community 59 - "SourceAlerts"
Cohesion: 0.11
Nodes (23): finish_run(), Observability (sección 10, §46): collector_runs, pipeline_errors and source…, A source's failure streak after a run (the admin alert reads it)., Close a run and keep the source's health counters in step. Returns the source's…, SourceHealth, start_run(), failing_text(), last_error_line() (+15 more)

### Community 60 - "components.json"
Cohesion: 0.09
Nodes (21): aliases, components, hooks, lib, ui, utils, iconLibrary, menuAccent (+13 more)

### Community 61 - "20260927120100_rls.sql"
Cohesion: 0.10
Nodes (20): public.app_config, public.collector_runs, public.crawl_targets, public.enforce_plan_limits(), public.events, public.fx_rates, public.geocode_cache, public.listing_snapshots (+12 more)

### Community 62 - "SearchDraft"
Cohesion: 0.15
Nodes (24): skipif, One vehicle the user is looking for: a proposed Search Profile (sección 4.3)., SearchDraft, _km(), _money(), normalize_draft(), normalize_drafts(), _positive() (+16 more)

### Community 63 - "Listing"
Cohesion: 0.07
Nodes (18): Listing, One ad as a collector read it, before normalization. `marca`/`modelo`/`version`…, Enrichment of listings with a match (sección 5.5). Cards don't carry…, PostgresTestCase, Helpers for tests that need Postgres (see conftest.py for the event loop)., Opens the worker pool on TEST_DATABASE_URL over a clean slate., Commercial access and payment boundaries against an isolated local database., AlertRepoTests (+10 more)

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
Cohesion: 0.13
Nodes (10): What this configuration leaves off (F7, punto 5): one line per channel, metric…, startup_warnings(), _database(), db_test_skip_reason(), Why the DB tests can't run here, or None. They TRUNCATE tables, so they only…, ConfigTests, F7, punto 4: the DB tests TRUNCATE, so they never touch the pilot's database., F7, punto 5: every channel or metric the .env leaves off is logged at startup. (+2 more)

### Community 69 - "new/page.tsx"
Cohesion: 0.16
Nodes (15): loadFormData(), EditSearchPage(), metadata, metadata, DeleteSearchButton(), Tabs(), TabsContent(), TabsList() (+7 more)

### Community 70 - "matches.py"
Cohesion: 0.17
Nodes (19): _existing(), filter_unseen(), insert_legacy_matches(), _keys(), mark_seen(), matched_by_other_profiles(), matches_of_listings(), Any (+11 more)

### Community 71 - "Comparación de modelos para búsqueda asistida"
Cohesion: 0.11
Nodes (17): Completar la clave, Comprobar y arrancar, GPT-6 Luna en el worker, Parámetros y fallos, Validación disponible, APIs: estructura de salida y razonamiento, APIs: precios comparables, Comparación de modelos para búsqueda asistida (+9 more)

### Community 72 - "test_llm_anthropic_api.py"
Cohesion: 0.27
Nodes (12): message(), provider(), parametrize, Request, Response, F7, punto 6: the Claude API provider (llm/anthropic_api.py) against a mocked…, replay(), test_golden_phrases() (+4 more)

### Community 74 - "Ese Auto · propuesta comercial y proyección"
Cohesion: 0.12
Nodes (16): 1. Qué vender, 2. Qué ya existe y qué falta, 3. Referencias de mercado, 4. Alternativas iniciales conservadas como referencia, 5. Oferta seleccionada en pesos: B, 6. Proyección a seis meses, 7. Validación y salida comercial, 8. Decisión a registrar (+8 more)

### Community 76 - "database.ts"
Cohesion: 0.10
Nodes (18): AdAttribution, capiEnabled(), Purchase, sendPurchase(), sha256(), checkout, fetchMock, send() (+10 more)

### Community 77 - "Page"
Cohesion: 0.07
Nodes (55): Browser, patch, AutoCosmos AR scraper. AutoCosmos exposes a public listings page at…, browser_context(), _ensure_browser(), BrowserContext, Shared Playwright helpers — reuse a single browser instance across scrapers., Yield a fresh browser context. Closes context on exit; browser is reused. (+47 more)

### Community 78 - "Comunes a cualquier ruta"
Cohesion: 0.12
Nodes (16): COM-02 · Una oferta coherente, COM-03 · Límites que siguen vigentes al vencer, COM-04 y COM-05 · Cobro y ciclo de vida, COM-06 · Autogestión, COM-07 · Producto que se puede prometer, COM-08 · Medir rentabilidad, no solo intención, COM-09 · Operación comercial, COM-10 · Salida controlada (+8 more)

### Community 79 - "Puesta en producción del piloto (F7)"
Cohesion: 0.13
Nodes (15): 10. Prueba de aceptación, 1. Dominio en Cloudflare, 2. Túnel de Cloudflare, 3. Resend (emails de login y de alertas), 4. API key de Anthropic (modo asistido), 5. Chat de Telegram para las alertas operativas, 6. Sesiones de MercadoLibre y Facebook, 7. Configuración (+7 more)

### Community 80 - "Automotive — Plan técnico del MVP"
Cohesion: 0.09
Nodes (22): 10. Backoffice y observabilidad (§45, §46), 11. Métricas y eventos (§35–38, §53), 12. Freemium (§33, §34), 14. Riesgos y decisiones abiertas, 15. Trazabilidad PRD → plan, 1. Punto de partida y gaps, 2. Arquitectura objetivo, 3. Estructura del repo (+14 more)

### Community 81 - "mercadolibre.py"
Cohesion: 0.08
Nodes (41): BeautifulSoup, json_ld(), json_ld_of_type(), multiline_text(), Any, Text with paragraph breaks kept (descriptions)., Every schema.org object in the page's JSON-LD blocks (flattening @graph)., to_int() (+33 more)

### Community 83 - "billing/page.tsx"
Cohesion: 0.19
Nodes (14): BillingPage(), metadata, checkPayment(), ownedCheckout(), startPayment(), stopSubscription(), BillingStatus(), STATUS (+6 more)

### Community 84 - "v6.py"
Cohesion: 0.30
Nodes (12): text_of(), _label_values(), _listing_id(), _parse_card(), parse_detail(), _parse_price(), parse_search(), Listing (+4 more)

### Community 85 - "test_description_intelligence.py"
Cohesion: 0.18
Nodes (15): DescriptionLLM, Read each complete description once, within a persistent daily budget., None when app_config.description_facts.llm is off or no provider is configured., answer(), read(), test_an_anticipo_cannot_become_the_cash_price(), test_cache_uses_title_description_and_analysis_version(), test_changed_description_invalidates_old_claims_even_when_new_text_has_no_facts() (+7 more)

### Community 86 - "searches/[id]/page.tsx"
Cohesion: 0.07
Nodes (42): metadata, NAMES, Dashboard(), metadata, COUNT_KEY, EMPTY, Filter, FILTERS (+34 more)

### Community 87 - "20261001120000_f4_web.sql"
Cohesion: 0.24
Nodes (7): public.dashboard_summary(), public.link_telegram(), public.match_cards, public.profiles, public.recent_opportunities(), public.search_result_counts(), public.search_results()

### Community 88 - "test_intelligence.py"
Cohesion: 0.11
Nodes (26): RedFlag, Weights, curves and thresholds of the intelligence layer (sección 6, Apéndice…, number(), Every user-facing string of the intelligence layer (§19, §24, §25). Kept in one…, One listing × one profile → everything a match row stores. Pure.…, _age_years(), description_known(), description_mismatches() (+18 more)

### Community 91 - "RuntimeError"
Cohesion: 0.18
Nodes (3): RuntimeError, Page, PersistentChromeTests

### Community 92 - "PROPUESTA_COMERCIAL.md"
Cohesion: 0.24
Nodes (4): Comprobaciones reproducibles, Ese Auto · implementación del lanzamiento comercial, Habilitación del entorno destino, Límites de esta entrega

### Community 93 - "Setup"
Cohesion: 0.18
Nodes (11): Backoffice y métricas (F6), Base de datos (Supabase), Correr el bot, Correr la web, Login de Facebook (una vez), MercadoLibre: sesion web, Migrar la base SQLite vieja, Modo asistido (LLM) (+3 more)

### Community 95 - "prompts/__init__.py"
Cohesion: 0.24
Nodes (8): catalog_text(), load(), parse_search_system(), parse_search_user(), CatalogModel, date, System prompts and user messages of the LLM layer, shared by every provider.…, One line per make: "Ford: Fiesta [S, SE, Titanium]; Focus [...]".

### Community 96 - "web/app/page.tsx"
Cohesion: 0.11
Nodes (19): BENEFITS, EXAMPLE, Landing(), STEPS, metadata, metadata, TermsPage(), Contact() (+11 more)

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

### Community 101 - "merge"
Cohesion: 0.23
Nodes (6): merge(), Values to write over `existing` and the change kinds they amount to. `incoming`…, _item(), MergeTests, Listing, _stored()

### Community 102 - "telegram.py"
Cohesion: 0.08
Nodes (29): InlineKeyboardMarkup, parse(), Inline buttons of a Telegram alert (sección 7.2): ⭐ Me interesa · ✖ Descartar.…, Channel, Notification, Protocol, The channel interface (sección 7.2): the engine never knows how an alert…, A notifications row, with the user's contact data, ready to send. (+21 more)

### Community 103 - "5. Pipeline de ingesta (§14, §15, §42)"
Cohesion: 0.25
Nodes (8): 5.1 Crawl targets, 5.2 Normalización, 5.3 Upsert, snapshots y detección de cambios, 5.4 Re-publicaciones (§15, heurística imperfecta aceptada), 5.5 Enrichment de la ficha, 5.6 Watchlist refresher (§30), 5.7 Bootstrap (evita el diluvio inicial; se conserva la idea actual), 5. Pipeline de ingesta (§14, §15, §42)

### Community 104 - "connection"
Cohesion: 0.10
Nodes (37): Postgres (Supabase) data access for the worker. Replaces the old SQLite module.…, close_pool(), connection(), AsyncConnection, Async Postgres connection pool (psycopg 3), one per worker process. The worker…, get_config(), Any, Business rules from the app_config table (Apéndice A), cached briefly so edits… (+29 more)

### Community 108 - "test_ops.py"
Cohesion: 0.15
Nodes (13): EnvFileTests, F7, punto 8: the watchdog's decisions (tools/watchdog.py), without network or…, tools/supabase_keys.py rewrites .env files in place., TransitionTests, WebCheckTests, WorkerHeartbeatTests, generate(), main() (+5 more)

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

### Community 129 - ".matches_filters"
Cohesion: 0.36
Nodes (3): Apply user filters that the source could not enforce server-side., KavakFilterTests, Listing

### Community 130 - "Description Intelligence Implementation Plan"
Cohesion: 0.29
Nodes (6): Description Intelligence Implementation Plan, Task 1: Contrato y conservación, Task 2: Análisis de todas las descripciones y caché, Task 3: Señales y preguntas, Task 4: Ficha y explicación, Task 5: Verificación y entrega

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

### Community 143 - "assess"
Cohesion: 0.18
Nodes (13): assess(), Any, datetime, PriceRef, The columns of `matches` this evaluation fills., Match, score, flags and questions whether or not it matches (explain_match)., explain(), load() (+5 more)

### Community 144 - "Descripciones como fuente de datos"
Cohesion: 0.40
Nodes (4): Datos y procedencia, Descripciones como fuente de datos, Flujo, Validación y operación

### Community 145 - "8. Capa LLM (§43, §44)"
Cohesion: 0.40
Nodes (5): 8.1 Interfaz, 8.2 `ClaudeCliProvider` (piloto), 8.3 `LocalProvider` (lanzamiento), 8.4 Flujo del modo asistido en la web, 8. Capa LLM (§43, §44)

### Community 146 - "raw_pages.py"
Cohesion: 0.24
Nodes (10): compress(), decompress(), iter_for_reparse(), mark_parsed(), purge_older_than(), raw_pages: the last detail page of each listing, compressed (normalization v3).…, Stored detail pages, oldest listing first. `below_version`: per source, only…, The stored page was read again with this parser version (tools/reprocess.py). (+2 more)

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
Nodes (9): (marca, modelo) combinations of a wizard filter: one search profile each., split_vehicles(), _canonical(), insert_profiles(), _profile_name(), AsyncConnection, Insert one search profile per (marca, modelo) of a wizard filter. Names are…, Apply an edited wizard filter to an existing alert. Keeps its matches (the… (+1 more)

### Community 184 - "simulate_alert.py"
Cohesion: 0.31
Nodes (7): process_batch(), Steps 4–5 for one batch of a target's listings: match and score them against…, main(), Simulate the arrival of a listing: what the crawl does with a new listing of a…, Returns the notifications the listing produced., simulate(), SimulatedEmail

### Community 185 - "targets.py"
Cohesion: 0.24
Nodes (9): due_targets(), enabled_sources(), finish_target(), Any, crawl_targets and the source cadence they run on (sección 5.1)., Make crawl_targets mirror `specs` (pipeline.crawl.TargetSpec): upsert the…, Active targets of enabled sources whose next_run_at has come (or never ran)., next_run_at = now + the source's interval (sección 5.1). A failed run retries… (+1 more)

### Community 200 - "_is_recent"
Cohesion: 0.38
Nodes (4): _is_recent(), Drop old listings, using first detection when publication is unknown., _is_recent reads stored listing rows (published_at is a timestamptz)., SchedulerRecencyTests

### Community 201 - "LocalProvider"
Cohesion: 0.36
Nodes (3): LocalProvider, CatalogModel, test_local_provider_is_a_stub_that_fails_fast()

### Community 202 - "ResendEmailChannelTests"
Cohesion: 0.39
Nodes (3): Request, F7, punto 7: a footer link and List-Unsubscribe one-click (RFC 8058)., ResendEmailChannelTests

### Community 203 - "run"
Cohesion: 0.33
Nodes (6): AbstractEventLoop, Any, T, Entry-point helper: run the worker's coroutines on a loop psycopg supports.…, run(), selector_loop()

### Community 204 - "IA sobre descripciones"
Cohesion: 0.33
Nodes (5): Activación y reproceso, Comportamiento, IA sobre descripciones, Presupuesto y caché, Verificación

### Community 205 - "heartbeat.py"
Cohesion: 0.60
Nodes (4): beat(), datetime, The worker's heartbeat (F7, punto 8): one row in worker_heartbeat, updated…, started_now()

### Community 206 - "open_pool"
Cohesion: 0.67
Nodes (3): AsyncConnectionPool, open_pool(), Open the process-wide pool (idempotent).

## Knowledge Gaps
- **533 isolated node(s):** `public.vehicle_catalog`, `public.pipeline_errors`, `public.app_config`, `public.geocode_cache`, `public.fx_rates` (+528 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **34 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `PostgresTestCase` connect `Listing` to `scraper_cli.py`, `test_ingest_postgres.py`, `.listing`, `BaseScraper`, `WebChannel`, `CommercialTests`, `migrate_sqlite.py`, `QueueTests`, `notifications.py`, `MercadoPagoTests`, `scheduler.py`, `LLMProvider`, `AvailabilityTests`, `platform_health.py`?**
  _High betweenness centrality (0.034) - this node is a cross-community bridge._
- **Why does `Listing` connect `Listing` to `.matches_filters`, `test_ingest_postgres.py`, `BaseScraper`, `merge`, `Target`, `AutoCosmosScraper`, `WebChannel`, `geo.py`, `migrate_sqlite.py`, `Page`, `ingest.py`, `CatalogModel`, `mercadolibre.py`, `v6.py`, `test_description_intelligence.py`, `facebook.py`, `listing.py`?**
  _High betweenness centrality (0.032) - this node is a cross-community bridge._
- **Why does `Links` connect `Links` to `TemplateSnapshotTests`, `test_ingest_postgres.py`, `BaseScraper`, `templates.py`, `telegram.py`, `WebChannel`, `Notifier`, `ResendEmailChannelTests`, `PRDCopyTests`, `TelegramChannel`?**
  _High betweenness centrality (0.017) - this node is a cross-community bridge._
- **Are the 42 inferred relationships involving `Links` (e.g. with `ResendEmailChannel` and `TelegramChannel`) actually correct?**
  _`Links` has 42 INFERRED edges - model-reasoned connections that need verification._
- **Are the 36 inferred relationships involving `Listing` (e.g. with `AutoCosmosScraper` and `Page`) actually correct?**
  _`Listing` has 36 INFERRED edges - model-reasoned connections that need verification._
- **What connects `public.vehicle_catalog`, `public.pipeline_errors`, `public.app_config` to the rest of the system?**
  _533 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Links` be split into smaller, more focused modules?**
  _Cohesion score 0.09042553191489362 - nodes in this community are weakly interconnected._
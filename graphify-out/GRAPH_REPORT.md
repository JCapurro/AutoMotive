# Graph Report - AutoMotive  (2026-10-02)

## Corpus Check
- 353 files · ~300,136 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 3226 nodes · 8246 edges · 186 communities (165 shown, 21 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 479 edges (avg confidence: 0.53)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- templates.py
- description_facts.py
- Event
- pro.ts
- listing-actions.tsx
- createAdminClient
- service.py
- targets.py
- WebChannel
- Links
- inspector.tsx
- ListingFacts
- test_llm_jobs_postgres.py
- connection
- database.ts
- ingest.py
- CatalogModel
- settings/page.tsx
- enrich.py
- test_ingest_postgres.py
- search-form.tsx
- db.ts
- facebook.py
- listing.py
- fiesta_listing
- LLMProvider
- test_llm_drafts.py
- watchdog.py
- format.ts
- web/app/page.tsx
- PRD — Automotive
- searches/[id]/page.tsx
- scraper_cli.py
- db/__init__.py
- test_llm_claude_cli.py
- [notificationId]/route.ts
- listings.py
- matching.py
- test_intelligence.py
- Listing
- pipeline/scoring.py
- geo.py
- migrate_sqlite.py
- 20260927120000_core_schema.sql
- test_parsers.py
- devDependencies
- dependencies
- compilerOptions
- crawl.py
- IntelligenceConfig
- transmission.py
- PriceRef
- test_handlers.py
- mercadopago-server.ts
- 20261007120000_ese_auto_commercial.sql
- server.ts
- test_db_postgres.py
- TelegramChannel
- 20261003120000_f6_backoffice_metrics.sql
- SourceAlerts
- components.json
- 20260927120100_rls.sql
- resolve_price
- app/listings/[id]/page.tsx
- matches.py
- .listing
- ClaudeCliProvider
- Site
- startup_warnings
- Notifier
- auth.ts
- createClient
- normalize_text
- CommercialTests
- Ese Auto · propuesta comercial y proyección
- reprocess.py
- red_flags.py
- Comunes a cualquier ruta
- Puesta en producción del piloto (F7)
- Automotive — Plan técnico del MVP
- .search
- MercadoPagoTests
- rescore.py
- v6.py
- test_llm_anthropic_api.py
- pgcase.py
- 20261001120000_f4_web.sql
- admin/actions.ts
- metrics/page.tsx
- autocosmos.py
- pool.py
- Setup
- prompts/__init__.py
- intelligence/engine.py
- 13. Roadmap por fases
- scripts
- 40. Modelo conceptual de datos
- toggle-group.tsx
- AutoMotive
- PRDCopyTests
- 5. Pipeline de ingesta (§14, §15, §42)
- MigrateSqliteTests
- web/app/layout.tsx
- RedFlagTests
- ResendEmailChannelTests
- 6. Intelligence (§16–20, §24, §25, §44)
- 4. Modelo de datos (Postgres / Supabase)
- test_db.py
- 47. Riesgos principales
- 58. Definición final del producto
- 8. Capa LLM (§43, §44)
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
- Ese Auto · backlog comercial
- Automotive — web
- 16. Matching Engine
- 23. Página de resultado
- 33. Freemium inicial
- 36. Métricas de activación
- 20260930120000_f3_notifications.sql
- opengraph-image.tsx
- 6. Proyección a seis meses
- 34. Alternativa de pricing
- 35. Métricas principales
- 38. Métricas de outcome
- 49. MVP final recomendado
- 7. Público objetivo
- 8. Persona principal
- 9. Persona secundaria futura
- sonner
- 20261005120000_f7_ops.sql
- AGENTS.md
- eslint.config.mjs
- next.config.ts
- postcss.config.mjs
- FakeSource
- automotive-worker
- 20261008120000_mercadopago.sql
- .from_app_config
- Mercado Pago · cobro y acceso automático
- Ese Auto · implementación del lanzamiento comercial
- 7. Motor de notificaciones (§21, §22, §32, §47)
- vercel.json

## God Nodes (most connected - your core abstractions)
1. `Links` - 88 edges
2. `Listing` - 72 edges
3. `createClient()` - 71 edges
4. `connection()` - 70 edges
5. `PRD — Automotive` - 59 edges
6. `requireUser()` - 55 edges
7. `Page` - 48 edges
8. `createAdminClient()` - 47 edges
9. `PostgresTestCase` - 45 edges
10. `Notifier` - 44 edges

## Surprising Connections (you probably didn't know these)
- `DigestItem` --uses--> `Links`  [INFERRED]
  worker/notifications/templates.py → worker/notifications/links.py
- `AdminLayout()` --calls--> `requireAdmin()`  [EXTRACTED]
  web/app/admin/layout.tsx → web/lib/admin.ts
- `PurchasedBanner()` --calls--> `answerInfluence()`  [EXTRACTED]
  web/components/app/listing-actions.tsx → web/app/app/listings/actions.ts
- `LoginPage()` --calls--> `safeNext()`  [EXTRACTED]
  web/app/login/page.tsx → web/lib/navigation.ts
- `EXAMPLE` --calls--> `money()`  [EXTRACTED]
  web/app/page.tsx → web/lib/format.ts

## Import Cycles
- None detected.

## Communities (186 total, 21 thin omitted)

### Community 0 - "templates.py"
Cohesion: 0.07
Nodes (42): parse(), Inline buttons of a Telegram alert (sección 7.2): ⭐ Me interesa · ✖ Descartar.…, Channel, Notification, Protocol, The channel interface (sección 7.2): the engine never knows how an alert…, A notifications row, with the user's contact data, ready to send., SendResult (+34 more)

### Community 1 - "description_facts.py"
Cohesion: 0.07
Nodes (37): _after_label(), Amount, _amounts(), _before_label(), _close(), _currency(), DescriptionFacts, _distinct() (+29 more)

### Community 2 - "Event"
Cohesion: 0.10
Nodes (28): at_least(), level_for(), rank(), Opportunity levels (§20, sección 6.4), thresholds from…, 🔥 high ≥ 85 · 🟢 good ≥ 70 · 🟡 match ≥ 50 · ⚪ low. `cap` is the highest level…, Audience, classify(), decide() (+20 more)

### Community 3 - "pro.ts"
Cohesion: 0.11
Nodes (36): confirmPayment(), launchCommercialPilot(), recordRefund(), joinWaitlist(), checkPayment(), ownedCheckout(), startPayment(), stopSubscription() (+28 more)

### Community 4 - "listing-actions.tsx"
Cohesion: 0.15
Nodes (19): Props, PurchasedBanner(), PurchaseDialog(), TODAY(), Button(), buttonVariants, Dialog(), DialogClose() (+11 more)

### Community 5 - "createAdminClient"
Cohesion: 0.11
Nodes (38): BillingPage(), metadata, ConfigPage(), HINTS, metadata, metadata, escapeLike(), metadata (+30 more)

### Community 6 - "service.py"
Cohesion: 0.14
Nodes (24): build_items(), Any, datetime, Daily digest (§32, sección 7.2). Every day at app_config.digest_hour (ART,…, Digest items from waiting rows and the day's top matches: waiting rows always…, Build today's digests. Returns how many were created (then delivered)., run_digest(), deliverable() (+16 more)

### Community 7 - "targets.py"
Cohesion: 0.24
Nodes (9): due_targets(), enabled_sources(), finish_target(), Any, crawl_targets and the source cadence they run on (sección 5.1)., Make crawl_targets mirror `specs` (pipeline.crawl.TargetSpec): upsert the…, Active targets of enabled sources whose next_run_at has come (or never ran)., next_run_at = now + the source's interval (sección 5.1). A failed run retries… (+1 more)

### Community 8 - "WebChannel"
Cohesion: 0.14
Nodes (16): ResendEmailChannel, WebChannel, MatchCandidate, A new, non-backfill match the crawl just stored., ListingEvent, AlertTypesTests, DailyCapAndDigestTests, DedupeTests (+8 more)

### Community 9 - "Links"
Cohesion: 0.07
Nodes (36): CallbackQueryHandler, InlineKeyboardMarkup, Update, _allowed(), help_(), invalid_code_text(), linked_text(), The Telegram bot after F4: it links the account and answers alert buttons.… (+28 more)

### Community 10 - "inspector.tsx"
Cohesion: 0.10
Nodes (25): CASCADE, Inspector(), LEVEL_RANK, STATUS_TONE, LevelBadge(), STATUS_STYLE, StatusBadge(), COMPARABLE_LEVEL (+17 more)

### Community 11 - "ListingFacts"
Cohesion: 0.13
Nodes (24): AsyncAnthropic, AnthropicApiProvider, CatalogModel, M, The Claude API with an API key (F7, punto 6): the provider for serving the…, `claude -p` as the pilot's LLM (sección 8.2). claude -p --output-format json…, The LLM layer (sección 8): providers behind one interface. provider.py…, LocalProvider (+16 more)

### Community 12 - "test_llm_jobs_postgres.py"
Cohesion: 0.16
Nodes (6): LlmJobsCase, QueueTests, The llm_jobs queue against the local Supabase Postgres (sección 8.4): what the…, What the web can do with the user's session (sección 4.4)., Run `sql` as the signed-in web user (role authenticated, RLS on)., WebAccessTests

### Community 13 - "connection"
Cohesion: 0.08
Nodes (44): connection(), AsyncConnection, get_geocode_cache(), has_fresh_geocode_failure(), Cache that this query failed to geocode, so we don't keep retrying., True if the query was tried and failed within the past `max_age_days`., set_geocode_cache(), set_geocode_cache_failure() (+36 more)

### Community 14 - "database.ts"
Cohesion: 0.10
Nodes (22): MatchInspector(), metadata, NotificationInspector(), context(), Inspection, inspectMatch(), inspectNotification(), ListingRow (+14 more)

### Community 15 - "ingest.py"
Cohesion: 0.14
Nodes (27): _empty(), _facts(), _geocode_rows(), ingest_rows(), IngestConfig, normalize_items(), _on_insert(), _on_update() (+19 more)

### Community 16 - "CatalogModel"
Cohesion: 0.16
Nodes (18): normalize_brand(), _best_by_name(), _brands_in(), CatalogModel, _finish(), _fuzzy(), _has_phrase(), _pick() (+10 more)

### Community 17 - "settings/page.tsx"
Cohesion: 0.13
Nodes (18): RFC-8058, POST(), declineRenewal(), metadata, unsubscribe(), metadata, UnsubscribePage(), LoginPage() (+10 more)

### Community 18 - "enrich.py"
Cohesion: 0.13
Nodes (27): Refresher, mark_detail_checked(), DescriptionLLM, drain(), enrich_pass(), ingest_detail(), Any, Listing (+19 more)

### Community 19 - "test_ingest_postgres.py"
Cohesion: 0.10
Nodes (24): RuntimeError, ListingDetail, What fetch_detail() found at a listing's URL (sección 5.5). `gone` means the…, ingest(), normalize → geocode → upsert. The whole batch is one transaction., PostgresTestCase, Opens the worker pool on TEST_DATABASE_URL over a clean slate., CanonicalUpsertTests (+16 more)

### Community 20 - "search-form.tsx"
Cohesion: 0.05
Nodes (66): loadFormData(), EditSearchPage(), metadata, metadata, AssistedSearch(), FALLBACK_TITLE, JobRow, Origin (+58 more)

### Community 21 - "db.ts"
Cohesion: 0.11
Nodes (25): SEARCH_FILTERS, alertedUser(), signIn(), ask(), setHeartbeat(), signIn(), globalSetup(), main() (+17 more)

### Community 22 - "facebook.py"
Cohesion: 0.10
Nodes (29): parse_relative_date(), Parse Spanish relative date strings shown by AR car classifieds. Examples…, Return a unix timestamp inferred from a Spanish relative-date string., _strip_accents(), _after_colon(), _city_slug(), _city_slug_from_origin(), _extract_location() (+21 more)

### Community 23 - "listing.py"
Cohesion: 0.09
Nodes (27): NamedTuple, FxQuote, attrs_hash(), fingerprint(), _hash(), listing_facts(), normalize_listing(), price_usd() (+19 more)

### Community 24 - "fiesta_listing"
Cohesion: 0.14
Nodes (14): evaluate(), match(), The reasons if every hard filter is ok or unknown; None if one fails., CurrencyTests, fiesta_listing(), fiesta_profile(), GoldenFixtureTests, GuardAndLevelTests (+6 more)

### Community 25 - "LLMProvider"
Cohesion: 0.08
Nodes (34): claim(), expire(), finish(), Any, AsyncConnection, llm_jobs: the queue between the web and the LLM layer (sección 8.4). The web…, The oldest queued job of `kinds`, now 'running'; None if there is none., done' with its output, or 'failed' with the error (never both). (+26 more)

### Community 26 - "test_llm_drafts.py"
Cohesion: 0.12
Nodes (32): _km(), _money(), normalize_draft(), normalize_drafts(), _positive(), Any, CatalogModel, date (+24 more)

### Community 27 - "watchdog.py"
Cohesion: 0.09
Nodes (30): timedelta, beat(), last_beat(), datetime, The worker's heartbeat (F7, punto 8): one row in worker_heartbeat, updated…, started_now(), EnvFileTests, F7, punto 8: the watchdog's decisions (tools/watchdog.py), without network or… (+22 more)

### Community 28 - "format.ts"
Cohesion: 0.10
Nodes (39): AdminListingPage(), ListingsPage(), DIGEST_SECTION, DigestItem, InboxPage(), metadata, WebPayload, ListingPage() (+31 more)

### Community 29 - "web/app/page.tsx"
Cohesion: 0.09
Nodes (17): AdminLayout(), metadata, BENEFITS, EXAMPLE, Landing(), STEPS, metadata, metadata (+9 more)

### Community 30 - "PRD — Automotive"
Cohesion: 0.05
Nodes (37): 11. Principios de producto, 13. Concepto de Search Profile, 14. Ingesta de publicaciones, 17. Opportunity Score, 18. Componentes iniciales del Opportunity Score, 19. Price Intelligence, 1. Resumen ejecutivo, 20. Niveles de oportunidad (+29 more)

### Community 31 - "searches/[id]/page.tsx"
Cohesion: 0.10
Nodes (28): Dashboard(), metadata, reportVisibleResults(), trackProCta(), COUNT_KEY, EMPTY, Filter, FILTERS (+20 more)

### Community 32 - "scraper_cli.py"
Cohesion: 0.10
Nodes (26): shutdown(), _collector_loop(), AbstractEventLoop, Any, T, Run collector coroutines on an event loop that can start subprocesses.…, run_collector(), USD/ARS rate fetcher with TTL cache. For pricing used cars in AR, the "blue"… (+18 more)

### Community 33 - "db/__init__.py"
Cohesion: 0.10
Nodes (33): Postgres (Supabase) data access for the worker. Replaces the old SQLite module.…, (marca, modelo) combinations of a wizard filter: one search profile each., split_vehicles(), alerts_for_target(), _canonical(), create_alert(), delete_alert(), enabled_profiles() (+25 more)

### Community 34 - "test_llm_claude_cli.py"
Cohesion: 0.12
Nodes (32): BaseModel, parse_envelope(), Any, Run the CLI once and return its stdout. Raises LLMTimeout / LLMError., The structured answer inside `--output-format json`'s envelope., run_cli(), json_schema(), Any (+24 more)

### Community 35 - "[notificationId]/route.ts"
Cohesion: 0.33
Nodes (10): GET(), handle(), HEAD(), peek(), Row, track(), ClickTarget, destination() (+2 more)

### Community 36 - "listings.py"
Cohesion: 0.09
Nodes (34): enrichment_queue(), find_repost_of(), insert_listing(), insert_snapshot(), lock_existing(), mark_gone(), matched_recheck_queue(), _param() (+26 more)

### Community 37 - "matching.py"
Cohesion: 0.15
Nodes (24): Result, _choice(), distance_km(), evaluate(), filter_currency(), _km(), _location(), _model() (+16 more)

### Community 38 - "test_intelligence.py"
Cohesion: 0.24
Nodes (9): RedFlag, Any, datetime, question_keys(), Questions for the seller (§25, sección 6.6). Deterministic templates. Always:…, One message ready to copy: "Hola, ¿cómo estás? ¿Lo seguís teniendo? …"., seller_questions(), F2 intelligence, pure (docs/TECHNICAL_PLAN.md, sección 6): no network, no… (+1 more)

### Community 39 - "Listing"
Cohesion: 0.09
Nodes (23): BaseScraper, CollectorBlocked, Listing, Run keyword detection over the title and tag the listing. Statistical detection…, One ad as a collector read it, before normalization. `marca`/`modelo`/`version`…, Apply user filters that the source could not enforce server-side., The source answered with a login wall, a security challenge or no session. The…, Download the ad's own page, with the source's login-wall and session checks,… (+15 more)

### Community 40 - "pipeline/scoring.py"
Cohesion: 0.14
Nodes (14): Weights, curves and thresholds of the intelligence layer (sección 6, Apéndice…, Any, datetime, The I/O around intelligence/: rows, comparables, fx and config in; matches out.…, Load the rows and comparables of these listings (once each)., Scorer, F2 intelligence against the local Supabase Postgres (docs/TECHNICAL_PLAN.md,…, explain() (+6 more)

### Community 41 - "geo.py"
Cohesion: 0.12
Nodes (20): Coords, _fallback_can_stand_alone(), filter_listings_by_radius(), geocode_location(), _geocode_nominatim(), haversine_km(), _looks_like_non_location_query(), _lookup_known_location() (+12 more)

### Community 42 - "migrate_sqlite.py"
Cohesion: 0.15
Nodes (13): Row, connection_kwargs(), Any, ensure_telegram_profile(), LoadEmailsTests, load_emails(), main(), Migration (+5 more)

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

### Community 48 - "crawl.py"
Cohesion: 0.14
Nodes (22): crawl_due(), derive_targets(), Any, BatchHandler, HealthHandler, SourceHealth, Crawl targets and their cadence (sección 5.1). Each tick `crawl_targets` is re-…, A target's query in the collectors' filter vocabulary. (+14 more)

### Community 49 - "IntelligenceConfig"
Cohesion: 0.23
Nodes (21): diff_pct(), How far below the median the published price is, in % (negative = above)., IntelligenceConfig, age_hours(), clamp(), completeness_component(), completeness_fields(), Component (+13 more)

### Community 50 - "transmission.py"
Cohesion: 0.25
Nodes (8): _classify(), fuel(), Transmission and fuel from free text (sección 5.2, paso 2). Sources rarely…, manual' | 'automatic' | None, from the first text that settles it. Pass the…, Canonical fuel ('nafta', 'diesel', 'gnc', 'hibrido', 'electrico') or None,…, private' | 'dealer' | None., seller_type(), transmission()

### Community 51 - "PriceRef"
Cohesion: 0.15
Nodes (14): AST, fetch(), PriceRef, Any, Price Intelligence (§19, sección 6.2). The statistics come from the SQL…, public.comparables() for one listing. `cfg` overrides app_config.comparables., CopyLintTests, _docstring_nodes() (+6 more)

### Community 52 - "test_handlers.py"
Cohesion: 0.13
Nodes (14): patch, start(), _is_recent(), Drop listings published more than `max_age_days` ago. If the source doesn't say…, _ctx(), _FakeChat, _FakeMessage, _FakeUpdate (+6 more)

### Community 53 - "mercadopago-server.ts"
Cohesion: 0.15
Nodes (29): GET(), POST(), checkoutUrl(), paymentPeriod(), sameSecret(), api(), applyPayment(), BillingCheckout (+21 more)

### Community 54 - "20261007120000_ese_auto_commercial.sql"
Cohesion: 0.09
Nodes (8): llm_jobs_guard_commercial, matches_guard_commercial, public.commercial_payments, public.guard_assisted_commercial_access(), public.guard_match_access(), public.plan_limits_for(), public.profiles, public.refund_commercial_payment()

### Community 55 - "server.ts"
Cohesion: 0.20
Nodes (15): GET(), GET(), POST(), Email, LoginState, sendMagicLink(), siteUrl(), verifyCode() (+7 more)

### Community 56 - "test_db_postgres.py"
Cohesion: 0.13
Nodes (8): AlertRepoTests, GeocodeAndConfigTests, _listing(), The bot's data layer against a real Postgres with the supabase/ migrations. Run…, /start <code> (public.link_telegram, F4)., SeenMatchesTests, store(), TelegramLinkTests

### Community 57 - "TelegramChannel"
Cohesion: 0.15
Nodes (9): Any, datetime, Notification, TelegramChannel, CallbackDataTests, FakeBot, Exception, TelegramChannelTests (+1 more)

### Community 58 - "20261003120000_f6_backoffice_metrics.sql"
Cohesion: 0.10
Nodes (16): pro_waitlist_set_updated_at, public.admin_notification_daily, public.admin_score_histogram, public.admin_searches, public.admin_source_health, public.admin_users, public.join_waitlist(), public.pro_waitlist (+8 more)

### Community 59 - "SourceAlerts"
Cohesion: 0.10
Nodes (24): finish_run(), Observability (sección 10, §46): collector_runs, pipeline_errors and source…, A source's failure streak after a run (the admin alert reads it)., Close a run and keep the source's health counters in step. Returns the source's…, SourceHealth, start_run(), failing_text(), last_error_line() (+16 more)

### Community 60 - "components.json"
Cohesion: 0.09
Nodes (21): aliases, components, hooks, lib, ui, utils, iconLibrary, menuAccent (+13 more)

### Community 61 - "20260927120100_rls.sql"
Cohesion: 0.10
Nodes (20): public.app_config, public.collector_runs, public.crawl_targets, public.enforce_plan_limits(), public.events, public.fx_rates, public.geocode_cache, public.listing_snapshots (+12 more)

### Community 62 - "resolve_price"
Cohesion: 0.15
Nodes (7): PriceResolution, What resolve_price() concluded, stored in description_facts.price_check. The…, The listing's effective price (sección 5.2, v3). `published`/`currency`: the…, resolve_price(), _usd(), _resolve(), ResolvePriceTests

### Community 63 - "app/listings/[id]/page.tsx"
Cohesion: 0.08
Nodes (25): markFor(), metadata, plain(), priceHistory(), SAME, SCORE_PART, ScoreInWords(), Similar (+17 more)

### Community 64 - "matches.py"
Cohesion: 0.17
Nodes (19): _existing(), filter_unseen(), insert_legacy_matches(), _keys(), mark_seen(), matched_by_other_profiles(), matches_of_listings(), Any (+11 more)

### Community 65 - ".listing"
Cohesion: 0.22
Nodes (6): ComparablesCascadeTests, IntelligenceCase, PriceRef, Insert a listing row directly: comparables are about stored columns., Sección 6.2: trim+transmission → transmission → model, first with n ≥ min_n., ScoredMatchesTests

### Community 66 - "ClaudeCliProvider"
Cohesion: 0.11
Nodes (19): fixture, Runner, ClaudeCliProvider, CatalogModel, M, load_recordings(), Any, Path (+11 more)

### Community 67 - "Site"
Cohesion: 0.20
Nodes (10): range, AutoCosmosSearchTests, card(), page(), Request, Response, AutoCosmos search: every page of the model, `?pidx=N`, retried on 503 (no…, Serves `pages[pidx]`; `fail[pidx]` is a list of statuses (or exceptions) to… (+2 more)

### Community 68 - "startup_warnings"
Cohesion: 0.14
Nodes (10): What this configuration leaves off (F7, punto 5): one line per channel, metric…, startup_warnings(), _database(), db_test_skip_reason(), Why the DB tests can't run here, or None. They TRUNCATE tables, so they only…, ConfigTests, F7, punto 4: the DB tests TRUNCATE, so they never touch the pilot's database., F7, punto 5: every channel or metric the .env leaves off is logged at startup. (+2 more)

### Community 69 - "Notifier"
Cohesion: 0.07
Nodes (42): AbstractEventLoop, Any, T, Entry-point helper: run the worker's coroutines on a loop psycopg supports.…, run(), selector_loop(), log_error(), Record a pipeline error. Never raises: observability must not break the… (+34 more)

### Community 70 - "auth.ts"
Cohesion: 0.13
Nodes (18): markOpened(), active(), BottomNav(), ITEMS, MobileInboxLink(), TopNav(), Inbox, InboxContext (+10 more)

### Community 71 - "createClient"
Cohesion: 0.10
Nodes (48): AppLayout(), answerInfluence(), currentStatus(), markSeen(), Purchase, recordPurchase(), setDiscardReason(), setSaved() (+40 more)

### Community 72 - "normalize_text"
Cohesion: 0.09
Nodes (23): _put(), Any, Translate between the Telegram wizard's filter dict and search_profiles. The…, Wizard dict + one (make, model) → search_profiles column values., search_profiles column values → the wizard dict the scheduler and handlers…, to_legacy(), to_profile(), load_models() (+15 more)

### Community 74 - "Ese Auto · propuesta comercial y proyección"
Cohesion: 0.22
Nodes (9): 1. Qué vender, 2. Qué ya existe y qué falta, 3. Referencias de mercado, 4. Alternativas iniciales conservadas como referencia, 5. Oferta seleccionada en pesos: B, 7. Validación y salida comercial, 8. Decisión a registrar, Ese Auto · propuesta comercial y proyección (+1 more)

### Community 76 - "reprocess.py"
Cohesion: 0.11
Nodes (23): AsyncConnection, date, quote_for_today(), fx_rates: the day's USD/ARS quote, frozen so price_usd can be reproduced…, The quote stored for today (blue, else oficial), fetching and storing it on…, today_ar(), llm_facts_last_day(), Descriptions the LLM read in the last 24 h… (+15 more)

### Community 77 - "red_flags.py"
Cohesion: 0.20
Nodes (15): ago(), money(), number(), Every user-facing string of the intelligence layer (§19, §24, §25). Kept in one…, USD 10.300 · ARS 12.500.000 (Argentine thousands separator)., _age_years(), description_known(), description_mismatches() (+7 more)

### Community 78 - "Comunes a cualquier ruta"
Cohesion: 0.22
Nodes (9): COM-02 · Una oferta coherente, COM-03 · Límites que siguen vigentes al vencer, COM-04 y COM-05 · Cobro y ciclo de vida, COM-06 · Autogestión, COM-07 · Producto que se puede prometer, COM-08 · Medir rentabilidad, no solo intención, COM-09 · Operación comercial, COM-10 · Salida controlada (+1 more)

### Community 79 - "Puesta en producción del piloto (F7)"
Cohesion: 0.13
Nodes (15): 10. Prueba de aceptación, 1. Dominio en Cloudflare, 2. Túnel de Cloudflare, 3. Resend (emails de login y de alertas), 4. API key de Anthropic (modo asistido), 5. Chat de Telegram para las alertas operativas, 6. Sesiones de MercadoLibre y Facebook, 7. Configuración (+7 more)

### Community 80 - "Automotive — Plan técnico del MVP"
Cohesion: 0.18
Nodes (11): 10. Backoffice y observabilidad (§45, §46), 11. Métricas y eventos (§35–38, §53), 12. Freemium (§33, §34), 14. Riesgos y decisiones abiertas, 15. Trazabilidad PRD → plan, 1. Punto de partida y gaps, 2. Arquitectura objetivo, 3. Estructura del repo (+3 more)

### Community 81 - ".search"
Cohesion: 0.15
Nodes (15): _browser_storage_state(), _build_url(), _extract_id(), _looks_like_login_wall(), _page_looks_like_login_wall(), _parse_card(), parse_search(), Listing (+7 more)

### Community 83 - "rescore.py"
Cohesion: 0.18
Nodes (16): purge_older_than(), nightly_loop(), Any, datetime, Re-scoring existing matches (sección 6.1). * After enrichment: transmission or…, Re-score (search_profile_id, listing_id) pairs. Returns rows updated., Seconds from `now` to the next `hour` ("HH:MM", ART)., Re-score matches once a night, then purge stale listings; also, once at… (+8 more)

### Community 84 - "v6.py"
Cohesion: 0.09
Nodes (45): BeautifulSoup, Browser, BrowserContext, browser_context(), _ensure_browser(), Shared Playwright helpers — reuse a single browser instance across scrapers., Yield a fresh browser context. Closes context on exit; browser is reused., dedupe() (+37 more)

### Community 85 - "test_llm_anthropic_api.py"
Cohesion: 0.13
Nodes (24): skipif, _items(), CatalogModel, vehicle_catalog as supabase/seed.sql inserts it, without a database. The LLM…, seed_catalog(), _year(), message(), provider() (+16 more)

### Community 86 - "pgcase.py"
Cohesion: 0.20
Nodes (6): get_config(), Any, Business rules from the app_config table (Apéndice A), cached briefly so edits…, Helpers for tests that need Postgres (see conftest.py for the event loop)., Commercial access and payment boundaries against an isolated local database., Real isolated PostgreSQL checks for automatic access and hostile/repeated money…

### Community 87 - "20261001120000_f4_web.sql"
Cohesion: 0.24
Nodes (7): public.dashboard_summary(), public.link_telegram(), public.match_cards, public.profiles, public.recent_opportunities(), public.search_result_counts(), public.search_results()

### Community 88 - "admin/actions.ts"
Cohesion: 0.23
Nodes (10): ActionResult, shape(), SourceInput, updateConfig(), updateSource(), ConfigEditor(), SourceForm(), Textarea() (+2 more)

### Community 89 - "metrics/page.tsx"
Cohesion: 0.11
Nodes (29): ErrorsPage(), metadata, CTA_EVENTS, day(), levelLabel(), median(), metadata, MetricsPage() (+21 more)

### Community 90 - "autocosmos.py"
Cohesion: 0.23
Nodes (10): AutoCosmosScraper, _price(), AsyncClient, Listing, Response, AutoCosmos AR scraper. AutoCosmos exposes a public listings page at…, GET, retried on a network error or a 5xx; the last answer or error wins., (price, currency, partial reason) from the price blocks of a card or detail. A… (+2 more)

### Community 91 - "pool.py"
Cohesion: 0.15
Nodes (14): AsyncConnectionPool, close_pool(), open_pool(), Async Postgres connection pool (psycopg 3), one per worker process. The worker…, Open the process-wide pool (idempotent)., compress(), decompress(), iter_for_reparse() (+6 more)

### Community 93 - "Setup"
Cohesion: 0.18
Nodes (11): Backoffice y métricas (F6), Base de datos (Supabase), Correr el bot, Correr la web, Login de Facebook (una vez), MercadoLibre: sesion web, Migrar la base SQLite vieja, Modo asistido (LLM) (+3 more)

### Community 95 - "prompts/__init__.py"
Cohesion: 0.24
Nodes (8): catalog_text(), load(), parse_search_system(), parse_search_user(), CatalogModel, date, System prompts and user messages of the LLM layer, shared by every provider.…, One line per make: "Ford: Fiesta [S, SE, Titanium]; Focus [...]".

### Community 96 - "intelligence/engine.py"
Cohesion: 0.17
Nodes (9): assess(), Evaluation, Any, datetime, PriceRef, One listing × one profile → everything a match row stores. Pure.…, The columns of `matches` this evaluation fills., Match, score, flags and questions whether or not it matches (explain_match). (+1 more)

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

### Community 101 - "AutoMotive"
Cohesion: 0.22
Nodes (9): Agregar una nueva fuente, AutoMotive, Comandos del bot, Cómo funciona, Estructura, Fuentes, Limitaciones, Matching y Opportunity Score (+1 more)

### Community 102 - "PRDCopyTests"
Cohesion: 0.24
Nodes (3): notification(), PRDCopyTests, The §22 lines, in order, at the top of the Telegram message and the email text.

### Community 103 - "5. Pipeline de ingesta (§14, §15, §42)"
Cohesion: 0.25
Nodes (8): 5.1 Crawl targets, 5.2 Normalización, 5.3 Upsert, snapshots y detección de cambios, 5.4 Re-publicaciones (§15, heurística imperfecta aceptada), 5.5 Enrichment de la ficha, 5.6 Watchlist refresher (§30), 5.7 Bootstrap (evita el diluvio inicial; se conserva la idea actual), 5. Pipeline de ingesta (§14, §15, §42)

### Community 104 - "MigrateSqliteTests"
Cohesion: 0.36
Nodes (3): _make_sqlite(), MigrateSqliteTests, Path

### Community 105 - "web/app/layout.tsx"
Cohesion: 0.29
Nodes (5): metadata, mono, sans, viewport, Toaster()

### Community 107 - "ResendEmailChannelTests"
Cohesion: 0.39
Nodes (3): Request, F7, punto 7: a footer link and List-Unsubscribe one-click (RFC 8058)., ResendEmailChannelTests

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

### Community 113 - "8. Capa LLM (§43, §44)"
Cohesion: 0.40
Nodes (5): 8.1 Interfaz, 8.2 `ClaudeCliProvider` (piloto), 8.3 `LocalProvider` (lanzamiento), 8.4 Flujo del modo asistido en la web, 8. Capa LLM (§43, §44)

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

### Community 129 - "Ese Auto · backlog comercial"
Cohesion: 0.29
Nodes (7): Ese Auto · backlog comercial, Estado de implementación al 2/10/2026, Módulos según la elección, Registro de decisión, Regla de alcance, Reserva: implementar solo con demanda demostrada, Secuencia de ejecución seleccionada: B

### Community 130 - "Automotive — web"
Cohesion: 0.40
Nodes (4): Automotive — web, Correrla, Rutas (plan técnico, sección 9), Tests

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

### Community 139 - "6. Proyección a seis meses"
Cohesion: 0.29
Nodes (7): 6. Proyección a seis meses, Comparación inicial A/B/C en USD · archivada, no vigente, Cuántas cuentas Agencia hacen falta para un ingreso objetivo · ARS, Evolución del escenario base B · ARS, Resultado mensual en mes 6, ruta B · ARS, Sensibilidad al costo en dólares, base mes 6, Supuestos de B

### Community 160 - "FakeSource"
Cohesion: 0.33
Nodes (3): FakeSource, Listing, Stands in for a collector: returns `results[name]`, serves `details[url]` (an…

### Community 180 - "20261008120000_mercadopago.sql"
Cohesion: 0.39
Nodes (5): profiles_guard_billing_delete, public.apply_mercadopago_payment(), public.billing_checkouts, public.commercial_payments, public.guard_billing_account_delete()

### Community 181 - ".from_app_config"
Cohesion: 0.50
Nodes (3): _merge(), Any, ConfigTests

### Community 182 - "Mercado Pago · cobro y acceso automático"
Cohesion: 0.33
Nodes (6): Configuración pendiente del entorno destino, Estado verificado con el MCP · 2/10/2026, Implementación, Mercado Pago · cobro y acceso automático, Operación y casos de revisión, Pasos en Mercado Pago y Vercel

### Community 183 - "Ese Auto · implementación del lanzamiento comercial"
Cohesion: 0.50
Nodes (4): Comprobaciones reproducibles, Ese Auto · implementación del lanzamiento comercial, Habilitación del entorno destino, Límites de esta entrega

### Community 184 - "7. Motor de notificaciones (§21, §22, §32, §47)"
Cohesion: 0.50
Nodes (4): 7.1 Decisión, 7.2 Canales, 7.3 Tracking de aperturas y clics, 7. Motor de notificaciones (§21, §22, §32, §47)

## Knowledge Gaps
- **472 isolated node(s):** `public.vehicle_catalog`, `public.pipeline_errors`, `public.app_config`, `public.geocode_cache`, `public.fx_rates` (+467 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **21 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Listing` connect `Listing` to `FakeSource`, `WebChannel`, `geo.py`, `migrate_sqlite.py`, `ingest.py`, `crawl.py`, `.search`, `enrich.py`, `test_ingest_postgres.py`, `v6.py`, `CatalogModel`, `facebook.py`, `listing.py`, `test_db_postgres.py`, `autocosmos.py`?**
  _High betweenness centrality (0.045) - this node is a cross-community bridge._
- **Why does `Links` connect `Links` to `templates.py`, `FakeSource`, `Notifier`, `PRDCopyTests`, `WebChannel`, `ResendEmailChannelTests`, `test_ingest_postgres.py`, `test_handlers.py`, `TelegramChannel`?**
  _High betweenness centrality (0.026) - this node is a cross-community bridge._
- **Why does `PostgresTestCase` connect `test_ingest_postgres.py` to `FakeSource`, `.listing`, `pipeline/scoring.py`, `CommercialTests`, `migrate_sqlite.py`, `MigrateSqliteTests`, `test_llm_jobs_postgres.py`, `WebChannel`, `MercadoPagoTests`, `test_handlers.py`, `pgcase.py`, `listing.py`, `test_db_postgres.py`?**
  _High betweenness centrality (0.026) - this node is a cross-community bridge._
- **Are the 41 inferred relationships involving `Links` (e.g. with `ResendEmailChannel` and `TelegramChannel`) actually correct?**
  _`Links` has 41 INFERRED edges - model-reasoned connections that need verification._
- **Are the 35 inferred relationships involving `Listing` (e.g. with `AutoCosmosScraper` and `Page`) actually correct?**
  _`Listing` has 35 INFERRED edges - model-reasoned connections that need verification._
- **What connects `public.vehicle_catalog`, `public.pipeline_errors`, `public.app_config` to the rest of the system?**
  _472 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `templates.py` be split into smaller, more focused modules?**
  _Cohesion score 0.0711864406779661 - nodes in this community are weakly interconnected._
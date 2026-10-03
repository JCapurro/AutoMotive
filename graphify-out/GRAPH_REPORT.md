# Graph Report - AutoMotive  (2026-10-03)

## Corpus Check
- 354 files · ~243,216 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 3240 nodes · 8279 edges · 183 communities (161 shown, 22 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 479 edges (avg confidence: 0.53)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `ea92d0bf`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- AutoCosmosScraper
- description_facts.py
- Notifier
- pro.ts
- listing-actions.tsx
- createAdminClient
- run_target
- red_flags.py
- NotificationsCase
- Links
- app/listings/[id]/page.tsx
- ListingFacts
- QueueTests
- notifications.py
- admin-inspect.ts
- ingest.py
- normalize_text
- settings/page.tsx
- enrich.py
- ingest
- search-form.tsx
- db.ts
- facebook.py
- Target
- fiesta_listing
- LLMProvider
- test_llm_drafts.py
- watchdog.py
- format.ts
- web/app/page.tsx
- PRD — Automotive
- searches/[id]/page.tsx
- scraper_cli.py
- connection
- test_llm_claude_cli.py
- [notificationId]/route.ts
- listings.py
- matching.py
- templates.py
- Listing
- test_ingest_postgres.py
- geo.py
- Migration
- 20260927120000_core_schema.sql
- test_parsers.py
- devDependencies
- dependencies
- compilerOptions
- Page
- IntelligenceConfig
- transmission.py
- assess
- _is_recent
- mercadopago-server.ts
- 20261007120000_ese_auto_commercial.sql
- server.ts
- PostgresTestCase
- TelegramChannel
- 20261003120000_f6_backoffice_metrics.sql
- SourceAlerts
- components.json
- 20260927120100_rls.sql
- resolve_price
- IngestCase
- matches.py
- .listing
- run
- Site
- startup_warnings
- scheduler.py
- listing.py
- createClient
- profiles.py
- CommercialTests
- Ese Auto · propuesta comercial y proyección
- ClaudeCliProvider
- test_intelligence.py
- Comunes a cualquier ruta
- Puesta en producción del piloto (F7)
- Automotive — Plan técnico del MVP
- mercadolibre.py
- MercadoPagoTests
- rescore.py
- v6.py
- test_llm_contract.py
- database.ts
- 20261001120000_f4_web.sql
- billing-forms.tsx
- metrics/page.tsx
- ListingDetail
- saved/page.tsx
- PROPUESTA_COMERCIAL.md
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
- main.py
- web/app/layout.tsx
- RedFlagTests
- load_models
- 6. Intelligence (§16–20, §24, §25, §44)
- 4. Modelo de datos (Postgres / Supabase)
- test_db.py
- 47. Riesgos principales
- 58. Definición final del producto
- pgcase.py
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
- Automotive — web
- simulate_alert.py
- 16. Matching Engine
- 23. Página de resultado
- 33. Freemium inicial
- 36. Métricas de activación
- 20260930120000_f3_notifications.sql
- opengraph-image.tsx
- WatchlistTests
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
- automotive-worker
- 20261008120000_mercadopago.sql
- .from_app_config
- Mercado Pago · cobro y acceso automático
- vercel.json

## God Nodes (most connected - your core abstractions)
1. `Links` - 88 edges
2. `Listing` - 72 edges
3. `createClient()` - 71 edges
4. `connection()` - 70 edges
5. `PRD — Automotive` - 59 edges
6. `requireUser()` - 55 edges
7. `createAdminClient()` - 49 edges
8. `Page` - 48 edges
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

## Communities (183 total, 22 thin omitted)

### Community 0 - "AutoCosmosScraper"
Cohesion: 0.24
Nodes (9): AutoCosmosScraper, _price(), AsyncClient, Listing, Response, GET, retried on a network error or a 5xx; the last answer or error wins., (price, currency, partial reason) from the price blocks of a card or detail. A…, _slug() (+1 more)

### Community 1 - "description_facts.py"
Cohesion: 0.07
Nodes (40): _after_label(), Amount, _amounts(), _before_label(), _close(), _currency(), DescriptionFacts, _distinct() (+32 more)

### Community 2 - "Notifier"
Cohesion: 0.06
Nodes (49): at_least(), rank(), Opportunity levels (§20, sección 6.4), thresholds from…, Audience, classify(), decide(), decide_all(), Decision (+41 more)

### Community 3 - "pro.ts"
Cohesion: 0.11
Nodes (32): joinWaitlist(), reportVisibleResults(), trackProCta(), checkPayment(), ownedCheckout(), startPayment(), stopSubscription(), metadata (+24 more)

### Community 4 - "listing-actions.tsx"
Cohesion: 0.12
Nodes (24): Props, PurchasedBanner(), PurchaseDialog(), TODAY(), SellerQuestions(), Button(), buttonVariants, Checkbox() (+16 more)

### Community 5 - "createAdminClient"
Cohesion: 0.09
Nodes (52): BillingPage(), metadata, ConfigPage(), HINTS, metadata, ErrorsPage(), metadata, metadata (+44 more)

### Community 6 - "run_target"
Cohesion: 0.20
Nodes (14): finish_run(), Close a run and keep the source's health counters in step. Returns the source's…, start_run(), finish_target(), next_run_at = now + the source's interval (sección 5.1). A failed run retries…, crawl_due(), BatchHandler, HealthHandler (+6 more)

### Community 7 - "red_flags.py"
Cohesion: 0.33
Nodes (10): _age_years(), description_known(), description_mismatches(), Any, datetime, Red flags (§24, sección 6.5). Pure, deterministic rules. Each flag has an id, a…, `diff_pct`: % below the comparables' median (None without enough of them).…, What the description states against what the listing publishes… (+2 more)

### Community 8 - "NotificationsCase"
Cohesion: 0.15
Nodes (12): MatchCandidate, A new, non-backfill match the crawl just stored., ListingEvent, AlertTypesTests, DailyCapAndDigestTests, DedupeTests, NotificationsCase, Acceptance: the three types of §22 reach Telegram and email with the right copy. (+4 more)

### Community 9 - "Links"
Cohesion: 0.11
Nodes (23): patch, Update, _allowed(), help_(), invalid_code_text(), linked_text(), The Telegram bot after F4: it links the account and answers alert buttons.…, register() (+15 more)

### Community 10 - "app/listings/[id]/page.tsx"
Cohesion: 0.06
Nodes (42): markFor(), metadata, plain(), priceHistory(), SAME, SCORE_PART, ScoreInWords(), Similar (+34 more)

### Community 11 - "ListingFacts"
Cohesion: 0.11
Nodes (28): AsyncAnthropic, BaseModel, AnthropicApiProvider, CatalogModel, M, The Claude API with an API key (F7, punto 6): the provider for serving the…, `claude -p` as the pilot's LLM (sección 8.2). claude -p --output-format json…, The LLM layer (sección 8): providers behind one interface. provider.py… (+20 more)

### Community 12 - "QueueTests"
Cohesion: 0.17
Nodes (5): LlmJobsCase, QueueTests, What the web can do with the user's session (sección 4.4)., Run `sql` as the signed-in web user (role authenticated, RLS on)., WebAccessTests

### Community 13 - "notifications.py"
Cohesion: 0.07
Nodes (41): apply_telegram_action(), digest_users(), existing_keys(), insert_decisions(), insert_digest(), insert_event(), interactions(), listing_audiences() (+33 more)

### Community 14 - "admin-inspect.ts"
Cohesion: 0.20
Nodes (11): MatchInspector(), NotificationInspector(), context(), Inspection, inspectMatch(), inspectNotification(), ListingRow, MatchRow (+3 more)

### Community 15 - "ingest.py"
Cohesion: 0.07
Nodes (48): AsyncConnection, quote_for_today(), The quote stored for today (blue, else oficial), fetching and storing it on…, DescriptionLLM, ingest_detail(), Listing, What a parsed detail page says, into the stored listing. `seen=False`…, The LLM for the descriptions the rules can't settle. (+40 more)

### Community 16 - "normalize_text"
Cohesion: 0.11
Nodes (28): vehicle_catalog: canonical make/model/trim names. The catalog is small (a few…, _km(), _money(), _positive(), The LLM's search drafts, checked against vehicle_catalog (sección 8.4, paso 4).…, normalize_brand(), normalize_model(), normalize_text() (+20 more)

### Community 17 - "settings/page.tsx"
Cohesion: 0.12
Nodes (21): RFC-8058, POST(), metadata, unsubscribe(), metadata, UnsubscribePage(), LoginPage(), metadata (+13 more)

### Community 18 - "enrich.py"
Cohesion: 0.11
Nodes (29): Refresher, mark_detail_checked(), matched_recheck_queue(), Active listings with a match (above 'low') that the crawl stopped seeing: past…, due_targets(), enabled_sources(), Any, crawl_targets and the source cadence they run on (sección 5.1). (+21 more)

### Community 19 - "ingest"
Cohesion: 0.18
Nodes (8): ingest(), normalize → geocode → upsert. The whole batch is one transaction., CanonicalUpsertTests, card(), DescriptionFactsTests, EnrichmentTests, Listing, Normalization v3: the description as a source of the price.

### Community 20 - "search-form.tsx"
Cohesion: 0.05
Nodes (69): previewSearch(), loadFormData(), EditSearchPage(), metadata, metadata, AssistedSearch(), FALLBACK_TITLE, JobRow (+61 more)

### Community 21 - "db.ts"
Cohesion: 0.11
Nodes (25): SEARCH_FILTERS, alertedUser(), signIn(), ask(), setHeartbeat(), signIn(), globalSetup(), main() (+17 more)

### Community 22 - "facebook.py"
Cohesion: 0.11
Nodes (28): CollectorBlocked, The source answered with a login wall, a security challenge or no session. The…, _after_colon(), _city_slug(), _city_slug_from_origin(), _extract_location(), FacebookMarketplaceScraper, _looks_like_location() (+20 more)

### Community 23 - "Target"
Cohesion: 0.08
Nodes (30): NamedTuple, FxQuote, normalize_listing(), price_usd(), CatalogModel, The crawl target a card was found through: a hint, never the truth., Map one scraped (or detail) Listing onto `listings` columns. Values that don't…, Target (+22 more)

### Community 24 - "fiesta_listing"
Cohesion: 0.14
Nodes (14): evaluate(), match(), The reasons if every hard filter is ok or unknown; None if one fails., CurrencyTests, fiesta_listing(), fiesta_profile(), GoldenFixtureTests, GuardAndLevelTests (+6 more)

### Community 25 - "LLMProvider"
Cohesion: 0.08
Nodes (33): claim(), expire(), finish(), Any, AsyncConnection, llm_jobs: the queue between the web and the LLM layer (sección 8.4). The web…, The oldest queued job of `kinds`, now 'running'; None if there is none., done' with its output, or 'failed' with the error (never both). (+25 more)

### Community 26 - "test_llm_drafts.py"
Cohesion: 0.13
Nodes (28): normalize_draft(), normalize_drafts(), Any, CatalogModel, date, llm_jobs.output for a parse_search job. Duplicates (same make, model and trim)…, The catalog model the draft names, or the make alone, or nothing., _trim() (+20 more)

### Community 27 - "watchdog.py"
Cohesion: 0.09
Nodes (30): timedelta, beat(), last_beat(), datetime, The worker's heartbeat (F7, punto 8): one row in worker_heartbeat, updated…, started_now(), EnvFileTests, F7, punto 8: the watchdog's decisions (tools/watchdog.py), without network or… (+22 more)

### Community 28 - "format.ts"
Cohesion: 0.12
Nodes (34): AdminListingPage(), escapeLike(), ListingsPage(), metadata, InboxPage(), ListingPage(), PriceVerdict(), similarListings() (+26 more)

### Community 29 - "web/app/page.tsx"
Cohesion: 0.07
Nodes (29): AdminLayout(), metadata, AppLayout(), BENEFITS, EXAMPLE, Landing(), STEPS, metadata (+21 more)

### Community 30 - "PRD — Automotive"
Cohesion: 0.05
Nodes (37): 11. Principios de producto, 13. Concepto de Search Profile, 14. Ingesta de publicaciones, 17. Opportunity Score, 18. Componentes iniciales del Opportunity Score, 19. Price Intelligence, 1. Resumen ejecutivo, 20. Niveles de oportunidad (+29 more)

### Community 31 - "searches/[id]/page.tsx"
Cohesion: 0.16
Nodes (14): COUNT_KEY, EMPTY, Filter, FILTERS, metadata, AutoRefresh(), FrequencySelect(), PauseButton() (+6 more)

### Community 32 - "scraper_cli.py"
Cohesion: 0.08
Nodes (33): shutdown(), _collector_loop(), AbstractEventLoop, Any, T, Run collector coroutines on an event loop that can start subprocesses.…, run_collector(), date (+25 more)

### Community 33 - "connection"
Cohesion: 0.08
Nodes (38): AsyncConnectionPool, Postgres (Supabase) data access for the worker. Replaces the old SQLite module.…, close_pool(), connection(), connection_kwargs(), open_pool(), Any, AsyncConnection (+30 more)

### Community 34 - "test_llm_claude_cli.py"
Cohesion: 0.19
Nodes (22): Run the CLI once and return its stdout. Raises LLMTimeout / LLMError., run_cli(), envelope(), FakeRunner, provider(), ClaudeCliProvider (sección 8.2): the command it runs, the subprocess (no shell,…, test_a_timeout_is_not_retried(), test_command_line_has_the_isolation_flags_and_no_user_text() (+14 more)

### Community 35 - "[notificationId]/route.ts"
Cohesion: 0.33
Nodes (10): GET(), handle(), HEAD(), peek(), Row, track(), ClickTarget, destination() (+2 more)

### Community 36 - "listings.py"
Cohesion: 0.10
Nodes (32): enrichment_queue(), find_repost_of(), insert_listing(), insert_snapshot(), llm_facts_last_day(), lock_existing(), mark_gone(), _param() (+24 more)

### Community 37 - "matching.py"
Cohesion: 0.11
Nodes (29): Result, money(), number(), USD 10.300 · ARS 12.500.000 (Argentine thousands separator)., _choice(), distance_km(), evaluate(), filter_currency() (+21 more)

### Community 38 - "templates.py"
Cohesion: 0.06
Nodes (53): CallbackQueryHandler, InlineKeyboardMarkup, handler(), Inline buttons of a Telegram alert (sección 7.2): ⭐ Me interesa · ✖ Descartar.…, Channel, Notification, Protocol, The channel interface (sección 7.2): the engine never knows how an alert… (+45 more)

### Community 39 - "Listing"
Cohesion: 0.16
Nodes (16): Listing, One ad as a collector read it, before normalization. `marca`/`modelo`/`version`…, Apply user filters that the source could not enforce server-side., KavakScraper, _parse_card(), parse_detail(), parse_search(), Listing (+8 more)

### Community 40 - "test_ingest_postgres.py"
Cohesion: 0.22
Nodes (5): fake(), MatchedRecheckTests, F1 ingestion against the local Supabase Postgres (docs/TECHNICAL_PLAN.md,…, Listings with a match the crawl stopped seeing are checked through their detail…, RepostTests

### Community 41 - "geo.py"
Cohesion: 0.12
Nodes (20): Coords, _fallback_can_stand_alone(), filter_listings_by_radius(), geocode_location(), _geocode_nominatim(), haversine_km(), _looks_like_non_location_query(), _lookup_known_location() (+12 more)

### Community 42 - "Migration"
Cohesion: 0.13
Nodes (12): Row, LoadEmailsTests, _make_sqlite(), MigrateSqliteTests, Path, load_emails(), main(), Migration (+4 more)

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
Cohesion: 0.06
Nodes (30): dom, dom.iterable, esnext, **/*.mts, .next/dev/types/**/*.ts, next-env.d.ts, .next-mp-test/dev/types/**/*.ts, .next-mp-test/types/**/*.ts (+22 more)

### Community 48 - "Page"
Cohesion: 0.12
Nodes (16): Browser, BrowserContext, What raw_pages keeps of a detail page: enough for parse_detail()., browser_context(), _ensure_browser(), Shared Playwright helpers — reuse a single browser instance across scrapers., Yield a fresh browser context. Closes context on exit; browser is reused., _expand() (+8 more)

### Community 49 - "IntelligenceConfig"
Cohesion: 0.19
Nodes (23): diff_pct(), How far below the median the published price is, in % (negative = above)., IntelligenceConfig, level_for(), 🔥 high ≥ 85 · 🟢 good ≥ 70 · 🟡 match ≥ 50 · ⚪ low. `cap` is the highest level…, age_hours(), clamp(), completeness_component() (+15 more)

### Community 50 - "transmission.py"
Cohesion: 0.25
Nodes (8): _classify(), fuel(), Transmission and fuel from free text (sección 5.2, paso 2). Sources rarely…, manual' | 'automatic' | None, from the first text that settles it. Pass the…, Canonical fuel ('nafta', 'diesel', 'gnc', 'hibrido', 'electrico') or None,…, private' | 'dealer' | None., seller_type(), transmission()

### Community 51 - "assess"
Cohesion: 0.15
Nodes (15): AST, assess(), Any, datetime, PriceRef, The columns of `matches` this evaluation fills., Match, score, flags and questions whether or not it matches (explain_match)., CopyLintTests (+7 more)

### Community 52 - "_is_recent"
Cohesion: 0.39
Nodes (4): _is_recent(), Drop listings published more than `max_age_days` ago. If the source doesn't say…, _is_recent reads stored listing rows (published_at is a timestamptz)., SchedulerRecencyTests

### Community 53 - "mercadopago-server.ts"
Cohesion: 0.13
Nodes (36): GET(), POST(), checkoutUrl(), paymentPeriod(), sameSecret(), api(), applyPayment(), BillingCheckout (+28 more)

### Community 54 - "20261007120000_ese_auto_commercial.sql"
Cohesion: 0.09
Nodes (8): llm_jobs_guard_commercial, matches_guard_commercial, public.commercial_payments, public.guard_assisted_commercial_access(), public.guard_match_access(), public.plan_limits_for(), public.profiles, public.refund_commercial_payment()

### Community 55 - "server.ts"
Cohesion: 0.20
Nodes (15): GET(), GET(), POST(), Email, LoginState, sendMagicLink(), siteUrl(), verifyCode() (+7 more)

### Community 56 - "PostgresTestCase"
Cohesion: 0.12
Nodes (10): PostgresTestCase, Opens the worker pool on TEST_DATABASE_URL over a clean slate., AlertRepoTests, GeocodeAndConfigTests, _listing(), The bot's data layer against a real Postgres with the supabase/ migrations. Run…, /start <code> (public.link_telegram, F4)., SeenMatchesTests (+2 more)

### Community 57 - "TelegramChannel"
Cohesion: 0.09
Nodes (21): parse(), AsyncClient, datetime, Notification, ResendEmailChannel, Any, datetime, TelegramChannel (+13 more)

### Community 58 - "20261003120000_f6_backoffice_metrics.sql"
Cohesion: 0.10
Nodes (16): pro_waitlist_set_updated_at, public.admin_notification_daily, public.admin_score_histogram, public.admin_searches, public.admin_source_health, public.admin_users, public.join_waitlist(), public.pro_waitlist (+8 more)

### Community 59 - "SourceAlerts"
Cohesion: 0.12
Nodes (20): A source's failure streak after a run (the admin alert reads it)., SourceHealth, failing_text(), last_error_line(), Any, datetime, SourceHealth, Operational alerts for the admin (sección 10, §46). A source that fails… (+12 more)

### Community 60 - "components.json"
Cohesion: 0.09
Nodes (21): aliases, components, hooks, lib, ui, utils, iconLibrary, menuAccent (+13 more)

### Community 61 - "20260927120100_rls.sql"
Cohesion: 0.10
Nodes (20): public.app_config, public.collector_runs, public.crawl_targets, public.enforce_plan_limits(), public.events, public.fx_rates, public.geocode_cache, public.listing_snapshots (+12 more)

### Community 62 - "resolve_price"
Cohesion: 0.15
Nodes (7): PriceResolution, What resolve_price() concluded, stored in description_facts.price_check. The…, The listing's effective price (sección 5.2, v3). `published`/`currency`: the…, resolve_price(), _usd(), _resolve(), ResolvePriceTests

### Community 63 - "IngestCase"
Cohesion: 0.23
Nodes (7): RuntimeError, CrawlTargetsTests, _FakeBot, IngestCase, One crawl-loop tick with every target due, no jitter., The crawl feeds the notification engine (sección 7): silent first run, one…, TelegramAlertsTests

### Community 64 - "matches.py"
Cohesion: 0.17
Nodes (19): _existing(), filter_unseen(), insert_legacy_matches(), _keys(), mark_seen(), matched_by_other_profiles(), matches_of_listings(), Any (+11 more)

### Community 65 - ".listing"
Cohesion: 0.22
Nodes (6): ComparablesCascadeTests, IntelligenceCase, PriceRef, Insert a listing row directly: comparables are about stored columns., Sección 6.2: trim+transmission → transmission → model, first with n ≥ min_n., ScoredMatchesTests

### Community 66 - "run"
Cohesion: 0.11
Nodes (20): fixture, AbstractEventLoop, Any, T, Entry-point helper: run the worker's coroutines on a loop psycopg supports.…, run(), selector_loop(), load_recordings() (+12 more)

### Community 67 - "Site"
Cohesion: 0.20
Nodes (10): range, AutoCosmosSearchTests, card(), page(), Request, Response, AutoCosmos search: every page of the model, `?pidx=N`, retried on 503 (no…, Serves `pages[pidx]`; `fail[pidx]` is a list of statuses (or exceptions) to… (+2 more)

### Community 68 - "startup_warnings"
Cohesion: 0.14
Nodes (10): What this configuration leaves off (F7, punto 5): one line per channel, metric…, startup_warnings(), _database(), db_test_skip_reason(), Why the DB tests can't run here, or None. They TRUNCATE tables, so they only…, ConfigTests, F7, punto 4: the DB tests TRUNCATE, so they never touch the pilot's database., F7, punto 5: every channel or metric the .env leaves off is logged at startup. (+2 more)

### Community 69 - "scheduler.py"
Cohesion: 0.11
Nodes (21): mark_failed(), mark_retry(), prepare_delivery(), Check the current access just before dispatch, including an already queued…, log_error(), Observability (sección 10, §46): collector_runs, pipeline_errors and source…, Record a pipeline error. Never raises: observability must not break the…, deliver_pending() (+13 more)

### Community 70 - "listing.py"
Cohesion: 0.31
Nodes (7): attrs_hash(), fingerprint(), _hash(), Any, Normalization v2: a collector Listing → a `listings` row (sección 5.2). Pure:…, hash(make, model, year, round(km, -3), seller, location) — sección 5.4. Without…, text_hash()

### Community 71 - "createClient"
Cohesion: 0.09
Nodes (48): markOpened(), answerInfluence(), currentStatus(), markSeen(), Purchase, recordPurchase(), setDiscardReason(), setSaved() (+40 more)

### Community 72 - "profiles.py"
Cohesion: 0.12
Nodes (24): _put(), Any, Translate between the Telegram wizard's filter dict and search_profiles. The…, (marca, modelo) combinations of a wizard filter: one search profile each., Wizard dict + one (make, model) → search_profiles column values., search_profiles column values → the wizard dict the scheduler and handlers…, split_vehicles(), to_legacy() (+16 more)

### Community 74 - "Ese Auto · propuesta comercial y proyección"
Cohesion: 0.12
Nodes (16): 1. Qué vender, 2. Qué ya existe y qué falta, 3. Referencias de mercado, 4. Alternativas iniciales conservadas como referencia, 5. Oferta seleccionada en pesos: B, 6. Proyección a seis meses, 7. Validación y salida comercial, 8. Decisión a registrar (+8 more)

### Community 76 - "ClaudeCliProvider"
Cohesion: 0.17
Nodes (10): Runner, ClaudeCliProvider, parse_envelope(), Any, CatalogModel, M, The structured answer inside `--output-format json`'s envelope., parametrize (+2 more)

### Community 77 - "test_intelligence.py"
Cohesion: 0.19
Nodes (11): RedFlag, ago(), Every user-facing string of the intelligence layer (§19, §24, §25). Kept in one…, Any, datetime, question_keys(), Questions for the seller (§25, sección 6.6). Deterministic templates. Always:…, One message ready to copy: "Hola, ¿cómo estás? ¿Lo seguís teniendo? …". (+3 more)

### Community 78 - "Comunes a cualquier ruta"
Cohesion: 0.12
Nodes (16): COM-02 · Una oferta coherente, COM-03 · Límites que siguen vigentes al vencer, COM-04 y COM-05 · Cobro y ciclo de vida, COM-06 · Autogestión, COM-07 · Producto que se puede prometer, COM-08 · Medir rentabilidad, no solo intención, COM-09 · Operación comercial, COM-10 · Salida controlada (+8 more)

### Community 79 - "Puesta en producción del piloto (F7)"
Cohesion: 0.13
Nodes (15): 10. Prueba de aceptación, 1. Dominio en Cloudflare, 2. Túnel de Cloudflare, 3. Resend (emails de login y de alertas), 4. API key de Anthropic (modo asistido), 5. Chat de Telegram para las alertas operativas, 6. Sesiones de MercadoLibre y Facebook, 7. Configuración (+7 more)

### Community 80 - "Automotive — Plan técnico del MVP"
Cohesion: 0.10
Nodes (20): 10. Backoffice y observabilidad (§45, §46), 11. Métricas y eventos (§35–38, §53), 12. Freemium (§33, §34), 14. Riesgos y decisiones abiertas, 15. Trazabilidad PRD → plan, 1. Punto de partida y gaps, 2. Arquitectura objetivo, 3. Estructura del repo (+12 more)

### Community 81 - "mercadolibre.py"
Cohesion: 0.11
Nodes (26): BeautifulSoup, json_ld(), json_ld_of_type(), Any, Every schema.org object in the page's JSON-LD blocks (flattening @graph)., _blocked(), _browser_storage_state(), _build_url() (+18 more)

### Community 83 - "rescore.py"
Cohesion: 0.11
Nodes (25): compress(), decompress(), iter_for_reparse(), mark_parsed(), purge_older_than(), raw_pages: the last detail page of each listing, compressed (normalization v3).…, Stored detail pages, oldest listing first. `below_version`: per source, only…, The stored page was read again with this parser version (tools/reprocess.py). (+17 more)

### Community 84 - "v6.py"
Cohesion: 0.16
Nodes (21): parse_relative_date(), Parse Spanish relative date strings shown by AR car classifieds. Examples…, Return a unix timestamp inferred from a Spanish relative-date string., _strip_accents(), dedupe(), multiline_text(), Text with paragraph breaks kept (descriptions)., soup() (+13 more)

### Community 85 - "test_llm_contract.py"
Cohesion: 0.12
Nodes (27): skipif, _items(), CatalogModel, vehicle_catalog as supabase/seed.sql inserts it, without a database. The LLM…, seed_catalog(), _year(), message(), provider() (+19 more)

### Community 86 - "database.ts"
Cohesion: 0.09
Nodes (22): DIGEST_SECTION, DigestItem, metadata, WebPayload, Inbox, InboxContext, InboxProvider(), Row (+14 more)

### Community 87 - "20261001120000_f4_web.sql"
Cohesion: 0.24
Nodes (7): public.dashboard_summary(), public.link_telegram(), public.match_cards, public.profiles, public.recent_opportunities(), public.search_result_counts(), public.search_results()

### Community 88 - "billing-forms.tsx"
Cohesion: 0.14
Nodes (22): ActionResult, shape(), SourceInput, updateConfig(), updateSource(), confirmPayment(), launchCommercialPilot(), recordRefund() (+14 more)

### Community 89 - "metrics/page.tsx"
Cohesion: 0.27
Nodes (11): CTA_EVENTS, day(), levelLabel(), median(), metadata, MetricsPage(), Rate(), WAITLIST (+3 more)

### Community 90 - "ListingDetail"
Cohesion: 0.17
Nodes (10): AutoCosmos AR scraper. AutoCosmos exposes a public listings page at…, BaseScraper, ListingDetail, Run keyword detection over the title and tag the listing. Statistical detection…, What fetch_detail() found at a listing's URL (sección 5.5). `gone` means the…, Download the ad's own page, with the source's login-wall and session checks,…, Read the ad's page: description, version, transmission, seller type, every…, MercadoLibreScraper (+2 more)

### Community 91 - "saved/page.tsx"
Cohesion: 0.33
Nodes (7): FOLLOWED, metadata, SavedPage(), Snapshot, watchEvents(), WebConfig, daysSince()

### Community 92 - "PROPUESTA_COMERCIAL.md"
Cohesion: 0.24
Nodes (4): Comprobaciones reproducibles, Ese Auto · implementación del lanzamiento comercial, Habilitación del entorno destino, Límites de esta entrega

### Community 93 - "Setup"
Cohesion: 0.18
Nodes (11): Backoffice y métricas (F6), Base de datos (Supabase), Correr el bot, Correr la web, Login de Facebook (una vez), MercadoLibre: sesion web, Migrar la base SQLite vieja, Modo asistido (LLM) (+3 more)

### Community 95 - "prompts/__init__.py"
Cohesion: 0.24
Nodes (8): catalog_text(), load(), parse_search_system(), parse_search_user(), CatalogModel, date, System prompts and user messages of the LLM layer, shared by every provider.…, One line per make: "Ford: Fiesta [S, SE, Titanium]; Focus [...]".

### Community 96 - "intelligence/engine.py"
Cohesion: 0.10
Nodes (20): fetch(), PriceRef, Any, Price Intelligence (§19, sección 6.2). The statistics come from the SQL…, public.comparables() for one listing. `cfg` overrides app_config.comparables., Weights, curves and thresholds of the intelligence layer (sección 6, Apéndice…, Evaluation, One listing × one profile → everything a match row stores. Pure.… (+12 more)

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

### Community 104 - "main.py"
Cohesion: 0.27
Nodes (9): amain(), build_notifier(), _every(), notifying(), stdout, plus LOG_FILE (UTF-8, rotated at midnight, LOG_KEEP_DAYS kept)., Run `job(stop)` now and then every `seconds` until stopped; errors are logged., The channels this worker can deliver on (sección 7.2)., A refresh pass whose price_drop / listing_gone events go to the engine. (+1 more)

### Community 105 - "web/app/layout.tsx"
Cohesion: 0.29
Nodes (5): metadata, mono, sans, viewport, Toaster()

### Community 107 - "load_models"
Cohesion: 0.24
Nodes (8): load_models(), match_model(), AsyncConnection, CatalogModel, Model-level rows with their trims, aliases and production years., Canonical (make, model), or None if it isn't in the catalog. The model matches…, resolve_make_model(), CatalogMatchTests

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

### Community 113 - "pgcase.py"
Cohesion: 0.40
Nodes (3): Helpers for tests that need Postgres (see conftest.py for the event loop)., Commercial access and payment boundaries against an isolated local database., Real isolated PostgreSQL checks for automatic access and hostile/repeated money…

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

### Community 129 - "Automotive — web"
Cohesion: 0.40
Nodes (4): Automotive — web, Correrla, Rutas (plan técnico, sección 9), Tests

### Community 130 - "simulate_alert.py"
Cohesion: 0.21
Nodes (12): _key(), match_alert(), process_batch(), Steps 4–5 for one batch of a target's listings: match and score them against…, One profile's view of a batch, read before any profile stores anything, so…, Store one profile's matches for a batch. Returns the new matches the…, _stage(), _Staged (+4 more)

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

### Community 180 - "20261008120000_mercadopago.sql"
Cohesion: 0.39
Nodes (5): profiles_guard_billing_delete, public.apply_mercadopago_payment(), public.billing_checkouts, public.commercial_payments, public.guard_billing_account_delete()

### Community 181 - ".from_app_config"
Cohesion: 0.50
Nodes (3): _merge(), Any, ConfigTests

### Community 182 - "Mercado Pago · cobro y acceso automático"
Cohesion: 0.20
Nodes (10): Acceso confirmado y preferencia Particular recuperada, Alta inicial con el MCP · 2/10/2026, Configuración pendiente del entorno destino, Ensayo aislado · 3/10/2026, Estado actual · 3/10/2026, Implementación, Mercado Pago · cobro y acceso automático, Operación y casos de revisión (+2 more)

## Knowledge Gaps
- **478 isolated node(s):** `public.vehicle_catalog`, `public.pipeline_errors`, `public.app_config`, `public.geocode_cache`, `public.fx_rates` (+473 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **22 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Listing` connect `Listing` to `AutoCosmosScraper`, `NotificationsCase`, `WatchlistTests`, `ingest.py`, `normalize_text`, `enrich.py`, `ingest`, `facebook.py`, `Target`, `test_ingest_postgres.py`, `geo.py`, `Migration`, `Page`, `PostgresTestCase`, `IngestCase`, `listing.py`, `profiles.py`, `mercadolibre.py`, `v6.py`, `ListingDetail`?**
  _High betweenness centrality (0.038) - this node is a cross-community bridge._
- **Why does `PostgresTestCase` connect `PostgresTestCase` to `intelligence/engine.py`, `.listing`, `run`, `listings.py`, `test_ingest_postgres.py`, `CommercialTests`, `Links`, `WatchlistTests`, `QueueTests`, `Migration`, `NotificationsCase`, `pgcase.py`, `MercadoPagoTests`, `ingest`, `Target`, `TelegramChannel`, `ListingDetail`, `IngestCase`?**
  _High betweenness centrality (0.026) - this node is a cross-community bridge._
- **Why does `Links` connect `Links` to `simulate_alert.py`, `listings.py`, `templates.py`, `PRDCopyTests`, `main.py`, `test_ingest_postgres.py`, `NotificationsCase`, `WatchlistTests`, `ingest`, `TelegramChannel`, `ListingDetail`, `IngestCase`?**
  _High betweenness centrality (0.024) - this node is a cross-community bridge._
- **Are the 41 inferred relationships involving `Links` (e.g. with `ResendEmailChannel` and `TelegramChannel`) actually correct?**
  _`Links` has 41 INFERRED edges - model-reasoned connections that need verification._
- **Are the 35 inferred relationships involving `Listing` (e.g. with `AutoCosmosScraper` and `Page`) actually correct?**
  _`Listing` has 35 INFERRED edges - model-reasoned connections that need verification._
- **What connects `public.vehicle_catalog`, `public.pipeline_errors`, `public.app_config` to the rest of the system?**
  _478 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `description_facts.py` be split into smaller, more focused modules?**
  _Cohesion score 0.06512890094979647 - nodes in this community are weakly interconnected._
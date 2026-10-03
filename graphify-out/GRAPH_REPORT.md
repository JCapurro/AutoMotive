# Graph Report - AutoMotive  (2026-10-03)

## Corpus Check
- 354 files · ~243,644 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 3239 nodes · 8278 edges · 178 communities (156 shown, 22 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 479 edges (avg confidence: 0.53)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `59f6512c`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- telegram.py
- description_facts.py
- decide
- pro.ts
- listing-actions.tsx
- createAdminClient
- crawl.py
- service.py
- WebChannel
- Links
- inspector.tsx
- ListingFacts
- test_llm_jobs_postgres.py
- notifications.py
- admin-inspect.ts
- ingest.py
- normalize_text
- settings/page.tsx
- main.py
- test_ingest_postgres.py
- search-form.tsx
- db.ts
- facebook.py
- listing.py
- fiesta_listing
- LLMProvider
- test_llm_drafts.py
- watchdog.py
- app/listings/[id]/page.tsx
- server.ts
- PRD — Automotive
- searches/[id]/page.tsx
- scraper_cli.py
- connection
- test_llm_claude_cli.py
- drafts.py
- listings.py
- matching.py
- templates.py
- raw_pages.py
- explain_match.py
- geo.py
- migrate_sqlite.py
- 20260927120000_core_schema.sql
- test_parsers.py
- devDependencies
- dependencies
- compilerOptions
- ResendEmailChannelTests
- IntelligenceConfig
- transmission.py
- assess
- patch
- mercadopago-server.ts
- 20261007120000_ese_auto_commercial.sql
- [notificationId]/route.ts
- Listing
- TelegramChannel
- 20261003120000_f6_backoffice_metrics.sql
- SourceAlerts
- components.json
- 20260927120100_rls.sql
- resolve_price
- TelegramLinkTests
- matches.py
- .listing
- test_llm_contract.py
- AutoCosmosScraper
- startup_warnings
- pipeline/scoring.py
- 8. Capa LLM (§43, §44)
- createClient
- to_profile
- CommercialTests
- Ese Auto · propuesta comercial y proyección
- ClaudeCliProvider
- test_intelligence.py
- Comunes a cualquier ruta
- Puesta en producción del piloto (F7)
- Automotive — Plan técnico del MVP
- mercadolibre.py
- pgcase.py
- rescore.py
- v6.py
- test_llm_anthropic_api.py
- database.ts
- 20261001120000_f4_web.sql
- auth.ts
- metrics/page.tsx
- .__init__
- PROPUESTA_COMERCIAL.md
- Setup
- prompts/__init__.py
- PriceRef
- 13. Roadmap por fases
- scripts
- 40. Modelo conceptual de datos
- toggle-group.tsx
- AutoMotive
- test_notifications_templates.py
- 5. Pipeline de ingesta (§14, §15, §42)
- RedFlagTests
- load_models
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
- Automotive — web
- Notifier
- 16. Matching Engine
- 23. Página de resultado
- 33. Freemium inicial
- 36. Métricas de activación
- 20260930120000_f3_notifications.sql
- opengraph-image.tsx
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
- `PurchasedBanner()` --calls--> `answerInfluence()`  [EXTRACTED]
  web/components/app/listing-actions.tsx → web/app/app/listings/actions.ts
- `LoginPage()` --calls--> `safeNext()`  [EXTRACTED]
  web/app/login/page.tsx → web/lib/navigation.ts
- `EXAMPLE` --calls--> `money()`  [EXTRACTED]
  web/app/page.tsx → web/lib/format.ts
- `Decision()` --calls--> `when()`  [EXTRACTED]
  web/components/admin/inspector.tsx → web/lib/admin-format.ts

## Import Cycles
- None detected.

## Communities (178 total, 22 thin omitted)

### Community 0 - "telegram.py"
Cohesion: 0.08
Nodes (26): InlineKeyboardMarkup, parse(), Inline buttons of a Telegram alert (sección 7.2): ⭐ Me interesa · ✖ Descartar.…, Channel, Notification, Protocol, The channel interface (sección 7.2): the engine never knows how an alert…, A notifications row, with the user's contact data, ready to send. (+18 more)

### Community 1 - "description_facts.py"
Cohesion: 0.07
Nodes (40): _after_label(), Amount, _amounts(), _before_label(), _close(), _currency(), DescriptionFacts, _distinct() (+32 more)

### Community 2 - "decide"
Cohesion: 0.11
Nodes (23): at_least(), rank(), Opportunity levels (§20, sección 6.4), thresholds from…, classify(), decide(), decide_all(), Decision, _Plan (+15 more)

### Community 3 - "pro.ts"
Cohesion: 0.06
Nodes (49): joinWaitlist(), reportVisibleResults(), trackProCta(), checkPayment(), ownedCheckout(), startPayment(), stopSubscription(), metadata (+41 more)

### Community 4 - "listing-actions.tsx"
Cohesion: 0.11
Nodes (26): Email, LoginState, sendMagicLink(), siteUrl(), verifyCode(), LoginForm(), Props, PurchasedBanner() (+18 more)

### Community 5 - "createAdminClient"
Cohesion: 0.09
Nodes (51): BillingPage(), metadata, ConfigPage(), HINTS, metadata, ErrorsPage(), metadata, escapeLike() (+43 more)

### Community 6 - "crawl.py"
Cohesion: 0.10
Nodes (31): due_targets(), enabled_sources(), finish_target(), Any, crawl_targets and the source cadence they run on (sección 5.1)., Make crawl_targets mirror `specs` (pipeline.crawl.TargetSpec): upsert the…, Active targets of enabled sources whose next_run_at has come (or never ran)., next_run_at = now + the source's interval (sección 5.1). A failed run retries… (+23 more)

### Community 7 - "service.py"
Cohesion: 0.13
Nodes (26): build_items(), Any, datetime, Daily digest (§32, sección 7.2). Every day at app_config.digest_hour (ART,…, Digest items from waiting rows and the day's top matches: waiting rows always…, Build today's digests. Returns how many were created (then delivered)., run_digest(), Audience (+18 more)

### Community 8 - "WebChannel"
Cohesion: 0.14
Nodes (16): ResendEmailChannel, WebChannel, MatchCandidate, A new, non-backfill match the crawl just stored., ListingEvent, AlertTypesTests, DailyCapAndDigestTests, DedupeTests (+8 more)

### Community 9 - "Links"
Cohesion: 0.11
Nodes (24): CallbackQueryHandler, Update, _allowed(), help_(), invalid_code_text(), linked_text(), The Telegram bot after F4: it links the account and answers alert buttons.…, register() (+16 more)

### Community 10 - "inspector.tsx"
Cohesion: 0.07
Nodes (40): metadata, CASCADE, Decision(), Inspector(), LEVEL_RANK, STATUS_TONE, Json(), LevelBadge() (+32 more)

### Community 11 - "ListingFacts"
Cohesion: 0.13
Nodes (24): AsyncAnthropic, AnthropicApiProvider, CatalogModel, M, The Claude API with an API key (F7, punto 6): the provider for serving the…, `claude -p` as the pilot's LLM (sección 8.2). claude -p --output-format json…, The LLM layer (sección 8): providers behind one interface. provider.py…, LocalProvider (+16 more)

### Community 12 - "test_llm_jobs_postgres.py"
Cohesion: 0.16
Nodes (6): LlmJobsCase, QueueTests, The llm_jobs queue against the local Supabase Postgres (sección 8.4): what the…, What the web can do with the user's session (sección 4.4)., Run `sql` as the signed-in web user (role authenticated, RLS on)., WebAccessTests

### Community 13 - "notifications.py"
Cohesion: 0.08
Nodes (38): apply_telegram_action(), digest_users(), existing_keys(), insert_decisions(), insert_digest(), insert_event(), interactions(), listing_audiences() (+30 more)

### Community 14 - "admin-inspect.ts"
Cohesion: 0.20
Nodes (11): MatchInspector(), NotificationInspector(), context(), Inspection, inspectMatch(), inspectNotification(), ListingRow, MatchRow (+3 more)

### Community 15 - "ingest.py"
Cohesion: 0.10
Nodes (40): Re-score the matches of the listings a detail pass updated., rescore_changed(), _empty(), _facts(), _geocode_rows(), ingest_rows(), IngestConfig, IngestResult (+32 more)

### Community 16 - "normalize_text"
Cohesion: 0.12
Nodes (24): vehicle_catalog: canonical make/model/trim names. The catalog is small (a few…, normalize_brand(), normalize_model(), normalize_text(), Brand/model normalization so comparables match across sources. Used both at…, Model names — strip extra trim qualifiers leaving only the base model., _strip_accents(), _best_by_name() (+16 more)

### Community 17 - "settings/page.tsx"
Cohesion: 0.13
Nodes (18): RFC-8058, POST(), declineRenewal(), metadata, unsubscribe(), metadata, UnsubscribePage(), LoginPage() (+10 more)

### Community 18 - "main.py"
Cohesion: 0.09
Nodes (36): Refresher, mark_detail_checked(), log_error(), Record a pipeline error. Never raises: observability must not break the…, amain(), _every(), notifying(), stdout, plus LOG_FILE (UTF-8, rotated at midnight, LOG_KEEP_DAYS kept). (+28 more)

### Community 19 - "test_ingest_postgres.py"
Cohesion: 0.08
Nodes (28): RuntimeError, ListingDetail, What fetch_detail() found at a listing's URL (sección 5.5). `gone` means the…, ingest(), Listing, normalize → geocode → upsert. The whole batch is one transaction., PostgresTestCase, Opens the worker pool on TEST_DATABASE_URL over a clean slate. (+20 more)

### Community 20 - "search-form.tsx"
Cohesion: 0.06
Nodes (54): Preview, SaveOrigin, AssistedSearch(), FALLBACK_TITLE, JobRow, Origin, Phase, Reviewed (+46 more)

### Community 21 - "db.ts"
Cohesion: 0.11
Nodes (25): SEARCH_FILTERS, alertedUser(), signIn(), ask(), setHeartbeat(), signIn(), globalSetup(), main() (+17 more)

### Community 22 - "facebook.py"
Cohesion: 0.10
Nodes (28): parse_relative_date(), Parse Spanish relative date strings shown by AR car classifieds. Examples…, Return a unix timestamp inferred from a Spanish relative-date string., _strip_accents(), _after_colon(), _city_slug(), _extract_location(), _looks_like_location() (+20 more)

### Community 23 - "listing.py"
Cohesion: 0.08
Nodes (35): NamedTuple, AsyncConnection, date, quote_for_today(), fx_rates: the day's USD/ARS quote, frozen so price_usd can be reproduced…, The quote stored for today (blue, else oficial), fetching and storing it on…, today_ar(), _fetch_quote() (+27 more)

### Community 24 - "fiesta_listing"
Cohesion: 0.15
Nodes (14): evaluate(), match(), The reasons if every hard filter is ok or unknown; None if one fails., CurrencyTests, fiesta_listing(), fiesta_profile(), GoldenFixtureTests, GuardAndLevelTests (+6 more)

### Community 25 - "LLMProvider"
Cohesion: 0.09
Nodes (28): claim(), expire(), finish(), Any, AsyncConnection, llm_jobs: the queue between the web and the LLM layer (sección 8.4). The web…, The oldest queued job of `kinds`, now 'running'; None if there is none., done' with its output, or 'failed' with the error (never both). (+20 more)

### Community 26 - "test_llm_drafts.py"
Cohesion: 0.20
Nodes (18): draft(), norm(), normalization/drafts.py: the deterministic step after the LLM (sección 8.4,…, test_catalog_names_win_over_the_llm_spelling(), test_duplicates_collapse_and_the_list_is_capped(), test_enums_become_the_form_empty_value(), test_km_and_radius(), test_known_make_unknown_model_keeps_the_make() (+10 more)

### Community 27 - "watchdog.py"
Cohesion: 0.09
Nodes (30): timedelta, beat(), last_beat(), datetime, The worker's heartbeat (F7, punto 8): one row in worker_heartbeat, updated…, started_now(), EnvFileTests, F7, punto 8: the watchdog's decisions (tools/watchdog.py), without network or… (+22 more)

### Community 28 - "app/listings/[id]/page.tsx"
Cohesion: 0.09
Nodes (45): AdminListingPage(), ListingsPage(), InboxPage(), ListingPage(), markFor(), metadata, plain(), priceHistory() (+37 more)

### Community 29 - "server.ts"
Cohesion: 0.17
Nodes (14): loadFormData(), EditSearchPage(), metadata, metadata, DeleteSearchButton(), Tabs(), TabsContent(), TabsList() (+6 more)

### Community 30 - "PRD — Automotive"
Cohesion: 0.05
Nodes (37): 11. Principios de producto, 13. Concepto de Search Profile, 14. Ingesta de publicaciones, 17. Opportunity Score, 18. Componentes iniciales del Opportunity Score, 19. Price Intelligence, 1. Resumen ejecutivo, 20. Niveles de oportunidad (+29 more)

### Community 31 - "searches/[id]/page.tsx"
Cohesion: 0.12
Nodes (23): Dashboard(), metadata, COUNT_KEY, EMPTY, Filter, FILTERS, metadata, SearchResultsPage() (+15 more)

### Community 32 - "scraper_cli.py"
Cohesion: 0.11
Nodes (25): shutdown(), _collector_loop(), AbstractEventLoop, Any, T, Run collector coroutines on an event loop that can start subprocesses.…, run_collector(), Return the current USD→ARS rate (see `usd_ars_quote`). (+17 more)

### Community 33 - "connection"
Cohesion: 0.09
Nodes (38): AsyncConnectionPool, Postgres (Supabase) data access for the worker. Replaces the old SQLite module.…, close_pool(), connection(), open_pool(), AsyncConnection, Async Postgres connection pool (psycopg 3), one per worker process. The worker…, Open the process-wide pool (idempotent). (+30 more)

### Community 34 - "test_llm_claude_cli.py"
Cohesion: 0.16
Nodes (26): BaseModel, Run the CLI once and return its stdout. Raises LLMTimeout / LLMError., run_cli(), json_schema(), Any, The model's JSON Schema, self-contained: `$defs` inlined and titles dropped.…, envelope(), FakeRunner (+18 more)

### Community 35 - "drafts.py"
Cohesion: 0.26
Nodes (14): _km(), _money(), normalize_draft(), normalize_drafts(), _positive(), Any, CatalogModel, date (+6 more)

### Community 36 - "listings.py"
Cohesion: 0.09
Nodes (33): enrichment_queue(), find_repost_of(), insert_listing(), insert_snapshot(), llm_facts_last_day(), lock_existing(), mark_gone(), matched_recheck_queue() (+25 more)

### Community 37 - "matching.py"
Cohesion: 0.13
Nodes (25): Result, _choice(), distance_km(), evaluate(), filter_currency(), _km(), _location(), MatchResult (+17 more)

### Community 38 - "templates.py"
Cohesion: 0.13
Nodes (30): money(), USD 10.300 · ARS 12.500.000 (Argentine thousands separator)., age_line(), ago_long(), before_after(), Content, _digest(), DigestItem (+22 more)

### Community 39 - "raw_pages.py"
Cohesion: 0.24
Nodes (10): compress(), decompress(), iter_for_reparse(), mark_parsed(), purge_older_than(), raw_pages: the last detail page of each listing, compressed (normalization v3).…, Stored detail pages, oldest listing first. `below_version`: per source, only…, The stored page was read again with this parser version (tools/reprocess.py). (+2 more)

### Community 40 - "explain_match.py"
Cohesion: 0.31
Nodes (9): profiles_by_ids(), Profiles (alert dicts with their "profile" row) by id, enabled or not., explain(), load(), main(), Any, Explain why a listing matches (or not) a search profile, and its score.…, Everything the tool prints, as data (also the --json output). (+1 more)

### Community 41 - "geo.py"
Cohesion: 0.12
Nodes (21): Coords, _city_slug_from_origin(), _fallback_can_stand_alone(), filter_listings_by_radius(), geocode_location(), _geocode_nominatim(), haversine_km(), _looks_like_non_location_query() (+13 more)

### Community 42 - "migrate_sqlite.py"
Cohesion: 0.11
Nodes (16): Row, connection_kwargs(), Any, ensure_telegram_profile(), LoadEmailsTests, _make_sqlite(), MigrateSqliteTests, Path (+8 more)

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

### Community 48 - "ResendEmailChannelTests"
Cohesion: 0.39
Nodes (3): Request, F7, punto 7: a footer link and List-Unsubscribe one-click (RFC 8058)., ResendEmailChannelTests

### Community 49 - "IntelligenceConfig"
Cohesion: 0.19
Nodes (23): diff_pct(), How far below the median the published price is, in % (negative = above)., IntelligenceConfig, level_for(), 🔥 high ≥ 85 · 🟢 good ≥ 70 · 🟡 match ≥ 50 · ⚪ low. `cap` is the highest level…, age_hours(), clamp(), completeness_component() (+15 more)

### Community 50 - "transmission.py"
Cohesion: 0.25
Nodes (8): _classify(), fuel(), Transmission and fuel from free text (sección 5.2, paso 2). Sources rarely…, manual' | 'automatic' | None, from the first text that settles it. Pass the…, Canonical fuel ('nafta', 'diesel', 'gnc', 'hibrido', 'electrico') or None,…, private' | 'dealer' | None., seller_type(), transmission()

### Community 51 - "assess"
Cohesion: 0.14
Nodes (15): AST, assess(), Any, datetime, PriceRef, The columns of `matches` this evaluation fills., Match, score, flags and questions whether or not it matches (explain_match)., CopyLintTests (+7 more)

### Community 52 - "patch"
Cohesion: 0.33
Nodes (5): patch, _is_recent(), Drop listings published more than `max_age_days` ago. If the source doesn't say…, _is_recent reads stored listing rows (published_at is a timestamptz)., SchedulerRecencyTests

### Community 53 - "mercadopago-server.ts"
Cohesion: 0.13
Nodes (36): GET(), POST(), checkoutUrl(), paymentPeriod(), sameSecret(), api(), applyPayment(), BillingCheckout (+28 more)

### Community 54 - "20261007120000_ese_auto_commercial.sql"
Cohesion: 0.09
Nodes (8): llm_jobs_guard_commercial, matches_guard_commercial, public.commercial_payments, public.guard_assisted_commercial_access(), public.guard_match_access(), public.plan_limits_for(), public.profiles, public.refund_commercial_payment()

### Community 55 - "[notificationId]/route.ts"
Cohesion: 0.09
Nodes (25): GET(), GET(), POST(), metadata, mono, sans, viewport, GET() (+17 more)

### Community 56 - "Listing"
Cohesion: 0.07
Nodes (26): BaseScraper, CollectorBlocked, Listing, Run keyword detection over the title and tag the listing. Statistical detection…, One ad as a collector read it, before normalization. `marca`/`modelo`/`version`…, Apply user filters that the source could not enforce server-side., The source answered with a login wall, a security challenge or no session. The…, Download the ad's own page, with the source's login-wall and session checks,… (+18 more)

### Community 57 - "TelegramChannel"
Cohesion: 0.18
Nodes (9): build_notifier(), The channels this worker can deliver on (sección 7.2)., Any, datetime, TelegramChannel, FakeBot, Exception, TelegramChannelTests (+1 more)

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

### Community 64 - "matches.py"
Cohesion: 0.17
Nodes (19): _existing(), filter_unseen(), insert_legacy_matches(), _keys(), mark_seen(), matched_by_other_profiles(), matches_of_listings(), Any (+11 more)

### Community 65 - ".listing"
Cohesion: 0.20
Nodes (6): ComparablesCascadeTests, IntelligenceCase, PriceRef, Insert a listing row directly: comparables are about stored columns., Sección 6.2: trim+transmission → transmission → model, first with n ≥ min_n., ScoredMatchesTests

### Community 66 - "test_llm_contract.py"
Cohesion: 0.10
Nodes (26): fixture, AbstractEventLoop, Any, T, Entry-point helper: run the worker's coroutines on a loop psycopg supports.…, run(), selector_loop(), build_provider() (+18 more)

### Community 67 - "AutoCosmosScraper"
Cohesion: 0.12
Nodes (19): range, AutoCosmosScraper, _price(), AsyncClient, Listing, Response, GET, retried on a network error or a 5xx; the last answer or error wins., (price, currency, partial reason) from the price blocks of a card or detail. A… (+11 more)

### Community 68 - "startup_warnings"
Cohesion: 0.16
Nodes (7): What this configuration leaves off (F7, punto 5): one line per channel, metric…, startup_warnings(), ConfigTests, F7, punto 4: the DB tests TRUNCATE, so they never touch the pilot's database., F7, punto 5: every channel or metric the .env leaves off is logged at startup., StartupWarningsTests, TestDatabaseGuardTests

### Community 69 - "pipeline/scoring.py"
Cohesion: 0.16
Nodes (10): Bootstrap of new or edited profiles (sección 5.7). A profile that was never…, Backfill one profile. Returns how many listings it matched., Bootstrap every profile that needs it. Returns how many were processed., rematch_profile(), run_pending(), datetime, The I/O around intelligence/: rows, comparables, fx and config in; matches out.…, F2 intelligence against the local Supabase Postgres (docs/TECHNICAL_PLAN.md,… (+2 more)

### Community 70 - "8. Capa LLM (§43, §44)"
Cohesion: 0.40
Nodes (5): 8.1 Interfaz, 8.2 `ClaudeCliProvider` (piloto), 8.3 `LocalProvider` (lanzamiento), 8.4 Flujo del modo asistido en la web, 8. Capa LLM (§43, §44)

### Community 71 - "createClient"
Cohesion: 0.10
Nodes (49): markOpened(), AppLayout(), answerInfluence(), currentStatus(), markSeen(), Purchase, recordPurchase(), setDiscardReason() (+41 more)

### Community 72 - "to_profile"
Cohesion: 0.14
Nodes (18): _put(), Any, Translate between the Telegram wizard's filter dict and search_profiles. The…, (marca, modelo) combinations of a wizard filter: one search profile each., Wizard dict + one (make, model) → search_profiles column values., search_profiles column values → the wizard dict the scheduler and handlers…, split_vehicles(), to_legacy() (+10 more)

### Community 74 - "Ese Auto · propuesta comercial y proyección"
Cohesion: 0.12
Nodes (16): 1. Qué vender, 2. Qué ya existe y qué falta, 3. Referencias de mercado, 4. Alternativas iniciales conservadas como referencia, 5. Oferta seleccionada en pesos: B, 6. Proyección a seis meses, 7. Validación y salida comercial, 8. Decisión a registrar (+8 more)

### Community 76 - "ClaudeCliProvider"
Cohesion: 0.17
Nodes (10): Runner, ClaudeCliProvider, parse_envelope(), Any, CatalogModel, M, The structured answer inside `--output-format json`'s envelope., parametrize (+2 more)

### Community 77 - "test_intelligence.py"
Cohesion: 0.12
Nodes (24): RedFlag, Weights, curves and thresholds of the intelligence layer (sección 6, Apéndice…, ago(), number(), Every user-facing string of the intelligence layer (§19, §24, §25). Kept in one…, One listing × one profile → everything a match row stores. Pure.…, _age_years(), description_known() (+16 more)

### Community 78 - "Comunes a cualquier ruta"
Cohesion: 0.12
Nodes (16): COM-02 · Una oferta coherente, COM-03 · Límites que siguen vigentes al vencer, COM-04 y COM-05 · Cobro y ciclo de vida, COM-06 · Autogestión, COM-07 · Producto que se puede prometer, COM-08 · Medir rentabilidad, no solo intención, COM-09 · Operación comercial, COM-10 · Salida controlada (+8 more)

### Community 79 - "Puesta en producción del piloto (F7)"
Cohesion: 0.13
Nodes (15): 10. Prueba de aceptación, 1. Dominio en Cloudflare, 2. Túnel de Cloudflare, 3. Resend (emails de login y de alertas), 4. API key de Anthropic (modo asistido), 5. Chat de Telegram para las alertas operativas, 6. Sesiones de MercadoLibre y Facebook, 7. Configuración (+7 more)

### Community 80 - "Automotive — Plan técnico del MVP"
Cohesion: 0.13
Nodes (15): 10. Backoffice y observabilidad (§45, §46), 11. Métricas y eventos (§35–38, §53), 12. Freemium (§33, §34), 14. Riesgos y decisiones abiertas, 15. Trazabilidad PRD → plan, 1. Punto de partida y gaps, 2. Arquitectura objetivo, 3. Estructura del repo (+7 more)

### Community 81 - "mercadolibre.py"
Cohesion: 0.14
Nodes (19): _blocked(), _browser_storage_state(), _build_url(), _extract_id(), _looks_like_login_wall(), _page_looks_like_login_wall(), _parse_card(), parse_search() (+11 more)

### Community 82 - "pgcase.py"
Cohesion: 0.18
Nodes (7): _database(), db_test_skip_reason(), Helpers for tests that need Postgres (see conftest.py for the event loop)., Why the DB tests can't run here, or None. They TRUNCATE tables, so they only…, Commercial access and payment boundaries against an isolated local database., MercadoPagoTests, Real isolated PostgreSQL checks for automatic access and hostile/repeated money…

### Community 83 - "rescore.py"
Cohesion: 0.18
Nodes (15): nightly_loop(), Any, datetime, Re-scoring existing matches (sección 6.1). * After enrichment: transmission or…, Re-score (search_profile_id, listing_id) pairs. Returns rows updated., Seconds from `now` to the next `hour` ("HH:MM", ART)., Re-score matches once a night, then purge stale listings; also, once at…, rescore() (+7 more)

### Community 84 - "v6.py"
Cohesion: 0.09
Nodes (45): BeautifulSoup, Browser, BrowserContext, AutoCosmos AR scraper. AutoCosmos exposes a public listings page at…, browser_context(), _ensure_browser(), Shared Playwright helpers — reuse a single browser instance across scrapers., Yield a fresh browser context. Closes context on exit; browser is reused. (+37 more)

### Community 85 - "test_llm_anthropic_api.py"
Cohesion: 0.13
Nodes (25): skipif, _items(), CatalogModel, vehicle_catalog as supabase/seed.sql inserts it, without a database. The LLM…, seed_catalog(), _year(), message(), provider() (+17 more)

### Community 86 - "database.ts"
Cohesion: 0.09
Nodes (22): DIGEST_SECTION, DigestItem, metadata, WebPayload, Inbox, InboxContext, InboxProvider(), Row (+14 more)

### Community 87 - "20261001120000_f4_web.sql"
Cohesion: 0.24
Nodes (7): public.dashboard_summary(), public.link_telegram(), public.match_cards, public.profiles, public.recent_opportunities(), public.search_result_counts(), public.search_results()

### Community 88 - "auth.ts"
Cohesion: 0.10
Nodes (29): ActionResult, shape(), SourceInput, updateConfig(), updateSource(), confirmPayment(), launchCommercialPilot(), recordRefund() (+21 more)

### Community 89 - "metrics/page.tsx"
Cohesion: 0.24
Nodes (12): CTA_EVENTS, day(), levelLabel(), median(), metadata, MetricsPage(), Rate(), WAITLIST (+4 more)

### Community 92 - "PROPUESTA_COMERCIAL.md"
Cohesion: 0.24
Nodes (4): Comprobaciones reproducibles, Ese Auto · implementación del lanzamiento comercial, Habilitación del entorno destino, Límites de esta entrega

### Community 93 - "Setup"
Cohesion: 0.18
Nodes (11): Backoffice y métricas (F6), Base de datos (Supabase), Correr el bot, Correr la web, Login de Facebook (una vez), MercadoLibre: sesion web, Migrar la base SQLite vieja, Modo asistido (LLM) (+3 more)

### Community 95 - "prompts/__init__.py"
Cohesion: 0.24
Nodes (8): catalog_text(), load(), parse_search_system(), parse_search_user(), CatalogModel, date, System prompts and user messages of the LLM layer, shared by every provider.…, One line per make: "Ford: Fiesta [S, SE, Titanium]; Focus [...]".

### Community 96 - "PriceRef"
Cohesion: 0.33
Nodes (5): fetch(), PriceRef, Any, Price Intelligence (§19, sección 6.2). The statistics come from the SQL…, public.comparables() for one listing. `cfg` overrides app_config.comparables.

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

### Community 102 - "test_notifications_templates.py"
Cohesion: 0.12
Nodes (10): notification(), Alert fixtures shared by the notification tests: the §22 examples., CopyLintTests, PRDCopyTests, Notification, Snapshots of the three alert types of §22 (+ the digest) on every channel. The…, §19: no "vale", "precio real", "tasación" in any alert., The §22 lines, in order, at the top of the Telegram message and the email text. (+2 more)

### Community 103 - "5. Pipeline de ingesta (§14, §15, §42)"
Cohesion: 0.25
Nodes (8): 5.1 Crawl targets, 5.2 Normalización, 5.3 Upsert, snapshots y detección de cambios, 5.4 Re-publicaciones (§15, heurística imperfecta aceptada), 5.5 Enrichment de la ficha, 5.6 Watchlist refresher (§30), 5.7 Bootstrap (evita el diluvio inicial; se conserva la idea actual), 5. Pipeline de ingesta (§14, §15, §42)

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

### Community 130 - "Notifier"
Cohesion: 0.12
Nodes (23): Evaluation, Notifier, batch_handler(), _key(), match_alert(), process_batch(), BatchHandler, HealthHandler (+15 more)

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
Cohesion: 0.40
Nodes (3): _merge(), Any, ConfigTests

### Community 182 - "Mercado Pago · cobro y acceso automático"
Cohesion: 0.18
Nodes (11): Acceso confirmado y preferencia Particular recuperada, Alta inicial con el MCP · 2/10/2026, Compra bloqueada por mezcla de participantes reales y de prueba, Configuración pendiente del entorno destino, Ensayo aislado · 3/10/2026, Estado actual · 3/10/2026, Implementación, Mercado Pago · cobro y acceso automático (+3 more)

## Knowledge Gaps
- **477 isolated node(s):** `public.vehicle_catalog`, `public.pipeline_errors`, `public.app_config`, `public.geocode_cache`, `public.fx_rates` (+472 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **22 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Listing` connect `Listing` to `AutoCosmosScraper`, `crawl.py`, `WebChannel`, `geo.py`, `migrate_sqlite.py`, `ingest.py`, `normalize_text`, `mercadolibre.py`, `main.py`, `test_ingest_postgres.py`, `v6.py`, `facebook.py`, `listing.py`, `TelegramLinkTests`?**
  _High betweenness centrality (0.041) - this node is a cross-community bridge._
- **Why does `PostgresTestCase` connect `test_ingest_postgres.py` to `.listing`, `pipeline/scoring.py`, `WebChannel`, `CommercialTests`, `migrate_sqlite.py`, `test_llm_jobs_postgres.py`, `pgcase.py`, `patch`, `listing.py`, `Listing`, `TelegramLinkTests`?**
  _High betweenness centrality (0.023) - this node is a cross-community bridge._
- **Why does `normalize_text()` connect `normalize_text` to `drafts.py`, `matching.py`, `crawl.py`, `test_notifications_templates.py`, `to_profile`, `load_models`, `test_intelligence.py`, `transmission.py`, `listing.py`?**
  _High betweenness centrality (0.020) - this node is a cross-community bridge._
- **Are the 41 inferred relationships involving `Links` (e.g. with `ResendEmailChannel` and `TelegramChannel`) actually correct?**
  _`Links` has 41 INFERRED edges - model-reasoned connections that need verification._
- **Are the 35 inferred relationships involving `Listing` (e.g. with `AutoCosmosScraper` and `Page`) actually correct?**
  _`Listing` has 35 INFERRED edges - model-reasoned connections that need verification._
- **What connects `public.vehicle_catalog`, `public.pipeline_errors`, `public.app_config` to the rest of the system?**
  _477 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `telegram.py` be split into smaller, more focused modules?**
  _Cohesion score 0.08305647840531562 - nodes in this community are weakly interconnected._
# Graph Report - AutoMotive  (2026-10-06)

## Corpus Check
- 410 files · ~279,086 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 3641 nodes · 9218 edges · 209 communities (177 shown, 32 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 533 edges (avg confidence: 0.55)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `83b8153f`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Links
- description_facts.py
- Event
- ListingDetail
- requireUser
- createAdminClient
- Target
- meta-pixel.tsx
- NotificationsCase
- format.ts
- app/listings/[id]/page.tsx
- ListingFacts
- test_llm_jobs_postgres.py
- notifications.py
- profiles.py
- ingest.py
- listing.py
- settings/page.tsx
- enrich.py
- searches/[id]/page.tsx
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
- listings/actions.ts
- main.py
- test_ingest_postgres.py
- test_llm_claude_cli.py
- PriceRef
- listings.py
- matching.py
- templates.py
- admin/actions.ts
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
- rescore.py
- test_llm_openai_api.py
- mercadopago-server.ts
- 20261007120000_ese_auto_commercial.sql
- createClient
- scheduler.py
- metrics/page.tsx
- 20261003120000_f6_backoffice_metrics.sql
- SourceAlerts
- components.json
- 20260927120100_rls.sql
- drafts.py
- Listing
- CollectorChecksTests
- .listing
- Automotive — web
- Site
- startup_warnings
- load_models
- matches.py
- Comparación de modelos para búsqueda asistida
- provider
- CommercialTests
- Ese Auto · propuesta comercial y proyección
- database.ts
- patch
- Comunes a cualquier ruta
- Puesta en producción del piloto (F7)
- Automotive — Plan técnico del MVP
- mercadolibre.py
- MercadoPagoTests
- pgcase.py
- MigrateSqliteTests
- test_description_intelligence.py
- description.ts
- 20261001120000_f4_web.sql
- test_intelligence.py
- TemplateSnapshotTests
- AvailabilityTests
- RuntimeError
- PROPUESTA_COMERCIAL.md
- Setup
- prompts/__init__.py
- auth.ts
- 13. Roadmap por fases
- scripts
- 40. Modelo conceptual de datos
- toggle-group.tsx
- normalize_listing
- service.py
- 5. Pipeline de ingesta (§14, §15, §42)
- connection
- DeliveryTests
- RedFlagTests
- GPT-6 Luna en el worker
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
- KavakScraper
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
- 6. Intelligence (§16–20, §24, §25, §44)
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
- .from_app_config
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
- collector_checks
- LocalProvider
- ResendEmailChannelTests
- run
- IA sobre descripciones
- watchdog.py
- Confirmación consumida por una vista previa
- 7. Motor de notificaciones (§21, §22, §32, §47)

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
- `AdminLayout()` --calls--> `requireAdmin()`  [EXTRACTED]
  web/app/admin/layout.tsx → web/lib/admin.ts
- `ConfirmEmailPage()` --calls--> `safeNext()`  [EXTRACTED]
  web/app/auth/confirm-email/page.tsx → web/lib/navigation.ts
- `ResetPasswordPage()` --calls--> `createClient()`  [EXTRACTED]
  web/app/auth/reset-password/page.tsx → web/lib/supabase/server.ts
- `LoginPage()` --calls--> `safeNext()`  [EXTRACTED]
  web/app/login/page.tsx → web/lib/navigation.ts

## Import Cycles
- None detected.

## Communities (209 total, 32 thin omitted)

### Community 0 - "Links"
Cohesion: 0.08
Nodes (29): CallbackQueryHandler, Update, _allowed(), help_(), invalid_code_text(), linked_text(), The Telegram bot after F4: it links the account and answers alert buttons.…, register() (+21 more)

### Community 1 - "description_facts.py"
Cohesion: 0.07
Nodes (40): input_hash(), _after_label(), Amount, _amounts(), _before_label(), _close(), _currency(), DescriptionFacts (+32 more)

### Community 2 - "Event"
Cohesion: 0.07
Nodes (39): at_least(), rank(), Opportunity levels (§20, sección 6.4), thresholds from…, Audience, classify(), decide(), decide_all(), Decision (+31 more)

### Community 3 - "ListingDetail"
Cohesion: 0.13
Nodes (7): ListingDetail, Page, What fetch_detail() found at a listing's URL (sección 5.5). `gone` means the…, Download the ad's own page, with the source's login-wall and session checks,…, Read the ad's page: description, version, transmission, seller type, every…, What raw_pages keeps of a detail page: enough for parse_detail()., DescriptionIntelligencePostgresTests

### Community 4 - "requireUser"
Cohesion: 0.08
Nodes (52): confirmPayment(), launchCommercialPilot(), recordRefund(), BillingPage(), metadata, joinWaitlist(), reportVisibleResults(), checkPayment() (+44 more)

### Community 5 - "createAdminClient"
Cohesion: 0.07
Nodes (60): ConfigPage(), HINTS, metadata, ErrorsPage(), metadata, metadata, MatchInspector(), metadata (+52 more)

### Community 6 - "Target"
Cohesion: 0.10
Nodes (31): finish_run(), log_error(), Observability (sección 10, §46): collector_runs, pipeline_errors and source…, Close a run and keep the source's health counters in step. Returns the source's…, Record a pipeline error. Never raises: observability must not break the…, start_run(), The crawl target a card was found through: a hint, never the truth., Target (+23 more)

### Community 7 - "meta-pixel.tsx"
Cohesion: 0.06
Nodes (36): markSeen(), metadata, mono, sans, viewport, metadata, ViewTracker(), Consent (+28 more)

### Community 8 - "NotificationsCase"
Cohesion: 0.14
Nodes (13): ResendEmailChannel, MatchCandidate, A new, non-backfill match the crawl just stored., AlertTypesTests, DailyCapAndDigestTests, DedupeTests, FakeBot, NotificationsCase (+5 more)

### Community 9 - "format.ts"
Cohesion: 0.11
Nodes (37): AdminListingPage(), escapeLike(), ListingsPage(), metadata, ListingPage(), PriceVerdict(), similarListings(), metadata (+29 more)

### Community 10 - "app/listings/[id]/page.tsx"
Cohesion: 0.07
Nodes (39): markFor(), metadata, plain(), priceHistory(), SAME, SCORE_PART, ScoreInWords(), Similar (+31 more)

### Community 11 - "ListingFacts"
Cohesion: 0.10
Nodes (32): AsyncAnthropic, AnthropicApiProvider, CatalogModel, M, The Claude API with an API key (F7, punto 6): the provider for serving the…, `claude -p` as the pilot's LLM (sección 8.2). claude -p --output-format json…, The LLM layer (sección 8): providers behind one interface. provider.py…, A local LLM for the launch (sección 8.3) — stub. The plan: an OpenAI-compatible… (+24 more)

### Community 12 - "test_llm_jobs_postgres.py"
Cohesion: 0.16
Nodes (6): LlmJobsCase, QueueTests, The llm_jobs queue against the local Supabase Postgres (sección 8.4): what the…, What the web can do with the user's session (sección 4.4)., Run `sql` as the signed-in web user (role authenticated, RLS on)., WebAccessTests

### Community 13 - "notifications.py"
Cohesion: 0.08
Nodes (38): apply_telegram_action(), delivery_payload(), digest_users(), insert_decisions(), insert_digest(), insert_event(), interactions(), listing_audiences() (+30 more)

### Community 14 - "profiles.py"
Cohesion: 0.13
Nodes (23): _put(), Any, Translate between the Telegram wizard's filter dict and search_profiles. The…, (marca, modelo) combinations of a wizard filter: one search profile each., Wizard dict + one (make, model) → search_profiles column values., search_profiles column values → the wizard dict the scheduler and handlers…, split_vehicles(), to_legacy() (+15 more)

### Community 15 - "ingest.py"
Cohesion: 0.11
Nodes (33): attrs_hash(), _hash(), Any, text_hash(), _empty(), _facts(), _geocode_rows(), ingest_rows() (+25 more)

### Community 16 - "listing.py"
Cohesion: 0.09
Nodes (33): vehicle_catalog: canonical make/model/trim names. The catalog is small (a few…, Normalization v2: a collector Listing → a `listings` row (sección 5.2). Pure:…, normalize_brand(), normalize_model(), normalize_text(), Brand/model normalization so comparables match across sources. Used both at…, Model names — strip extra trim qualifiers leaving only the base model., _strip_accents() (+25 more)

### Community 17 - "settings/page.tsx"
Cohesion: 0.11
Nodes (24): RFC-8058, AdminLayout(), metadata, POST(), metadata, ConfirmEmailPage(), metadata, metadata (+16 more)

### Community 18 - "enrich.py"
Cohesion: 0.08
Nodes (41): Refresher, mark_detail_checked(), compress(), decompress(), iter_for_reparse(), mark_parsed(), purge_older_than(), raw_pages: the last detail page of each listing, compressed (normalization v3).… (+33 more)

### Community 19 - "searches/[id]/page.tsx"
Cohesion: 0.06
Nodes (47): Dashboard(), metadata, trackProCta(), deleteSearch(), setSearchEnabled(), setSearchFrequency(), COUNT_KEY, EMPTY (+39 more)

### Community 20 - "search-form.tsx"
Cohesion: 0.04
Nodes (88): AssistedStart, canonical(), enabledSources(), escapeLike(), jobText(), Preview, PreviewListing, previewSearch() (+80 more)

### Community 21 - "db.ts"
Cohesion: 0.11
Nodes (25): SEARCH_FILTERS, alertedUser(), signIn(), ask(), setHeartbeat(), signIn(), globalSetup(), main() (+17 more)

### Community 22 - "facebook.py"
Cohesion: 0.08
Nodes (35): CollectorBlocked, The source answered with a login wall, a security challenge or no session. The…, _after_colon(), _city_slug(), _city_slug_from_origin(), _extract_location(), FacebookMarketplaceScraper, _looks_like_location() (+27 more)

### Community 23 - "resolve_price"
Cohesion: 0.15
Nodes (7): PriceResolution, What resolve_price() concluded, stored in description_facts.price_check. The…, The listing's effective price (sección 5.2, v3). `published`/`currency`: the…, resolve_price(), _usd(), _resolve(), ResolvePriceTests

### Community 24 - "fiesta_listing"
Cohesion: 0.13
Nodes (15): timedelta, evaluate(), match(), The reasons if every hard filter is ok or unknown; None if one fails., CurrencyTests, fiesta_listing(), fiesta_profile(), GoldenFixtureTests (+7 more)

### Community 25 - "LLMProvider"
Cohesion: 0.09
Nodes (28): claim(), expire(), finish(), Any, AsyncConnection, llm_jobs: the queue between the web and the LLM layer (sección 8.4). The web…, The oldest queued job of `kinds`, now 'running'; None if there is none., done' with its output, or 'failed' with the error (never both). (+20 more)

### Community 26 - "test_llm_drafts.py"
Cohesion: 0.13
Nodes (28): _items(), CatalogModel, vehicle_catalog as supabase/seed.sql inserts it, without a database. The LLM…, seed_catalog(), _year(), draft(), norm(), normalization/drafts.py: the deterministic step after the LLM (sección 8.4,… (+20 more)

### Community 27 - "platform_health.py"
Cohesion: 0.27
Nodes (13): exclusive_check(), load_state(), main(), notify_changes(), publish_snapshot(), Path, Platform and collector health, run by the existing five-minute watchdog. python…, OS lock releases on process exit, including an interrupted/crashed check. (+5 more)

### Community 29 - "test_llm_contract.py"
Cohesion: 0.10
Nodes (23): fixture, skipif, build_provider(), The provider `LLM_PROVIDER` names., load_recordings(), Any, Path, {user text: trimmed envelope}. (+15 more)

### Community 30 - "PRD — Automotive"
Cohesion: 0.05
Nodes (37): 11. Principios de producto, 13. Concepto de Search Profile, 14. Ingesta de publicaciones, 17. Opportunity Score, 18. Componentes iniciales del Opportunity Score, 19. Price Intelligence, 1. Resumen ejecutivo, 20. Niveles de oportunidad (+29 more)

### Community 31 - "listings/actions.ts"
Cohesion: 0.12
Nodes (23): answerInfluence(), currentStatus(), Purchase, recordPurchase(), setDiscardReason(), setSaved(), setStatus(), Supabase (+15 more)

### Community 32 - "main.py"
Cohesion: 0.05
Nodes (51): Browser, _ensure_browser(), Shared Playwright helpers — reuse a single browser instance across scrapers., shutdown(), _collector_loop(), AbstractEventLoop, Any, T (+43 more)

### Community 33 - "test_ingest_postgres.py"
Cohesion: 0.08
Nodes (33): BaseScraper, Page, TelegramChannel, WebChannel, Notifier, ingest(), normalize → geocode → upsert. The whole batch is one transaction., PostgresTestCase (+25 more)

### Community 34 - "test_llm_claude_cli.py"
Cohesion: 0.09
Nodes (36): BaseModel, Runner, ClaudeCliProvider, parse_envelope(), Any, CatalogModel, M, Run the CLI once and return its stdout. Raises LLMTimeout / LLMError. (+28 more)

### Community 35 - "PriceRef"
Cohesion: 0.15
Nodes (14): AST, fetch(), PriceRef, Any, Price Intelligence (§19, sección 6.2). The statistics come from the SQL…, public.comparables() for one listing. `cfg` overrides app_config.comparables., CopyLintTests, _docstring_nodes() (+6 more)

### Community 36 - "listings.py"
Cohesion: 0.10
Nodes (32): enrichment_queue(), find_repost_of(), finish_description_run(), insert_listing(), insert_snapshot(), lock_existing(), mark_gone(), matched_recheck_queue() (+24 more)

### Community 37 - "matching.py"
Cohesion: 0.11
Nodes (30): Result, ago(), money(), number(), Every user-facing string of the intelligence layer (§19, §24, §25). Kept in one…, USD 10.300 · ARS 12.500.000 (Argentine thousands separator)., _choice(), distance_km() (+22 more)

### Community 38 - "templates.py"
Cohesion: 0.11
Nodes (33): age_line(), ago_long(), before_after(), Button, Content, _digest(), DigestItem, email() (+25 more)

### Community 39 - "admin/actions.ts"
Cohesion: 0.21
Nodes (10): ActionResult, shape(), SourceInput, updateConfig(), updateSource(), ConfigEditor(), SourceForm(), Checkbox() (+2 more)

### Community 40 - "AutoCosmosScraper"
Cohesion: 0.24
Nodes (9): AutoCosmosScraper, _price(), AsyncClient, Listing, Response, GET, retried on a network error or a 5xx; the last answer or error wins., (price, currency, partial reason) from the price blocks of a card or detail. A…, _slug() (+1 more)

### Community 41 - "geo.py"
Cohesion: 0.12
Nodes (20): Coords, _fallback_can_stand_alone(), filter_listings_by_radius(), geocode_location(), _geocode_nominatim(), haversine_km(), _looks_like_non_location_query(), _lookup_known_location() (+12 more)

### Community 42 - "migrate_sqlite.py"
Cohesion: 0.17
Nodes (11): connection_kwargs(), Any, LoadEmailsTests, load_emails(), main(), Migration, AsyncConnection, Copy the SQLite bot database into Supabase Postgres (docs/TECHNICAL_PLAN.md,… (+3 more)

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

### Community 51 - "rescore.py"
Cohesion: 0.11
Nodes (27): build_items(), digest_loop(), Any, datetime, Daily digest (§32, sección 7.2). Every day at app_config.digest_hour (ART,…, Run the digest every day at digest_hour. At startup, if today's hour already…, Digest items from waiting rows and the day's top matches: waiting rows always…, Build today's digests. Returns how many were created (then delivered). (+19 more)

### Community 52 - "test_llm_openai_api.py"
Cohesion: 0.20
Nodes (20): answer(), provider(), parametrize, Responses wire contract and failure handling, with no live API calls. Replays…, replay(), test_connection_error_is_retried_once_and_sanitized(), test_golden_wire_contract(), test_http_errors_are_safe_and_retry_only_transient() (+12 more)

### Community 53 - "mercadopago-server.ts"
Cohesion: 0.09
Nodes (48): GET(), POST(), reply(), checkoutUrl(), paymentPeriod(), sameSecret(), api(), applyPayment() (+40 more)

### Community 54 - "20261007120000_ese_auto_commercial.sql"
Cohesion: 0.09
Nodes (8): llm_jobs_guard_commercial, matches_guard_commercial, public.commercial_payments, public.guard_assisted_commercial_access(), public.guard_match_access(), public.plan_limits_for(), public.profiles, public.refund_commercial_payment()

### Community 55 - "createClient"
Cohesion: 0.10
Nodes (33): declineRenewal(), FOLLOWED, SavedPage(), GET(), HEAD(), GET(), HEAD(), POST() (+25 more)

### Community 56 - "scheduler.py"
Cohesion: 0.10
Nodes (28): Evaluation, Bootstrap of new or edited profiles (sección 5.7). A profile that was never…, Backfill one profile. Returns how many listings it matched., Bootstrap every profile that needs it. Returns how many were processed., rematch_profile(), run_pending(), batch_handler(), _key() (+20 more)

### Community 57 - "metrics/page.tsx"
Cohesion: 0.22
Nodes (13): CTA_EVENTS, day(), levelLabel(), median(), metadata, MetricsPage(), Rate(), WAITLIST (+5 more)

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

### Community 62 - "drafts.py"
Cohesion: 0.19
Nodes (18): trim_envelope(), _km(), _money(), normalize_draft(), normalize_drafts(), _positive(), Any, CatalogModel (+10 more)

### Community 63 - "Listing"
Cohesion: 0.11
Nodes (11): Listing, Run keyword detection over the title and tag the listing. Statistical detection…, One ad as a collector read it, before normalization. `marca`/`modelo`/`version`…, AlertRepoTests, GeocodeAndConfigTests, _listing(), The bot's data layer against a real Postgres with the supabase/ migrations. Run…, /start <code> (public.link_telegram, F4). (+3 more)

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
Cohesion: 0.16
Nodes (7): What this configuration leaves off (F7, punto 5): one line per channel, metric…, startup_warnings(), ConfigTests, F7, punto 4: the DB tests TRUNCATE, so they never touch the pilot's database., F7, punto 5: every channel or metric the .env leaves off is logged at startup., StartupWarningsTests, TestDatabaseGuardTests

### Community 69 - "load_models"
Cohesion: 0.24
Nodes (8): load_models(), match_model(), AsyncConnection, CatalogModel, Model-level rows with their trims, aliases and production years., Canonical (make, model), or None if it isn't in the catalog. The model matches…, resolve_make_model(), CatalogMatchTests

### Community 70 - "matches.py"
Cohesion: 0.17
Nodes (19): _existing(), filter_unseen(), insert_legacy_matches(), _keys(), mark_seen(), matched_by_other_profiles(), matches_of_listings(), Any (+11 more)

### Community 71 - "Comparación de modelos para búsqueda asistida"
Cohesion: 0.17
Nodes (12): APIs: estructura de salida y razonamiento, APIs: precios comparables, Comparación de modelos para búsqueda asistida, Decisión económica provisional, DeepSeek y Kimi locales, Estado del trabajo en el proyecto, Hardware local y otros modelos abiertos, Jev aplicado al contrato (+4 more)

### Community 72 - "provider"
Cohesion: 0.27
Nodes (10): message(), provider(), parametrize, Request, Response, replay(), test_golden_phrases(), test_http_errors() (+2 more)

### Community 74 - "Ese Auto · propuesta comercial y proyección"
Cohesion: 0.12
Nodes (16): 1. Qué vender, 2. Qué ya existe y qué falta, 3. Referencias de mercado, 4. Alternativas iniciales conservadas como referencia, 5. Oferta seleccionada en pesos: B, 6. Proyección a seis meses, 7. Validación y salida comercial, 8. Decisión a registrar (+8 more)

### Community 76 - "database.ts"
Cohesion: 0.14
Nodes (12): Filters, metadata, NotificationTable(), BillingCheckoutRow, CompositeTypes, Constants, DatabaseWithoutInternals, DefaultSchema (+4 more)

### Community 77 - "patch"
Cohesion: 0.14
Nodes (20): patch, parse_publication_date(), parse_relative_date(), Any, Return a unix timestamp inferred from a Spanish relative-date string., Explicit publication date (ISO, Argentine calendar date or relative). Date-only…, _strip_accents(), _is_recent() (+12 more)

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
Cohesion: 0.06
Nodes (67): BeautifulSoup, AutoCosmos AR scraper. AutoCosmos exposes a public listings page at…, browser_context(), BrowserContext, Yield a fresh browser context. Closes context on exit; browser is reused., publication_date(), Parse Spanish relative date strings shown by AR car classifieds. Examples…, Read only publication-specific fields of the current ad/card. The caller… (+59 more)

### Community 83 - "pgcase.py"
Cohesion: 0.28
Nodes (6): _database(), db_test_skip_reason(), Helpers for tests that need Postgres (see conftest.py for the event loop)., Why the DB tests can't run here, or None. They TRUNCATE tables, so they only…, Commercial access and payment boundaries against an isolated local database., Real isolated PostgreSQL checks for automatic access and hostile/repeated money…

### Community 84 - "MigrateSqliteTests"
Cohesion: 0.36
Nodes (3): _make_sqlite(), MigrateSqliteTests, Path

### Community 85 - "test_description_intelligence.py"
Cohesion: 0.18
Nodes (15): DescriptionLLM, Read each complete description once, within a persistent daily budget., None when app_config.description_facts.llm is off or no provider is configured., answer(), read(), test_an_anticipo_cannot_become_the_cash_price(), test_cache_uses_title_description_and_analysis_version(), test_changed_description_invalidates_old_claims_even_when_new_text_has_no_facts() (+7 more)

### Community 86 - "description.ts"
Cohesion: 0.19
Nodes (15): DescriptionPriceContext(), SellerDescription(), FUEL, TRANSMISSION, BOOL, DescriptionListing, folded(), LABEL (+7 more)

### Community 87 - "20261001120000_f4_web.sql"
Cohesion: 0.24
Nodes (7): public.dashboard_summary(), public.link_telegram(), public.match_cards, public.profiles, public.recent_opportunities(), public.search_result_counts(), public.search_results()

### Community 88 - "test_intelligence.py"
Cohesion: 0.12
Nodes (24): RedFlag, Weights, curves and thresholds of the intelligence layer (sección 6, Apéndice…, One listing × one profile → everything a match row stores. Pure.…, _age_years(), description_known(), description_mismatches(), Any, datetime (+16 more)

### Community 91 - "RuntimeError"
Cohesion: 0.10
Nodes (13): RuntimeError, Page, _blocked(), _ensure_context(), mercadolibre_context(), BrowserContext, Tecc's Mercado Libre transport: installed Chrome with a dedicated profile. The…, Serialize page operations on one Chrome context for the worker lifetime. (+5 more)

### Community 92 - "PROPUESTA_COMERCIAL.md"
Cohesion: 0.24
Nodes (4): Comprobaciones reproducibles, Ese Auto · implementación del lanzamiento comercial, Habilitación del entorno destino, Límites de esta entrega

### Community 93 - "Setup"
Cohesion: 0.18
Nodes (11): Backoffice y métricas (F6), Base de datos (Supabase), Correr el bot, Correr la web, Login de Facebook (una vez), MercadoLibre: sesion web, Migrar la base SQLite vieja, Modo asistido (LLM) (+3 more)

### Community 95 - "prompts/__init__.py"
Cohesion: 0.24
Nodes (8): catalog_text(), load(), parse_search_system(), parse_search_user(), CatalogModel, date, System prompts and user messages of the LLM layer, shared by every provider.…, One line per make: "Ford: Fiesta [S, SE, Titanium]; Focus [...]".

### Community 96 - "auth.ts"
Cohesion: 0.15
Nodes (18): AppLayout(), active(), BottomNav(), ITEMS, TopNav(), PlanStatus(), isAdmin, currentUser (+10 more)

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

### Community 101 - "normalize_listing"
Cohesion: 0.10
Nodes (21): NamedTuple, FxQuote, fingerprint(), listing_facts(), normalize_listing(), price_usd(), CatalogModel, Listing (+13 more)

### Community 102 - "service.py"
Cohesion: 0.08
Nodes (30): InlineKeyboardMarkup, parse(), Inline buttons of a Telegram alert (sección 7.2): ⭐ Me interesa · ✖ Descartar.…, Channel, Notification, Protocol, The channel interface (sección 7.2): the engine never knows how an alert…, A notifications row, with the user's contact data, ready to send. (+22 more)

### Community 103 - "5. Pipeline de ingesta (§14, §15, §42)"
Cohesion: 0.25
Nodes (8): 5.1 Crawl targets, 5.2 Normalización, 5.3 Upsert, snapshots y detección de cambios, 5.4 Re-publicaciones (§15, heurística imperfecta aceptada), 5.5 Enrichment de la ficha, 5.6 Watchlist refresher (§30), 5.7 Bootstrap (evita el diluvio inicial; se conserva la idea actual), 5. Pipeline de ingesta (§14, §15, §42)

### Community 104 - "connection"
Cohesion: 0.07
Nodes (42): AsyncConnectionPool, Postgres (Supabase) data access for the worker. Replaces the old SQLite module.…, close_pool(), connection(), open_pool(), AsyncConnection, Async Postgres connection pool (psycopg 3), one per worker process. The worker…, Open the process-wide pool (idempotent). (+34 more)

### Community 107 - "GPT-6 Luna en el worker"
Cohesion: 0.29
Nodes (5): Completar la clave, Comprobar y arrancar, GPT-6 Luna en el worker, Parámetros y fallos, Validación disponible

### Community 108 - "test_ops.py"
Cohesion: 0.14
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

### Community 129 - "KavakScraper"
Cohesion: 0.20
Nodes (6): Apply user filters that the source could not enforce server-side., KavakScraper, Page, _slug(), KavakFilterTests, Listing

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

### Community 143 - "assess"
Cohesion: 0.18
Nodes (13): assess(), Any, datetime, PriceRef, The columns of `matches` this evaluation fills., Match, score, flags and questions whether or not it matches (explain_match)., explain(), load() (+5 more)

### Community 144 - "Descripciones como fuente de datos"
Cohesion: 0.40
Nodes (4): Datos y procedencia, Descripciones como fuente de datos, Flujo, Validación y operación

### Community 145 - "8. Capa LLM (§43, §44)"
Cohesion: 0.40
Nodes (5): 8.1 Interfaz, 8.2 `ClaudeCliProvider` (piloto), 8.3 `LocalProvider` (lanzamiento), 8.4 Flujo del modo asistido en la web, 8. Capa LLM (§43, §44)

### Community 146 - "6. Intelligence (§16–20, §24, §25, §44)"
Cohesion: 0.29
Nodes (7): 6.1 Matching, 6.2 Comparables y Price Intelligence (§19), 6.3 Opportunity Score 0–100 (§17–18), 6.4 Niveles (§20), 6.5 Red flags (§24), 6.6 Preguntas al vendedor (§25), 6. Intelligence (§16–20, §24, §25, §44)

### Community 160 - "20261010120000_mvp_email_free_trial.sql"
Cohesion: 0.83
Nodes (3): public.enable_free_trial(), public.profiles, public.search_profiles

### Community 180 - "20261008120000_mercadopago.sql"
Cohesion: 0.39
Nodes (5): profiles_guard_billing_delete, public.apply_mercadopago_payment(), public.billing_checkouts, public.commercial_payments, public.guard_billing_account_delete()

### Community 182 - "Mercado Pago · cobro y acceso automático"
Cohesion: 0.14
Nodes (14): Acceso confirmado y preferencia Particular recuperada, Alta inicial con el MCP · 2/10/2026, Cobertura del ensayo que continúa pendiente, Compra bloqueada por mezcla de participantes reales y de prueba, Ensayo aislado · 3/10/2026, Estado actual · 5/10/2026, Historial de preparación · 3/10/2026, Implementación (+6 more)

### Community 183 - ".from_app_config"
Cohesion: 0.40
Nodes (3): _merge(), Any, ConfigTests

### Community 184 - "simulate_alert.py"
Cohesion: 0.38
Nodes (5): main(), Simulate the arrival of a listing: what the crawl does with a new listing of a…, Returns the notifications the listing produced., simulate(), SimulatedEmail

### Community 185 - "targets.py"
Cohesion: 0.24
Nodes (9): due_targets(), enabled_sources(), finish_target(), Any, crawl_targets and the source cadence they run on (sección 5.1)., Make crawl_targets mirror `specs` (pipeline.crawl.TargetSpec): upsert the…, Active targets of enabled sources whose next_run_at has come (or never ran)., next_run_at = now + the source's interval (sección 5.1). A failed run retries… (+1 more)

### Community 200 - "collector_checks"
Cohesion: 0.40
Nodes (3): HealthDatabaseTests, collector_checks(), datetime

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

### Community 205 - "watchdog.py"
Cohesion: 0.21
Nodes (12): beat(), last_beat(), datetime, The worker's heartbeat (F7, punto 8): one row in worker_heartbeat, updated…, started_now(), inspect_database(), check_db_and_worker(), load_state() (+4 more)

### Community 206 - "Confirmación consumida por una vista previa"
Cohesion: 0.40
Nodes (4): Confirmación consumida por una vista previa, Corrección, Evidencia de producción, Validación y alcance

### Community 207 - "7. Motor de notificaciones (§21, §22, §32, §47)"
Cohesion: 0.50
Nodes (4): 7.1 Decisión, 7.2 Canales, 7.3 Tracking de aperturas y clics, 7. Motor de notificaciones (§21, §22, §32, §47)

## Knowledge Gaps
- **541 isolated node(s):** `public.vehicle_catalog`, `public.pipeline_errors`, `public.app_config`, `public.geocode_cache`, `public.fx_rates` (+536 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **32 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Listing` connect `Listing` to `KavakScraper`, `test_ingest_postgres.py`, `ListingDetail`, `normalize_listing`, `Target`, `AutoCosmosScraper`, `geo.py`, `migrate_sqlite.py`, `ingest.py`, `listing.py`, `mercadolibre.py`, `enrich.py`, `test_description_intelligence.py`, `facebook.py`?**
  _High betweenness centrality (0.034) - this node is a cross-community bridge._
- **Why does `Links` connect `Links` to `main.py`, `test_ingest_postgres.py`, `templates.py`, `service.py`, `NotificationsCase`, `ResendEmailChannelTests`, `test_mvp_worker.py`, `PRDCopyTests`, `TemplateSnapshotTests`?**
  _High betweenness centrality (0.026) - this node is a cross-community bridge._
- **Why does `connection()` connect `connection` to `listings.py`, `matches.py`, `Target`, `notifications.py`, `profiles.py`, `enrich.py`, `targets.py`, `RuntimeError`?**
  _High betweenness centrality (0.023) - this node is a cross-community bridge._
- **Are the 42 inferred relationships involving `Links` (e.g. with `ResendEmailChannel` and `TelegramChannel`) actually correct?**
  _`Links` has 42 INFERRED edges - model-reasoned connections that need verification._
- **Are the 36 inferred relationships involving `Listing` (e.g. with `AutoCosmosScraper` and `Page`) actually correct?**
  _`Listing` has 36 INFERRED edges - model-reasoned connections that need verification._
- **What connects `public.vehicle_catalog`, `public.pipeline_errors`, `public.app_config` to the rest of the system?**
  _541 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Links` be split into smaller, more focused modules?**
  _Cohesion score 0.08078431372549019 - nodes in this community are weakly interconnected._
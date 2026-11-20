
export type Json = string | number | boolean | null | { [key: string]: Json | undefined } | Json[]

type BillingCheckoutRow = { id: string; user_id: string; offer: string; offer_version: string; amount: number; currency: string; billing_email: string; status: string; provider_id: string | null; init_point: string | null; created_at: string; last_synced_at: string | null; sync_error: string | null; next_payment_at: string | null; ad_attribution: Json | null; founder_number: number | null; founder_price_until: string | null; founder_offer: boolean }

export type Database = {

  "public": {
          Tables: {
      admin_metric_observation: {
        Row: { singleton: boolean; first_value_tracking_since: string }
        Insert: never
        Update: never
        Relationships: []
      }
      admin_unmet_demand: {
        Row: { search_profile_id: number; user_id: string; make: string | null; model: string | null; zone_label: string | null; result_count: number; market: number; market_in_zone: number; relaxed_zone: number; relaxed_price: number; relaxed_trim: number; relaxed_year: number; cause: string; computed_at: string }
        Insert: never
        Update: never
        Relationships: []
      }
      admin_unmet_demand_run: {
        Row: { singleton: boolean; computed_at: string; duration_ms: number; searches: number; skipped_model_less: number; max_results: number; min_age_hours: number; cap_enforced: boolean; hidden_by_level: Json; hidden_accounts: number }
        Insert: never
        Update: never
        Relationships: []
      }
      admin_search_observations: {
        Row: { search_profile_id: number; user_id: string; search_created_at: string; first_good_at: string | null }
        Insert: never
        Update: never
        Relationships: []
      }
      admin_config_audit: {
        Row: { id: number; target_type: string; target_key: string; actor_id: string; actor_email: string | null; before_value: Json; after_value: Json; created_at: string }
        Insert: never
        Update: never
        Relationships: []
      }
      // Prospección (20261225120000_prospecting): service role only; written by worker/prospector and admin_prospect_action.
      prospects: {
        Row: { id: number; prospect_key: string; seller_keys: string[]; kind: string; display_name: string; first_name: string | null; sources: string[]; province_id: string | null; region: string | null; locality: string | null; phone: string | null; phone_source: string | null; phone_evidence: string | null; phone_checked_at: string | null; status: string; step_sent: number; next_due_on: string | null; listing_count: number | null; first_sent_at: string | null; last_sent_at: string | null; replied_at: string | null; closed_at: string | null; notes: string | null; created_at: string; updated_at: string }
        Insert: never
        Update: never
        Relationships: []
      }
      prospect_messages: {
        Row: { id: number; prospect_id: number; step: string; batch_date: string; status: string; facts: Json; variants: Json; chosen_index: number | null; final_text: string | null; edited: boolean; hook_type: string | null; hook_listing_id: number | null; hook_url: string | null; review: Json; model: string | null; sent_at: string | null; created_at: string; updated_at: string }
        Insert: never
        Update: never
        Relationships: [{ foreignKeyName: "prospect_messages_prospect_id_fkey"; columns: ["prospect_id"]; isOneToOne: false; referencedRelation: "prospects"; referencedColumns: ["id"] }]
      }
      prospect_events: {
        Row: { id: number; prospect_id: number; message_id: number | null; kind: string; note: string | null; actor_id: string | null; created_at: string }
        Insert: never
        Update: never
        Relationships: [{ foreignKeyName: "prospect_events_prospect_id_fkey"; columns: ["prospect_id"]; isOneToOne: false; referencedRelation: "prospects"; referencedColumns: ["id"] }]
      }
      admin_experiments: {
        Row: { slug: string; title: string; config_key: string | null; hypothesis: string; metric: string; baseline_text: string | null; baseline_value: number | null; started_at: string | null; review_at: string | null; status: string; result_text: string | null; result_value: number | null; verdict_note: string | null; decided_at: string | null; created_at: string; updated_at: string }
        Insert: never
        Update: never
        Relationships: []
      }
      lifecycle_emails: {
        Row: { id: number; user_id: string; kind: string; event_key: string; search_profile_id: number | null; payload: Json; target: string; status: string; attempts: number; error: string | null; provider_id: string | null; created_at: string; sent_at: string | null; clicked_at: string | null; opened_at: string | null }
        Insert: { user_id: string; kind: string; event_key: string; target: string; search_profile_id?: number | null; payload?: Json; status?: string; attempts?: number; error?: string | null; provider_id?: string | null; created_at?: string; sent_at?: string | null; clicked_at?: string | null }
        Update: { status?: string; attempts?: number; error?: string | null; provider_id?: string | null; sent_at?: string | null; clicked_at?: string | null }
        Relationships: []
      }
      email_feedback: {
        Row: { id: number; lifecycle_email_id: number; user_id: string; reason: string; comment: string | null; created_at: string; updated_at: string }
        Insert: { lifecycle_email_id: number; user_id: string; reason: string; comment?: string | null; created_at?: string; updated_at?: string }
        Update: { reason?: string; comment?: string | null; updated_at?: string }
        Relationships: [{ foreignKeyName: "email_feedback_lifecycle_email_id_fkey"; columns: ["lifecycle_email_id"]; isOneToOne: true; referencedRelation: "lifecycle_emails"; referencedColumns: ["id"] }]
      }
      account_proofs: {
        Row: { session_id: string; user_id: string; method: string; created_at: string }
        Insert: { session_id: string; user_id: string; method: string; created_at?: string }
        Update: { session_id?: string; user_id?: string; method?: string; created_at?: string }
        Relationships: []
      }
      auth_throttle: {
        Row: { id: number; kind: string; key: string; created_at: string }
        Insert: { id?: never; kind: string; key: string; created_at?: string }
        Update: { id?: never; kind?: string; key?: string; created_at?: string }
        Relationships: []
      }
      search_diagnoses: {
        Row: { search_profile_id: number; user_id: string; fingerprint: string; result_count: number; max_results: number; funnel: Json; explanation: string; suggestions: Json; provider: string | null; llm_error: string | null; created_at: string; notified_at: string | null; notified_fingerprint: string | null; dismissed_at: string | null }
        Insert: never
        Update: { dismissed_at?: string | null }
        Relationships: []
      }
      // PAR-02 resto (20261203120000_par02_duplicates): service role only; the web reads neither.
      listing_duplicates: {
        Row: { listing_id: number; other_id: number; kind: string; shown: boolean; photo_distance: number | null; evidence: Json; detected_at: string }
        Insert: { listing_id: number; other_id: number; kind: string; shown: boolean; photo_distance?: number | null; evidence?: Json; detected_at?: string }
        Update: { kind?: string; shown?: boolean; photo_distance?: number | null; evidence?: Json; detected_at?: string }
        Relationships: [
          { foreignKeyName: "listing_duplicates_listing_id_fkey"; columns: ["listing_id"]; isOneToOne: false; referencedRelation: "listings"; referencedColumns: ["id"] },
          { foreignKeyName: "listing_duplicates_other_id_fkey"; columns: ["other_id"]; isOneToOne: false; referencedRelation: "listings"; referencedColumns: ["id"] },
        ]
      }
      photo_hash_runs: {
        Row: { id: number; listing_id: number | null; started_at: string; finished_at: string | null; images_requested: number; images_hashed: number | null; error: string | null }
        Insert: { id?: never; listing_id?: number | null; started_at?: string; finished_at?: string | null; images_requested: number; images_hashed?: number | null; error?: string | null }
        Update: { id?: never; listing_id?: number | null; finished_at?: string | null; images_hashed?: number | null; error?: string | null }
        Relationships: [{ foreignKeyName: "photo_hash_runs_listing_id_fkey"; columns: ["listing_id"]; isOneToOne: false; referencedRelation: "listings"; referencedColumns: ["id"] }]
      }
      // Filtro de color (20261214120000_listing_color): the vision pass's daily budget, server-only.
      color_vision_runs: {
        Row: { id: number; listing_id: number | null; started_at: string; finished_at: string | null; photos: number; model: string | null; result: string | null; error: string | null }
        Insert: { id?: never; listing_id?: number | null; started_at?: string; finished_at?: string | null; photos: number; model?: string | null; result?: string | null; error?: string | null }
        Update: { id?: never; listing_id?: number | null; finished_at?: string | null; photos?: number; model?: string | null; result?: string | null; error?: string | null }
        Relationships: [{ foreignKeyName: "color_vision_runs_listing_id_fkey"; columns: ["listing_id"]; isOneToOne: false; referencedRelation: "listings"; referencedColumns: ["id"] }]
      }
      // PAR-05 Prueba B (20261204120000_par05_sell_intent): each account its own row; timestamps set by a trigger.
      sell_intent: {
        Row: { user_id: string; answer: "yes" | "no"; source: "email" | "ficha"; answered_at: string; wants_notice: boolean; wants_notice_at: string | null; agencies_contact_ok: boolean; agencies_contact_at: string | null; created_at: string; updated_at: string }
        Insert: { user_id: string; answer: "yes" | "no"; source: "email" | "ficha"; wants_notice?: boolean; agencies_contact_ok?: boolean }
        Update: { answer?: "yes" | "no"; source?: "email" | "ficha"; wants_notice?: boolean; agencies_contact_ok?: boolean }
        Relationships: []
      }
      // Agencias, fase 3 (20261231120000_dealer_phase3): the seller reads their own car; writes through save_my_sell_vehicle.
      sell_intent_vehicles: {
        Row: { user_id: string; make: string; model: string; year: number | null; mileage_km: number | null; updated_at: string }
        Insert: never
        Update: never
        Relationships: []
      }
      // Agencias (20261228120000_dealer_program): RLS lets a member read their dealer's rows; every write goes through the RPCs.
      dealers: {
        Row: { id: number; name: string; contact_email: string | null; phone: string | null; whatsapp: string | null; address_text: string | null; locality_label: string; lat: number; lon: number; profile_links: Json; status: string; approved_at: string | null; approved_by: string | null; created_by: string | null; created_at: string; updated_at: string; alerts_email: boolean; alerts_checked_at: string | null }
        Insert: never
        Update: { status?: string; approved_at?: string | null; approved_by?: string | null }
        Relationships: []
      }
      dealer_members: {
        Row: { dealer_id: number; user_id: string; role: string; created_at: string }
        Insert: never
        Update: never
        Relationships: [{ foreignKeyName: "dealer_members_dealer_id_fkey"; columns: ["dealer_id"]; isOneToOne: false; referencedRelation: "dealers"; referencedColumns: ["id"] }]
      }
      dealer_sources: {
        Row: { id: number; dealer_id: number; source: string; profile_url: string | null; seller_name_hint: string | null; seller_key: string | null; status: string; approved_at: string | null; created_at: string; profile_read_at: string | null; profile_count: number | null; profile_error: string | null }
        Insert: never
        Update: { seller_key?: string | null; status?: string; approved_at?: string | null }
        Relationships: [{ foreignKeyName: "dealer_sources_dealer_id_fkey"; columns: ["dealer_id"]; isOneToOne: false; referencedRelation: "dealers"; referencedColumns: ["id"] }]
      }
      dealer_imports: {
        Row: { id: number; dealer_id: number; filename: string | null; kind: string; rows_total: number; rows_imported: number; created_by: string | null; created_at: string }
        Insert: never
        Update: never
        Relationships: [{ foreignKeyName: "dealer_imports_dealer_id_fkey"; columns: ["dealer_id"]; isOneToOne: false; referencedRelation: "dealers"; referencedColumns: ["id"] }]
      }
      dealer_stock_items: {
        Row: { id: number; dealer_id: number; origin: string; import_id: number | null; listing_id: number | null; duplicate_listing_id: number | null; make: string | null; model: string | null; trim: string | null; year: number | null; mileage_km: number | null; price: number | null; currency: string | null; transmission: string | null; fuel: string | null; color: string | null; body_type: string | null; title: string | null; description: string | null; images: Json; status: string; confirmed_at: string | null; in_stock_since: string | null; sync_state: string; sync_error: string | null; synced_at: string | null; matched_at: string | null; created_by: string | null; created_at: string; updated_at: string }
        Insert: never
        Update: never
        Relationships: [
          { foreignKeyName: "dealer_stock_items_dealer_id_fkey"; columns: ["dealer_id"]; isOneToOne: false; referencedRelation: "dealers"; referencedColumns: ["id"] },
          { foreignKeyName: "dealer_stock_items_listing_id_fkey"; columns: ["listing_id"]; isOneToOne: true; referencedRelation: "listings"; referencedColumns: ["id"] },
        ]
      }
      // Fase 1 (20261229120000): service role only (RLS on, no policies); the worker's alert state and queue, and the stock photos/PDFs waiting to be read.
      dealer_alert_state: {
        Row: { item_id: number; market_median_usd: number | null; market_n: number | null; market_at: string | null; demand_searches: number | null; demand_people: number | null; demand_at: string | null; cheaper_since: string | null; updated_at: string }
        Insert: never
        Update: never
        Relationships: [{ foreignKeyName: "dealer_alert_state_item_id_fkey"; columns: ["item_id"]; isOneToOne: true; referencedRelation: "dealer_stock_items"; referencedColumns: ["id"] }]
      }
      dealer_alerts: {
        Row: { id: number; dealer_id: number; item_id: number | null; kind: string; dedup_key: string; payload: Json; created_at: string; sent_at: string | null }
        Insert: never
        Update: never
        Relationships: [{ foreignKeyName: "dealer_alerts_dealer_id_fkey"; columns: ["dealer_id"]; isOneToOne: false; referencedRelation: "dealers"; referencedColumns: ["id"] }]
      }
      dealer_stock_reads: {
        Row: { id: number; dealer_id: number; job_id: number | null; media_type: string; filename: string | null; bytes: number; data: string | null; created_by: string | null; created_at: string; read_at: string | null }
        Insert: never
        Update: never
        Relationships: [{ foreignKeyName: "dealer_stock_reads_dealer_id_fkey"; columns: ["dealer_id"]; isOneToOne: false; referencedRelation: "dealers"; referencedColumns: ["id"] }]
      }
      dealer_item_private: {
        Row: { item_id: number; purchase_price: number | null; purchase_currency: string | null; notes: string | null; updated_at: string }
        Insert: never
        Update: never
        Relationships: [{ foreignKeyName: "dealer_item_private_item_id_fkey"; columns: ["item_id"]; isOneToOne: true; referencedRelation: "dealer_stock_items"; referencedColumns: ["id"] }]
      }
      // authenticated reads every column but buyer_user_id, consent_text and notification_id (column grants).
      dealer_leads: {
        Row: { id: number; dealer_id: number; item_id: number | null; listing_id: number | null; buyer_user_id: string; buyer_name: string; buyer_phone: string; message: string | null; consent_text: string; consent_at: string; notification_id: number | null; origin: string; status: string; status_changed_at: string | null; dealer_notified_at: string | null; created_at: string; updated_at: string; furthest_status: string }
        Insert: never
        Update: never
        Relationships: [
          { foreignKeyName: "dealer_leads_dealer_id_fkey"; columns: ["dealer_id"]; isOneToOne: false; referencedRelation: "dealers"; referencedColumns: ["id"] },
          { foreignKeyName: "dealer_leads_listing_id_fkey"; columns: ["listing_id"]; isOneToOne: false; referencedRelation: "listings"; referencedColumns: ["id"] },
          { foreignKeyName: "dealer_leads_item_id_fkey"; columns: ["item_id"]; isOneToOne: false; referencedRelation: "dealer_stock_items"; referencedColumns: ["id"] },
        ]
      }
      dealer_match_log: {
        Row: { listing_id: number; search_profile_id: number; dealer_id: number; user_id: string; first_matched_at: string }
        Insert: never
        Update: never
        Relationships: [
          { foreignKeyName: "dealer_match_log_dealer_id_fkey"; columns: ["dealer_id"]; isOneToOne: false; referencedRelation: "dealers"; referencedColumns: ["id"] },
        ]
      }
      dealer_sales: {
        Row: { id: number; dealer_id: number; item_id: number | null; lead_id: number | null; via_ese_auto: boolean; declared_by: string | null; declared_at: string }
        Insert: never
        Update: never
        Relationships: [
          { foreignKeyName: "dealer_sales_dealer_id_fkey"; columns: ["dealer_id"]; isOneToOne: false; referencedRelation: "dealers"; referencedColumns: ["id"] },
          { foreignKeyName: "dealer_sales_item_id_fkey"; columns: ["item_id"]; isOneToOne: false; referencedRelation: "dealer_stock_items"; referencedColumns: ["id"] },
          { foreignKeyName: "dealer_sales_lead_id_fkey"; columns: ["lead_id"]; isOneToOne: false; referencedRelation: "dealer_leads"; referencedColumns: ["id"] },
        ]
      }
      platform_health_checks: {
        Row: { id: number; checked_at: string; checks: Json; email_pending: boolean; last_email_at: string | null }
        Insert: { id: number; checked_at: string; checks: Json; email_pending?: boolean; last_email_at?: string | null }
        Update: { id?: number; checked_at?: string; checks?: Json; email_pending?: boolean; last_email_at?: string | null }
        Relationships: []
      }

            billing_checkouts: {
              Row: BillingCheckoutRow
              Insert: Pick<BillingCheckoutRow, 'user_id' | 'offer' | 'offer_version' | 'amount' | 'billing_email'> & Partial<BillingCheckoutRow>
              Update: Partial<BillingCheckoutRow>
              Relationships: []
            },
            "app_config": {
                  Row: {
                    "key": string,"updated_at": string,"value": NonNullable<Json>
                  }
                  Insert: {
                    "key": string,"updated_at"?: string,"value": NonNullable<Json>
                  }
                  Update: {
                    "key"?: string,"updated_at"?: string,"value"?: NonNullable<Json>
                  }
                  Relationships: [

                  ]
                },"collector_runs": {
                  Row: {
                    "error": string | null,"finished_at": string | null,"found": number | null,"id": number,"new": number | null,"source": string,"started_at": string,"status": Database["public"]['Enums']["run_status"],"target_id": number | null,"updated": number | null
                  }
                  Insert: {
                    "error"?: string | null,"finished_at"?: string | null,"found"?: number | null,"id"?: never,"new"?: number | null,"source": string,"started_at"?: string,"status"?: Database["public"]['Enums']["run_status"],"target_id"?: number | null,"updated"?: number | null
                  }
                  Update: {
                    "error"?: string | null,"finished_at"?: string | null,"found"?: number | null,"id"?: never,"new"?: number | null,"source"?: string,"started_at"?: string,"status"?: Database["public"]['Enums']["run_status"],"target_id"?: number | null,"updated"?: number | null
                  }
                  Relationships: [
                    {
      foreignKeyName: "collector_runs_source_fkey"
      columns: ["source"]
isOneToOne: false
      referencedRelation: "admin_source_health"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "collector_runs_source_fkey"
      columns: ["source"]
isOneToOne: false
      referencedRelation: "sources"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "collector_runs_target_id_fkey"
      columns: ["target_id"]
isOneToOne: false
      referencedRelation: "crawl_targets"
      referencedColumns: ["id"]
    }
                  ]
                },"commercial_payments": {
                  Row: {
                    "checkout_id": string | null,"amount": number,"currency": string,"id": number,"note": string | null,"offer": string,"offer_version": string,"paid_at": string,"period_end": string,"period_start": string,"provider": string,"reference": string,"refund_reference": string | null,"refunded_at": string | null,"refunded_by": string | null,"meta_sent_at": string | null,"user_id": string,"verified_at": string,"verified_by": string | null
                  }
                  Insert: {
                    "checkout_id"?: string | null,"amount": number,"currency": string,"id"?: never,"note"?: string | null,"offer": string,"offer_version": string,"paid_at": string,"period_end": string,"period_start": string,"provider": string,"reference": string,"refund_reference"?: string | null,"refunded_at"?: string | null,"refunded_by"?: string | null,"meta_sent_at"?: string | null,"user_id": string,"verified_at"?: string,"verified_by"?: string | null
                  }
                  Update: {
                    "checkout_id"?: string | null,"amount"?: number,"currency"?: string,"id"?: never,"note"?: string | null,"offer"?: string,"offer_version"?: string,"paid_at"?: string,"period_end"?: string,"period_start"?: string,"provider"?: string,"reference"?: string,"refund_reference"?: string | null,"refunded_at"?: string | null,"refunded_by"?: string | null,"meta_sent_at"?: string | null,"user_id"?: string,"verified_at"?: string,"verified_by"?: string | null
                  }
                  Relationships: [
                    {
      foreignKeyName: "commercial_payments_refunded_by_fkey"
      columns: ["refunded_by"]
isOneToOne: false
      referencedRelation: "admin_users"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "commercial_payments_refunded_by_fkey"
      columns: ["refunded_by"]
isOneToOne: false
      referencedRelation: "metric_users"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "commercial_payments_refunded_by_fkey"
      columns: ["refunded_by"]
isOneToOne: false
      referencedRelation: "profiles"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "commercial_payments_user_id_fkey"
      columns: ["user_id"]
isOneToOne: false
      referencedRelation: "admin_users"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "commercial_payments_user_id_fkey"
      columns: ["user_id"]
isOneToOne: false
      referencedRelation: "metric_users"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "commercial_payments_user_id_fkey"
      columns: ["user_id"]
isOneToOne: false
      referencedRelation: "profiles"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "commercial_payments_verified_by_fkey"
      columns: ["verified_by"]
isOneToOne: false
      referencedRelation: "admin_users"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "commercial_payments_verified_by_fkey"
      columns: ["verified_by"]
isOneToOne: false
      referencedRelation: "metric_users"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "commercial_payments_verified_by_fkey"
      columns: ["verified_by"]
isOneToOne: false
      referencedRelation: "profiles"
      referencedColumns: ["id"]
    }
                  ]
                },"catalog_misses": {
                  Row: {
                    "count": number,"first_seen_at": string,"last_llm_job_id": number | null,"last_seen_at": string,"make": string | null,"said": string
                  }
                  Insert: {
                    "count"?: number,"first_seen_at"?: string,"last_llm_job_id"?: number | null,"last_seen_at"?: string,"make"?: string | null,"said": string
                  }
                  Update: {
                    "count"?: number,"first_seen_at"?: string,"last_llm_job_id"?: number | null,"last_seen_at"?: string,"make"?: string | null,"said"?: string
                  }
                  Relationships: [

                  ]
                },"crawl_targets": {
                  Row: {
                    "active": boolean,"body_type": string | null,"created_at": string,"first_run_done": boolean,"id": number,"last_full_read_at": string | null,"last_run_at": string | null,"make": string | null,"model": string | null,"next_run_at": string | null,"prefilter_rejected": string[],"query": NonNullable<Json>,"source": string,"updated_at": string
                  }
                  Insert: {
                    "active"?: boolean,"body_type"?: string | null,"created_at"?: string,"first_run_done"?: boolean,"id"?: never,"last_full_read_at"?: string | null,"last_run_at"?: string | null,"make"?: string | null,"model"?: string | null,"next_run_at"?: string | null,"prefilter_rejected"?: string[],"query"?: NonNullable<Json>,"source": string,"updated_at"?: string
                  }
                  Update: {
                    "active"?: boolean,"body_type"?: string | null,"created_at"?: string,"first_run_done"?: boolean,"id"?: never,"last_full_read_at"?: string | null,"last_run_at"?: string | null,"make"?: string | null,"model"?: string | null,"next_run_at"?: string | null,"prefilter_rejected"?: string[],"query"?: NonNullable<Json>,"source"?: string,"updated_at"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "crawl_targets_source_fkey"
      columns: ["source"]
isOneToOne: false
      referencedRelation: "admin_source_health"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "crawl_targets_source_fkey"
      columns: ["source"]
isOneToOne: false
      referencedRelation: "sources"
      referencedColumns: ["id"]
    }
                  ]
                },"events": {
                  Row: {
                    "created_at": string,"id": number,"name": string,"props": NonNullable<Json>,"user_id": string | null
                  }
                  Insert: {
                    "created_at"?: string,"id"?: never,"name": string,"props"?: NonNullable<Json>,"user_id"?: string | null
                  }
                  Update: {
                    "created_at"?: string,"id"?: never,"name"?: string,"props"?: NonNullable<Json>,"user_id"?: string | null
                  }
                  Relationships: [
                    {
      foreignKeyName: "events_user_id_fkey"
      columns: ["user_id"]
isOneToOne: false
      referencedRelation: "admin_users"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "events_user_id_fkey"
      columns: ["user_id"]
isOneToOne: false
      referencedRelation: "metric_users"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "events_user_id_fkey"
      columns: ["user_id"]
isOneToOne: false
      referencedRelation: "profiles"
      referencedColumns: ["id"]
    }
                  ]
                },"fx_rates": {
                  Row: {
                    "date": string,"fetched_at": string,"kind": string,"rate": number,"source": string | null
                  }
                  Insert: {
                    "date": string,"fetched_at"?: string,"kind": string,"rate": number,"source"?: string | null
                  }
                  Update: {
                    "date"?: string,"fetched_at"?: string,"kind"?: string,"rate"?: number,"source"?: string | null
                  }
                  Relationships: [

                  ]
                },"geocode_cache": {
                  Row: {
                    "lat": number,"lon": number,"not_found": boolean,"query": string,"source": string,"updated_at": string
                  }
                  Insert: {
                    "lat": number,"lon": number,"not_found"?: boolean,"query": string,"source": string,"updated_at"?: string
                  }
                  Update: {
                    "lat"?: number,"lon"?: number,"not_found"?: boolean,"query"?: string,"source"?: string,"updated_at"?: string
                  }
                  Relationships: [

                  ]
                },"listing_snapshots": {
                  Row: {
                    "attrs_hash": string,"change_kind": string,"currency": string | null,"fx_rate": number | null,"id": number,"listing_id": number,"mileage_km": number | null,"observed_at": string,"price": number | null,"price_usd": number | null
                  }
                  Insert: {
                    "attrs_hash": string,"change_kind": string,"currency"?: string | null,"fx_rate"?: number | null,"id"?: never,"listing_id": number,"mileage_km"?: number | null,"observed_at"?: string,"price"?: number | null,"price_usd"?: number | null
                  }
                  Update: {
                    "attrs_hash"?: string,"change_kind"?: string,"currency"?: string | null,"fx_rate"?: number | null,"id"?: never,"listing_id"?: number,"mileage_km"?: number | null,"observed_at"?: string,"price"?: number | null,"price_usd"?: number | null
                  }
                  Relationships: [
                    {
      foreignKeyName: "listing_snapshots_listing_id_fkey"
      columns: ["listing_id"]
isOneToOne: false
      referencedRelation: "listings"
      referencedColumns: ["id"]
    }
                  ]
                },"listings": {
                  Row: {
                    "attributes": NonNullable<Json>,"body_type": string | null,"color": string | null,"currency": string | null,"dealer_confirmed_at": string | null,"dealer_id": number | null,"dealer_status": string | null,"dealer_inferred": boolean,"description": string | null,"description_facts": Json | null,"detail_checked_at": string | null,"enriched_at": string | null,"external_id": string,"fingerprint": string | null,"first_seen_at": string,"fuel": string | null,"id": number,"images": NonNullable<Json>,"last_full_seen_at": string | null,"last_seen_at": string,"lat": number | null,"location_text": string | null,"lon": number | null,"make": string | null,"mileage_km": number | null,"model": string | null,"normalization_confidence": number | null,"price": number | null,"price_partial": boolean,"price_partial_reason": string | null,"price_published": number | null,"price_published_currency": string | null,"price_source": string,"price_usd": number | null,"probable_repost_of": number | null,"published_at": string | null,"seller_key": string | null,"seller_listing_count": number | null,"seller_name": string | null,"seller_type": string | null,"source": string,"status": Database["public"]['Enums']["listing_status"],"title": string,"transmission": string | null,"trim": string | null,"url": string,"year": number | null
                  }
                  Insert: {
                    "attributes"?: NonNullable<Json>,"body_type"?: string | null,"color"?: string | null,"currency"?: string | null,"dealer_confirmed_at"?: string | null,"dealer_id"?: number | null,"dealer_status"?: string | null,"dealer_inferred"?: boolean,"description"?: string | null,"description_facts"?: Json | null,"detail_checked_at"?: string | null,"enriched_at"?: string | null,"external_id": string,"fingerprint"?: string | null,"first_seen_at"?: string,"fuel"?: string | null,"id"?: never,"images"?: NonNullable<Json>,"last_full_seen_at"?: string | null,"last_seen_at"?: string,"lat"?: number | null,"location_text"?: string | null,"lon"?: number | null,"make"?: string | null,"mileage_km"?: number | null,"model"?: string | null,"normalization_confidence"?: number | null,"price"?: number | null,"price_partial"?: boolean,"price_partial_reason"?: string | null,"price_published"?: number | null,"price_published_currency"?: string | null,"price_source"?: string,"price_usd"?: number | null,"probable_repost_of"?: number | null,"published_at"?: string | null,"seller_key"?: string | null,"seller_listing_count"?: number | null,"seller_name"?: string | null,"seller_type"?: string | null,"source": string,"status"?: Database["public"]['Enums']["listing_status"],"title": string,"transmission"?: string | null,"trim"?: string | null,"url": string,"year"?: number | null
                  }
                  Update: {
                    "attributes"?: NonNullable<Json>,"body_type"?: string | null,"color"?: string | null,"currency"?: string | null,"dealer_confirmed_at"?: string | null,"dealer_id"?: number | null,"dealer_status"?: string | null,"dealer_inferred"?: boolean,"description"?: string | null,"description_facts"?: Json | null,"detail_checked_at"?: string | null,"enriched_at"?: string | null,"external_id"?: string,"fingerprint"?: string | null,"first_seen_at"?: string,"fuel"?: string | null,"id"?: never,"images"?: NonNullable<Json>,"last_full_seen_at"?: string | null,"last_seen_at"?: string,"lat"?: number | null,"location_text"?: string | null,"lon"?: number | null,"make"?: string | null,"mileage_km"?: number | null,"model"?: string | null,"normalization_confidence"?: number | null,"price"?: number | null,"price_partial"?: boolean,"price_partial_reason"?: string | null,"price_published"?: number | null,"price_published_currency"?: string | null,"price_source"?: string,"price_usd"?: number | null,"probable_repost_of"?: number | null,"published_at"?: string | null,"seller_key"?: string | null,"seller_listing_count"?: number | null,"seller_name"?: string | null,"seller_type"?: string | null,"source"?: string,"status"?: Database["public"]['Enums']["listing_status"],"title"?: string,"transmission"?: string | null,"trim"?: string | null,"url"?: string,"year"?: number | null
                  }
                  Relationships: [
                    {
      foreignKeyName: "listings_probable_repost_of_fkey"
      columns: ["probable_repost_of"]
isOneToOne: false
      referencedRelation: "listings"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "listings_source_fkey"
      columns: ["source"]
isOneToOne: false
      referencedRelation: "admin_source_health"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "listings_source_fkey"
      columns: ["source"]
isOneToOne: false
      referencedRelation: "sources"
      referencedColumns: ["id"]
    }
                  ]
                },"llm_jobs": {
                  Row: {
                    "created_at": string,"error": string | null,"finished_at": string | null,"id": number,"input": NonNullable<Json>,"kind": string,"latency_ms": number | null,"output": Json | null,"provider": string | null,"started_at": string | null,"status": Database["public"]['Enums']["llm_job_status"],"user_id": string
                  }
                  Insert: {
                    "created_at"?: string,"error"?: string | null,"finished_at"?: string | null,"id"?: never,"input": NonNullable<Json>,"kind": string,"latency_ms"?: number | null,"output"?: Json | null,"provider"?: string | null,"started_at"?: string | null,"status"?: Database["public"]['Enums']["llm_job_status"],"user_id"?: string
                  }
                  Update: {
                    "created_at"?: string,"error"?: string | null,"finished_at"?: string | null,"id"?: never,"input"?: NonNullable<Json>,"kind"?: string,"latency_ms"?: number | null,"output"?: Json | null,"provider"?: string | null,"started_at"?: string | null,"status"?: Database["public"]['Enums']["llm_job_status"],"user_id"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "llm_jobs_user_id_fkey"
      columns: ["user_id"]
isOneToOne: false
      referencedRelation: "admin_users"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "llm_jobs_user_id_fkey"
      columns: ["user_id"]
isOneToOne: false
      referencedRelation: "metric_users"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "llm_jobs_user_id_fkey"
      columns: ["user_id"]
isOneToOne: false
      referencedRelation: "profiles"
      referencedColumns: ["id"]
    }
                  ]
                },"model_guides": {
                  // PAR-04 (20261205120000_par04_model_guides, 20261205120300_par04_guide_review_fixes).
                  // anon/authenticated read only published rows and only the public columns; writes go
                  // through the admin_* RPCs (service role).
                  Row: {
                    "id": number,"make": string,"model": string,"generation_label": string | null,"year_from": number | null,"year_to": number | null,"slug_make": string,"slug_model": string,"body": Json,"questions": Json,"sources": Json,"status": string,"origin": string,"llm_job_id": number | null,"llm_version": string | null,"generated_at": string | null,"reviewed_by": string | null,"reviewed_at": string | null,"published_at": string | null,"created_at": string,"updated_at": string,"content_updated_at": string
                  }
                  Insert: {
                    "id"?: never,"make": string,"model": string,"generation_label"?: string | null,"year_from"?: number | null,"year_to"?: number | null,"slug_make": string,"slug_model": string,"body"?: Json,"questions"?: Json,"sources"?: Json,"status"?: string,"origin"?: string,"llm_job_id"?: number | null,"llm_version"?: string | null,"generated_at"?: string | null,"reviewed_by"?: string | null,"reviewed_at"?: string | null,"published_at"?: string | null,"created_at"?: string,"updated_at"?: string,"content_updated_at"?: string
                  }
                  Update: {
                    "id"?: never,"make"?: string,"model"?: string,"generation_label"?: string | null,"year_from"?: number | null,"year_to"?: number | null,"slug_make"?: string,"slug_model"?: string,"body"?: Json,"questions"?: Json,"sources"?: Json,"status"?: string,"origin"?: string,"llm_job_id"?: number | null,"llm_version"?: string | null,"generated_at"?: string | null,"reviewed_by"?: string | null,"reviewed_at"?: string | null,"published_at"?: string | null,"created_at"?: string,"updated_at"?: string,"content_updated_at"?: string
                  }
                  Relationships: []
                },"matches": {
                  Row: {
                    "contact_questions": (string)[] | null,"generated_at": string,"id": number,"is_backfill": boolean,"level": Database["public"]['Enums']["match_level"],"listing_id": number,"margin_ref": Json | null,"match_reasons": NonNullable<Json>,"price_ref": Json | null,"red_flags": NonNullable<Json>,"score": number,"score_breakdown": NonNullable<Json>,"scoring_version": string,"search_profile_id": number,"seller_questions": string | null,"updated_at": string
                    /** PAR-04 (20261205120200_par04_question_origins): absent on a base without the migration. */
                    "question_origins"?: Json | null
                  }
                  Insert: {
                    "contact_questions"?: (string)[] | null,"generated_at"?: string,"id"?: never,"is_backfill"?: boolean,"level": Database["public"]['Enums']["match_level"],"listing_id": number,"margin_ref"?: Json | null,"match_reasons": NonNullable<Json>,"price_ref"?: Json | null,"red_flags"?: NonNullable<Json>,"score": number,"score_breakdown": NonNullable<Json>,"scoring_version": string,"search_profile_id": number,"seller_questions"?: string | null,"updated_at"?: string
                  }
                  Update: {
                    "contact_questions"?: (string)[] | null,"generated_at"?: string,"id"?: never,"is_backfill"?: boolean,"level"?: Database["public"]['Enums']["match_level"],"listing_id"?: number,"margin_ref"?: Json | null,"match_reasons"?: NonNullable<Json>,"price_ref"?: Json | null,"red_flags"?: NonNullable<Json>,"score"?: number,"score_breakdown"?: NonNullable<Json>,"scoring_version"?: string,"search_profile_id"?: number,"seller_questions"?: string | null,"updated_at"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "matches_listing_id_fkey"
      columns: ["listing_id"]
isOneToOne: false
      referencedRelation: "listings"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "matches_search_profile_id_fkey"
      columns: ["search_profile_id"]
isOneToOne: false
      referencedRelation: "admin_searches"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "matches_search_profile_id_fkey"
      columns: ["search_profile_id"]
isOneToOne: false
      referencedRelation: "search_profiles"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "matches_search_profile_id_fkey"
      columns: ["search_profile_id"]
isOneToOne: false
      referencedRelation: "v_first_value"
      referencedColumns: ["search_profile_id"]
    }
                  ]
                },"notifications": {
                  Row: {
                    "attempts": number,"channel": Database["public"]['Enums']["notification_channel"],"clicked_at": string | null,"created_at": string,"dedupe_key": string,"digested_in": number | null,"error": string | null,"id": number,"kind": Database["public"]['Enums']["notification_kind"],"listing_id": number | null,"match_id": number | null,"opened_at": string | null,"payload": NonNullable<Json>,"search_profile_id": number | null,"sent_at": string | null,"status": Database["public"]['Enums']["notification_status"],"user_id": string
                  }
                  Insert: {
                    "attempts"?: number,"channel": Database["public"]['Enums']["notification_channel"],"clicked_at"?: string | null,"created_at"?: string,"dedupe_key": string,"digested_in"?: number | null,"error"?: string | null,"id"?: never,"kind": Database["public"]['Enums']["notification_kind"],"listing_id"?: number | null,"match_id"?: number | null,"opened_at"?: string | null,"payload"?: NonNullable<Json>,"search_profile_id"?: number | null,"sent_at"?: string | null,"status"?: Database["public"]['Enums']["notification_status"],"user_id": string
                  }
                  Update: {
                    "attempts"?: number,"channel"?: Database["public"]['Enums']["notification_channel"],"clicked_at"?: string | null,"created_at"?: string,"dedupe_key"?: string,"digested_in"?: number | null,"error"?: string | null,"id"?: never,"kind"?: Database["public"]['Enums']["notification_kind"],"listing_id"?: number | null,"match_id"?: number | null,"opened_at"?: string | null,"payload"?: NonNullable<Json>,"search_profile_id"?: number | null,"sent_at"?: string | null,"status"?: Database["public"]['Enums']["notification_status"],"user_id"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "notifications_digested_in_fkey"
      columns: ["digested_in"]
isOneToOne: false
      referencedRelation: "metric_alert_rows"
      referencedColumns: ["notification_id"]
    },{
      foreignKeyName: "notifications_digested_in_fkey"
      columns: ["digested_in"]
isOneToOne: false
      referencedRelation: "notifications"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "notifications_listing_id_fkey"
      columns: ["listing_id"]
isOneToOne: false
      referencedRelation: "listings"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "notifications_match_id_fkey"
      columns: ["match_id"]
isOneToOne: false
      referencedRelation: "match_cards"
      referencedColumns: ["match_id"]
    },{
      foreignKeyName: "notifications_match_id_fkey"
      columns: ["match_id"]
isOneToOne: false
      referencedRelation: "matches"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "notifications_search_profile_id_fkey"
      columns: ["search_profile_id"]
isOneToOne: false
      referencedRelation: "admin_searches"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "notifications_search_profile_id_fkey"
      columns: ["search_profile_id"]
isOneToOne: false
      referencedRelation: "search_profiles"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "notifications_search_profile_id_fkey"
      columns: ["search_profile_id"]
isOneToOne: false
      referencedRelation: "v_first_value"
      referencedColumns: ["search_profile_id"]
    },{
      foreignKeyName: "notifications_user_id_fkey"
      columns: ["user_id"]
isOneToOne: false
      referencedRelation: "admin_users"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "notifications_user_id_fkey"
      columns: ["user_id"]
isOneToOne: false
      referencedRelation: "metric_users"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "notifications_user_id_fkey"
      columns: ["user_id"]
isOneToOne: false
      referencedRelation: "profiles"
      referencedColumns: ["id"]
    }
                  ]
                },"owned_vehicles": {
                  Row: {
                    "automotive_influence": Database["public"]['Enums']["purchase_influence"] | null,"created_at": string,"id": number,"listing_id": number | null,"purchase_currency": string | null,"purchase_date": string | null,"purchase_price": number | null,"search_profile_id": number | null,"updated_at": string,"user_id": string,"vehicle": NonNullable<Json>
                  }
                  Insert: {
                    "automotive_influence"?: Database["public"]['Enums']["purchase_influence"] | null,"created_at"?: string,"id"?: never,"listing_id"?: number | null,"purchase_currency"?: string | null,"purchase_date"?: string | null,"purchase_price"?: number | null,"search_profile_id"?: number | null,"updated_at"?: string,"user_id": string,"vehicle"?: NonNullable<Json>
                  }
                  Update: {
                    "automotive_influence"?: Database["public"]['Enums']["purchase_influence"] | null,"created_at"?: string,"id"?: never,"listing_id"?: number | null,"purchase_currency"?: string | null,"purchase_date"?: string | null,"purchase_price"?: number | null,"search_profile_id"?: number | null,"updated_at"?: string,"user_id"?: string,"vehicle"?: NonNullable<Json>
                  }
                  Relationships: [
                    {
      foreignKeyName: "owned_vehicles_listing_id_fkey"
      columns: ["listing_id"]
isOneToOne: false
      referencedRelation: "listings"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "owned_vehicles_search_profile_id_fkey"
      columns: ["search_profile_id"]
isOneToOne: false
      referencedRelation: "admin_searches"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "owned_vehicles_search_profile_id_fkey"
      columns: ["search_profile_id"]
isOneToOne: false
      referencedRelation: "search_profiles"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "owned_vehicles_search_profile_id_fkey"
      columns: ["search_profile_id"]
isOneToOne: false
      referencedRelation: "v_first_value"
      referencedColumns: ["search_profile_id"]
    },{
      foreignKeyName: "owned_vehicles_user_id_fkey"
      columns: ["user_id"]
isOneToOne: false
      referencedRelation: "admin_users"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "owned_vehicles_user_id_fkey"
      columns: ["user_id"]
isOneToOne: false
      referencedRelation: "metric_users"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "owned_vehicles_user_id_fkey"
      columns: ["user_id"]
isOneToOne: false
      referencedRelation: "profiles"
      referencedColumns: ["id"]
    }
                  ]
                },"pipeline_errors": {
                  Row: {
                    "created_at": string,"error": string,"id": number,"ref": string | null,"stage": string
                  }
                  Insert: {
                    "created_at"?: string,"error": string,"id"?: never,"ref"?: string | null,"stage": string
                  }
                  Update: {
                    "created_at"?: string,"error"?: string,"id"?: never,"ref"?: string | null,"stage"?: string
                  }
                  Relationships: [

                  ]
                },"pro_waitlist": {
                  Row: {
                    "created_at": string,"placement": string | null,"plan": string,"updated_at": string,"user_id": string
                  }
                  Insert: {
                    "created_at"?: string,"placement"?: string | null,"plan": string,"updated_at"?: string,"user_id": string
                  }
                  Update: {
                    "created_at"?: string,"placement"?: string | null,"plan"?: string,"updated_at"?: string,"user_id"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "pro_waitlist_user_id_fkey"
      columns: ["user_id"]
isOneToOne: true
      referencedRelation: "admin_users"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "pro_waitlist_user_id_fkey"
      columns: ["user_id"]
isOneToOne: true
      referencedRelation: "metric_users"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "pro_waitlist_user_id_fkey"
      columns: ["user_id"]
isOneToOne: true
      referencedRelation: "profiles"
      referencedColumns: ["id"]
    }
                  ]
                },"profiles": {
                  Row: {
                    "contact_template": string | null,"created_at": string,"default_channels": (string)[],"default_notification_frequency": Database["public"]['Enums']["notify_frequency"],"default_origin_label": string | null,"default_origin_lat": number | null,"default_origin_lon": number | null,"email": string | null,"email_only": boolean,"email_unsubscribe_token": string,"free_trial_started_at": string | null,"id": string,"phone": string | null,"plan": Database["public"]['Enums']["user_plan"],"plan_expires_at": string | null,"role": Database["public"]['Enums']["user_role"],"seller_filter_access": boolean,"telegram_chat_id": number | null,"telegram_link_code": string,"telegram_user_id": number | null,"updated_at": string
                  }
                  Insert: {
                    "contact_template"?: string | null,"created_at"?: string,"default_channels"?: (string)[],"default_notification_frequency"?: Database["public"]['Enums']["notify_frequency"],"default_origin_label"?: string | null,"default_origin_lat"?: number | null,"default_origin_lon"?: number | null,"email"?: string | null,"email_only"?: boolean,"email_unsubscribe_token"?: string,"free_trial_started_at"?: string | null,"id": string,"phone"?: string | null,"plan"?: Database["public"]['Enums']["user_plan"],"plan_expires_at"?: string | null,"role"?: Database["public"]['Enums']["user_role"],"seller_filter_access"?: boolean,"telegram_chat_id"?: number | null,"telegram_link_code"?: string,"telegram_user_id"?: number | null,"updated_at"?: string
                  }
                  Update: {
                    "contact_template"?: string | null,"created_at"?: string,"default_channels"?: (string)[],"default_notification_frequency"?: Database["public"]['Enums']["notify_frequency"],"default_origin_label"?: string | null,"default_origin_lat"?: number | null,"default_origin_lon"?: number | null,"email"?: string | null,"email_only"?: boolean,"email_unsubscribe_token"?: string,"free_trial_started_at"?: string | null,"id"?: string,"phone"?: string | null,"plan"?: Database["public"]['Enums']["user_plan"],"plan_expires_at"?: string | null,"role"?: Database["public"]['Enums']["user_role"],"seller_filter_access"?: boolean,"telegram_chat_id"?: number | null,"telegram_link_code"?: string,"telegram_user_id"?: number | null,"updated_at"?: string
                  }
                  Relationships: [

                  ]
                },"raw_pages": {
                  Row: {
                    "fetched_at": string,"html_gz": string,"kind": string,"listing_id": number,"parser_version": number,"status": number,"url": string
                  }
                  Insert: {
                    "fetched_at"?: string,"html_gz": string,"kind"?: string,"listing_id": number,"parser_version": number,"status": number,"url": string
                  }
                  Update: {
                    "fetched_at"?: string,"html_gz"?: string,"kind"?: string,"listing_id"?: number,"parser_version"?: number,"status"?: number,"url"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "raw_pages_listing_id_fkey"
      columns: ["listing_id"]
isOneToOne: false
      referencedRelation: "listings"
      referencedColumns: ["id"]
    }
                  ]
                },"search_profiles": {
                  Row: {
                    "bootstrapped_at": string | null,"channels": (string)[],"created_at": string,"enabled": boolean,"filters": NonNullable<Json>,"id": number,"name": string,"notification_frequency": Database["public"]['Enums']["notify_frequency"],"notify_min_level": Database["public"]['Enums']["match_level"],"opportunity_threshold_pct": number | null,"opportunity_threshold_usd": number | null,"origin_lat": number | null,"origin_lon": number | null,"preferences": NonNullable<Json>,"radius_km": number | null,"raw_query": string | null,"rematch_requested_at": string | null,"updated_at": string,"user_id": string
                  }
                  Insert: {
                    "bootstrapped_at"?: string | null,"channels"?: (string)[],"created_at"?: string,"enabled"?: boolean,"filters": NonNullable<Json>,"id"?: never,"name": string,"notification_frequency"?: Database["public"]['Enums']["notify_frequency"],"notify_min_level"?: Database["public"]['Enums']["match_level"],"opportunity_threshold_pct"?: number | null,"opportunity_threshold_usd"?: number | null,"origin_lat"?: number | null,"origin_lon"?: number | null,"preferences"?: NonNullable<Json>,"radius_km"?: number | null,"raw_query"?: string | null,"rematch_requested_at"?: string | null,"updated_at"?: string,"user_id": string
                  }
                  Update: {
                    "bootstrapped_at"?: string | null,"channels"?: (string)[],"created_at"?: string,"enabled"?: boolean,"filters"?: NonNullable<Json>,"id"?: never,"name"?: string,"notification_frequency"?: Database["public"]['Enums']["notify_frequency"],"notify_min_level"?: Database["public"]['Enums']["match_level"],"opportunity_threshold_pct"?: number | null,"opportunity_threshold_usd"?: number | null,"origin_lat"?: number | null,"origin_lon"?: number | null,"preferences"?: NonNullable<Json>,"radius_km"?: number | null,"raw_query"?: string | null,"rematch_requested_at"?: string | null,"updated_at"?: string,"user_id"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "search_profiles_user_id_fkey"
      columns: ["user_id"]
isOneToOne: false
      referencedRelation: "admin_users"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "search_profiles_user_id_fkey"
      columns: ["user_id"]
isOneToOne: false
      referencedRelation: "metric_users"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "search_profiles_user_id_fkey"
      columns: ["user_id"]
isOneToOne: false
      referencedRelation: "profiles"
      referencedColumns: ["id"]
    }
                  ]
                },"seller_classification_runs": {
                  Row: {
                    "error": string | null,"finished_at": string | null,"id": number,"inferred_changed": number | null,"mode": string,"params": Json | null,"rows_read": number | null,"rows_written": number | null,"started_at": string,"status": string,"trigger": string
                  }
                  Insert: {
                    "error"?: string | null,"finished_at"?: string | null,"id"?: never,"inferred_changed"?: number | null,"mode": string,"params"?: Json | null,"rows_read"?: number | null,"rows_written"?: number | null,"started_at"?: string,"status"?: string,"trigger": string
                  }
                  Update: {
                    "error"?: string | null,"finished_at"?: string | null,"id"?: never,"inferred_changed"?: number | null,"mode"?: string,"params"?: Json | null,"rows_read"?: number | null,"rows_written"?: number | null,"started_at"?: string,"status"?: string,"trigger"?: string
                  }
                  Relationships: [
                    
                  ]
                },"sources": {
                  Row: {
                    "consecutive_failures": number,"crawl_interval_seconds": number,"created_at": string,"detail_interval_seconds": number,"enabled": boolean,"id": string,"last_ok_at": string | null,"name": string,"priority": number,"updated_at": string
                  }
                  Insert: {
                    "consecutive_failures"?: number,"crawl_interval_seconds": number,"created_at"?: string,"detail_interval_seconds"?: number,"enabled"?: boolean,"id": string,"last_ok_at"?: string | null,"name": string,"priority"?: number,"updated_at"?: string
                  }
                  Update: {
                    "consecutive_failures"?: number,"crawl_interval_seconds"?: number,"created_at"?: string,"detail_interval_seconds"?: number,"enabled"?: boolean,"id"?: string,"last_ok_at"?: string | null,"name"?: string,"priority"?: number,"updated_at"?: string
                  }
                  Relationships: [

                  ]
                },"user_listing_interactions": {
                  Row: {
                    "listing_id": number,"note": string | null,"rejection_reason": Database["public"]['Enums']["rejection_reason"] | null,"saved": boolean,"status": Database["public"]['Enums']["interaction_status"],"updated_at": string,"user_id": string
                  }
                  Insert: {
                    "listing_id": number,"note"?: string | null,"rejection_reason"?: Database["public"]['Enums']["rejection_reason"] | null,"saved"?: boolean,"status"?: Database["public"]['Enums']["interaction_status"],"updated_at"?: string,"user_id": string
                  }
                  Update: {
                    "listing_id"?: number,"note"?: string | null,"rejection_reason"?: Database["public"]['Enums']["rejection_reason"] | null,"saved"?: boolean,"status"?: Database["public"]['Enums']["interaction_status"],"updated_at"?: string,"user_id"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "user_listing_interactions_listing_id_fkey"
      columns: ["listing_id"]
isOneToOne: false
      referencedRelation: "listings"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "user_listing_interactions_user_id_fkey"
      columns: ["user_id"]
isOneToOne: false
      referencedRelation: "admin_users"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "user_listing_interactions_user_id_fkey"
      columns: ["user_id"]
isOneToOne: false
      referencedRelation: "metric_users"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "user_listing_interactions_user_id_fkey"
      columns: ["user_id"]
isOneToOne: false
      referencedRelation: "profiles"
      referencedColumns: ["id"]
    }
                  ]
                },"vehicle_catalog": {
                  Row: {
                    "aliases": (string)[],"body_types": (string)[],"created_at": string,"fuels": (string)[],"id": number,"make": string,"model": string,"timing_belt": boolean | null,"transmissions": (string)[],"trim": string | null,"year_from": number | null,"year_to": number | null
                  }
                  Insert: {
                    "aliases"?: (string)[],"body_types"?: (string)[],"created_at"?: string,"fuels"?: (string)[],"id"?: never,"make": string,"model": string,"timing_belt"?: boolean | null,"transmissions"?: (string)[],"trim"?: string | null,"year_from"?: number | null,"year_to"?: number | null
                  }
                  Update: {
                    "aliases"?: (string)[],"body_types"?: (string)[],"created_at"?: string,"fuels"?: (string)[],"id"?: never,"make"?: string,"model"?: string,"timing_belt"?: boolean | null,"transmissions"?: (string)[],"trim"?: string | null,"year_from"?: number | null,"year_to"?: number | null
                  }
                  Relationships: [

                  ]
                },"worker_heartbeat": {
                  Row: {
                    "beat_at": string,"host": string | null,"id": number,"pid": number | null,"started_at": string
                  }
                  Insert: {
                    "beat_at"?: string,"host"?: string | null,"id"?: number,"pid"?: number | null,"started_at": string
                  }
                  Update: {
                    "beat_at"?: string,"host"?: string | null,"id"?: number,"pid"?: number | null,"started_at"?: string
                  }
                  Relationships: [

                  ]
                }
          }
          Views: {
            "admin_notification_daily": {
                  Row: {
                    "channel": Database["public"]['Enums']["notification_channel"] | null,"clicked": number | null,"day": string | null,"degraded": number | null,"digests_sent": number | null,"failed": number | null,"queued": number | null,"sent": number | null,"to_digest": number | null
                  }
                  Relationships: [

                  ]
                },"admin_score_histogram": {
                  Row: {
                    "bucket": number | null,"level": Database["public"]['Enums']["match_level"] | null,"matches": number | null,"source": string | null
                  }
                  Relationships: [
                    {
      foreignKeyName: "listings_source_fkey"
      columns: ["source"]
isOneToOne: false
      referencedRelation: "admin_source_health"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "listings_source_fkey"
      columns: ["source"]
isOneToOne: false
      referencedRelation: "sources"
      referencedColumns: ["id"]
    }
                  ]
                },"admin_searches": {
                  Row: {
                    "alerts": number | null,"bootstrapped_at": string | null,"channels": (string)[] | null,"created_at": string | null,"email": string | null,"enabled": boolean | null,"filters": Json | null,"high_matches": number | null,"id": number | null,"matches": number | null,"name": string | null,"notification_frequency": Database["public"]['Enums']["notify_frequency"] | null,"notify_min_level": Database["public"]['Enums']["match_level"] | null,"rematch_requested_at": string | null,"user_id": string | null
                  }
                  Relationships: [
                    {
      foreignKeyName: "search_profiles_user_id_fkey"
      columns: ["user_id"]
isOneToOne: false
      referencedRelation: "admin_users"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "search_profiles_user_id_fkey"
      columns: ["user_id"]
isOneToOne: false
      referencedRelation: "metric_users"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "search_profiles_user_id_fkey"
      columns: ["user_id"]
isOneToOne: false
      referencedRelation: "profiles"
      referencedColumns: ["id"]
    }
                  ]
                },"admin_seller_coverage": {
                  Row: {
                    "active": number | null,"dealer_inferred": number | null,"min_listings": number | null,"over_threshold": number | null,"seller_key_null": number | null,"seller_key_null_pct": number | null,"seller_name_null": number | null,"seller_name_null_pct": number | null,"seller_type_null": number | null,"seller_type_null_pct": number | null,"seller_unknown_pct": number | null,"source": string | null
                  }
                  Relationships: [
                    {
      foreignKeyName: "listings_source_fkey"
      columns: ["source"]
isOneToOne: false
      referencedRelation: "admin_source_health"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "listings_source_fkey"
      columns: ["source"]
isOneToOne: false
      referencedRelation: "sources"
      referencedColumns: ["id"]
    }
                  ]
                },"admin_source_health": {
                  Row: {
                    "avg_seconds_24h": number | null,"consecutive_failures": number | null,"crawl_interval_seconds": number | null,"detail_interval_seconds": number | null,"enabled": boolean | null,"failed_24h": number | null,"found_24h": number | null,"id": string | null,"last_error": string | null,"last_ok_at": string | null,"last_run_at": string | null,"last_run_status": Database["public"]['Enums']["run_status"] | null,"name": string | null,"new_24h": number | null,"priority": number | null,"runs_24h": number | null,"updated_24h": number | null
                  }
                  Relationships: [

                  ]
                },"admin_users": {
                  Row: {
                    "alerts_7d": number | null,"created_at": string | null,"email": string | null,"email_only": boolean | null,"enabled_searches": number | null,"id": string | null,"last_activity_at": string | null,"plan": Database["public"]['Enums']["user_plan"] | null,"plan_expires_at": string | null,"role": Database["public"]['Enums']["user_role"] | null,"searches": number | null,"telegram_linked": boolean | null,"telegram_only": boolean | null,"waitlist_plan": string | null
                  }
                  Relationships: [

                  ]
                },"commercial_revenue": {
                  Row: {
                    "agency_accounts": number | null,"agency_monthly_equivalent": number | null,"confirmed_revenue": number | null,"particular_sales": number | null,"refunds": number | null
                  }
                  Relationships: [

                  ]
                },"llm_job_stats": {
                  Row: {
                    "day": string | null,"done": number | null,"failed": number | null,"jobs": number | null,"kind": string | null,"latency_max_ms": number | null,"latency_p50_ms": number | null,"latency_p95_ms": number | null,"provider": string | null
                  }
                  Relationships: [

                  ]
                },"match_cards": {
                  Row: {
                    "body_type": string | null,"color": string | null,"color_method": string | null,"currency": string | null,"dealer_confirmed_at": string | null,"dealer_id": number | null,"dealer_name": string | null,"financing_offered": boolean | null,"first_seen_at": string | null,"fuel": string | null,"generated_at": string | null,"images": Json | null,"is_backfill": boolean | null,"level": Database["public"]['Enums']["match_level"] | null,"listing_id": number | null,"listing_status": Database["public"]['Enums']["listing_status"] | null,"location_text": string | null,"make": string | null,"match_id": number | null,"mileage_km": number | null,"model": string | null,"note": string | null,"price": number | null,"price_kind": string | null,"price_published": number | null,"price_published_currency": string | null,"price_ref": Json | null,"price_source": string | null,"price_usd": number | null,"probable_repost_of": number | null,"profile_name": string | null,"published_at": string | null,"red_flags": Json | null,"rejection_reason": Database["public"]['Enums']["rejection_reason"] | null,"saved": boolean | null,"seller_unknown": boolean | null,"score": number | null,"search_profile_id": number | null,"source": string | null,"status": Database["public"]['Enums']["interaction_status"] | null,"title": string | null,"transmission": string | null,"trim": string | null,"user_id": string | null,"year": number | null
                  }
                  Relationships: [
                    {
      foreignKeyName: "listings_probable_repost_of_fkey"
      columns: ["probable_repost_of"]
isOneToOne: false
      referencedRelation: "listings"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "listings_source_fkey"
      columns: ["source"]
isOneToOne: false
      referencedRelation: "admin_source_health"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "listings_source_fkey"
      columns: ["source"]
isOneToOne: false
      referencedRelation: "sources"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "matches_listing_id_fkey"
      columns: ["listing_id"]
isOneToOne: false
      referencedRelation: "listings"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "matches_search_profile_id_fkey"
      columns: ["search_profile_id"]
isOneToOne: false
      referencedRelation: "admin_searches"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "matches_search_profile_id_fkey"
      columns: ["search_profile_id"]
isOneToOne: false
      referencedRelation: "search_profiles"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "matches_search_profile_id_fkey"
      columns: ["search_profile_id"]
isOneToOne: false
      referencedRelation: "v_first_value"
      referencedColumns: ["search_profile_id"]
    },{
      foreignKeyName: "search_profiles_user_id_fkey"
      columns: ["user_id"]
isOneToOne: false
      referencedRelation: "admin_users"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "search_profiles_user_id_fkey"
      columns: ["user_id"]
isOneToOne: false
      referencedRelation: "metric_users"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "search_profiles_user_id_fkey"
      columns: ["user_id"]
isOneToOne: false
      referencedRelation: "profiles"
      referencedColumns: ["id"]
    }
                  ]
                },"metric_alert_rows": {
                  Row: {
                    "channel": string | null,"clicked_at": string | null,"dedupe_key": string | null,"delivered_at": string | null,"discarded": boolean | null,"kind": string | null,"level": string | null,"listing_id": number | null,"match_id": number | null,"notification_id": number | null,"opened_at": string | null,"rejection_reason": string | null,"saved": boolean | null,"score": number | null,"search_profile_id": number | null,"user_id": string | null,"via_digest": boolean | null
                  }
                  Relationships: [
                    {
      foreignKeyName: "notifications_listing_id_fkey"
      columns: ["listing_id"]
isOneToOne: false
      referencedRelation: "listings"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "notifications_match_id_fkey"
      columns: ["match_id"]
isOneToOne: false
      referencedRelation: "match_cards"
      referencedColumns: ["match_id"]
    },{
      foreignKeyName: "notifications_match_id_fkey"
      columns: ["match_id"]
isOneToOne: false
      referencedRelation: "matches"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "notifications_search_profile_id_fkey"
      columns: ["search_profile_id"]
isOneToOne: false
      referencedRelation: "admin_searches"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "notifications_search_profile_id_fkey"
      columns: ["search_profile_id"]
isOneToOne: false
      referencedRelation: "search_profiles"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "notifications_search_profile_id_fkey"
      columns: ["search_profile_id"]
isOneToOne: false
      referencedRelation: "v_first_value"
      referencedColumns: ["search_profile_id"]
    },{
      foreignKeyName: "notifications_user_id_fkey"
      columns: ["user_id"]
isOneToOne: false
      referencedRelation: "admin_users"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "notifications_user_id_fkey"
      columns: ["user_id"]
isOneToOne: false
      referencedRelation: "metric_users"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "notifications_user_id_fkey"
      columns: ["user_id"]
isOneToOne: false
      referencedRelation: "profiles"
      referencedColumns: ["id"]
    }
                  ]
                },"metric_alerts": {
                  Row: {
                    "channels": (string)[] | null,"clicked_at": string | null,"dedupe_key": string | null,"delivered_at": string | null,"discarded": boolean | null,"kind": string | null,"level": string | null,"listing_id": number | null,"opened_at": string | null,"rejection_reason": string | null,"saved": boolean | null,"score": number | null,"search_profile_id": number | null,"user_id": string | null,"via_digest": boolean | null
                  }
                  Relationships: [
                    {
      foreignKeyName: "notifications_user_id_fkey"
      columns: ["user_id"]
isOneToOne: false
      referencedRelation: "admin_users"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "notifications_user_id_fkey"
      columns: ["user_id"]
isOneToOne: false
      referencedRelation: "metric_users"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "notifications_user_id_fkey"
      columns: ["user_id"]
isOneToOne: false
      referencedRelation: "profiles"
      referencedColumns: ["id"]
    }
                  ]
                },"metric_users": {
                  Row: {
                    "created_at": string | null,"email": string | null,"id": string | null,"plan": Database["public"]['Enums']["user_plan"] | null,"plan_expires_at": string | null,"telegram_only": boolean | null
                  }
                  Insert: {
                           "created_at"?: string | null,"email"?: string | null,"id"?: string | null,"plan"?: Database["public"]['Enums']["user_plan"] | null,"plan_expires_at"?: string | null,"telegram_only"?: never
                         }
                        Update: {
                           "created_at"?: string | null,"email"?: string | null,"id"?: string | null,"plan"?: Database["public"]['Enums']["user_plan"] | null,"plan_expires_at"?: string | null,"telegram_only"?: never
                         }
                        Relationships: [

                  ]
                },"v_activation": {
                  Row: {
                    "activation_pct": number | null,"cohort_week": string | null,"signed_up": number | null,"target_pct": number | null,"with_search": number | null
                  }
                  Relationships: [

                  ]
                },"v_alert_funnel": {
                  Row: {
                    "channel": string | null,"click_rate_pct": number | null,"clicked": number | null,"discarded": number | null,"dismiss_rate_pct": number | null,"level": string | null,"open_rate_pct": number | null,"opened": number | null,"save_rate_pct": number | null,"saved": number | null,"sent": number | null
                  }
                  Relationships: [

                  ]
                },"v_alerts_per_user_day": {
                  Row: {
                    "alerts": number | null,"alerts_per_user": number | null,"cap": number | null,"day": string | null,"max_per_user": number | null,"users": number | null
                  }
                  Relationships: [

                  ]
                },"v_contacted_metric": {
                  Row: {
                    "events": number | null,"users": number | null
                  }
                  Relationships: [

                  ]
                },"v_first_value": {
                  Row: {
                    "created_at": string | null,"first_value_at": string | null,"hours_to_first_value": number | null,"is_backfill": boolean | null,"search_profile_id": number | null,"user_id": string | null
                  }
                  Relationships: [
                    {
      foreignKeyName: "search_profiles_user_id_fkey"
      columns: ["user_id"]
isOneToOne: false
      referencedRelation: "admin_users"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "search_profiles_user_id_fkey"
      columns: ["user_id"]
isOneToOne: false
      referencedRelation: "metric_users"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "search_profiles_user_id_fkey"
      columns: ["user_id"]
isOneToOne: false
      referencedRelation: "profiles"
      referencedColumns: ["id"]
    }
                  ]
                },"v_high_score_engagement": {
                  Row: {
                    "alerts": number | null,"click_rate_pct": number | null,"dismiss_rate_pct": number | null,"engagement_pct": number | null,"open_rate_pct": number | null,"save_rate_pct": number | null,"segment": string | null
                  }
                  Relationships: [

                  ]
                },"v_north_star_weekly": {
                  Row: {
                    "active_users": number | null,"relevant_opens": number | null,"relevant_opens_per_active_user": number | null,"week": string | null
                  }
                  Relationships: [

                  ]
                },"v_outcomes": {
                  Row: {
                    "automotive_influence": Database["public"]['Enums']["purchase_influence"] | null,"came_from_alert": boolean | null,"created_at": string | null,"days_since_search": number | null,"days_using_automotive": number | null,"listing_id": number | null,"owned_vehicle_id": number | null,"purchase_currency": string | null,"purchase_date": string | null,"purchase_price": number | null,"search_profile_id": number | null,"title": string | null,"user_id": string | null
                  }
                  Relationships: [
                    {
      foreignKeyName: "owned_vehicles_listing_id_fkey"
      columns: ["listing_id"]
isOneToOne: false
      referencedRelation: "listings"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "owned_vehicles_search_profile_id_fkey"
      columns: ["search_profile_id"]
isOneToOne: false
      referencedRelation: "admin_searches"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "owned_vehicles_search_profile_id_fkey"
      columns: ["search_profile_id"]
isOneToOne: false
      referencedRelation: "search_profiles"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "owned_vehicles_search_profile_id_fkey"
      columns: ["search_profile_id"]
isOneToOne: false
      referencedRelation: "v_first_value"
      referencedColumns: ["search_profile_id"]
    },{
      foreignKeyName: "owned_vehicles_user_id_fkey"
      columns: ["user_id"]
isOneToOne: false
      referencedRelation: "admin_users"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "owned_vehicles_user_id_fkey"
      columns: ["user_id"]
isOneToOne: false
      referencedRelation: "metric_users"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "owned_vehicles_user_id_fkey"
      columns: ["user_id"]
isOneToOne: false
      referencedRelation: "profiles"
      referencedColumns: ["id"]
    }
                  ]
                },"v_validation_criteria": {
                  Row: {
                    "criterion": string | null,"denominator": number | null,"label": string | null,"met": boolean | null,"metric": string | null,"numerator": number | null,"ordinal": number | null,"threshold": number | null,"unit": string | null,"value": number | null
                  }
                  Relationships: [

                  ]
                }
          }
          Functions: {
      admin_match_review_draw: {
        Args: { p_week?: string | null; p_size?: number }
        Returns: Json
      }
      admin_match_review_queue: {
        Args: { p_week?: string | null }
        Returns: Json
      }
      admin_match_review_save: {
        Args: { p_id: number; p_verdict: string; p_reasons: string[]; p_note: string | null; p_actor_id: string }
        Returns: Json
      }
      admin_match_review_stats: {
        Args: { p_weeks?: number }
        Returns: Json
      }
      admin_match_review_week: {
        Args: { p_at?: string }
        Returns: string
      }
      admin_decision_metrics: {
        Args: { p_start: string; p_end: string; p_as_of: string }
        Returns: Json
      }
      // PAR-05 Prueba B: service role only.
      admin_sell_intent_metrics: {
        Args: { p_since?: string | null }
        Returns: Json
      }
      admin_prospect_action: {
        Args: { p_actor_id: string; p_prospect_id: number; p_message_id: number | null; p_action: string; p_text: string | null }
        Returns: string
      }
      admin_create_experiment: {
        Args: { p_actor_id: string; p_slug: string; p_title: string; p_config_key: string | null; p_hypothesis: string; p_metric: string; p_baseline_text: string | null; p_baseline_value: number | null; p_started_at: string | null; p_review_at: string | null }
        Returns: string
      }
      admin_update_experiment: {
        Args: { p_actor_id: string; p_slug: string; p_title: string; p_config_key: string | null; p_hypothesis: string; p_metric: string; p_baseline_text: string | null; p_baseline_value: number | null; p_started_at: string | null; p_review_at: string | null }
        Returns: undefined
      }
      admin_record_experiment_verdict: {
        Args: { p_actor_id: string; p_slug: string; p_status: string; p_result_text: string | null; p_result_value: number | null; p_verdict_note: string | null }
        Returns: undefined
      }
      admin_update_setting: {
        Args: { p_target_type: string; p_target_key: string; p_expected: Json; p_value: Json; p_actor_id: string }
        Returns: number
      }
      // Agencias (20261228120000_dealer_program). Panel and buyer RPCs: authenticated; admin_*, dealer_sweep, dealer_market_ref, dealer_demand, dealer_blue_rate: service role.
      dealer_program: { Args: Record<string, never>; Returns: Json }
      is_dealer_member: { Args: { p_dealer_id: number }; Returns: boolean }
      dealer_listing_hidden: { Args: { p_source: string; p_dealer_id: number | null; p_dealer_status: string | null; p_confirmed_at: string | null }; Returns: string | null }
      dealer_public_name: { Args: { p_dealer_id: number }; Returns: string | null }
      dealer_market_ref: { Args: { p_make: string; p_model: string; p_year: number; p_price_usd: number | null; p_exclude_listing: number | null }; Returns: Json }
      dealer_demand: { Args: { p_make: string; p_model: string; p_year: number; p_price: number | null; p_currency: string | null; p_mileage_km: number | null; p_lat: number; p_lon: number; p_exclude_users: string[]; p_source: string | null }; Returns: Json }
      dealer_blue_rate: { Args: Record<string, never>; Returns: number | null }
      my_dealer: { Args: Record<string, never>; Returns: Json }
      create_dealer: { Args: { p_name: string; p_locality_label: string; p_lat: number; p_lon: number; p_phone?: string | null; p_whatsapp?: string | null; p_contact_email?: string | null; p_address_text?: string | null; p_profile_links?: Json }; Returns: number }
      update_my_dealer: { Args: { p_name: string; p_locality_label: string; p_lat: number; p_lon: number; p_phone?: string | null; p_whatsapp?: string | null; p_contact_email?: string | null; p_address_text?: string | null; p_profile_links?: Json }; Returns: undefined }
      dealer_add_source: { Args: { p_source: string; p_profile_url: string | null; p_seller_name_hint: string | null }; Returns: number }
      dealer_upsert_item: { Args: { p_item_id: number | null; p_values: Json }; Returns: number }
      dealer_import_items: { Args: { p_rows: Json; p_filename: string | null; p_kind: string }; Returns: Json }
      dealer_set_item_status: { Args: { p_item_id: number; p_status: string }; Returns: undefined }
      dealer_confirm_items: { Args: { p_item_ids?: number[] | null }; Returns: number }
      dealer_resolve_duplicate: { Args: { p_item_id: number; p_mine: boolean }; Returns: undefined }
      dealer_set_item_private: { Args: { p_item_id: number; p_purchase_price: number | null; p_purchase_currency: string | null; p_notes: string | null }; Returns: undefined }
      dealer_stock_insights: { Args: Record<string, never>; Returns: { item_id: number; listing_id: number | null; origin: string; status: string; sync_state: string; make: string | null; model: string | null; trim: string | null; year: number | null; mileage_km: number | null; price: number | null; currency: string | null; price_usd: number | null; confirmed_at: string | null; confirm_due_at: string | null; hidden_reason: string | null; market: Json; days_in_stock: number | null; model_days_to_sell: Json; demand: Json }[] }
      dealer_market_listings: { Args: { p_item_id: number }; Returns: { listing_id: number; source: string; url: string; title: string; trim: string | null; year: number | null; mileage_km: number | null; price: number | null; currency: string | null; price_usd: number; location_text: string | null; seller_type: string | null; first_seen_at: string; in_ref: boolean }[] }
      dealer_price_context: { Args: Record<string, never>; Returns: { item_id: number; context: Json }[] }
      dealer_set_alerts: { Args: { p_on: boolean }; Returns: undefined }
      /** Returns the llm_jobs id of the read (kind dealer_stock_read). */
      dealer_request_stock_read: { Args: { p_data: string; p_media_type: string; p_filename?: string | null }; Returns: number }
      dealer_alert_scan: { Args: { p_dealer_id: number; p_cheaper_pct?: number; p_radius_km?: number }; Returns: { item_id: number; listing_id: number | null; make: string | null; model: string | null; trim: string | null; year: number | null; mileage_km: number | null; price: number | null; currency: string | null; price_usd: number | null; market: Json; model_days: Json; days_in_stock: number | null; demand: Json | null; cheaper: Json | null; state: Json | null }[] }
      dealer_set_lead_status: { Args: { p_lead_id: number; p_status: string }; Returns: undefined }
      dealer_declare_sale: { Args: { p_item_id?: number | null; p_lead_id?: number | null; p_via_ese_auto: boolean }; Returns: undefined }
      my_dealer_reach: { Args: Record<string, never>; Returns: Json }
      dealer_funnel: { Args: { p_start: string; p_end: string; p_dealer?: number | null }; Returns: Json }
      admin_dealer_funnel: { Args: { p_start: string; p_end: string }; Returns: Json }
      request_dealer_contact: { Args: { p_listing_id: number; p_name: string; p_phone: string; p_message: string | null; p_consent: boolean; p_consent_text: string; p_notification_id?: number | null }; Returns: Json }
      listing_dealer_card: { Args: { p_listing_id: number }; Returns: Json }
      dealer_badges: { Args: { p_listing_ids: number[] }; Returns: { listing_id: number; dealer_name: string; confirmed_at: string | null }[] }
      // Agencias, fase 3 (20261231120000_dealer_phase3). dealer_seller_requests has no client access: only these RPCs.
      dealer_sellers_config: { Args: Record<string, never>; Returns: Json }
      dealer_buy_opportunities: { Args: Record<string, never>; Returns: { make: string | null; model: string; searches: number; active_searches: Json; year_from: number | null; year_to: number | null; budget: number | null; budget_currency: string | null; supply_total: number; supply_near: number }[] }
      dealer_buy_market_listings: { Args: { p_make: string | null; p_model: string; p_year_from: number | null; p_year_to: number | null }; Returns: { listing_id: number; source: string; url: string; title: string; trim: string | null; year: number | null; mileage_km: number | null; price: number | null; currency: string | null; price_usd: number | null; location_text: string | null; seller_type: string | null; first_seen_at: string; near: boolean }[] }
      save_my_sell_vehicle: { Args: { p_make: string; p_model: string; p_year: number | null; p_mileage_km: number | null }; Returns: undefined }
      dealer_sellers: { Args: Record<string, never>; Returns: { ref: string; make: string | null; model: string | null; year: number | null; mileage_km_rounded: number | null; distance_band: string; recent: boolean; request_id: number | null; request_status: string | null; requested_on: string | null; shared_name: string | null; shared_phone: string | null; shared_email: string | null; can_request: boolean }[] }
      dealer_request_seller: { Args: { p_ref: string; p_message?: string | null }; Returns: Json }
      my_dealer_seller_requests: { Args: Record<string, never>; Returns: { id: number; dealer_name: string; dealer_locality: string; message: string | null; status: string; created_at: string; answered_at: string | null }[] }
      answer_dealer_seller_request: { Args: { p_request_id: number; p_accept: boolean; p_name?: string | null; p_phone?: string | null; p_share_email?: boolean; p_consent_text?: string | null }; Returns: undefined }
      dealer_sweep: { Args: Record<string, never>; Returns: { matches_deleted: number; notifications_skipped: number; expired_deleted: number }[] }
      admin_dealer_seller_candidates: { Args: { p_source: string; p_hint: string }; Returns: { seller_key: string; seller_name: string | null; active: number }[] }
            // PAR-04: model guides (service role, except log_guide_event: anon and authenticated).
            admin_save_model_guide: { Args: { p_id: number | null; p_values: Json; p_expected_updated_at: string | null; p_actor_id: string }; Returns: Json },
            admin_set_model_guide_status: { Args: { p_id: number; p_status: string; p_actor_id: string; p_expected_updated_at?: string | null }; Returns: Json },
            admin_request_model_guide: { Args: { p_guide_id: number; p_force: boolean; p_actor_id: string }; Returns: number },
            admin_guide_candidates: { Args: { p_limit?: number }; Returns: { make: string; model: string; year_from: number | null; year_to: number | null; active_searches: number; guide_id: number | null; guide_status: string | null }[] },
            admin_guide_event_counts: { Args: { p_days?: number }; Returns: { guide_id: number; viewed: number; cta_clicked: number; questions_copied: number }[] },
            model_guide_jobs_since: { Args: { p_since: string }; Returns: number },
            log_guide_event: { Args: { p_name: string; p_slug_make: string; p_slug_model: string }; Returns: undefined },
            // Landing hero (20261219120000): landing_feed is service role only; log_landing_event is anon and authenticated.
            landing_feed: { Args: Record<string, never>; Returns: Json },
            log_landing_event: { Args: { p_name: string; p_variant: string; p_how?: string }; Returns: undefined },
            begin_billing_checkout: { Args: { p_user: string; p_offer: string; p_email: string; p_version: string; p_expected_amount: number; p_founder_code?: string }; Returns: Json },
            founder_offer: { Args: { p_code: string }; Returns: Json },
            apply_mercadopago_payment: { Args: { p_checkout: string; p_reference: string; p_status: string; p_amount: number; p_currency: string; p_paid_at: string; p_start: string; p_end: string }; Returns: number },
            claim_auth_throttle: { Args: { p_kind: string; p_key: string; p_limit: number; p_window_seconds: number }; Returns: boolean },
            auth_account_for_email: { Args: { p_email: string }; Returns: { user_id: string; email_only: boolean; confirmed: boolean }[] },
            mark_email_only_account: { Args: { p_user: string }; Returns: boolean },
            auth_account_for_canonical_email: { Args: { p_email: string }; Returns: { user_id: string; email: string; email_only: boolean; confirmed: boolean }[] },
            record_trial_signals: { Args: { p_user: string; p_email: string; p_ip_key: string | null; p_device_key: string | null }; Returns: undefined },
            save_email_only_resume: { Args: { p_user: string; p_code_hash: string }; Returns: undefined },
            claim_email_only_resume: { Args: { p_user: string; p_code_hash: string; p_window_seconds: number }; Returns: boolean },
            complete_email_only_account: { Args: { p_user: string; p_session: string; p_method: string }; Returns: boolean },
            secure_email_only_account: { Args: { p_user: string }; Returns: boolean },
            "commercial_access_active":
{ Args: { "p_user": string }; Returns: boolean
                           },
"comparable_pool":
{ Args: { "p_km_tol_pct"?: number,"p_listing_id": number,"p_max_age_days"?: number,"p_year_tol"?: number }; Returns: Database["public"]["Tables"]["listings"]["Row"][]
                          SetofOptions: {
        from: "*"
        to: "listings"
        isOneToOne: false
        isSetofReturn: true
      } },
"comparables":
{ Args: { "p_km_tol_pct"?: number,"p_listing_id": number,"p_max_age_days"?: number,"p_min_n"?: number,"p_year_tol"?: number }; Returns: Json
                           },
"dashboard_summary":
{ Args: Record<PropertyKey, never>; Returns: {
              "enabled": boolean,"filters": Json,"name": string,"new_this_week": number,"notification_frequency": Database["public"]['Enums']["notify_frequency"],"opportunities_this_week": number,"pending": boolean,"profile_id": number,"total": number,"unseen": number
            }[]
                           },
"decline_commercial_renewal":
{ Args: Record<PropertyKey, never>; Returns: undefined
                           },
"delete_my_account":
{ Args: Record<PropertyKey, never>; Returns: undefined
                           },
"effective_search_frequency":
{ Args: { "p_frequency": Database["public"]['Enums']["notify_frequency"],"p_user": string }; Returns: Database["public"]['Enums']["notify_frequency"]
                           },
"enable_commercial_pilot":
{ Args: Record<PropertyKey, never>; Returns: Json
                           },
"ensure_telegram_profile":
{ Args: { "p_chat_id": number,"p_telegram_user_id": number }; Returns: string
                           },
"expire_commercial_access":
{ Args: { "p_user"?: string }; Returns: number
                           },
"haversine_km":
{ Args: { "lat1": number,"lat2": number,"lon1": number,"lon2": number }; Returns: number
                           },
"join_waitlist":
{ Args: { "p_placement"?: string,"p_plan": string }; Returns: undefined
                           },
"link_telegram":
{ Args: { "p_chat_id": number,"p_code": string,"p_telegram_user_id": number }; Returns: string
                           },
"listing_price_tracks":
{ Args: { "p_listing_ids": (number)[] }; Returns: {
              "cum_pct": number | null,"cum_usd": number | null,"drops": number,"first_at": string,"first_currency": string,"first_price": number,"last_currency": string,"last_drop_at": string | null,"last_price": number,"listing_id": number,"rises": number
            }[]
                           },
"missed_since_expiry":
{ Args: Record<PropertyKey, never>; Returns: Json
                           },
"my_plan_feature":
{ Args: { "p_feature": string }; Returns: boolean
                           },
"my_margin_access":
{ Args: Record<PropertyKey, never>; Returns: Json
                           },
"my_margin_sort_keys":
{ Args: { "p_profile_id": number }; Returns: {
              "low": number,"match_id": number
            }[]
                           },
"my_match_margins":
{ Args: { "p_match_ids": (number)[] }; Returns: {
              "margin_ref": Json,"match_id": number
            }[]
                           },
"my_plan_limits":
{ Args: Record<PropertyKey, never>; Returns: Json
                           },
"my_plan_snapshot":
{ Args: Record<PropertyKey, never>; Returns: Json
                           },
"my_search_hidden_results":
{ Args: { "p_profile_id": number }; Returns: number
                           },
"submit_product_feedback":
{ Args: { "p_message": string,"p_profile": number | null,"p_request": string }; Returns: string
                           },
"sync_seller_filter_access":
{ Args: { "p_everyone"?: boolean,"p_user"?: string }; Returns: number
                           },
"notification_access_active":
{ Args: { "p_listing": number,"p_search": number,"p_user": string }; Returns: boolean
                           },
"plan_limits_for":
{ Args: { "p_user": string }; Returns: Json
                           },
"prepare_notification_delivery":
{ Args: { "p_id": number }; Returns: boolean
                           },
"preview_search":
{ Args: { "p_filters": Json,"p_origin_lat"?: number,"p_origin_lon"?: number,"p_radius_km"?: number }; Returns: Json
                           },
"pro_cta_state":
{ Args: Record<PropertyKey, never>; Returns: Json
                           },
"purge_stale_listings":
{ Args: { "p_days"?: number }; Returns: number
                           },
"recent_opportunities":
{ Args: { "p_limit"?: number }; Returns: {
              "body_type": string | null,
"color": string | null,
"color_method": string | null,
"currency": string | null,
"dealer_confirmed_at": string | null,
"dealer_id": number | null,
"dealer_name": string | null,
"financing_offered": boolean | null,
"first_seen_at": string | null,
"fuel": string | null,
"generated_at": string | null,
"images": Json | null,
"is_backfill": boolean | null,
"level": Database["public"]['Enums']["match_level"] | null,
"listing_id": number | null,
"listing_status": Database["public"]['Enums']["listing_status"] | null,
"location_text": string | null,
"make": string | null,
"match_id": number | null,
"mileage_km": number | null,
"model": string | null,
"note": string | null,
"price": number | null,
"price_kind": string | null,
"price_published": number | null,
"price_published_currency": string | null,
"price_ref": Json | null,
"price_source": string | null,
"price_usd": number | null,
"probable_repost_of": number | null,
"profile_name": string | null,
"published_at": string | null,
"red_flags": Json | null,
"rejection_reason": Database["public"]['Enums']["rejection_reason"] | null,
"saved": boolean | null,
"score": number | null,
"search_profile_id": number | null,
"source": string | null,
"status": Database["public"]['Enums']["interaction_status"] | null,
"title": string | null,
"transmission": string | null,
"trim": string | null,
"user_id": string | null,
"year": number | null
            }[]
                          SetofOptions: {
        from: "*"
        to: "match_cards"
        isOneToOne: false
        isSetofReturn: true
      } },
"record_commercial_payment":
{ Args: { "p_note"?: string,"p_offer": string,"p_paid_at"?: string,"p_provider": string,"p_reference": string,"p_user": string }; Returns: number
                           },
"record_plan_limit_hit":
{ Args: { "p_limit": string,"p_props"?: Json }; Returns: boolean
                           },
"record_purchase":
{ Args: { "p_currency"?: string,"p_date"?: string,"p_listing_id": number,"p_price"?: number,"p_search_profile_id"?: number }; Returns: number
                           },
"refund_commercial_payment":
{ Args: { "p_id": number,"p_reference": string }; Returns: undefined
                           },
"search_access_active":
{ Args: { "p_search": number }; Returns: boolean
                           },
"search_follow_counts":
{ Args: { "p_profile_id": number }; Returns: {
              "contacted_count": number,"purchased_count": number,"visit_scheduled_count": number
            }[]
                           },
"search_result_counts":
{ Args: { "p_profile_id": number }; Returns: {
              "all_count": number,"discarded_count": number,"new_count": number,"opportunities_count": number,"saved_count": number
            }[]
                           },
"search_results":
{ Args: { "p_filter"?: string,"p_limit"?: number,"p_offset"?: number,"p_profile_id": number,"p_sort"?: string }; Returns: {
              "body_type": string | null,
"color": string | null,
"color_method": string | null,
"currency": string | null,
"dealer_confirmed_at": string | null,
"dealer_id": number | null,
"dealer_name": string | null,
"financing_offered": boolean | null,
"first_seen_at": string | null,
"fuel": string | null,
"generated_at": string | null,
"images": Json | null,
"is_backfill": boolean | null,
"level": Database["public"]['Enums']["match_level"] | null,
"listing_id": number | null,
"listing_status": Database["public"]['Enums']["listing_status"] | null,
"location_text": string | null,
"make": string | null,
"match_id": number | null,
"mileage_km": number | null,
"model": string | null,
"note": string | null,
"price": number | null,
"price_kind": string | null,
"price_published": number | null,
"price_published_currency": string | null,
"price_ref": Json | null,
"price_source": string | null,
"price_usd": number | null,
"probable_repost_of": number | null,
"profile_name": string | null,
"published_at": string | null,
"red_flags": Json | null,
"rejection_reason": Database["public"]['Enums']["rejection_reason"] | null,
"saved": boolean | null,
"score": number | null,
"search_profile_id": number | null,
"source": string | null,
"status": Database["public"]['Enums']["interaction_status"] | null,
"title": string | null,
"transmission": string | null,
"trim": string | null,
"user_id": string | null,
"year": number | null
            }[]
                          SetofOptions: {
        from: "*"
        to: "match_cards"
        isOneToOne: false
        isSetofReturn: true
      } },
"track_email_open":
{ Args: { "p_id": number,"p_kind": string }; Returns: boolean
                           },
"track_lifecycle_click":
{ Args: { "p_id": number }; Returns: string | null
                           },
"my_bonus_trial":
{ Args: Record<PropertyKey, never>; Returns: Json
                           },
"start_my_bonus_trial":
{ Args: Record<PropertyKey, never>; Returns: Json
                           },
"record_email_feedback":
{ Args: { "p_email": number,"p_reason": string,"p_comment": string | null }; Returns: number | null
                           },
"track_notification_click":
{ Args: { "p_listing_id"?: number,"p_notification_id": number,"p_to"?: string }; Returns: {
              "listing_id": number,"url": string
            }[]
                           },
"unlink_telegram":
{ Args: Record<PropertyKey, never>; Returns: undefined
                           },
"unsubscribe_email":
{ Args: { "p_token": string }; Returns: string
                           }
          }
          Enums: {
            "interaction_status": "new"|"seen"|"interested"|"discarded"|"contacted"|"visit_scheduled"|"purchased","listing_status": "active"|"gone","llm_job_status": "queued"|"running"|"done"|"failed","match_level": "high"|"good"|"match"|"low","notification_channel": "telegram"|"email"|"web"|"push","notification_kind": "new_match"|"opportunity"|"price_drop"|"listing_gone"|"digest","notification_status": "queued"|"digest"|"sent"|"failed"|"skipped","notify_frequency": "immediate"|"daily","purchase_influence": "a_lot"|"some"|"little"|"none","rejection_reason": "too_expensive"|"too_many_km"|"wrong_trim"|"location"|"automatic"|"seller"|"apparent_condition"|"documentation"|"other","run_status": "running"|"ok"|"failed","user_plan": "free"|"pro"|"pass","user_role": "user"|"admin"
          }
          CompositeTypes: {
            [_ in never]: never
          }
        }
}

type DatabaseWithoutInternals = Omit<Database, '__InternalSupabase'>

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never = never
> = DefaultSchemaTableNameOrOptions extends { schema: keyof DatabaseWithoutInternals }
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
  ? (DefaultSchema["Tables"] & DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
      Row: infer R
    }
    ? R
    : never
  : never

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never
> = DefaultSchemaTableNameOrOptions extends { schema: keyof DatabaseWithoutInternals }
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
  ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
      Insert: infer I
    }
    ? I
    : never
  : never

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never
> = DefaultSchemaTableNameOrOptions extends { schema: keyof DatabaseWithoutInternals }
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
  ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
      Update: infer U
    }
    ? U
    : never
  : never

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    | keyof DefaultSchema["Enums"]
    | { schema: keyof DatabaseWithoutInternals },
  EnumName extends DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never = never
> = DefaultSchemaEnumNameOrOptions extends { schema: keyof DatabaseWithoutInternals }
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
  ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
  : never

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never = never
> = PublicCompositeTypeNameOrOptions extends { schema: keyof DatabaseWithoutInternals }
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
  ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
  : never

export const Constants = {
  "public": {
          Enums: {
            "interaction_status": ["new", "seen", "interested", "discarded", "contacted", "visit_scheduled", "purchased"],"listing_status": ["active", "gone"],"llm_job_status": ["queued", "running", "done", "failed"],"match_level": ["high", "good", "match", "low"],"notification_channel": ["telegram", "email", "web", "push"],"notification_kind": ["new_match", "opportunity", "price_drop", "listing_gone", "digest"],"notification_status": ["queued", "digest", "sent", "failed", "skipped"],"notify_frequency": ["immediate", "daily"],"purchase_influence": ["a_lot", "some", "little", "none"],"rejection_reason": ["too_expensive", "too_many_km", "wrong_trim", "location", "automatic", "seller", "apparent_condition", "documentation", "other"],"run_status": ["running", "ok", "failed"],"user_plan": ["free", "pro", "pass"],"user_role": ["user", "admin"]
          }
        }
} as const


export type Json = string | number | boolean | null | { [key: string]: Json | undefined } | Json[]

type BillingCheckoutRow = { id: string; user_id: string; offer: string; offer_version: string; amount: number; currency: string; billing_email: string; status: string; provider_id: string | null; init_point: string | null; created_at: string; last_synced_at: string | null; sync_error: string | null; next_payment_at: string | null; ad_attribution: Json | null }

export type Database = {

  "public": {
          Tables: {
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
                },"crawl_targets": {
                  Row: {
                    "active": boolean,"created_at": string,"first_run_done": boolean,"id": number,"last_run_at": string | null,"make": string | null,"model": string | null,"next_run_at": string | null,"query": NonNullable<Json>,"source": string,"updated_at": string
                  }
                  Insert: {
                    "active"?: boolean,"created_at"?: string,"first_run_done"?: boolean,"id"?: never,"last_run_at"?: string | null,"make"?: string | null,"model"?: string | null,"next_run_at"?: string | null,"query"?: NonNullable<Json>,"source": string,"updated_at"?: string
                  }
                  Update: {
                    "active"?: boolean,"created_at"?: string,"first_run_done"?: boolean,"id"?: never,"last_run_at"?: string | null,"make"?: string | null,"model"?: string | null,"next_run_at"?: string | null,"query"?: NonNullable<Json>,"source"?: string,"updated_at"?: string
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
                    "attributes": NonNullable<Json>,"currency": string | null,"description": string | null,"description_facts": Json | null,"detail_checked_at": string | null,"enriched_at": string | null,"external_id": string,"fingerprint": string | null,"first_seen_at": string,"fuel": string | null,"id": number,"images": NonNullable<Json>,"last_seen_at": string,"lat": number | null,"location_text": string | null,"lon": number | null,"make": string | null,"mileage_km": number | null,"model": string | null,"normalization_confidence": number | null,"price": number | null,"price_partial": boolean,"price_partial_reason": string | null,"price_published": number | null,"price_published_currency": string | null,"price_source": string,"price_usd": number | null,"probable_repost_of": number | null,"published_at": string | null,"seller_name": string | null,"seller_type": string | null,"source": string,"status": Database["public"]['Enums']["listing_status"],"title": string,"transmission": string | null,"trim": string | null,"url": string,"year": number | null
                  }
                  Insert: {
                    "attributes"?: NonNullable<Json>,"currency"?: string | null,"description"?: string | null,"description_facts"?: Json | null,"detail_checked_at"?: string | null,"enriched_at"?: string | null,"external_id": string,"fingerprint"?: string | null,"first_seen_at"?: string,"fuel"?: string | null,"id"?: never,"images"?: NonNullable<Json>,"last_seen_at"?: string,"lat"?: number | null,"location_text"?: string | null,"lon"?: number | null,"make"?: string | null,"mileage_km"?: number | null,"model"?: string | null,"normalization_confidence"?: number | null,"price"?: number | null,"price_partial"?: boolean,"price_partial_reason"?: string | null,"price_published"?: number | null,"price_published_currency"?: string | null,"price_source"?: string,"price_usd"?: number | null,"probable_repost_of"?: number | null,"published_at"?: string | null,"seller_name"?: string | null,"seller_type"?: string | null,"source": string,"status"?: Database["public"]['Enums']["listing_status"],"title": string,"transmission"?: string | null,"trim"?: string | null,"url": string,"year"?: number | null
                  }
                  Update: {
                    "attributes"?: NonNullable<Json>,"currency"?: string | null,"description"?: string | null,"description_facts"?: Json | null,"detail_checked_at"?: string | null,"enriched_at"?: string | null,"external_id"?: string,"fingerprint"?: string | null,"first_seen_at"?: string,"fuel"?: string | null,"id"?: never,"images"?: NonNullable<Json>,"last_seen_at"?: string,"lat"?: number | null,"location_text"?: string | null,"lon"?: number | null,"make"?: string | null,"mileage_km"?: number | null,"model"?: string | null,"normalization_confidence"?: number | null,"price"?: number | null,"price_partial"?: boolean,"price_partial_reason"?: string | null,"price_published"?: number | null,"price_published_currency"?: string | null,"price_source"?: string,"price_usd"?: number | null,"probable_repost_of"?: number | null,"published_at"?: string | null,"seller_name"?: string | null,"seller_type"?: string | null,"source"?: string,"status"?: Database["public"]['Enums']["listing_status"],"title"?: string,"transmission"?: string | null,"trim"?: string | null,"url"?: string,"year"?: number | null
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
                },"matches": {
                  Row: {
                    "generated_at": string,"id": number,"is_backfill": boolean,"level": Database["public"]['Enums']["match_level"],"listing_id": number,"match_reasons": NonNullable<Json>,"price_ref": Json | null,"red_flags": NonNullable<Json>,"score": number,"score_breakdown": NonNullable<Json>,"scoring_version": string,"search_profile_id": number,"seller_questions": string | null,"updated_at": string
                  }
                  Insert: {
                    "generated_at"?: string,"id"?: never,"is_backfill"?: boolean,"level": Database["public"]['Enums']["match_level"],"listing_id": number,"match_reasons": NonNullable<Json>,"price_ref"?: Json | null,"red_flags"?: NonNullable<Json>,"score": number,"score_breakdown": NonNullable<Json>,"scoring_version": string,"search_profile_id": number,"seller_questions"?: string | null,"updated_at"?: string
                  }
                  Update: {
                    "generated_at"?: string,"id"?: never,"is_backfill"?: boolean,"level"?: Database["public"]['Enums']["match_level"],"listing_id"?: number,"match_reasons"?: NonNullable<Json>,"price_ref"?: Json | null,"red_flags"?: NonNullable<Json>,"score"?: number,"score_breakdown"?: NonNullable<Json>,"scoring_version"?: string,"search_profile_id"?: number,"seller_questions"?: string | null,"updated_at"?: string
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
                    "created_at": string,"default_channels": (string)[],"default_notification_frequency": Database["public"]['Enums']["notify_frequency"],"default_origin_label": string | null,"default_origin_lat": number | null,"default_origin_lon": number | null,"email": string | null,"email_unsubscribe_token": string,"free_trial_started_at": string | null,"id": string,"phone": string | null,"plan": Database["public"]['Enums']["user_plan"],"plan_expires_at": string | null,"role": Database["public"]['Enums']["user_role"],"telegram_chat_id": number | null,"telegram_link_code": string,"telegram_user_id": number | null,"updated_at": string
                  }
                  Insert: {
                    "created_at"?: string,"default_channels"?: (string)[],"default_notification_frequency"?: Database["public"]['Enums']["notify_frequency"],"default_origin_label"?: string | null,"default_origin_lat"?: number | null,"default_origin_lon"?: number | null,"email"?: string | null,"email_unsubscribe_token"?: string,"free_trial_started_at"?: string | null,"id": string,"phone"?: string | null,"plan"?: Database["public"]['Enums']["user_plan"],"plan_expires_at"?: string | null,"role"?: Database["public"]['Enums']["user_role"],"telegram_chat_id"?: number | null,"telegram_link_code"?: string,"telegram_user_id"?: number | null,"updated_at"?: string
                  }
                  Update: {
                    "created_at"?: string,"default_channels"?: (string)[],"default_notification_frequency"?: Database["public"]['Enums']["notify_frequency"],"default_origin_label"?: string | null,"default_origin_lat"?: number | null,"default_origin_lon"?: number | null,"email"?: string | null,"email_unsubscribe_token"?: string,"free_trial_started_at"?: string | null,"id"?: string,"phone"?: string | null,"plan"?: Database["public"]['Enums']["user_plan"],"plan_expires_at"?: string | null,"role"?: Database["public"]['Enums']["user_role"],"telegram_chat_id"?: number | null,"telegram_link_code"?: string,"telegram_user_id"?: number | null,"updated_at"?: string
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
                    "bootstrapped_at": string | null,"channels": (string)[],"created_at": string,"enabled": boolean,"filters": NonNullable<Json>,"id": number,"name": string,"notification_frequency": Database["public"]['Enums']["notify_frequency"],"notify_min_level": Database["public"]['Enums']["match_level"],"origin_lat": number | null,"origin_lon": number | null,"preferences": NonNullable<Json>,"radius_km": number | null,"raw_query": string | null,"rematch_requested_at": string | null,"updated_at": string,"user_id": string
                  }
                  Insert: {
                    "bootstrapped_at"?: string | null,"channels"?: (string)[],"created_at"?: string,"enabled"?: boolean,"filters": NonNullable<Json>,"id"?: never,"name": string,"notification_frequency"?: Database["public"]['Enums']["notify_frequency"],"notify_min_level"?: Database["public"]['Enums']["match_level"],"origin_lat"?: number | null,"origin_lon"?: number | null,"preferences"?: NonNullable<Json>,"radius_km"?: number | null,"raw_query"?: string | null,"rematch_requested_at"?: string | null,"updated_at"?: string,"user_id": string
                  }
                  Update: {
                    "bootstrapped_at"?: string | null,"channels"?: (string)[],"created_at"?: string,"enabled"?: boolean,"filters"?: NonNullable<Json>,"id"?: never,"name"?: string,"notification_frequency"?: Database["public"]['Enums']["notify_frequency"],"notify_min_level"?: Database["public"]['Enums']["match_level"],"origin_lat"?: number | null,"origin_lon"?: number | null,"preferences"?: NonNullable<Json>,"radius_km"?: number | null,"raw_query"?: string | null,"rematch_requested_at"?: string | null,"updated_at"?: string,"user_id"?: string
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
                    "aliases": (string)[],"created_at": string,"fuels": (string)[],"id": number,"make": string,"model": string,"timing_belt": boolean | null,"transmissions": (string)[],"trim": string | null,"year_from": number | null,"year_to": number | null
                  }
                  Insert: {
                    "aliases"?: (string)[],"created_at"?: string,"fuels"?: (string)[],"id"?: never,"make": string,"model": string,"timing_belt"?: boolean | null,"transmissions"?: (string)[],"trim"?: string | null,"year_from"?: number | null,"year_to"?: number | null
                  }
                  Update: {
                    "aliases"?: (string)[],"created_at"?: string,"fuels"?: (string)[],"id"?: never,"make"?: string,"model"?: string,"timing_belt"?: boolean | null,"transmissions"?: (string)[],"trim"?: string | null,"year_from"?: number | null,"year_to"?: number | null
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
                },"admin_source_health": {
                  Row: {
                    "avg_seconds_24h": number | null,"consecutive_failures": number | null,"crawl_interval_seconds": number | null,"detail_interval_seconds": number | null,"enabled": boolean | null,"failed_24h": number | null,"found_24h": number | null,"id": string | null,"last_error": string | null,"last_ok_at": string | null,"last_run_at": string | null,"last_run_status": Database["public"]['Enums']["run_status"] | null,"name": string | null,"new_24h": number | null,"priority": number | null,"runs_24h": number | null,"updated_24h": number | null
                  }
                  Relationships: [

                  ]
                },"admin_users": {
                  Row: {
                    "alerts_7d": number | null,"created_at": string | null,"email": string | null,"enabled_searches": number | null,"id": string | null,"last_activity_at": string | null,"plan": Database["public"]['Enums']["user_plan"] | null,"plan_expires_at": string | null,"role": Database["public"]['Enums']["user_role"] | null,"searches": number | null,"telegram_linked": boolean | null,"telegram_only": boolean | null,"waitlist_plan": string | null
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
                    "currency": string | null,"financing_offered": boolean | null,"first_seen_at": string | null,"fuel": string | null,"generated_at": string | null,"images": Json | null,"is_backfill": boolean | null,"level": Database["public"]['Enums']["match_level"] | null,"listing_id": number | null,"listing_status": Database["public"]['Enums']["listing_status"] | null,"location_text": string | null,"make": string | null,"match_id": number | null,"mileage_km": number | null,"model": string | null,"price": number | null,"price_kind": string | null,"price_published": number | null,"price_published_currency": string | null,"price_ref": Json | null,"price_source": string | null,"price_usd": number | null,"probable_repost_of": number | null,"profile_name": string | null,"published_at": string | null,"red_flags": Json | null,"rejection_reason": Database["public"]['Enums']["rejection_reason"] | null,"saved": boolean | null,"score": number | null,"search_profile_id": number | null,"source": string | null,"status": Database["public"]['Enums']["interaction_status"] | null,"title": string | null,"transmission": string | null,"trim": string | null,"user_id": string | null,"year": number | null
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
            begin_billing_checkout: { Args: { p_user: string; p_offer: string; p_email: string; p_version: string; p_expected_amount: number }; Returns: Json },
            apply_mercadopago_payment: { Args: { p_checkout: string; p_reference: string; p_status: string; p_amount: number; p_currency: string; p_paid_at: string; p_start: string; p_end: string }; Returns: number },
            "commercial_access_active":
{ Args: { "p_user": string }; Returns: boolean
                           },
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
"my_plan_limits":
{ Args: Record<PropertyKey, never>; Returns: Json
                           },
"my_plan_snapshot":
{ Args: Record<PropertyKey, never>; Returns: Json
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
              "currency": string | null,
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
"search_result_counts":
{ Args: { "p_profile_id": number }; Returns: {
              "all_count": number,"discarded_count": number,"new_count": number,"opportunities_count": number,"saved_count": number
            }[]
                           },
"search_results":
{ Args: { "p_filter"?: string,"p_limit"?: number,"p_offset"?: number,"p_profile_id": number,"p_sort"?: string }; Returns: {
              "currency": string | null,
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

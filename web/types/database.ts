
export type Json = string | number | boolean | null | { [key: string]: Json | undefined } | Json[]

export type Database = {
  
  "public": {
          Tables: {
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
                    "attributes": NonNullable<Json>,"currency": string | null,"description": string | null,"detail_checked_at": string | null,"enriched_at": string | null,"external_id": string,"fingerprint": string | null,"first_seen_at": string,"fuel": string | null,"id": number,"images": NonNullable<Json>,"last_seen_at": string,"lat": number | null,"location_text": string | null,"lon": number | null,"make": string | null,"mileage_km": number | null,"model": string | null,"normalization_confidence": number | null,"price": number | null,"price_partial": boolean,"price_partial_reason": string | null,"price_usd": number | null,"probable_repost_of": number | null,"published_at": string | null,"seller_name": string | null,"seller_type": string | null,"source": string,"status": Database["public"]['Enums']["listing_status"],"title": string,"transmission": string | null,"trim": string | null,"url": string,"year": number | null
                  }
                  Insert: {
                    "attributes"?: NonNullable<Json>,"currency"?: string | null,"description"?: string | null,"detail_checked_at"?: string | null,"enriched_at"?: string | null,"external_id": string,"fingerprint"?: string | null,"first_seen_at"?: string,"fuel"?: string | null,"id"?: never,"images"?: NonNullable<Json>,"last_seen_at"?: string,"lat"?: number | null,"location_text"?: string | null,"lon"?: number | null,"make"?: string | null,"mileage_km"?: number | null,"model"?: string | null,"normalization_confidence"?: number | null,"price"?: number | null,"price_partial"?: boolean,"price_partial_reason"?: string | null,"price_usd"?: number | null,"probable_repost_of"?: number | null,"published_at"?: string | null,"seller_name"?: string | null,"seller_type"?: string | null,"source": string,"status"?: Database["public"]['Enums']["listing_status"],"title": string,"transmission"?: string | null,"trim"?: string | null,"url": string,"year"?: number | null
                  }
                  Update: {
                    "attributes"?: NonNullable<Json>,"currency"?: string | null,"description"?: string | null,"detail_checked_at"?: string | null,"enriched_at"?: string | null,"external_id"?: string,"fingerprint"?: string | null,"first_seen_at"?: string,"fuel"?: string | null,"id"?: never,"images"?: NonNullable<Json>,"last_seen_at"?: string,"lat"?: number | null,"location_text"?: string | null,"lon"?: number | null,"make"?: string | null,"mileage_km"?: number | null,"model"?: string | null,"normalization_confidence"?: number | null,"price"?: number | null,"price_partial"?: boolean,"price_partial_reason"?: string | null,"price_usd"?: number | null,"probable_repost_of"?: number | null,"published_at"?: string | null,"seller_name"?: string | null,"seller_type"?: string | null,"source"?: string,"status"?: Database["public"]['Enums']["listing_status"],"title"?: string,"transmission"?: string | null,"trim"?: string | null,"url"?: string,"year"?: number | null
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
      referencedRelation: "search_profiles"
      referencedColumns: ["id"]
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
      referencedRelation: "search_profiles"
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
      referencedRelation: "search_profiles"
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
                },"profiles": {
                  Row: {
                    "created_at": string,"default_channels": (string)[],"default_notification_frequency": Database["public"]['Enums']["notify_frequency"],"default_origin_label": string | null,"default_origin_lat": number | null,"default_origin_lon": number | null,"email": string | null,"id": string,"phone": string | null,"plan": Database["public"]['Enums']["user_plan"],"plan_expires_at": string | null,"role": Database["public"]['Enums']["user_role"],"telegram_chat_id": number | null,"telegram_link_code": string,"telegram_user_id": number | null,"updated_at": string
                  }
                  Insert: {
                    "created_at"?: string,"default_channels"?: (string)[],"default_notification_frequency"?: Database["public"]['Enums']["notify_frequency"],"default_origin_label"?: string | null,"default_origin_lat"?: number | null,"default_origin_lon"?: number | null,"email"?: string | null,"id": string,"phone"?: string | null,"plan"?: Database["public"]['Enums']["user_plan"],"plan_expires_at"?: string | null,"role"?: Database["public"]['Enums']["user_role"],"telegram_chat_id"?: number | null,"telegram_link_code"?: string,"telegram_user_id"?: number | null,"updated_at"?: string
                  }
                  Update: {
                    "created_at"?: string,"default_channels"?: (string)[],"default_notification_frequency"?: Database["public"]['Enums']["notify_frequency"],"default_origin_label"?: string | null,"default_origin_lat"?: number | null,"default_origin_lon"?: number | null,"email"?: string | null,"id"?: string,"phone"?: string | null,"plan"?: Database["public"]['Enums']["user_plan"],"plan_expires_at"?: string | null,"role"?: Database["public"]['Enums']["user_role"],"telegram_chat_id"?: number | null,"telegram_link_code"?: string,"telegram_user_id"?: number | null,"updated_at"?: string
                  }
                  Relationships: [
                    
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
                }
          }
          Views: {
            "llm_job_stats": {
                  Row: {
                    "day": string | null,"done": number | null,"failed": number | null,"jobs": number | null,"kind": string | null,"latency_max_ms": number | null,"latency_p50_ms": number | null,"latency_p95_ms": number | null,"provider": string | null
                  }
                  Relationships: [
                    
                  ]
                },"match_cards": {
                  Row: {
                    "currency": string | null,"first_seen_at": string | null,"fuel": string | null,"generated_at": string | null,"images": Json | null,"is_backfill": boolean | null,"level": Database["public"]['Enums']["match_level"] | null,"listing_id": number | null,"listing_status": Database["public"]['Enums']["listing_status"] | null,"location_text": string | null,"make": string | null,"match_id": number | null,"mileage_km": number | null,"model": string | null,"price": number | null,"price_ref": Json | null,"price_usd": number | null,"probable_repost_of": number | null,"profile_name": string | null,"published_at": string | null,"red_flags": Json | null,"rejection_reason": Database["public"]['Enums']["rejection_reason"] | null,"saved": boolean | null,"score": number | null,"search_profile_id": number | null,"source": string | null,"status": Database["public"]['Enums']["interaction_status"] | null,"title": string | null,"transmission": string | null,"trim": string | null,"user_id": string | null,"year": number | null
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
      referencedRelation: "search_profiles"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "search_profiles_user_id_fkey"
      columns: ["user_id"]
isOneToOne: false
      referencedRelation: "profiles"
      referencedColumns: ["id"]
    }
                  ]
                }
          }
          Functions: {
            "comparables":
{ Args: { "p_km_tol_pct"?: number,"p_listing_id": number,"p_max_age_days"?: number,"p_min_n"?: number,"p_year_tol"?: number }; Returns: Json
                           },
"dashboard_summary":
{ Args: Record<PropertyKey, never>; Returns: {
              "enabled": boolean,"filters": Json,"name": string,"new_this_week": number,"notification_frequency": Database["public"]['Enums']["notify_frequency"],"opportunities_this_week": number,"pending": boolean,"profile_id": number,"total": number,"unseen": number
            }[]
                           },
"ensure_telegram_profile":
{ Args: { "p_chat_id": number,"p_telegram_user_id": number }; Returns: string
                           },
"haversine_km":
{ Args: { "lat1": number,"lat2": number,"lon1": number,"lon2": number }; Returns: number
                           },
"link_telegram":
{ Args: { "p_chat_id": number,"p_code": string,"p_telegram_user_id": number }; Returns: string
                           },
"preview_search":
{ Args: { "p_filters": Json,"p_origin_lat"?: number,"p_origin_lon"?: number,"p_radius_km"?: number }; Returns: Json
                           },
"recent_opportunities":
{ Args: { "p_limit"?: number }; Returns: {
              "currency": string | null,
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
"price_ref": Json | null,
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
"record_purchase":
{ Args: { "p_currency"?: string,"p_date"?: string,"p_listing_id": number,"p_price"?: number,"p_search_profile_id"?: number }; Returns: number
                           },
"search_result_counts":
{ Args: { "p_profile_id": number }; Returns: {
              "all_count": number,"discarded_count": number,"new_count": number,"opportunities_count": number,"saved_count": number
            }[]
                           },
"search_results":
{ Args: { "p_filter"?: string,"p_limit"?: number,"p_offset"?: number,"p_profile_id": number,"p_sort"?: string }; Returns: {
              "currency": string | null,
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
"price_ref": Json | null,
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


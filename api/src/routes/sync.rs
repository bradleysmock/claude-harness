use axum::{
    body::Bytes,
    extract::{Path, Query, State},
    http::{HeaderMap, StatusCode},
    response::IntoResponse,
    routing::{delete, get, post},
    Json, Router,
};
use base64::{engine::general_purpose::STANDARD, Engine};
use chrono::Utc;
use hmac::{Hmac, Mac};
use serde::Deserialize;
use serde_json::json;
use sha2::Sha256;
use uuid::Uuid;

use crate::models::{ExternalListingRecord, SyncCredential};
use crate::AppState;

// ─── Request bodies ───────────────────────────────────────────────────────────

#[derive(Deserialize)]
struct ConnectPlatformBody {
    platform: String,
    shop_domain: Option<String>,
    shop_id: Option<String>,
}

#[derive(Deserialize)]
struct CreateListingBody {
    inventory_item_id: String,
    platform: String,
    external_id: String,
    external_variant_id: Option<String>,
    external_url: Option<String>,
}

#[derive(Deserialize, Default)]
struct ListingsQuery {
    inventory_item_id: Option<String>,
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

fn valid_platform(p: &str) -> bool {
    matches!(p, "etsy" | "shopify")
}

fn verify_shopify_hmac(body: &[u8], expected_b64: &str, secret: &str) -> bool {
    type HmacSha256 = Hmac<Sha256>;

    let expected_bytes = match STANDARD.decode(expected_b64) {
        Ok(b) => b,
        Err(_) => return false,
    };

    let mut mac = match HmacSha256::new_from_slice(secret.as_bytes()) {
        Ok(m) => m,
        Err(_) => return false,
    };
    mac.update(body);
    mac.verify_slice(&expected_bytes).is_ok()
}

fn extract_variant_ids(payload: &serde_json::Value) -> Vec<String> {
    let mut ids: Vec<String> = payload
        .get("line_items")
        .and_then(|li| li.as_array())
        .map(|items| {
            items
                .iter()
                .filter_map(|item| item.get("variant_id"))
                .filter(|v| !v.is_null())
                .map(|v| match v {
                    serde_json::Value::Number(n) => n.to_string(),
                    serde_json::Value::String(s) => s.clone(),
                    _ => v.to_string(),
                })
                .collect()
        })
        .unwrap_or_default();
    ids.sort();
    ids.dedup();
    ids
}

// ─── Handlers ─────────────────────────────────────────────────────────────────

async fn connect_platform(
    State(state): State<AppState>,
    Json(body): Json<ConnectPlatformBody>,
) -> impl IntoResponse {
    if !valid_platform(&body.platform) {
        return (
            StatusCode::UNPROCESSABLE_ENTITY,
            Json(json!({"error": "invalid platform; must be 'etsy' or 'shopify'"})),
        )
            .into_response();
    }

    let cred = SyncCredential {
        platform: body.platform.clone(),
        shop_domain: body.shop_domain,
        shop_id: body.shop_id,
        connected_at: Utc::now().to_rfc3339(),
    };

    let mut guard = state.lock().await;
    let (farm, path) = &mut *guard;
    farm.sync_credentials
        .retain(|c| c.platform != body.platform);
    farm.sync_credentials.push(cred.clone());
    let _ = crate::store::save(path, farm);

    (StatusCode::OK, Json(cred)).into_response()
}

async fn list_platforms(State(state): State<AppState>) -> impl IntoResponse {
    let guard = state.lock().await;
    let (farm, _) = &*guard;
    (StatusCode::OK, Json(farm.sync_credentials.clone()))
}

async fn disconnect_platform(
    State(state): State<AppState>,
    Path(platform): Path<String>,
) -> impl IntoResponse {
    let mut guard = state.lock().await;
    let (farm, path) = &mut *guard;
    let before = farm.sync_credentials.len();
    farm.sync_credentials.retain(|c| c.platform != platform);
    if farm.sync_credentials.len() == before {
        return (
            StatusCode::NOT_FOUND,
            Json(json!({"error": "platform not connected"})),
        )
            .into_response();
    }
    let _ = crate::store::save(path, farm);
    StatusCode::NO_CONTENT.into_response()
}

async fn create_listing(
    State(state): State<AppState>,
    Json(body): Json<CreateListingBody>,
) -> impl IntoResponse {
    if !valid_platform(&body.platform) {
        return (
            StatusCode::UNPROCESSABLE_ENTITY,
            Json(json!({"error": "invalid platform"})),
        )
            .into_response();
    }

    let mut guard = state.lock().await;
    let (farm, path) = &mut *guard;

    let exists = farm
        .external_listings
        .iter()
        .any(|l| l.inventory_item_id == body.inventory_item_id && l.platform == body.platform);
    if exists {
        return (
            StatusCode::UNPROCESSABLE_ENTITY,
            Json(json!({"error": "listing already exists for this item and platform"})),
        )
            .into_response();
    }

    let record = ExternalListingRecord {
        id: Uuid::new_v4().to_string(),
        inventory_item_id: body.inventory_item_id,
        platform: body.platform,
        external_id: body.external_id,
        external_variant_id: body.external_variant_id,
        external_url: body.external_url,
        synced_at: Utc::now().to_rfc3339(),
    };

    farm.external_listings.push(record.clone());
    let _ = crate::store::save(path, farm);

    (StatusCode::CREATED, Json(record)).into_response()
}

async fn list_listings(
    State(state): State<AppState>,
    Query(params): Query<ListingsQuery>,
) -> impl IntoResponse {
    let guard = state.lock().await;
    let (farm, _) = &*guard;

    let listings: Vec<ExternalListingRecord> = farm
        .external_listings
        .iter()
        .filter(|l| match &params.inventory_item_id {
            Some(id) => &l.inventory_item_id == id,
            None => true,
        })
        .cloned()
        .collect();

    (StatusCode::OK, Json(listings))
}

async fn remove_listing(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> impl IntoResponse {
    let mut guard = state.lock().await;
    let (farm, path) = &mut *guard;
    let before = farm.external_listings.len();
    farm.external_listings.retain(|l| l.id != id);
    if farm.external_listings.len() == before {
        return (
            StatusCode::NOT_FOUND,
            Json(json!({"error": "listing not found"})),
        )
            .into_response();
    }
    let _ = crate::store::save(path, farm);
    StatusCode::NO_CONTENT.into_response()
}

async fn mark_item_sold(
    State(state): State<AppState>,
    Path(id): Path<String>,
    headers: HeaderMap,
) -> impl IntoResponse {
    let idempotency_key = headers
        .get("idempotency-key")
        .and_then(|v| v.to_str().ok())
        .map(str::to_string);

    let mut guard = state.lock().await;
    let (farm, path) = &mut *guard;

    // Key already used — return the original item without mutating
    if let Some(ref key) = idempotency_key {
        if let Some(item_id) = farm.idempotency_keys.get(key) {
            if let Some(item) = farm.inventory.iter().find(|i| &i.id == item_id) {
                return (StatusCode::OK, Json(json!(item.clone()))).into_response();
            }
        }
    }

    let pos = farm.inventory.iter().position(|i| i.id == id);
    match pos {
        None => (
            StatusCode::NOT_FOUND,
            Json(json!({"error": "inventory item not found"})),
        )
            .into_response(),
        Some(idx) if farm.inventory[idx].stage == "sold" => {
            let existing = farm.inventory[idx].clone();
            (StatusCode::OK, Json(json!(existing))).into_response()
        }
        Some(idx) => {
            farm.inventory[idx].stage = "sold".to_string();
            // Store key atomically with the stage change
            if let Some(key) = idempotency_key {
                farm.idempotency_keys.insert(key, id);
            }
            let updated = farm.inventory[idx].clone();
            let _ = crate::store::save(path, farm);
            (StatusCode::OK, Json(updated)).into_response()
        }
    }
}

async fn shopify_webhook(
    State(state): State<AppState>,
    headers: HeaderMap,
    body: Bytes,
) -> impl IntoResponse {
    let secret = match std::env::var("SHOPIFY_WEBHOOK_SECRET") {
        Ok(s) => s,
        Err(_) => {
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"error": "webhook secret not configured"})),
            )
                .into_response()
        }
    };

    let hmac_header = match headers
        .get("x-shopify-hmac-sha256")
        .and_then(|v| v.to_str().ok())
    {
        Some(h) => h.to_string(),
        None => {
            return (
                StatusCode::UNAUTHORIZED,
                Json(json!({"error": "missing HMAC header"})),
            )
                .into_response()
        }
    };

    if !verify_shopify_hmac(&body, &hmac_header, &secret) {
        return (
            StatusCode::UNAUTHORIZED,
            Json(json!({"error": "invalid webhook signature"})),
        )
            .into_response();
    }

    let payload: serde_json::Value = match serde_json::from_slice(&body) {
        Ok(v) => v,
        Err(_) => {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({"error": "invalid JSON body"})),
            )
                .into_response()
        }
    };

    let variant_ids = extract_variant_ids(&payload);

    let mut marked_sold: Vec<String> = Vec::new();
    let mut guard = state.lock().await;
    let (farm, path) = &mut *guard;

    for variant_id in &variant_ids {
        let item_id_opt: Option<String> = farm
            .external_listings
            .iter()
            .find(|l| {
                l.platform == "shopify"
                    && l.external_variant_id.as_deref() == Some(variant_id.as_str())
            })
            .map(|l| l.inventory_item_id.clone());

        if let Some(item_id) = item_id_opt {
            if let Some(item) = farm
                .inventory
                .iter_mut()
                .find(|i| i.id == item_id && i.stage != "sold")
            {
                item.stage = "sold".to_string();
                marked_sold.push(item_id);
            }
        }
    }

    if !marked_sold.is_empty() {
        let _ = crate::store::save(path, farm);
    }

    (StatusCode::OK, Json(json!({"marked_sold": marked_sold}))).into_response()
}

// ─── Router ───────────────────────────────────────────────────────────────────

pub fn sync_router() -> Router<AppState> {
    Router::new()
        .route(
            "/api/sync/platforms",
            get(list_platforms).post(connect_platform),
        )
        .route("/api/sync/platforms/:platform", delete(disconnect_platform))
        .route(
            "/api/sync/listings",
            get(list_listings).post(create_listing),
        )
        .route("/api/sync/listings/:id", delete(remove_listing))
        .route("/api/inventory/:id/mark-sold", post(mark_item_sold))
        .route("/api/sync/webhooks/shopify", post(shopify_webhook))
}

// ─── Tests ────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod sync_tests {
    use std::path::PathBuf;
    use std::sync::Arc;

    use axum::body::Body;
    use axum::http::{Method, Request, StatusCode};
    use serde_json::{json, Value};
    use tokio::sync::Mutex;
    use tower::ServiceExt;

    use crate::models::{FarmData, InventoryItem};
    use crate::{build_app, AppState};

    fn make_state() -> AppState {
        Arc::new(Mutex::new((
            FarmData::default(),
            PathBuf::from("/tmp/test_sync.json"),
        )))
    }

    async fn body_json(body: axum::body::Body) -> Value {
        let bytes = axum::body::to_bytes(body, usize::MAX).await.unwrap();
        serde_json::from_slice(&bytes).unwrap()
    }

    fn make_inventory_item(id: &str, stage: &str) -> InventoryItem {
        InventoryItem {
            id: id.to_string(),
            name: "Test Item".to_string(),
            stage: stage.to_string(),
            weight_oz: 10.0,
            location: String::new(),
            clip_id: None,
            mill_order_id: None,
            sku: None,
            notes: String::new(),
        }
    }

    // ── platforms ──────────────────────────────────────────────────────────────

    #[tokio::test]
    async fn test_connect_etsy_returns_200() {
        let app = build_app(make_state());
        let resp = app
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/api/sync/platforms")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        serde_json::to_vec(&json!({"platform": "etsy", "shop_id": "123"})).unwrap(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let json = body_json(resp.into_body()).await;
        assert_eq!(json["platform"], "etsy");
        assert_eq!(json["shop_id"], "123");
        assert!(json["connected_at"].is_string());
    }

    #[tokio::test]
    async fn test_connect_invalid_platform_returns_422() {
        let app = build_app(make_state());
        let resp = app
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/api/sync/platforms")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        serde_json::to_vec(&json!({"platform": "twitter"})).unwrap(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::UNPROCESSABLE_ENTITY);
    }

    #[tokio::test]
    async fn test_connect_platform_upserts() {
        let state = make_state();
        let app = build_app(state);
        let post = |body: Value| {
            Request::builder()
                .method(Method::POST)
                .uri("/api/sync/platforms")
                .header("content-type", "application/json")
                .body(Body::from(serde_json::to_vec(&body).unwrap()))
                .unwrap()
        };
        let _ = app
            .clone()
            .oneshot(post(json!({"platform": "etsy", "shop_id": "old"})))
            .await
            .unwrap();
        let resp = app
            .clone()
            .oneshot(post(json!({"platform": "etsy", "shop_id": "new"})))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let list_resp = app
            .oneshot(
                Request::builder()
                    .uri("/api/sync/platforms")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        let arr = body_json(list_resp.into_body()).await;
        assert_eq!(arr.as_array().unwrap().len(), 1);
        assert_eq!(arr[0]["shop_id"], "new");
    }

    #[tokio::test]
    async fn test_list_platforms_empty() {
        let app = build_app(make_state());
        let resp = app
            .oneshot(
                Request::builder()
                    .uri("/api/sync/platforms")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        assert_eq!(body_json(resp.into_body()).await, json!([]));
    }

    #[tokio::test]
    async fn test_disconnect_platform_returns_204() {
        let state = make_state();
        let app = build_app(state);
        let _ = app
            .clone()
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/api/sync/platforms")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        serde_json::to_vec(&json!({"platform": "shopify"})).unwrap(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        let resp = app
            .oneshot(
                Request::builder()
                    .method(Method::DELETE)
                    .uri("/api/sync/platforms/shopify")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::NO_CONTENT);
    }

    #[tokio::test]
    async fn test_disconnect_unconnected_returns_404() {
        let app = build_app(make_state());
        let resp = app
            .oneshot(
                Request::builder()
                    .method(Method::DELETE)
                    .uri("/api/sync/platforms/etsy")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::NOT_FOUND);
    }

    // ── listings ───────────────────────────────────────────────────────────────

    #[tokio::test]
    async fn test_create_listing_returns_201() {
        let app = build_app(make_state());
        let body = json!({
            "inventory_item_id": "item-1",
            "platform": "etsy",
            "external_id": "listing-abc"
        });
        let resp = app
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/api/sync/listings")
                    .header("content-type", "application/json")
                    .body(Body::from(serde_json::to_vec(&body).unwrap()))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::CREATED);
        let json = body_json(resp.into_body()).await;
        assert!(json["id"].is_string());
        assert_eq!(json["platform"], "etsy");
        assert_eq!(json["external_id"], "listing-abc");
    }

    #[tokio::test]
    async fn test_create_listing_duplicate_returns_422() {
        let state = make_state();
        let app = build_app(state);
        let body = json!({
            "inventory_item_id": "item-1",
            "platform": "etsy",
            "external_id": "listing-abc"
        });
        let req = || {
            Request::builder()
                .method(Method::POST)
                .uri("/api/sync/listings")
                .header("content-type", "application/json")
                .body(Body::from(serde_json::to_vec(&body).unwrap()))
                .unwrap()
        };
        let _ = app.clone().oneshot(req()).await.unwrap();
        let resp = app.oneshot(req()).await.unwrap();
        assert_eq!(resp.status(), StatusCode::UNPROCESSABLE_ENTITY);
    }

    #[tokio::test]
    async fn test_list_listings_filter_by_item() {
        let state = make_state();
        let app = build_app(state);
        for (item_id, ext_id) in [("item-1", "e1"), ("item-2", "e2")] {
            let _ = app
                .clone()
                .oneshot(
                    Request::builder()
                        .method(Method::POST)
                        .uri("/api/sync/listings")
                        .header("content-type", "application/json")
                        .body(Body::from(
                            serde_json::to_vec(&json!({
                                "inventory_item_id": item_id,
                                "platform": "etsy",
                                "external_id": ext_id
                            }))
                            .unwrap(),
                        ))
                        .unwrap(),
                )
                .await
                .unwrap();
        }
        let resp = app
            .oneshot(
                Request::builder()
                    .uri("/api/sync/listings?inventory_item_id=item-1")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        let arr = body_json(resp.into_body()).await;
        let items = arr.as_array().unwrap();
        assert_eq!(items.len(), 1);
        assert_eq!(items[0]["inventory_item_id"], "item-1");
    }

    #[tokio::test]
    async fn test_delete_listing_returns_204() {
        let state = make_state();
        let app = build_app(state);
        let create_resp = app
            .clone()
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/api/sync/listings")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        serde_json::to_vec(&json!({
                            "inventory_item_id": "item-1",
                            "platform": "etsy",
                            "external_id": "e1"
                        }))
                        .unwrap(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        let listing_id = body_json(create_resp.into_body()).await["id"]
            .as_str()
            .unwrap()
            .to_string();

        let resp = app
            .oneshot(
                Request::builder()
                    .method(Method::DELETE)
                    .uri(format!("/api/sync/listings/{}", listing_id))
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::NO_CONTENT);
    }

    #[tokio::test]
    async fn test_delete_listing_not_found_returns_404() {
        let app = build_app(make_state());
        let resp = app
            .oneshot(
                Request::builder()
                    .method(Method::DELETE)
                    .uri("/api/sync/listings/no-such-id")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::NOT_FOUND);
    }

    // ── mark-sold ──────────────────────────────────────────────────────────────

    #[tokio::test]
    async fn test_mark_item_sold_returns_200() {
        let state = make_state();
        {
            let mut guard = state.lock().await;
            guard.0.inventory.push(make_inventory_item("inv-1", "yarn"));
        }
        let app = build_app(state);
        let resp = app
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/api/inventory/inv-1/mark-sold")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let json = body_json(resp.into_body()).await;
        assert_eq!(json["stage"], "sold");
    }

    #[tokio::test]
    async fn test_mark_item_sold_already_sold_returns_200_idempotent() {
        let state = make_state();
        {
            let mut guard = state.lock().await;
            guard.0.inventory.push(make_inventory_item("inv-1", "sold"));
        }
        let app = build_app(state);
        let resp = app
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/api/inventory/inv-1/mark-sold")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let json = body_json(resp.into_body()).await;
        assert_eq!(json["stage"], "sold");
    }

    #[tokio::test]
    async fn test_mark_item_sold_not_found_returns_404() {
        let app = build_app(make_state());
        let resp = app
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/api/inventory/no-such/mark-sold")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::NOT_FOUND);
    }

    // ── shopify webhook ────────────────────────────────────────────────────────

    static ENV_LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());

    fn compute_hmac_b64(body: &[u8], secret: &str) -> String {
        use base64::{engine::general_purpose::STANDARD, Engine};
        use hmac::{Hmac, Mac};
        use sha2::Sha256;
        type HmacSha256 = Hmac<Sha256>;
        let mut mac = HmacSha256::new_from_slice(secret.as_bytes()).unwrap();
        mac.update(body);
        STANDARD.encode(mac.finalize().into_bytes())
    }

    #[tokio::test]
    async fn test_webhook_missing_secret_env_returns_500() {
        let _lock = ENV_LOCK.lock().unwrap();
        std::env::remove_var("SHOPIFY_WEBHOOK_SECRET");
        let app = build_app(make_state());
        let resp = app
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/api/sync/webhooks/shopify")
                    .header("content-type", "application/json")
                    .header("x-shopify-hmac-sha256", "dummy")
                    .body(Body::from(b"{}".to_vec()))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::INTERNAL_SERVER_ERROR);
    }

    #[tokio::test]
    async fn test_webhook_bad_hmac_returns_401() {
        let _lock = ENV_LOCK.lock().unwrap();
        std::env::set_var("SHOPIFY_WEBHOOK_SECRET", "test-secret");
        let app = build_app(make_state());
        let body = b"{}";
        let resp = app
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/api/sync/webhooks/shopify")
                    .header("content-type", "application/json")
                    .header("x-shopify-hmac-sha256", "badsignature==")
                    .body(Body::from(body.to_vec()))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
        std::env::remove_var("SHOPIFY_WEBHOOK_SECRET");
    }

    #[tokio::test]
    async fn test_webhook_valid_marks_sold_by_variant_id() {
        let _lock = ENV_LOCK.lock().unwrap();
        let secret = "webhook-secret-xyz";
        std::env::set_var("SHOPIFY_WEBHOOK_SECRET", secret);

        let state = make_state();
        {
            let mut guard = state.lock().await;
            guard.0.inventory.push(make_inventory_item("inv-1", "yarn"));
            guard
                .0
                .external_listings
                .push(crate::models::ExternalListingRecord {
                    id: "listing-1".to_string(),
                    inventory_item_id: "inv-1".to_string(),
                    platform: "shopify".to_string(),
                    external_id: "prod-999".to_string(),
                    external_variant_id: Some("var-42".to_string()),
                    external_url: None,
                    synced_at: "2024-01-01T00:00:00Z".to_string(),
                });
        }

        let payload = json!({
            "line_items": [
                {"variant_id": "var-42", "quantity": 1}
            ]
        });
        let body_bytes = serde_json::to_vec(&payload).unwrap();
        let hmac = compute_hmac_b64(&body_bytes, secret);

        let app = build_app(state);
        let resp = app
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/api/sync/webhooks/shopify")
                    .header("content-type", "application/json")
                    .header("x-shopify-hmac-sha256", hmac)
                    .body(Body::from(body_bytes))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let json = body_json(resp.into_body()).await;
        assert_eq!(json["marked_sold"], json!(["inv-1"]));

        std::env::remove_var("SHOPIFY_WEBHOOK_SECRET");
    }

    #[tokio::test]
    async fn test_webhook_no_matching_variant_returns_empty() {
        let _lock = ENV_LOCK.lock().unwrap();
        let secret = "test-secret-2";
        std::env::set_var("SHOPIFY_WEBHOOK_SECRET", secret);

        let payload = json!({"line_items": [{"variant_id": "var-999"}]});
        let body_bytes = serde_json::to_vec(&payload).unwrap();
        let hmac = compute_hmac_b64(&body_bytes, secret);

        let app = build_app(make_state());
        let resp = app
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/api/sync/webhooks/shopify")
                    .header("content-type", "application/json")
                    .header("x-shopify-hmac-sha256", hmac)
                    .body(Body::from(body_bytes))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let json = body_json(resp.into_body()).await;
        assert_eq!(json["marked_sold"], json!([]));

        std::env::remove_var("SHOPIFY_WEBHOOK_SECRET");
    }
}

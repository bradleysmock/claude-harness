use axum::{
    extract::{Path, State},
    http::{header, HeaderMap, StatusCode},
    response::{IntoResponse, Response},
    routing::{get, patch},
    Json, Router,
};
use serde::Deserialize;
use serde_json::json;

use crate::AppState;

// ── Request types ──────────────────────────────────────────────────────────

#[derive(Debug, Deserialize)]
struct CreatePreOrderBody {
    customer_name: String,
    contact: String,
    product_description: String,
    weight_oz: f64,
    deposit_usd: f64,
    inventory_item_id: Option<String>,
    forecast_delivery_date: Option<String>,
}

#[derive(Debug, Deserialize)]
struct PatchStatusBody {
    status: String,
}

// ── Helpers ────────────────────────────────────────────────────────────────

fn err_json(msg: &str) -> Json<serde_json::Value> {
    Json(json!({"error": msg}))
}

fn is_valid_date(s: &str) -> bool {
    let parts: Vec<&str> = s.splitn(3, '-').collect();
    if parts.len() != 3 {
        return false;
    }
    parts[0].len() == 4
        && parts[1].len() == 2
        && parts[2].len() == 2
        && parts.iter().all(|p| p.chars().all(|c| c.is_ascii_digit()))
}

fn today_iso() -> String {
    chrono::Utc::now()
        .date_naive()
        .format("%Y-%m-%d")
        .to_string()
}

fn status_str(s: &crate::models::PreOrderStatus) -> &'static str {
    match s {
        crate::models::PreOrderStatus::Pending => "pending",
        crate::models::PreOrderStatus::Fulfilled => "fulfilled",
        crate::models::PreOrderStatus::Cancelled => "cancelled",
    }
}

// ── Handlers ───────────────────────────────────────────────────────────────

async fn list_preorders(State(state): State<AppState>) -> Response {
    let guard = state.lock().await;
    let (farm, _) = &*guard;
    let mut res = Json(json!(farm.pre_orders)).into_response();
    res.headers_mut().insert(
        header::CACHE_CONTROL,
        axum::http::HeaderValue::from_static("no-store"),
    );
    res
}

async fn create_preorder(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(body): Json<CreatePreOrderBody>,
) -> (StatusCode, Json<serde_json::Value>) {
    if body.customer_name.trim().is_empty()
        || body.contact.trim().is_empty()
        || body.product_description.trim().is_empty()
    {
        return (
            StatusCode::UNPROCESSABLE_ENTITY,
            err_json("customer_name, contact, and product_description must not be empty"),
        );
    }
    if body.weight_oz <= 0.0 {
        return (
            StatusCode::UNPROCESSABLE_ENTITY,
            err_json("weight_oz must be greater than 0"),
        );
    }
    if body.deposit_usd < 0.0 {
        return (
            StatusCode::UNPROCESSABLE_ENTITY,
            err_json("deposit_usd must not be negative"),
        );
    }
    if let Some(ref d) = body.forecast_delivery_date {
        if !is_valid_date(d) {
            return (
                StatusCode::UNPROCESSABLE_ENTITY,
                err_json("forecast_delivery_date must be YYYY-MM-DD"),
            );
        }
    }

    let idempotency_key = headers
        .get("idempotency-key")
        .and_then(|v| v.to_str().ok())
        .map(str::to_string);

    let mut guard = state.lock().await;
    let (farm, path) = &mut *guard;

    // Idempotency check: if key already used, return original without duplicate
    if let Some(ref key) = idempotency_key {
        if let Some(existing_id) = farm.idempotency_keys.get(key) {
            if let Some(existing) = farm.pre_orders.iter().find(|p| &p.id == existing_id) {
                return (StatusCode::CREATED, Json(json!(existing.clone())));
            }
        }
    }

    let id = uuid::Uuid::new_v4().to_string();
    let pre_order = crate::models::PreOrder {
        id: id.clone(),
        customer_name: body.customer_name,
        contact: body.contact,
        product_description: body.product_description,
        weight_oz: body.weight_oz,
        deposit_usd: body.deposit_usd,
        status: crate::models::PreOrderStatus::Pending,
        created_date: today_iso(),
        inventory_item_id: body.inventory_item_id,
        forecast_delivery_date: body.forecast_delivery_date,
    };

    // Store key and record atomically inside the same lock acquisition
    if let Some(key) = idempotency_key {
        farm.idempotency_keys.insert(key, id);
    }
    farm.pre_orders.push(pre_order.clone());

    if let Err(e) = crate::store::save(path, farm) {
        return (
            StatusCode::INTERNAL_SERVER_ERROR,
            err_json(&format!("save failed: {e}")),
        );
    }

    (StatusCode::CREATED, Json(json!(pre_order)))
}

async fn patch_preorder_status(
    State(state): State<AppState>,
    Path(id): Path<String>,
    Json(body): Json<PatchStatusBody>,
) -> (StatusCode, Json<serde_json::Value>) {
    let requested = body.status.as_str();
    if requested != "fulfilled" && requested != "cancelled" {
        return (
            StatusCode::UNPROCESSABLE_ENTITY,
            err_json("status must be 'fulfilled' or 'cancelled'"),
        );
    }

    let mut guard = state.lock().await;
    let (farm, path) = &mut *guard;

    let Some(order) = farm.pre_orders.iter_mut().find(|p| p.id == id) else {
        return (StatusCode::NOT_FOUND, err_json("pre-order not found"));
    };

    let current = status_str(&order.status);
    let valid = matches!(
        (&order.status, requested),
        (crate::models::PreOrderStatus::Pending, "fulfilled")
            | (crate::models::PreOrderStatus::Pending, "cancelled")
    );

    if !valid {
        return (
            StatusCode::UNPROCESSABLE_ENTITY,
            err_json(&format!("Cannot transition from {current} to {requested}")),
        );
    }

    order.status = if requested == "fulfilled" {
        crate::models::PreOrderStatus::Fulfilled
    } else {
        crate::models::PreOrderStatus::Cancelled
    };

    let updated = order.clone();

    if let Err(e) = crate::store::save(path, farm) {
        return (
            StatusCode::INTERNAL_SERVER_ERROR,
            err_json(&format!("save failed: {e}")),
        );
    }

    (StatusCode::OK, Json(json!(updated)))
}

// ── Router ─────────────────────────────────────────────────────────────────

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/api/pre-orders", get(list_preorders).post(create_preorder))
        .route("/api/pre-orders/:id/status", patch(patch_preorder_status))
}

// ── Tests ──────────────────────────────────────────────────────────────────

#[cfg(test)]
mod preorders_tests {
    use std::path::PathBuf;
    use std::sync::Arc;

    use axum::body::Body;
    use axum::http::{Method, Request, StatusCode};
    use serde_json::Value;
    use tokio::sync::Mutex;
    use tower::ServiceExt;

    use crate::models::FarmData;
    use crate::{build_app, AppState};

    fn make_state() -> AppState {
        use std::sync::atomic::{AtomicU64, Ordering};
        static COUNTER: AtomicU64 = AtomicU64::new(0);
        let n = COUNTER.fetch_add(1, Ordering::Relaxed);
        let pid = std::process::id();
        let path = PathBuf::from(format!("/tmp/flock_test_preorders_{}_{}.json", pid, n));
        Arc::new(Mutex::new((FarmData::default(), path)))
    }

    async fn body_json(body: Body) -> Value {
        let bytes = axum::body::to_bytes(body, usize::MAX).await.unwrap();
        serde_json::from_slice(&bytes).unwrap_or(Value::Null)
    }

    async fn post_json(app: &axum::Router, uri: &str, body: Value) -> (StatusCode, Value) {
        let req = Request::builder()
            .method(Method::POST)
            .uri(uri)
            .header("content-type", "application/json")
            .body(Body::from(serde_json::to_vec(&body).unwrap()))
            .unwrap();
        let resp = app.clone().oneshot(req).await.unwrap();
        let status = resp.status();
        let json = body_json(resp.into_body()).await;
        (status, json)
    }

    async fn post_json_with_key(
        app: &axum::Router,
        uri: &str,
        body: Value,
        key: &str,
    ) -> (StatusCode, Value) {
        let req = Request::builder()
            .method(Method::POST)
            .uri(uri)
            .header("content-type", "application/json")
            .header("idempotency-key", key)
            .body(Body::from(serde_json::to_vec(&body).unwrap()))
            .unwrap();
        let resp = app.clone().oneshot(req).await.unwrap();
        let status = resp.status();
        let json = body_json(resp.into_body()).await;
        (status, json)
    }

    async fn patch_json(app: &axum::Router, uri: &str, body: Value) -> (StatusCode, Value) {
        let req = Request::builder()
            .method(Method::PATCH)
            .uri(uri)
            .header("content-type", "application/json")
            .body(Body::from(serde_json::to_vec(&body).unwrap()))
            .unwrap();
        let resp = app.clone().oneshot(req).await.unwrap();
        let status = resp.status();
        let json = body_json(resp.into_body()).await;
        (status, json)
    }

    async fn get_json(app: &axum::Router, uri: &str) -> (StatusCode, Value) {
        let req = Request::builder()
            .method(Method::GET)
            .uri(uri)
            .body(Body::empty())
            .unwrap();
        let resp = app.clone().oneshot(req).await.unwrap();
        let status = resp.status();
        let json = body_json(resp.into_body()).await;
        (status, json)
    }

    fn valid_body() -> Value {
        serde_json::json!({
            "customer_name": "Alice",
            "contact": "alice@example.com",
            "product_description": "Merino yarn, 8oz",
            "weight_oz": 8.0,
            "deposit_usd": 20.0
        })
    }

    #[tokio::test]
    async fn test_post_preorder_returns_201() {
        let app = build_app(make_state());
        let (status, json) = post_json(&app, "/api/pre-orders", valid_body()).await;
        assert_eq!(status, StatusCode::CREATED);
        assert!(json["id"].is_string());
        assert_eq!(json["customer_name"], "Alice");
        assert_eq!(json["status"], "pending");
    }

    #[tokio::test]
    async fn test_get_preorders_includes_created() {
        let state = make_state();
        let app = build_app(state);
        let (_, created) = post_json(&app, "/api/pre-orders", valid_body()).await;
        let (status, json) = get_json(&app, "/api/pre-orders").await;
        assert_eq!(status, StatusCode::OK);
        let arr = json.as_array().unwrap();
        assert_eq!(arr.len(), 1);
        assert_eq!(arr[0]["id"], created["id"]);
    }

    #[tokio::test]
    async fn test_get_preorders_no_store_header() {
        let app = build_app(make_state());
        let req = Request::builder()
            .method(Method::GET)
            .uri("/api/pre-orders")
            .body(Body::empty())
            .unwrap();
        let resp = app.clone().oneshot(req).await.unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let cc = resp.headers().get("cache-control").unwrap();
        assert_eq!(cc.to_str().unwrap(), "no-store");
    }

    #[tokio::test]
    async fn test_patch_status_fulfilled() {
        let state = make_state();
        let app = build_app(state);
        let (_, created) = post_json(&app, "/api/pre-orders", valid_body()).await;
        let id = created["id"].as_str().unwrap();
        let (status, json) = patch_json(
            &app,
            &format!("/api/pre-orders/{id}/status"),
            serde_json::json!({"status": "fulfilled"}),
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(json["status"], "fulfilled");
    }

    #[tokio::test]
    async fn test_patch_status_already_fulfilled_returns_422() {
        let state = make_state();
        let app = build_app(state);
        let (_, created) = post_json(&app, "/api/pre-orders", valid_body()).await;
        let id = created["id"].as_str().unwrap();
        patch_json(
            &app,
            &format!("/api/pre-orders/{id}/status"),
            serde_json::json!({"status": "fulfilled"}),
        )
        .await;
        let (status, json) = patch_json(
            &app,
            &format!("/api/pre-orders/{id}/status"),
            serde_json::json!({"status": "cancelled"}),
        )
        .await;
        assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY);
        assert!(json["error"]
            .as_str()
            .unwrap()
            .contains("Cannot transition"));
    }

    #[tokio::test]
    async fn test_post_missing_required_field_returns_422() {
        let app = build_app(make_state());
        let (status, _) = post_json(
            &app,
            "/api/pre-orders",
            serde_json::json!({"contact": "x", "product_description": "y", "weight_oz": 1.0, "deposit_usd": 5.0}),
        )
        .await;
        assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY);
    }

    #[tokio::test]
    async fn test_idempotency_key_dedup() {
        let state = make_state();
        let app = build_app(state);
        let key = "test-idem-key-123";
        let (s1, j1) = post_json_with_key(&app, "/api/pre-orders", valid_body(), key).await;
        let (s2, j2) = post_json_with_key(&app, "/api/pre-orders", valid_body(), key).await;
        assert_eq!(s1, StatusCode::CREATED);
        assert_eq!(s2, StatusCode::CREATED);
        assert_eq!(j1["id"], j2["id"]);
        // Only one pre-order in list
        let (_, list) = get_json(&app, "/api/pre-orders").await;
        assert_eq!(list.as_array().unwrap().len(), 1);
    }

    #[tokio::test]
    async fn test_patch_unknown_id_returns_404() {
        let app = build_app(make_state());
        let (status, _) = patch_json(
            &app,
            "/api/pre-orders/no-such-id/status",
            serde_json::json!({"status": "fulfilled"}),
        )
        .await;
        assert_eq!(status, StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn test_patch_invalid_status_value_returns_422() {
        let state = make_state();
        let app = build_app(state);
        let (_, created) = post_json(&app, "/api/pre-orders", valid_body()).await;
        let id = created["id"].as_str().unwrap();
        let (status, _) = patch_json(
            &app,
            &format!("/api/pre-orders/{id}/status"),
            serde_json::json!({"status": "bogus"}),
        )
        .await;
        assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY);
    }
}

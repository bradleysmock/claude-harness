mod models;
mod routes;
mod store;

use std::net::SocketAddr;
use std::path::PathBuf;
use std::sync::Arc;

use axum::{routing::get, Json, Router};
use models::FarmData;
use routes::{animals_router, mill_inventory_router, preorders_router, sync_router};
use serde_json::json;
use tokio::sync::Mutex;
use tower_http::cors::{AllowHeaders, AllowMethods, CorsLayer};

pub type AppState = Arc<Mutex<(FarmData, PathBuf)>>;

pub async fn health() -> Json<serde_json::Value> {
    Json(json!({"status": "ok"}))
}

pub fn build_app(state: AppState) -> Router {
    let cors = CorsLayer::new()
        .allow_origin(
            "http://localhost:5173"
                .parse::<axum::http::HeaderValue>()
                .unwrap(),
        )
        .allow_methods(AllowMethods::any())
        .allow_headers(AllowHeaders::any());

    Router::new()
        .route("/api/health", get(health))
        .merge(animals_router())
        .merge(mill_inventory_router())
        .merge(preorders_router())
        .merge(sync_router())
        .layer(cors)
        .with_state(state)
}

#[tokio::main]
async fn main() {
    let data_file = std::env::var("FLOCK_DATA_FILE")
        .map(PathBuf::from)
        .unwrap_or_else(|_| {
            let home = std::env::var("HOME")
                .map(PathBuf::from)
                .unwrap_or_else(|_| PathBuf::from("/tmp"));
            home.join(".flock").join("farm.json")
        });

    let farm_data = store::load(&data_file).expect("Failed to load farm data");
    let state: AppState = Arc::new(Mutex::new((farm_data, data_file)));

    let app = build_app(state);
    let addr = SocketAddr::from(([0, 0, 0, 0], 3001));
    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    axum::serve(listener, app).await.unwrap();
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::body::Body;
    use axum::http::{Method, Request, StatusCode};
    use tower::ServiceExt;

    #[test]
    fn test_farm_data_default_has_empty_fields() {
        let data = FarmData::default();
        assert!(data.animals.is_empty());
        assert!(data.clips.is_empty());
        assert!(data.mill_orders.is_empty());
        assert!(data.inventory.is_empty());
    }

    #[test]
    fn test_load_nonexistent_path_returns_default() {
        let path = std::path::Path::new("/tmp/nonexistent_flock_test_12345_xyz.json");
        let result = store::load(path);
        assert!(result.is_ok());
        let data = result.unwrap();
        assert!(data.animals.is_empty());
    }

    #[test]
    fn test_save_and_load_roundtrip() {
        let dir = std::env::temp_dir();
        let path = dir.join("flock_test_roundtrip_abc.json");

        let mut data = FarmData::default();
        data.animals.push(models::Animal {
            id: "test-id".to_string(),
            name: "Woolly".to_string(),
            species: "sheep".to_string(),
            breed: "Merino".to_string(),
            dob: None,
            color: "white".to_string(),
            notes: "".to_string(),
            photo_paths: vec![],
        });

        store::save(&path, &data).unwrap();
        assert!(path.exists());

        let loaded = store::load(&path).unwrap();
        assert_eq!(loaded.animals.len(), 1);
        assert_eq!(loaded.animals[0].name, "Woolly");

        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn test_save_atomic_rename() {
        let dir = std::env::temp_dir();
        let path = dir.join("flock_test_atomic_abc.json");
        let tmp_path = dir.join("flock_test_atomic_abc.tmp");

        let data = FarmData::default();
        store::save(&path, &data).unwrap();

        assert!(!tmp_path.exists());
        assert!(path.exists());

        let _ = std::fs::remove_file(&path);
    }

    #[tokio::test]
    async fn test_health_endpoint_returns_200() {
        let state: AppState = Arc::new(Mutex::new((
            FarmData::default(),
            PathBuf::from("/tmp/test.json"),
        )));
        let app = build_app(state);

        let response = app
            .oneshot(
                Request::builder()
                    .uri("/api/health")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);

        let body = axum::body::to_bytes(response.into_body(), usize::MAX)
            .await
            .unwrap();
        let json: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(json["status"], "ok");
    }

    #[tokio::test]
    async fn test_animals_route_returns_200() {
        let state: AppState = Arc::new(Mutex::new((
            FarmData::default(),
            PathBuf::from("/tmp/test.json"),
        )));
        let app = build_app(state);

        let response = app
            .oneshot(
                Request::builder()
                    .uri("/api/animals")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_mill_orders_route_returns_200() {
        let state: AppState = Arc::new(Mutex::new((
            FarmData::default(),
            PathBuf::from("/tmp/test.json"),
        )));
        let app = build_app(state);

        let response = app
            .oneshot(
                Request::builder()
                    .uri("/api/mill-orders")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_cors_preflight() {
        let state: AppState = Arc::new(Mutex::new((
            FarmData::default(),
            PathBuf::from("/tmp/test.json"),
        )));
        let app = build_app(state);

        let response = app
            .oneshot(
                Request::builder()
                    .method(Method::OPTIONS)
                    .uri("/api/health")
                    .header("Origin", "http://localhost:5173")
                    .header("Access-Control-Request-Method", "GET")
                    .header("Access-Control-Request-Headers", "content-type")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        let headers = response.headers();
        let acao = headers
            .get("access-control-allow-origin")
            .map(|v| v.to_str().unwrap_or(""))
            .unwrap_or("");
        assert!(
            acao.contains("localhost:5173"),
            "Expected CORS origin header containing localhost:5173, got: {}",
            acao
        );
    }
}

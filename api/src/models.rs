use serde::{Deserialize, Serialize};
use std::collections::HashMap;

// ── Pre-order domain ──────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Default)]
#[serde(rename_all = "snake_case")]
pub enum PreOrderStatus {
    #[default]
    Pending,
    Fulfilled,
    Cancelled,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PreOrder {
    pub id: String,
    pub customer_name: String,
    pub contact: String,
    pub product_description: String,
    pub weight_oz: f64,
    pub deposit_usd: f64,
    #[serde(default)]
    pub status: PreOrderStatus,
    pub created_date: String,
    pub inventory_item_id: Option<String>,
    pub forecast_delivery_date: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Animal {
    pub id: String,
    pub name: String,
    pub species: String,
    pub breed: String,
    pub dob: Option<String>,
    pub color: String,
    pub notes: String,
    pub photo_paths: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ClipRecord {
    pub id: String,
    pub animal_id: String,
    pub clip_date: String,
    pub raw_weight_oz: f64,
    pub skirted_weight_oz: Option<f64>,
    pub staple_length_in: Option<f64>,
    pub micron: Option<f64>,
    pub condition: String,
    pub destination: String,
    pub notes: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MillOrder {
    pub id: String,
    pub mill_name: String,
    pub process_type: String,
    pub send_date: String,
    pub expected_return_date: Option<String>,
    pub return_date: Option<String>,
    pub return_weight_oz: Option<f64>,
    pub cost_usd: Option<f64>,
    pub product_description: String,
    pub clip_ids: Vec<String>,
    pub notes: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InventoryItem {
    pub id: String,
    pub name: String,
    pub stage: String,
    pub weight_oz: f64,
    pub location: String,
    pub clip_id: Option<String>,
    pub mill_order_id: Option<String>,
    pub sku: Option<String>,
    pub notes: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SyncCredential {
    pub platform: String,
    pub shop_domain: Option<String>,
    pub shop_id: Option<String>,
    pub connected_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExternalListingRecord {
    pub id: String,
    pub inventory_item_id: String,
    pub platform: String,
    pub external_id: String,
    pub external_variant_id: Option<String>,
    pub external_url: Option<String>,
    pub synced_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct FarmData {
    #[serde(default)]
    pub animals: Vec<Animal>,
    #[serde(default)]
    pub clips: HashMap<String, Vec<ClipRecord>>,
    #[serde(default)]
    pub mill_orders: Vec<MillOrder>,
    #[serde(default)]
    pub inventory: Vec<InventoryItem>,
    #[serde(default)]
    pub sync_credentials: Vec<SyncCredential>,
    #[serde(default)]
    pub external_listings: Vec<ExternalListingRecord>,
    #[serde(default)]
    pub pre_orders: Vec<PreOrder>,
    #[serde(default)]
    pub idempotency_keys: HashMap<String, String>,
}

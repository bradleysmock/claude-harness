pub mod animals;
pub mod mill_inventory;
pub mod preorders;
pub mod sync;

pub use animals::router as animals_router;
pub use mill_inventory::router as mill_inventory_router;
pub use preorders::router as preorders_router;
pub use sync::sync_router;

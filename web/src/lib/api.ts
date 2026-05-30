const BASE = '/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { error?: string }).error ?? `HTTP ${res.status}`);
  }
  if (res.status === 204) return undefined as unknown as T;
  return res.json();
}

// ── Types ─────────────────────────────────────────────────────────────────────

export interface Animal {
  id: string;
  name: string;
  species: string;
  breed: string;
  dob: string | null;
  color: string;
  notes: string;
  photo_paths: string[];
}

export interface AnimalSummary extends Animal {
  clip_count: number;
  last_clip_date: string | null;
}

export interface ClipHistory {
  clip_count: number;
  total_raw_oz: number;
  avg_skirted_yield: number | null;
  last_clip_date: string | null;
}

export interface AnimalDetail {
  animal: Animal;
  clip_history: ClipHistory;
}

export interface ClipRecord {
  id: string;
  animal_id: string;
  clip_date: string;
  raw_weight_oz: number;
  skirted_weight_oz: number | null;
  staple_length_in: number | null;
  micron: number | null;
  condition: string;
  destination: string;
  notes: string;
}

export interface MillOrder {
  id: string;
  mill_name: string;
  process_type: string;
  send_date: string;
  expected_return_date: string | null;
  return_date: string | null;
  return_weight_oz: number | null;
  cost_usd: number | null;
  product_description: string;
  clip_ids: string[];
  notes: string;
}

export interface MillOrderSummary extends MillOrder {
  cost_per_oz: number | null;
}

export interface InventoryItem {
  id: string;
  name: string;
  stage: string;
  weight_oz: number;
  location: string;
  clip_id: string | null;
  mill_order_id: string | null;
  sku: string | null;
  notes: string;
}

export interface StageSummary {
  stage: string;
  total_weight_oz: number;
  item_count: number;
}

// ── Request bodies ─────────────────────────────────────────────────────────────

export interface NewAnimal {
  name: string;
  species: string;
  breed: string;
  color: string;
  notes: string;
}

export interface NewClip {
  clip_date: string;
  raw_weight_oz: number;
  skirted_weight_oz?: number | null;
  staple_length_in?: number | null;
  micron?: number | null;
  condition: string;
  destination: string;
}

export interface NewMillOrder {
  mill_name: string;
  process_type: string;
  send_date: string;
  product_description: string;
  clip_ids: string[];
}

export interface MillReturn {
  return_date: string;
  return_weight_oz: number;
  cost_usd: number;
}

// ── API functions ──────────────────────────────────────────────────────────────

export function getAnimals(species?: string): Promise<AnimalSummary[]> {
  const q = species ? `?species=${encodeURIComponent(species)}` : '';
  return request<AnimalSummary[]>(`/animals${q}`);
}

export function addAnimal(body: NewAnimal): Promise<Animal> {
  return request<Animal>('/animals', { method: 'POST', body: JSON.stringify(body) });
}

export function getAnimal(id: string): Promise<AnimalDetail> {
  return request<AnimalDetail>(`/animals/${id}`);
}

export function deleteAnimal(id: string): Promise<void> {
  return request<void>(`/animals/${id}`, { method: 'DELETE' });
}

export function getClips(animalId: string): Promise<ClipRecord[]> {
  return request<ClipRecord[]>(`/animals/${animalId}/clips`);
}

export function addClip(animalId: string, body: NewClip): Promise<ClipRecord> {
  return request<ClipRecord>(`/animals/${animalId}/clips`, { method: 'POST', body: JSON.stringify(body) });
}

export function getMillOrders(openOnly?: boolean): Promise<MillOrderSummary[]> {
  const q = openOnly ? '?open_only=true' : '';
  return request<MillOrderSummary[]>(`/mill-orders${q}`);
}

export function addMillOrder(body: NewMillOrder): Promise<MillOrder> {
  return request<MillOrder>('/mill-orders', { method: 'POST', body: JSON.stringify(body) });
}

export function recordReturn(orderId: string, body: MillReturn): Promise<MillOrder> {
  return request<MillOrder>(`/mill-orders/${orderId}/return`, { method: 'POST', body: JSON.stringify(body) });
}

export function getInventory(stage?: string): Promise<InventoryItem[]> {
  const q = stage ? `?stage=${encodeURIComponent(stage)}` : '';
  return request<InventoryItem[]>(`/inventory${q}`);
}

export function getInventorySummary(): Promise<StageSummary[]> {
  return request<StageSummary[]>('/inventory/summary');
}

export function markItemSold(itemId: string, idempotencyKey: string): Promise<InventoryItem> {
  return request<InventoryItem>(`/inventory/${itemId}/mark-sold`, {
    method: 'POST',
    headers: { 'Idempotency-Key': idempotencyKey },
  });
}

// ── Pre-order types ────────────────────────────────────────────────────────────

export interface PreOrder {
  id: string;
  customer_name: string;
  contact: string;
  product_description: string;
  weight_oz: number;
  deposit_usd: number;
  status: 'pending' | 'fulfilled' | 'cancelled';
  created_date: string;
  inventory_item_id: string | null;
  forecast_delivery_date: string | null;
}

export interface NewPreOrder {
  customer_name: string;
  contact: string;
  product_description: string;
  weight_oz: number;
  deposit_usd: number;
  inventory_item_id?: string | null;
  forecast_delivery_date?: string | null;
}

export function isPreOrder(x: unknown): x is PreOrder {
  if (typeof x !== 'object' || x === null) return false;
  const o = x as Record<string, unknown>;
  return (
    typeof o['id'] === 'string' &&
    typeof o['customer_name'] === 'string' &&
    typeof o['contact'] === 'string' &&
    typeof o['product_description'] === 'string' &&
    typeof o['weight_oz'] === 'number' &&
    typeof o['deposit_usd'] === 'number' &&
    typeof o['created_date'] === 'string' &&
    (o['status'] === 'pending' || o['status'] === 'fulfilled' || o['status'] === 'cancelled')
  );
}

export function getPreOrders(): Promise<PreOrder[]> {
  return request<PreOrder[]>('/pre-orders');
}

export function createPreOrder(body: NewPreOrder, idempotencyKey: string): Promise<PreOrder> {
  return request<PreOrder>('/pre-orders', {
    method: 'POST',
    body: JSON.stringify(body),
    headers: { 'Idempotency-Key': idempotencyKey },
  });
}

export function updatePreOrderStatus(
  id: string,
  status: 'fulfilled' | 'cancelled',
): Promise<PreOrder> {
  return request<PreOrder>(`/pre-orders/${id}/status`, {
    method: 'PATCH',
    body: JSON.stringify({ status }),
  });
}

// ── Sync types ─────────────────────────────────────────────────────────────────

export interface SyncCredential {
  platform: string;
  shop_domain: string | null;
  shop_id: string | null;
  connected_at: string;
}

export interface ExternalListingRecord {
  id: string;
  inventory_item_id: string;
  platform: string;
  external_id: string;
  external_variant_id: string | null;
  external_url: string | null;
  synced_at: string;
}

export interface ConnectPlatformBody {
  platform: 'etsy' | 'shopify';
  shop_domain?: string;
  shop_id?: string;
}

export interface CreateListingBody {
  inventory_item_id: string;
  platform: string;
  external_id: string;
  external_variant_id?: string;
  external_url?: string;
}

// ── Sync API functions ─────────────────────────────────────────────────────────

export function getSyncPlatforms(): Promise<SyncCredential[]> {
  return request<SyncCredential[]>('/sync/platforms');
}

export function connectPlatform(body: ConnectPlatformBody): Promise<SyncCredential> {
  return request<SyncCredential>('/sync/platforms', { method: 'POST', body: JSON.stringify(body) });
}

export function disconnectPlatform(platform: string): Promise<void> {
  return request<void>(`/sync/platforms/${encodeURIComponent(platform)}`, { method: 'DELETE' });
}

export function getSyncListings(inventoryItemId?: string): Promise<ExternalListingRecord[]> {
  const q = inventoryItemId ? `?inventory_item_id=${encodeURIComponent(inventoryItemId)}` : '';
  return request<ExternalListingRecord[]>(`/sync/listings${q}`);
}

export function createSyncListing(body: CreateListingBody): Promise<ExternalListingRecord> {
  return request<ExternalListingRecord>('/sync/listings', { method: 'POST', body: JSON.stringify(body) });
}

export function removeSyncListing(id: string): Promise<void> {
  return request<void>(`/sync/listings/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

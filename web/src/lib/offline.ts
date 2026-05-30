import { createPreOrder, getInventory, getPreOrders, markItemSold } from './api';
import type { InventoryItem, NewPreOrder } from './api';

// ── Storage keys ───────────────────────────────────────────────────────────────

const QUEUE_KEY = '__flock_queue';
const DEVICE_INVENTORY_KEY = '__flock_device_inventory';
const DEVICE_FORECAST_KEY = '__flock_device_forecast';

// ── Types ──────────────────────────────────────────────────────────────────────

export type OfflineOp =
  | { type: 'mark-sold'; itemId: string; timestamp: number; idempotencyKey: string }
  | { type: 'create-pre-order'; body: NewPreOrder; timestamp: number; idempotencyKey: string };

// ── Idempotency key ────────────────────────────────────────────────────────────

export function generateIdempotencyKey(): string {
  return crypto.randomUUID();
}

// ── Queue helpers ──────────────────────────────────────────────────────────────

function readQueue(): OfflineOp[] {
  try {
    const raw = localStorage.getItem(QUEUE_KEY);
    if (!raw) return [];
    return JSON.parse(raw) as OfflineOp[];
  } catch {
    return [];
  }
}

function writeQueue(ops: OfflineOp[]): void {
  localStorage.setItem(QUEUE_KEY, JSON.stringify(ops));
}

function insertSorted(ops: OfflineOp[], op: OfflineOp): OfflineOp[] {
  const next = [...ops, op];
  next.sort((a, b) => a.timestamp - b.timestamp);
  return next;
}

export function getQueueLength(): number {
  return readQueue().length;
}

export function queueSale(itemId: string): void {
  const op: OfflineOp = {
    type: 'mark-sold',
    itemId,
    timestamp: Date.now(),
    idempotencyKey: generateIdempotencyKey(),
  };
  writeQueue(insertSorted(readQueue(), op));
}

export function queuePreOrder(body: NewPreOrder): void {
  const op: OfflineOp = {
    type: 'create-pre-order',
    body,
    timestamp: Date.now(),
    idempotencyKey: generateIdempotencyKey(),
  };
  writeQueue(insertSorted(readQueue(), op));
}

// ── Device sync ────────────────────────────────────────────────────────────────

export async function syncToDevice(): Promise<void> {
  const [inventory, preOrders] = await Promise.all([getInventory(), getPreOrders()]);
  localStorage.setItem(DEVICE_INVENTORY_KEY, JSON.stringify(inventory));
  localStorage.setItem(DEVICE_FORECAST_KEY, JSON.stringify(preOrders));

  // Forecast endpoint may not exist yet — swallow any error
  try {
    const res = await fetch('/api/forecast');
    if (res.ok) {
      const forecast: unknown = await res.json();
      localStorage.setItem(DEVICE_FORECAST_KEY, JSON.stringify(forecast));
    }
  } catch {
    // intentional: forecast is optional
  }
}

export function getDeviceInventory(): InventoryItem[] {
  try {
    const raw = localStorage.getItem(DEVICE_INVENTORY_KEY);
    if (!raw) return [];
    return JSON.parse(raw) as InventoryItem[];
  } catch {
    return [];
  }
}

// ── Server sync ────────────────────────────────────────────────────────────────

export async function syncToServer(): Promise<void> {
  const queue = readQueue();
  const remaining = [...queue];

  for (let i = 0; i < queue.length; i++) {
    const op = queue[i];
    try {
      if (op.type === 'mark-sold') {
        await markItemSold(op.itemId, op.idempotencyKey);
      } else {
        await createPreOrder(op.body, op.idempotencyKey);
      }
      // Per-item advance: remove this op and persist immediately
      remaining.shift();
      writeQueue(remaining);
    } catch (err) {
      // Halt-on-first-error: stop and re-throw so the caller knows where we stopped
      throw err;
    }
  }
}

// ── Queue export ───────────────────────────────────────────────────────────────

export function exportQueue(): void {
  const queue = readQueue();
  const json = JSON.stringify(queue, null, 2);
  const blob = new Blob([json], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `flock-queue-${Date.now()}.json`;
  a.click();
  URL.revokeObjectURL(url);
  // Queue is NOT cleared
}

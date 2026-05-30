<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import {
    createPreOrder,
    getInventory,
    markItemSold,
    type InventoryItem,
    type NewPreOrder,
  } from '../lib/api';
  import {
    exportQueue,
    generateIdempotencyKey,
    getDeviceInventory,
    getQueueLength,
    queuePreOrder,
    queueSale,
    syncToDevice,
    syncToServer,
  } from '../lib/offline';

  // ── State ──────────────────────────────────────────────────────────────────

  let online = navigator.onLine;
  let items: InventoryItem[] = [];
  let queueCount = getQueueLength();
  let offlineNoCache = false;
  let deviceSyncMsg = '';
  let serverSyncMsg = '';
  let serverSyncError = '';
  let isSyncing = false;

  // Mark-sold state per item
  let markSoldOpen: Record<string, boolean> = {};
  let buyerNote: Record<string, string> = {};

  // Pre-order form
  let showPreOrderForm = false;
  let po: NewPreOrder = {
    customer_name: '',
    contact: '',
    product_description: '',
    weight_oz: 0,
    deposit_usd: 0,
  };
  let poMsg = '';

  // Forecast
  let forecastRaw: unknown = null;

  // ── Lifecycle ──────────────────────────────────────────────────────────────

  function handleOnline() {
    online = true;
    loadInventory();
  }

  function handleOffline() {
    online = false;
  }

  function handleBeforeUnload(e: BeforeUnloadEvent) {
    if (getQueueLength() > 0) {
      e.preventDefault();
      e.returnValue = '';
    }
  }

  onMount(() => {
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);
    window.addEventListener('beforeunload', handleBeforeUnload);
    loadInventory();
    loadForecast();
  });

  onDestroy(() => {
    window.removeEventListener('online', handleOnline);
    window.removeEventListener('offline', handleOffline);
    window.removeEventListener('beforeunload', handleBeforeUnload);
  });

  // ── Data loading ───────────────────────────────────────────────────────────

  async function loadInventory() {
    if (online) {
      try {
        const fetched = await getInventory();
        items = fetched.filter((i) => i.stage === 'yarn' || i.stage === 'roving');
        offlineNoCache = false;
        return;
      } catch (err) {
        const msg = (err as Error).message;
        if (msg === 'offline-no-cache') {
          offlineNoCache = true;
        }
      }
    }
    const cached = getDeviceInventory().filter((i) => i.stage === 'yarn' || i.stage === 'roving');
    items = cached;
  }

  function loadForecast() {
    try {
      const raw = localStorage.getItem('__flock_device_forecast');
      forecastRaw = raw ? JSON.parse(raw) : null;
    } catch {
      forecastRaw = null;
    }
  }

  function refreshQueue() {
    queueCount = getQueueLength();
  }

  // ── Mark sold ──────────────────────────────────────────────────────────────

  async function confirmMarkSold(item: InventoryItem) {
    if (online) {
      try {
        await markItemSold(item.id, generateIdempotencyKey());
        items = items.filter((i) => i.id !== item.id);
      } catch (err) {
        const msg = (err as Error).message;
        if (msg === 'offline-no-cache') offlineNoCache = true;
      }
    } else {
      queueSale(item.id);
      refreshQueue();
      showToast('sale-toast', 'Queued for sync');
    }
    markSoldOpen = { ...markSoldOpen, [item.id]: false };
  }

  // ── Pre-order submit ───────────────────────────────────────────────────────

  async function submitPreOrder() {
    if (!po.customer_name || !po.contact || !po.product_description || po.weight_oz <= 0) {
      poMsg = 'Please fill in all required fields.';
      return;
    }
    if (online) {
      try {
        await createPreOrder(po, generateIdempotencyKey());
        poMsg = 'Pre-order created!';
        resetPoForm();
      } catch (err) {
        const msg = (err as Error).message;
        if (msg === 'offline-no-cache') {
          offlineNoCache = true;
          poMsg = '';
        } else {
          poMsg = msg;
        }
      }
    } else {
      queuePreOrder({ ...po });
      refreshQueue();
      poMsg = 'Queued for sync';
      resetPoForm();
    }
  }

  function resetPoForm() {
    po = { customer_name: '', contact: '', product_description: '', weight_oz: 0, deposit_usd: 0 };
    setTimeout(() => {
      poMsg = '';
      showPreOrderForm = false;
    }, 1500);
  }

  // ── Sync actions ───────────────────────────────────────────────────────────

  async function doSyncToDevice() {
    isSyncing = true;
    deviceSyncMsg = '';
    try {
      await syncToDevice();
      await loadInventory();
      loadForecast();
      deviceSyncMsg = 'Device synced';
      offlineNoCache = false;
    } catch {
      deviceSyncMsg = 'Sync failed';
    } finally {
      isSyncing = false;
    }
  }

  async function doSyncToServer() {
    isSyncing = true;
    serverSyncMsg = '';
    serverSyncError = '';
    try {
      await syncToServer();
      refreshQueue();
      serverSyncMsg = 'Sync complete';
    } catch (err) {
      serverSyncError = (err as Error).message;
    } finally {
      isSyncing = false;
    }
  }

  // ── Toast (lightweight) ────────────────────────────────────────────────────

  let toasts: Record<string, string> = {};
  function showToast(id: string, msg: string) {
    toasts = { ...toasts, [id]: msg };
    setTimeout(() => {
      const { [id]: _, ...rest } = toasts;
      toasts = rest;
    }, 2500);
  }

  // ── Navigation guard (in-app) ─────────────────────────────────────────────
  // Exposed so App.svelte can call it before switching away.
  export function canLeave(): boolean {
    if (getQueueLength() > 0) {
      return window.confirm('You have unsynced operations. Leave anyway?');
    }
    return true;
  }
</script>

<div class="booth-page">
  <!-- ── Status bar ──────────────────────────────────────────────────────── -->
  <div class="status-bar">
    <h2 class="page-title">Booth Mode</h2>
    <div class="status-chips">
      <span class="chip chip-{online ? 'online' : 'offline'}">
        {online ? 'Online' : 'Offline'}
      </span>
      {#if queueCount > 0}
        <span class="chip chip-queue">{queueCount} pending</span>
      {/if}
    </div>
  </div>

  <!-- ── Offline-no-cache warning ───────────────────────────────────────── -->
  {#if offlineNoCache}
    <div class="banner banner-warn">
      Device not synced — go online and tap <strong>Sync to device</strong>
    </div>
  {/if}

  <!-- ── Sync controls ──────────────────────────────────────────────────── -->
  <div class="sync-row">
    <button class="btn btn-secondary" disabled={isSyncing} on:click={doSyncToDevice}>
      {isSyncing ? '…' : 'Sync to device'}
    </button>
    <button class="btn btn-secondary" disabled={isSyncing || queueCount === 0} on:click={doSyncToServer}>
      {isSyncing ? '…' : 'Sync to server'}
    </button>
    {#if queueCount > 0}
      <button class="btn btn-ghost" on:click={exportQueue}>Export queue</button>
    {/if}
    {#if deviceSyncMsg}<span class="sync-msg">{deviceSyncMsg}</span>{/if}
    {#if serverSyncMsg}<span class="sync-msg success">{serverSyncMsg}</span>{/if}
    {#if serverSyncError}<span class="sync-msg error">{serverSyncError}</span>{/if}
  </div>

  <!-- ── Inventory list ─────────────────────────────────────────────────── -->
  <section class="section">
    <h3 class="section-title">Sellable Inventory</h3>
    {#if items.length === 0}
      <div class="empty-state">No yarn or roving items. Sync device while online to load inventory.</div>
    {:else}
      <div class="item-list">
        {#each items as item (item.id)}
          <div class="item-card card">
            <div class="item-info">
              <span class="item-name">{item.name}</span>
              <span class="item-meta">{item.stage} · {item.weight_oz.toFixed(1)} oz</span>
            </div>
            {#if markSoldOpen[item.id]}
              <div class="mark-sold-inline">
                <input
                  class="input-sm"
                  placeholder="Buyer note (optional)"
                  bind:value={buyerNote[item.id]}
                />
                <button class="btn btn-primary btn-sm" on:click={() => confirmMarkSold(item)}>
                  Confirm sold
                </button>
                <button
                  class="btn btn-ghost btn-sm"
                  on:click={() => (markSoldOpen = { ...markSoldOpen, [item.id]: false })}
                >
                  Cancel
                </button>
              </div>
            {:else}
              <button
                class="btn btn-sm btn-outline"
                on:click={() => (markSoldOpen = { ...markSoldOpen, [item.id]: true })}
              >
                Mark Sold
              </button>
            {/if}
          </div>
        {/each}
      </div>
    {/if}
  </section>

  <!-- ── Pre-order form ─────────────────────────────────────────────────── -->
  <section class="section">
    <div class="section-header">
      <h3 class="section-title">Pre-Orders</h3>
      <button class="btn btn-secondary btn-sm" on:click={() => (showPreOrderForm = !showPreOrderForm)}>
        {showPreOrderForm ? 'Cancel' : 'New Pre-Order'}
      </button>
    </div>

    {#if showPreOrderForm}
      <div class="pre-order-form card">
        <div class="form-grid">
          <label class="field">
            <span>Customer name *</span>
            <input class="input" bind:value={po.customer_name} placeholder="Name" />
          </label>
          <label class="field">
            <span>Contact *</span>
            <input class="input" bind:value={po.contact} placeholder="Email or phone" />
          </label>
          <label class="field">
            <span>Product description *</span>
            <input class="input" bind:value={po.product_description} placeholder="e.g. Merino yarn 8oz" />
          </label>
          <label class="field">
            <span>Weight oz *</span>
            <input class="input" type="number" min="0.1" step="0.5" bind:value={po.weight_oz} />
          </label>
          <label class="field">
            <span>Deposit USD</span>
            <input class="input" type="number" min="0" step="1" bind:value={po.deposit_usd} />
          </label>
          <label class="field">
            <span>Delivery date (optional)</span>
            <input class="input" type="date" bind:value={po.forecast_delivery_date} />
          </label>
        </div>
        {#if poMsg}
          <p class="form-msg">{poMsg}</p>
        {/if}
        <button class="btn btn-primary" on:click={submitPreOrder}>Submit</button>
      </div>
    {/if}
  </section>

  <!-- ── Forecast panel ─────────────────────────────────────────────────── -->
  <section class="section">
    <h3 class="section-title">Forecast</h3>
    {#if forecastRaw === null || (Array.isArray(forecastRaw) && forecastRaw.length === 0)}
      <div class="empty-state">No forecast data — sync device while online</div>
    {:else}
      <pre class="forecast-raw">{JSON.stringify(forecastRaw, null, 2)}</pre>
    {/if}
  </section>

  <!-- ── Toast overlay ──────────────────────────────────────────────────── -->
  {#each Object.entries(toasts) as [id, msg] (id)}
    <div class="toast">{msg}</div>
  {/each}
</div>

<style>
  .booth-page { padding: 0; }

  .status-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 16px;
    flex-wrap: wrap;
    gap: 8px;
  }

  .page-title { margin: 0; font-family: var(--font-heading); font-size: 20px; }

  .status-chips { display: flex; gap: 8px; align-items: center; }

  .chip {
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 600;
  }
  .chip-online  { background: #d4edda; color: #155724; }
  .chip-offline { background: #fff3cd; color: #856404; }
  .chip-queue   { background: #cce5ff; color: #004085; }

  .banner {
    padding: 10px 14px;
    border-radius: var(--radius);
    margin-bottom: 14px;
    font-size: 13px;
  }
  .banner-warn {
    background: rgba(255, 193, 7, 0.15);
    border: 1px solid rgba(255, 193, 7, 0.4);
    color: #856404;
  }

  .sync-row {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    margin-bottom: 20px;
  }

  .sync-msg { font-size: 13px; color: var(--color-text-muted); }
  .sync-msg.success { color: #155724; }
  .sync-msg.error { color: var(--color-accent); }

  .section { margin-bottom: 28px; }
  .section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
  .section-title { margin: 0 0 10px; font-family: var(--font-heading); font-size: 15px; font-weight: 600; }

  .item-list { display: flex; flex-direction: column; gap: 8px; }

  .item-card {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 14px;
    gap: 12px;
    flex-wrap: wrap;
  }

  .item-info { display: flex; flex-direction: column; gap: 2px; }
  .item-name { font-weight: 600; font-size: 14px; }
  .item-meta { font-size: 12px; color: var(--color-text-muted); }

  .mark-sold-inline { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }

  .input { width: 100%; padding: 7px 10px; border: 1px solid var(--color-border); border-radius: var(--radius); font-size: 14px; font-family: var(--font-body); background: var(--color-surface); color: var(--color-text); }
  .input-sm { padding: 5px 8px; border: 1px solid var(--color-border); border-radius: var(--radius); font-size: 13px; font-family: var(--font-body); background: var(--color-surface); color: var(--color-text); min-width: 140px; }

  .pre-order-form { padding: 16px; }

  .form-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; margin-bottom: 14px; }

  .field { display: flex; flex-direction: column; gap: 4px; font-size: 13px; color: var(--color-text-muted); }

  .form-msg { font-size: 13px; color: var(--color-text-muted); margin: 0 0 10px; }

  .empty-state { color: var(--color-text-muted); font-size: 13px; font-style: italic; padding: 12px 0; }

  .forecast-raw { font-size: 11px; color: var(--color-text-muted); white-space: pre-wrap; max-height: 200px; overflow-y: auto; }

  .btn { padding: 8px 14px; border-radius: var(--radius); font-size: 13px; font-weight: 500; cursor: pointer; border: 1px solid transparent; font-family: var(--font-body); transition: background 0.12s; }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .btn-primary { background: var(--color-primary); color: #fff; border-color: var(--color-primary); }
  .btn-secondary { background: var(--color-surface-2); color: var(--color-text); border-color: var(--color-border); }
  .btn-outline { background: transparent; color: var(--color-primary); border-color: var(--color-primary); }
  .btn-ghost { background: transparent; color: var(--color-text-muted); }
  .btn-sm { padding: 5px 10px; font-size: 12px; }

  .toast {
    position: fixed;
    bottom: 20px;
    right: 20px;
    background: #333;
    color: #fff;
    padding: 10px 16px;
    border-radius: var(--radius);
    font-size: 13px;
    z-index: 999;
  }
</style>

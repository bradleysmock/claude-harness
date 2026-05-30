<script lang="ts">
  import Nav from './lib/Nav.svelte';
  import Animals from './routes/Animals.svelte';
  import Booth from './routes/Booth.svelte';
  import Inventory from './routes/Inventory.svelte';
  import MillOrders from './routes/MillOrders.svelte';
  import Sync from './routes/Sync.svelte';

  let currentPage = 'animals';
  let boothRef: Booth | null = null;

  function handleNavigate(e: CustomEvent<string>) {
    const next = e.detail;
    if (currentPage === 'booth' && boothRef && !boothRef.canLeave()) return;
    currentPage = next;
  }
</script>

<div class="app-shell">
  <Nav {currentPage} on:navigate={handleNavigate} />
  <main class="content-area">
    <div class="content-inner">
      {#if currentPage === 'animals'}
        <Animals />
      {:else if currentPage === 'mill'}
        <MillOrders />
      {:else if currentPage === 'inventory'}
        <Inventory />
      {:else if currentPage === 'sync'}
        <Sync />
      {:else if currentPage === 'booth'}
        <Booth bind:this={boothRef} />
      {/if}
    </div>
  </main>
</div>

<style>
  .app-shell {
    display: flex;
    min-height: 100vh;
    background: var(--color-bg);
  }

  .content-area {
    flex: 1;
    overflow-y: auto;
    min-width: 0;
  }

  .content-inner {
    max-width: 1100px;
    padding: 28px 32px;
    margin: 0 auto;
  }

  @media (max-width: 640px) {
    .app-shell { flex-direction: column; }
    .content-inner { padding: 16px; }
  }
</style>

<script lang="ts">
  import { createEventDispatcher } from 'svelte';

  export let currentPage: string = 'animals';

  const dispatch = createEventDispatcher<{ navigate: string }>();

  const items = [
    { id: 'animals',   label: 'Animals',     icon: '🐑' },
    { id: 'mill',      label: 'Mill Orders',  icon: '🧶' },
    { id: 'inventory', label: 'Inventory',    icon: '📦' },
    { id: 'sync',      label: 'Sync',         icon: '🔗' },
    { id: 'booth',     label: 'Booth',        icon: '🏪' },
  ];

  function navigate(page: string) {
    dispatch('navigate', page);
  }
</script>

<nav class="sidebar">
  <div class="sidebar-brand">
    <svg class="sheep-icon" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <!-- Body cloud puffs -->
      <circle cx="24" cy="26" r="11" fill="#EDE5D8" stroke="#C8B89A" stroke-width="1.5"/>
      <circle cx="14" cy="28" r="7" fill="#EDE5D8" stroke="#C8B89A" stroke-width="1.5"/>
      <circle cx="34" cy="28" r="7" fill="#EDE5D8" stroke="#C8B89A" stroke-width="1.5"/>
      <circle cx="19" cy="22" r="7" fill="#EDE5D8" stroke="#C8B89A" stroke-width="1.5"/>
      <circle cx="29" cy="22" r="7" fill="#EDE5D8" stroke="#C8B89A" stroke-width="1.5"/>
      <!-- Head -->
      <ellipse cx="24" cy="13" rx="6" ry="5.5" fill="#8B6F47"/>
      <!-- Ears -->
      <ellipse cx="18.5" cy="11" rx="2.5" ry="3.5" fill="#8B6F47" transform="rotate(-15 18.5 11)"/>
      <ellipse cx="29.5" cy="11" rx="2.5" ry="3.5" fill="#8B6F47" transform="rotate(15 29.5 11)"/>
      <!-- Eyes -->
      <circle cx="21.5" cy="12" r="1.2" fill="#fff"/>
      <circle cx="26.5" cy="12" r="1.2" fill="#fff"/>
      <circle cx="21.8" cy="12.2" r="0.6" fill="#3D3530"/>
      <circle cx="26.8" cy="12.2" r="0.6" fill="#3D3530"/>
      <!-- Legs -->
      <rect x="16" y="36" width="3.5" height="8" rx="1.5" fill="#8B6F47"/>
      <rect x="21" y="37" width="3.5" height="8" rx="1.5" fill="#8B6F47"/>
      <rect x="26" y="37" width="3.5" height="8" rx="1.5" fill="#8B6F47"/>
      <rect x="31" y="36" width="3.5" height="8" rx="1.5" fill="#8B6F47"/>
    </svg>
    <span class="brand-name">Flock &amp; Fiber</span>
  </div>

  <ul class="nav-items">
    {#each items as item}
      <li>
        <button
          class="nav-item"
          class:active={currentPage === item.id}
          on:click={() => navigate(item.id)}
        >
          <span class="nav-icon">{item.icon}</span>
          <span class="nav-label">{item.label}</span>
        </button>
      </li>
    {/each}
  </ul>

  <div class="sidebar-footer">
    <span>Small-batch fiber, thoughtfully tracked</span>
  </div>
</nav>

<style>
  .sidebar {
    width: 220px;
    min-height: 100vh;
    background: var(--color-surface);
    border-right: 1px solid var(--color-border);
    display: flex;
    flex-direction: column;
    flex-shrink: 0;
  }

  .sidebar-brand {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 20px 18px 16px;
    border-bottom: 1px solid var(--color-border);
  }

  .sheep-icon {
    width: 36px;
    height: 36px;
    flex-shrink: 0;
  }

  .brand-name {
    font-family: var(--font-heading);
    font-size: 16px;
    font-weight: 700;
    color: var(--color-primary);
    line-height: 1.2;
  }

  .nav-items {
    list-style: none;
    padding: 10px 8px;
    flex: 1;
  }

  .nav-item {
    display: flex;
    align-items: center;
    gap: 10px;
    width: 100%;
    padding: 10px 12px;
    border: none;
    border-radius: var(--radius);
    background: transparent;
    color: var(--color-text-muted);
    font-family: var(--font-body);
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    text-align: left;
    transition: background 0.12s, color 0.12s, border-color 0.12s;
    border-left: 3px solid transparent;
  }

  .nav-item:hover {
    background: var(--color-surface-2);
    color: var(--color-text);
  }

  .nav-item.active {
    background: var(--color-surface-2);
    color: var(--color-primary);
    border-left-color: var(--color-primary);
    font-weight: 600;
  }

  .nav-icon {
    font-size: 16px;
    line-height: 1;
  }

  .sidebar-footer {
    padding: 14px 18px;
    border-top: 1px solid var(--color-border);
    font-size: 10px;
    color: var(--color-text-muted);
    font-style: italic;
    line-height: 1.4;
  }

  @media (max-width: 640px) {
    .sidebar {
      width: 100%;
      min-height: auto;
      flex-direction: row;
      align-items: center;
      border-right: none;
      border-bottom: 1px solid var(--color-border);
      padding: 0;
    }

    .sidebar-brand {
      border-bottom: none;
      flex-shrink: 0;
    }

    .nav-items {
      display: flex;
      flex-direction: row;
      padding: 6px;
      gap: 2px;
    }

    .sidebar-footer {
      display: none;
    }

    .nav-item {
      padding: 8px 12px;
      border-left: none;
      border-bottom: 3px solid transparent;
    }

    .nav-item.active {
      border-left-color: transparent;
      border-bottom-color: var(--color-primary);
    }
  }
</style>

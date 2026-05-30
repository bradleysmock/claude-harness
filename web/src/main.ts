import App from './App.svelte';
import './lib/design.css';

const app = new App({
  target: document.getElementById('app')!,
});

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(console.error);
}

export default app;

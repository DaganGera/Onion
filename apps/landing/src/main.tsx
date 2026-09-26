import '@fontsource/instrument-serif/400.css';
import '@fontsource/instrument-serif/400-italic.css';
import '@fontsource-variable/anek-latin/wdth.css';
import './styles.css';
import { createRoot } from 'react-dom/client';
import { App } from './App';

// The web app used to live at the site root; retire that service worker so /app/ and the landing load fresh.
navigator.serviceWorker?.getRegistrations?.().then((rs) => rs.forEach((r) => { if (!r.scope.includes('/app/')) r.unregister(); })).catch(() => {});

createRoot(document.getElementById('root')!).render(<App />);

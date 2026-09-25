import { render } from 'preact';
import '@fontsource/ibm-plex-sans/400.css';
import '@fontsource/ibm-plex-sans/500.css';
import '@fontsource/ibm-plex-sans/600.css';
import '@fontsource/ibm-plex-sans-condensed/600.css';
import '@fontsource/ibm-plex-mono/400.css';
import '@fontsource/ibm-plex-mono/600.css';
import '@fontsource/noto-sans-devanagari/400.css';
import '@fontsource/noto-sans-devanagari/600.css';
import '@fontsource/noto-sans-tamil/400.css';
import '@fontsource/noto-sans-telugu/400.css';
import '@fontsource/noto-sans-kannada/400.css';
import '@fontsource/noto-sans-gujarati/400.css';
import '@fontsource/noto-sans-bengali/400.css';
import '@fontsource/noto-sans-gurmukhi/400.css';
import './styles/app.css';
import './styles/shell.css';
import { App } from './App';

render(<App />, document.getElementById('app')!);

if ('serviceWorker' in navigator && import.meta.env.PROD) {
  import('virtual:pwa-register').then(({ registerSW }) => registerSW({ immediate: true })).catch(() => {});
}

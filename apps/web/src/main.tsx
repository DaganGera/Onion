import { render } from 'preact';
import '@fontsource-variable/anek-latin/wdth.css';
import '@fontsource-variable/anek-devanagari/wdth.css';
import '@fontsource-variable/anek-bangla/wdth.css';
import '@fontsource-variable/anek-gujarati/wdth.css';
import '@fontsource-variable/anek-gurmukhi/wdth.css';
import '@fontsource-variable/anek-kannada/wdth.css';
import '@fontsource-variable/anek-tamil/wdth.css';
import '@fontsource-variable/anek-telugu/wdth.css';
import '@fontsource/ibm-plex-mono/400.css';
import '@fontsource/ibm-plex-mono/600.css';
import './styles/app.css';
import './styles/shell.css';
import { App } from './App';

render(<App />, document.getElementById('app')!);

if ('serviceWorker' in navigator && import.meta.env.PROD) {
  import('virtual:pwa-register').then(({ registerSW }) => registerSW({ immediate: true })).catch(() => {});
}

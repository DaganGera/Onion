import { useEffect, useState } from 'preact/hooks';
import { useRoute } from './lib/router';
import { setLang, t, useLang } from './lib/i18n';
import { loadSettings } from './lib/device';
import { ToastHost } from './components/ui';
import { Home } from './screens/Home';
import { NewLot } from './screens/NewLot';
import { Capture } from './screens/Capture';
import { Result } from './screens/Result';
import { Certificate } from './screens/Certificate';
import { Verify } from './screens/Verify';
import { Packs } from './screens/Packs';
import { Fleet } from './screens/Fleet';
import { Settings } from './screens/Settings';
import { About } from './screens/About';
import { Lots } from './screens/Lots';
import { More } from './screens/More';
import { BottomNav, type Tab } from './components/nav';
import { Login } from './screens/Login';
import { Users } from './screens/Users';
import { restoreSession, touch, useSession } from './lib/auth';

export function App() {
  const { path, q } = useRoute();
  const [ready, setReady] = useState(false);
  const me = useSession();
  useLang();
  // Any tap keeps the session alive; 15 minutes without one locks the app.
  useEffect(() => {
    const f = () => touch();
    addEventListener('pointerdown', f, { passive: true });
    const iv = setInterval(touch, 30_000);
    return () => { removeEventListener('pointerdown', f); clearInterval(iv); };
  }, []);
  useEffect(() => {
    const t0 = performance.now();
    Promise.all([loadSettings().then((s) => setLang(s.lang)), restoreSession()]).finally(() => {
      setReady(true);
      // Keep the startup screen up at least ~1.2 s so it reads as intentional, then fade it out.
      const wait = Math.max(0, 1200 - (performance.now() - t0));
      setTimeout(() => { const el = document.getElementById('splash'); if (el) { el.classList.add('gone'); setTimeout(() => el.remove(), 450); } }, wait);
    });
  }, []);
  if (!ready) return null;
  const [p0, p1] = path;
  // Checking a receipt needs no account: that is the farmer's and buyer's way in.
  if (!me && p0 !== 'verify') return <div class="shell"><div class="screen"><Login onIn={() => { /* session hook re-renders */ }} /></div><ToastHost /></div>;
  let view;
  let tab: Tab | null | undefined; // undefined = no bottom bar on this screen
  switch (p0) {
    case 'new': view = <NewLot />; break;
    case 'capture': view = <Capture lotId={p1} replay={q.get('replay') === '1'} />; break;
    case 'lot': view = <Result lotId={p1} />; break;
    case 'cert': view = <Certificate hash={p1} />; break;
    case 'verify': view = <Verify code={q.get('c') ?? ''} />; tab = 'verify'; break;
    case 'lots': view = <Lots />; tab = 'lots'; break;
    case 'more': view = <More />; tab = 'more'; break;
    case 'packs': view = <Packs lotId={p1} />; break;
    case 'fleet': view = <Fleet />; break;
    case 'settings': view = <Settings />; break;
    case 'users': view = <Users />; break;
    case 'about': view = <About />; break;
    default: view = <Home />; tab = 'home';
  }
  return (
    <div class="shell">
      <div class="screen" key={p0 ?? 'home'}>{view}</div>
      {tab !== undefined && me && <BottomNav active={tab} />}
      {!me && p0 === 'verify' && <a class="signin-fab" href="#/">{t('lg.signin', 'Sign in')}</a>}
      <ToastHost />
    </div>
  );
}

import { useEffect, useState } from 'preact/hooks';
import { useRoute } from './lib/router';
import { setLang, useLang } from './lib/i18n';
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

export function App() {
  const { path, q } = useRoute();
  const [ready, setReady] = useState(false);
  useLang();
  useEffect(() => { loadSettings().then((s) => setLang(s.lang)).finally(() => setReady(true)); }, []);
  if (!ready) return null;
  const [p0, p1] = path;
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
    case 'about': view = <About />; break;
    default: view = <Home />; tab = 'home';
  }
  return (
    <div class="shell">
      <div class="screen" key={p0 ?? 'home'}>{view}</div>
      {tab !== undefined && <BottomNav active={tab} />}
      <ToastHost />
    </div>
  );
}

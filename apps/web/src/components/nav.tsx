import { House, Layers, ScanLine, ShieldCheck, Menu } from 'lucide-preact';
import { t } from '../lib/i18n';
import { goTab, go } from '../lib/router';

export type Tab = 'home' | 'lots' | 'verify' | 'more';

/** Five-slot bottom bar; the centre slot is a raised scan button that starts a new lot. */
export function BottomNav({ active }: { active: Tab | null }) {
  const item = (tab: Tab, to: string, label: string, Icon: typeof House) => (
    <button class="tab" aria-current={active === tab ? 'page' : undefined} onClick={() => goTab(to)}>
      <Icon size={23} strokeWidth={active === tab ? 2.4 : 1.8} aria-hidden="true" />
      <span>{label}</span>
    </button>
  );
  return (
    <nav class="tabbar" aria-label={t('nav.main', 'Main')}>
      {item('home', '', t('tab.home', 'Home'), House)}
      {item('lots', 'lots', t('tab.lots', 'Lots'), Layers)}
      <div class="tab-scan-slot">
        <button class="tab-scan" onClick={() => go('new')} aria-label={t('tab.scan', 'Grade a new lot')}>
          <ScanLine size={30} strokeWidth={2.2} aria-hidden="true" />
        </button>
        <span class="tab-scan-label">{t('tab.scan.s', 'Scan')}</span>
      </div>
      {item('verify', 'verify', t('tab.verify', 'Verify'), ShieldCheck)}
      {item('more', 'more', t('tab.more', 'More'), Menu)}
    </nav>
  );
}

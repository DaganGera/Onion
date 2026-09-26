import { can, logout, ROLE_LABEL, useSession } from '../lib/auth';
import { goTab } from '../lib/router';
import { useEffect, useState } from 'preact/hooks';
import { LogOut, Users as Users2, History, LayoutDashboard, Settings as Cog, Languages, Printer, Info, KeyRound, ChevronRight, FileDown, Volume2 } from 'lucide-preact';
import { keyFingerprint, loadSettings, saveSettings, type Settings } from '../lib/device';
import { LANGS, setLang, t } from '../lib/i18n';
import { exportLog } from '../lib/lots';
import { TopBar } from '../components/ui';

export function More() {
  const me = useSession();
  const [s, setS] = useState<Settings | null>(null);
  const [fp, setFp] = useState('');
  useEffect(() => { loadSettings().then(setS); keyFingerprint().then(setFp); }, []);
  const row = (href: string, Icon: typeof History, title: string, sub: string, ext = false) => (
    <a class="menurow" href={href} {...(ext ? { target: '_blank', rel: 'noopener' } : {})}>
      <span class="micon"><Icon size={20} aria-hidden="true" /></span>
      <span class="mbody"><b>{title}</b><small>{sub}</small></span>
      <ChevronRight size={18} aria-hidden="true" />
    </a>
  );
  const upd = async (p: Partial<Settings>) => { if (!s) return; const n = { ...s, ...p }; setS(n); await saveSettings(n); if (p.lang) await setLang(p.lang); };
  const exportIt = async () => {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([JSON.stringify(await exportLog(), null, 1)], { type: 'application/json' }));
    a.download = `parakh-log-${new Date().toISOString().slice(0, 10)}.json`; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  };

  return (
    <>
      <TopBar title={t('more.title', 'More')} />
      <main class="page with-tabs">
        <section class="profile">
          <div class="avatar lg" aria-hidden="true">{(me?.name ?? 'O').slice(0, 1)}</div>
          <div class="grow">
            <b>{me?.name} <span class="mono xs muted">{me?.id}</span></b>
            <small><span class={`chip role-${me?.role}`}>{me ? t('role.' + me.role, ROLE_LABEL[me.role]) : ''}</span> · {s?.centre}</small>
            <small class="mono"><KeyRound size={12} aria-hidden="true" /> {fp}</small>
          </div>
        </section>

        <section class="menu">
          <label class="menurow">
            <span class="micon"><Languages size={20} aria-hidden="true" /></span>
            <span class="mbody"><b>{t('set.lang', 'Language')}</b><small>{t('more.lang.s', 'App text and spoken result')}</small></span>
            <select class="minisel" value={s?.lang ?? 'en'} onChange={(e) => upd({ lang: (e.target as HTMLSelectElement).value })}>
              {LANGS.map((l) => <option key={l.code} value={l.code}>{l.name}</option>)}
            </select>
          </label>
          <label class="menurow">
            <span class="micon"><Volume2 size={20} aria-hidden="true" /></span>
            <span class="mbody"><b>{t('set.speak', 'Read the lot decision aloud')}</b><small>{t('more.speak.s', 'Uses the phone’s voice')}</small></span>
            <input type="checkbox" class="switch" checked={!!s?.speak} onChange={(e) => upd({ speak: (e.target as HTMLInputElement).checked })} />
          </label>
        </section>

        <section class="menu">
          {row('#/packs', History, t('home.packs', 'Rule packs'), t('more.packs.s', 'Norms in force and time travel'))}
          {can(me, 'fleet.view') && row('#/fleet', LayoutDashboard, t('nav.fleet', 'Fleet dashboard'), t('more.fleet.s', 'Centre drift and overrides'))}
          {row('./calibration_mat.pdf', Printer, t('nav.mat', 'Calibration mat (A4)'), t('more.mat.s', 'Print at 100% for exact sizes'), true)}
          {can(me, 'log.export') && <button class="menurow" onClick={exportIt}>
            <span class="micon"><FileDown size={20} aria-hidden="true" /></span>
            <span class="mbody"><b>{t('set.export', 'Export log')}</b><small>{t('more.export.s', 'Transparency log to publish')}</small></span>
            <ChevronRight size={18} aria-hidden="true" />
          </button>}
        </section>

        <section class="menu">
          {can(me, 'users.manage') && row('#/users', Users2, t('us.title', 'Users & roles'), t('more.users.s', 'Add officers and auditors, reset PINs'))}
          {row('#/settings', Cog, t('nav.settings', 'Settings & log'), t('more.settings.s', 'Centre, keys, models, rates'))}
          {row('#/about', Info, t('nav.about', 'How it works & limits'), t('more.about.s', 'What the app can and cannot do'))}
        </section>
        <button class="btn quiet" onClick={() => { logout(); goTab(''); }}><LogOut size={18} aria-hidden="true" />{t('more.switch', 'Switch user / lock')}</button>
        <p class="xs muted center">SAMA · SIH 2026 · PS 26031 · AlgoRangersV1</p>
      </main>
    </>
  );
}

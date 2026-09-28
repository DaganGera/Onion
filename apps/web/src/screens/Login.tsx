import { useEffect, useState } from 'preact/hooks';
import { ShieldCheck, Delete, ChevronLeft, UserPlus, Play } from 'lucide-preact';
import { addUser, listUsers, login, seedDemoUsers, ROLE_LABEL, validPin, type User } from '../lib/auth';
import { t } from '../lib/i18n';
import { go } from '../lib/router';

const initials = (n: string) => n.split(/[\s.]+/).filter(Boolean).map((w) => w[0]).slice(0, 2).join('').toUpperCase();

function PinPad({ value, onChange, onDone, len = 4 }: { value: string; onChange: (v: string) => void; onDone: (v: string) => void; len?: number }) {
  const press = (d: string) => { const v = (value + d).slice(0, 6); onChange(v); if (v.length === len) onDone(v); };
  return (
    <div class="pinpad">
      <div class="pindots" aria-label={t('lg.pin.n', '{n} digits entered', { n: value.length })}>
        {Array.from({ length: Math.max(len, value.length) }, (_, i) => <i key={i} data-on={i < value.length ? '1' : undefined} />)}
      </div>
      <div class="pinkeys">
        {['1', '2', '3', '4', '5', '6', '7', '8', '9'].map((d) => <button key={d} class="pinkey" onClick={() => press(d)}>{d}</button>)}
        <span />
        <button class="pinkey" onClick={() => press('0')}>0</button>
        <button class="pinkey ghost" aria-label={t('lg.del', 'Delete')} onClick={() => onChange(value.slice(0, -1))}><Delete size={22} aria-hidden="true" /></button>
      </div>
    </div>
  );
}

/** First run: create the supervisor account, or load the three demo accounts. */
function Setup({ onDone }: { onDone: () => void }) {
  const [name, setName] = useState('');
  const [id, setId] = useState('SUP-01');
  const [pin, setPin] = useState('');
  const [pin2, setPin2] = useState('');
  const [err, setErr] = useState('');
  const create = async () => {
    setErr('');
    if (pin !== pin2) { setErr(t('lg.mismatch', 'The two PINs do not match.')); return; }
    try { await addUser({ id, name, role: 'supervisor', pin }, 'setup'); onDone(); } catch (e) { setErr((e as Error).message); }
  };
  const demo = async () => { await seedDemoUsers(); onDone(); };
  return (
    <main class="page login">
      <div class="login-head">
        <img src="./icon.svg" alt="" width="64" height="64" />
        <h1>{t('lg.welcome', 'Set up this phone')}</h1>
        <p class="muted">{t('lg.welcome.p', 'The first account is the centre supervisor. The supervisor adds officers and auditors. Farmers never need an account.')}</p>
      </div>
      <section class="section">
        <label class="field"><span>{t('lg.name', 'Your name')}</span><input class="input" value={name} onInput={(e) => setName((e.target as HTMLInputElement).value)} /></label>
        <label class="field"><span>{t('lg.id', 'ID printed on receipts')}</span><input class="input mono" value={id} onInput={(e) => setId((e.target as HTMLInputElement).value)} /></label>
        <label class="field"><span>{t('lg.newpin', 'PIN (4 to 6 digits)')}</span><input class="input mono" type="password" inputMode="numeric" autoComplete="new-password" value={pin} onInput={(e) => setPin((e.target as HTMLInputElement).value.replace(/\D/g, ''))} /></label>
        <label class="field"><span>{t('lg.newpin2', 'Repeat PIN')}</span><input class="input mono" type="password" inputMode="numeric" autoComplete="new-password" value={pin2} onInput={(e) => setPin2((e.target as HTMLInputElement).value.replace(/\D/g, ''))} /></label>
        {err && <p class="banner warn" role="alert">{err}</p>}
        <button class="btn primary" disabled={!name.trim() || !validPin(pin)} onClick={create}><UserPlus size={18} aria-hidden="true" />{t('lg.create', 'Create supervisor account')}</button>
      </section>
      <div class="login-or"><span>{t('lg.or', 'or')}</span></div>
      <button class="btn quiet" onClick={demo}><Play size={18} aria-hidden="true" />{t('lg.demo', 'Explore the demo (3 sample accounts)')}</button>
      <a class="login-farmer" href="#/verify"><ShieldCheck size={18} aria-hidden="true" />{t('lg.farmer', 'Farmer or buyer? Check a receipt without an account')}</a>
    </main>
  );
}

export function Login({ onIn }: { onIn: () => void }) {
  const [users, setUsers] = useState<User[] | null>(null);
  const [pick, setPick] = useState<User | null>(null);
  const [pin, setPin] = useState('');
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  const load = () => listUsers().then((us) => setUsers(us.filter((u) => u.active)));
  useEffect(() => { load(); }, []);
  if (!users) return null;
  if (!users.length) return <Setup onDone={load} />;

  const tryPin = async (v: string) => {
    if (!pick) return;
    setBusy(true); setErr('');
    try { await login(pick.id, v); onIn(); } catch (e) { setErr((e as Error).message); setPin(''); } finally { setBusy(false); }
  };

  if (pick) return (
    <main class="page login">
      <button class="linkbtn login-back" onClick={() => { setPick(null); setPin(''); setErr(''); }}><ChevronLeft size={18} aria-hidden="true" />{t('lg.others', 'Other accounts')}</button>
      <div class="login-head">
        <div class="avatar lg" aria-hidden="true">{initials(pick.name)}</div>
        <h1>{pick.name}</h1>
        <p class="muted"><span class={`chip role-${pick.role}`}>{t('role.' + pick.role, ROLE_LABEL[pick.role])}</span> <span class="mono">{pick.id}</span></p>
      </div>
      <p class="center small">{t('lg.enter', 'Enter your PIN')}{pick.demo ? <span class="muted"> · {t('lg.demopin', 'demo PIN')} <b class="mono">{({ supervisor: '1111', officer: '2222', auditor: '3333' } as Record<string, string>)[pick.role]}</b></span> : null}</p>
      <PinPad value={pin} onChange={setPin} onDone={tryPin} />
      {busy && <p class="center small muted">{t('lg.checking', 'Checking…')}</p>}
      {err && <p class="banner warn center" role="alert">{err}</p>}
    </main>
  );

  return (
    <main class="page login">
      <div class="login-head">
        <img src="./icon.svg" alt="" width="56" height="56" />
        <h1>{t('lg.who', 'Who is using this phone?')}</h1>
        <p class="muted">{t('lg.who.p', 'Every lot and every change is recorded under your name.')}</p>
      </div>
      <div class="userlist" role="list">
        {users.map((u) => (
          <button key={u.id} class="usertile" role="listitem" onClick={() => setPick(u)}>
            <span class="avatar" aria-hidden="true">{initials(u.name)}</span>
            <span class="grow"><b>{u.name}</b><small><span class={`chip role-${u.role}`}>{t('role.' + u.role, ROLE_LABEL[u.role])}</span> <span class="mono">{u.id}</span></small></span>
          </button>
        ))}
      </div>
      <a class="login-farmer" href="#/verify" onClick={() => go('verify')}><ShieldCheck size={18} aria-hidden="true" />{t('lg.farmer', 'Farmer or buyer? Check a receipt without an account')}</a>
    </main>
  );
}

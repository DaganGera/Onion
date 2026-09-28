import { useEffect, useState } from 'preact/hooks';
import { UserPlus, KeyRound } from 'lucide-preact';
import { addUser, can, listUsers, updateUser, useSession, ROLE_LABEL, validPin, type Role, type User } from '../lib/auth';
import { t } from '../lib/i18n';
import { toast, TopBar } from '../components/ui';

/** Supervisor only: add officers and auditors, reset PINs, switch accounts off. */
export function Users() {
  const me = useSession();
  const [users, setUsers] = useState<User[]>([]);
  const [name, setName] = useState('');
  const [id, setId] = useState('');
  const [role, setRole] = useState<Role>('officer');
  const [pin, setPin] = useState('');
  const [err, setErr] = useState('');
  const [resetFor, setResetFor] = useState<string | null>(null);
  const [newPin, setNewPin] = useState('');
  const load = () => listUsers().then(setUsers);
  useEffect(() => { load(); }, []);

  if (!can(me, 'users.manage')) return (
    <>
      <TopBar title={t('us.title', 'Users & roles')} backTo="more" />
      <main class="page"><p class="banner warn">{t('perm.no', 'Your role cannot do this. Ask the centre supervisor.')}</p></main>
    </>
  );

  const add = async () => {
    setErr('');
    try { await addUser({ id, name, role, pin }, me!.id); setName(''); setId(''); setPin(''); await load(); toast(t('us.added', 'Account added.')); }
    catch (e) { setErr((e as Error).message); }
  };
  const act = async (fn: () => Promise<void>, msg: string) => { try { await fn(); await load(); toast(msg); } catch (e) { toast((e as Error).message); } };

  return (
    <>
      <TopBar title={t('us.title', 'Users & roles')} backTo="more" />
      <main class="page">
        <section class="section">
          <h2 style={{ fontSize: 'var(--text-lg)' }}>{t('us.roles', 'What each role can do')}</h2>
          <ul class="rolelist small">
            <li><span class="chip role-supervisor">{t('role.supervisor', ROLE_LABEL.supervisor)}</span> {t('us.r.sup', 'Everything an officer can do, plus add people, change the rule pack in force, re-grade a lot under another pack, and edit centre settings.')}</li>
            <li><span class="chip role-officer">{t('role.officer', ROLE_LABEL.officer)}</span> {t('us.r.off', 'Start lots, photograph trays, change a verdict with a reason, and sign receipts.')}</li>
            <li><span class="chip role-auditor">{t('role.auditor', ROLE_LABEL.auditor)}</span> {t('us.r.aud', 'Read only: lots, receipts, fleet dashboard, log export. Cannot grade, change or sign.')}</li>
            <li><span class="chip">{t('role.farmer', 'Farmer')}</span> {t('us.r.farm', 'No account. Contests a bulb on the officer’s screen, and checks receipts on any phone.')}</li>
          </ul>
        </section>

        <section class="section">
          <h2 style={{ fontSize: 'var(--text-lg)' }}>{t('us.people', 'People on this phone')}</h2>
          <div class="userlist" role="list">
            {users.map((u) => (
              <div key={u.id} class="usertile static" role="listitem" data-off={u.active ? undefined : '1'}>
                <span class="grow"><b>{u.name}</b><small><span class={`chip role-${u.role}`}>{t('role.' + u.role, ROLE_LABEL[u.role])}</span> <span class="mono">{u.id}</span>{!u.active && <> · {t('us.off', 'switched off')}</>}</small></span>
                <span class="row">
                  <button class="linkbtn xs" onClick={() => { setResetFor(resetFor === u.id ? null : u.id); setNewPin(''); }}><KeyRound size={14} aria-hidden="true" />{t('us.reset', 'Reset PIN')}</button>
                  {u.id !== me!.id && <button class="linkbtn xs" onClick={() => act(() => updateUser(u.id, { active: !u.active }), u.active ? t('us.disabled', 'Account switched off.') : t('us.enabled', 'Account switched on.'))}>{u.active ? t('us.disable', 'Switch off') : t('us.enable', 'Switch on')}</button>}
                </span>
                {resetFor === u.id && (
                  <span class="row resetrow">
                    <input class="input mono" type="password" inputMode="numeric" autoComplete="new-password" aria-label={t('us.newpin', 'New PIN for {n} (4 to 6 digits)', { n: u.name })} placeholder={t('us.newpin.s', 'New PIN')} value={newPin} onInput={(e) => setNewPin((e.target as HTMLInputElement).value.replace(/\D/g, ''))} />
                    <button class="btn primary sm" disabled={!validPin(newPin)} onClick={() => act(async () => { await updateUser(u.id, { pin: newPin }); setResetFor(null); }, t('us.pinset', 'PIN changed.'))}>{t('us.save', 'Save')}</button>
                  </span>
                )}
              </div>
            ))}
          </div>
          <p class="note">{t('us.keep', 'Accounts are switched off, never deleted, so old receipts still name who signed them.')}</p>
        </section>

        <section class="section">
          <h2 style={{ fontSize: 'var(--text-lg)' }}>{t('us.add', 'Add a person')}</h2>
          <label class="field"><span>{t('lg.name', 'Name')}</span><input class="input" value={name} onInput={(e) => setName((e.target as HTMLInputElement).value)} /></label>
          <label class="field"><span>{t('lg.id', 'ID printed on receipts')}</span><input class="input mono" placeholder="OFF-08" value={id} onInput={(e) => setId((e.target as HTMLInputElement).value)} /></label>
          <label class="field"><span>{t('us.role', 'Role')}</span>
            <select class="select" value={role} onChange={(e) => setRole((e.target as HTMLSelectElement).value as Role)}>
              {(['officer', 'auditor', 'supervisor'] as Role[]).map((r) => <option key={r} value={r}>{t('role.' + r, ROLE_LABEL[r])}</option>)}
            </select>
          </label>
          <label class="field"><span>{t('lg.newpin', 'PIN (4 to 6 digits)')}</span><input class="input mono" type="password" inputMode="numeric" autoComplete="new-password" value={pin} onInput={(e) => setPin((e.target as HTMLInputElement).value.replace(/\D/g, ''))} /></label>
          {err && <p class="banner warn" role="alert">{err}</p>}
          <button class="btn primary" disabled={!name.trim() || !id.trim() || !validPin(pin)} onClick={add}><UserPlus size={18} aria-hidden="true" />{t('us.addbtn', 'Add account')}</button>
        </section>
      </main>
    </>
  );
}

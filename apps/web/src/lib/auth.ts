import { useEffect, useState } from 'preact/hooks';
import { kvGet, kvSet } from './db';

/**
 * Local, offline accounts. Each phone keeps its own list of people who may use it.
 * PINs are never stored: only PBKDF2-SHA256 hashes with a per-user salt.
 * The farmer has no account; verifying a receipt needs no login.
 */
export type Role = 'supervisor' | 'officer' | 'auditor';

export interface User {
  id: string;          // e.g. OFF-07, shown on receipts
  name: string;
  role: Role;
  salt: string;        // hex
  pinHash: string;     // hex, PBKDF2-SHA256
  createdAt: string;
  createdBy: string;   // user id of the supervisor who added them, or 'setup'
  active: boolean;
  demo?: boolean;      // demo accounts show their PIN on the login screen
}

export type Action =
  | 'lot.create'      // start a lot, capture, grade
  | 'bulb.override'   // officer changes an AI verdict
  | 'bulb.contest'    // farmer contests, on the officer's phone
  | 'cert.sign'       // sign a receipt revision
  | 'pack.change'     // switch the rule pack in force
  | 'users.manage'
  | 'settings.edit'
  | 'fleet.view'
  | 'log.export';

const RULES: Record<Role, Action[]> = {
  supervisor: ['lot.create', 'bulb.override', 'bulb.contest', 'cert.sign', 'pack.change', 'users.manage', 'settings.edit', 'fleet.view', 'log.export'],
  officer: ['lot.create', 'bulb.override', 'bulb.contest', 'cert.sign'],
  auditor: ['fleet.view', 'log.export'],
};

export const ROLE_LABEL: Record<Role, string> = { supervisor: 'Supervisor', officer: 'Procurement officer', auditor: 'Auditor' };

export function can(user: User | null, action: Action): boolean {
  return !!user && user.active && RULES[user.role].includes(action);
}

const ITER = 150_000;
const LOCK_MS = 15 * 60 * 1000;   // auto-lock after 15 min without a tap
const MAX_TRIES = 5, COOLDOWN_MS = 30_000;

const hex = (b: ArrayBuffer | Uint8Array) => [...new Uint8Array(b)].map((x) => x.toString(16).padStart(2, '0')).join('');
const unhex = (h: string) => new Uint8Array(h.match(/../g)!.map((x) => parseInt(x, 16)));

async function hashPin(pin: string, saltHex: string): Promise<string> {
  const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(pin), 'PBKDF2', false, ['deriveBits']);
  const bits = await crypto.subtle.deriveBits({ name: 'PBKDF2', hash: 'SHA-256', salt: unhex(saltHex), iterations: ITER }, key, 256);
  return hex(bits);
}

export const validPin = (pin: string) => /^\d{4,6}$/.test(pin);

export async function listUsers(): Promise<User[]> {
  return kvGet<User[]>('users', []);
}
async function saveUsers(us: User[]) { await kvSet('users', us); }

export async function addUser(u: { id: string; name: string; role: Role; pin: string; demo?: boolean }, by: string): Promise<User> {
  const id = u.id.trim().toUpperCase(), name = u.name.trim();
  if (!id || !name) throw new Error('Name and ID are required.');
  if (!validPin(u.pin)) throw new Error('PIN must be 4 to 6 digits.');
  const us = await listUsers();
  if (us.some((x) => x.id === id)) throw new Error(`ID ${id} is already used on this phone.`);
  const salt = hex(crypto.getRandomValues(new Uint8Array(16)));
  const user: User = { id, name, role: u.role, salt, pinHash: await hashPin(u.pin, salt), createdAt: new Date().toISOString(), createdBy: by, active: true, demo: u.demo };
  await saveUsers([...us, user]);
  return user;
}

export async function updateUser(id: string, patch: Partial<Pick<User, 'active' | 'role' | 'name'>> & { pin?: string }) {
  const us = await listUsers();
  const i = us.findIndex((x) => x.id === id);
  if (i < 0) return;
  const next = { ...us[i], ...patch };
  delete (next as { pin?: string }).pin;
  if (patch.pin) {
    if (!validPin(patch.pin)) throw new Error('PIN must be 4 to 6 digits.');
    next.salt = hex(crypto.getRandomValues(new Uint8Array(16)));
    next.pinHash = await hashPin(patch.pin, next.salt);
  }
  // Never leave the phone without an active supervisor.
  const after = us.map((x, j) => (j === i ? next : x));
  if (!after.some((x) => x.active && x.role === 'supervisor')) throw new Error('At least one active supervisor must remain.');
  us[i] = next;
  await saveUsers(us);
}

/** Three demo accounts so judges can try every role. PINs are shown on the login screen. */
export async function seedDemoUsers() {
  if ((await listUsers()).length) return;
  await addUser({ id: 'SUP-01', name: 'S. Patil', role: 'supervisor', pin: '1111', demo: true }, 'setup');
  await addUser({ id: 'OFF-07', name: 'R. Shinde', role: 'officer', pin: '2222', demo: true }, 'SUP-01');
  await addUser({ id: 'AUD-03', name: 'A. Kulkarni', role: 'auditor', pin: '3333', demo: true }, 'SUP-01');
}

/* ---------- session ---------- */

let current: User | null = null;
let lastActive = 0;
const subs = new Set<(u: User | null) => void>();
const emit = () => subs.forEach((f) => f(current));
const tries = new Map<string, { n: number; until: number }>();

export function currentUser() { return current; }

export async function login(id: string, pin: string): Promise<User> {
  const t = tries.get(id);
  if (t && t.until > Date.now()) throw new Error(`Too many wrong PINs. Try again in ${Math.ceil((t.until - Date.now()) / 1000)} s.`);
  const u = (await listUsers()).find((x) => x.id === id);
  if (!u || !u.active) throw new Error('This account is not active.');
  if ((await hashPin(pin, u.salt)) !== u.pinHash) {
    const n = (t?.n ?? 0) + 1;
    tries.set(id, n >= MAX_TRIES ? { n: 0, until: Date.now() + COOLDOWN_MS } : { n, until: 0 });
    throw new Error(n >= MAX_TRIES ? 'Too many wrong PINs. Wait 30 s.' : 'Wrong PIN.');
  }
  tries.delete(id);
  current = u; lastActive = Date.now();
  try { sessionStorage.setItem('sama.session', JSON.stringify({ id: u.id, at: lastActive })); } catch { /* private mode */ }
  emit();
  return u;
}

export function logout() {
  current = null;
  try { sessionStorage.removeItem('sama.session'); } catch { /* ignore */ }
  emit();
}

/** Restore a session from this tab (survives reloads, not app restarts), unless it has timed out. */
export async function restoreSession() {
  try {
    const s = JSON.parse(sessionStorage.getItem('sama.session') ?? 'null') as { id: string; at: number } | null;
    if (!s || Date.now() - s.at > LOCK_MS) return;
    const u = (await listUsers()).find((x) => x.id === s.id && x.active);
    if (u) { current = u; lastActive = Date.now(); emit(); }
  } catch { /* ignore */ }
}

/** Call on user interaction; locks the app after LOCK_MS of inactivity. */
export function touch() {
  if (!current) return;
  if (Date.now() - lastActive > LOCK_MS) { logout(); return; }
  lastActive = Date.now();
  try { sessionStorage.setItem('sama.session', JSON.stringify({ id: current.id, at: lastActive })); } catch { /* ignore */ }
}

export function useSession(): User | null {
  const [u, setU] = useState(current);
  useEffect(() => { subs.add(setU); setU(current); return () => { subs.delete(setU); }; }, []);
  return u;
}

/** "R. Shinde (OFF-07)" for lots and receipts. */
export const who = (u: User) => `${u.name} (${u.id})`;

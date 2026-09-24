import { useEffect, useState } from 'preact/hooks';

/**
 * English strings live inline at the call site: t('key', 'English text').
 * Other languages are JSON maps of key -> text in src/locales/<code>.json,
 * machine-drafted and marked for proofreading (docs/OPEN_QUESTIONS.md).
 * Missing keys fall back to English, never to a raw key.
 */
export const LANGS: { code: string; name: string; bcp: string }[] = [
  { code: 'en', name: 'English', bcp: 'en-IN' },
  { code: 'hi', name: 'हिन्दी', bcp: 'hi-IN' },
  { code: 'mr', name: 'मराठी', bcp: 'mr-IN' },
  { code: 'ta', name: 'தமிழ்', bcp: 'ta-IN' },
  { code: 'te', name: 'తెలుగు', bcp: 'te-IN' },
  { code: 'kn', name: 'ಕನ್ನಡ', bcp: 'kn-IN' },
  { code: 'gu', name: 'ગુજરાતી', bcp: 'gu-IN' },
  { code: 'bn', name: 'বাংলা', bcp: 'bn-IN' },
  { code: 'pa', name: 'ਪੰਜਾਬੀ', bcp: 'pa-IN' },
];

const loaders = import.meta.glob('../locales/*.json');
let dict: Record<string, string> = {};
let lang = 'en';
const listeners = new Set<() => void>();

export async function setLang(code: string) {
  lang = code;
  dict = {};
  const l = loaders[`../locales/${code}.json`];
  if (code !== 'en' && l) dict = ((await l()) as { default: Record<string, string> }).default;
  document.documentElement.lang = LANGS.find((x) => x.code === code)?.bcp ?? 'en';
  listeners.forEach((f) => f());
}

export function getLang() { return lang; }

export function t(key: string, en: string, vars?: Record<string, string | number>): string {
  let s = dict[key] ?? en;
  if (vars) for (const [k, v] of Object.entries(vars)) s = s.split(`{${k}}`).join(String(v));
  return s;
}

export function useLang() {
  const [, force] = useState(0);
  useEffect(() => { const f = () => force((x) => x + 1); listeners.add(f); return () => { listeners.delete(f); }; }, []);
  return lang;
}

export function speak(text: string) {
  try {
    if (!('speechSynthesis' in window)) return;
    const u = new SpeechSynthesisUtterance(text);
    u.lang = LANGS.find((x) => x.code === lang)?.bcp ?? 'en-IN';
    const v = speechSynthesis.getVoices().find((v) => v.lang.startsWith(u.lang.slice(0, 2)));
    if (v) u.voice = v;
    speechSynthesis.cancel();
    speechSynthesis.speak(u);
  } catch { /* speech is a nicety */ }
}

import { useEffect, useState } from 'preact/hooks';

export function parseHash(): { path: string[]; q: URLSearchParams } {
  const h = location.hash.replace(/^#\/?/, '');
  const [p, qs] = h.split('?');
  return { path: p ? p.split('/').map(decodeURIComponent) : [], q: new URLSearchParams(qs ?? '') };
}

export function useRoute() {
  const [r, setR] = useState(parseHash());
  useEffect(() => {
    const f = () => { setR(parseHash()); window.scrollTo(0, 0); };
    addEventListener('hashchange', f);
    return () => removeEventListener('hashchange', f);
  }, []);
  return r;
}

export const go = (to: string) => { location.hash = to.startsWith('#') ? to : '#/' + to.replace(/^\//, ''); };
export const back = (fallback = '') => (history.length > 1 ? history.back() : go(fallback));

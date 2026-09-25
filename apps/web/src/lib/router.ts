import { useEffect, useState } from 'preact/hooks';

export function parseHash(): { path: string[]; q: URLSearchParams } {
  const h = location.hash.replace(/^#\/?/, '');
  const [p, qs] = h.split('?');
  return { path: p ? p.split('/').map(decodeURIComponent) : [], q: new URLSearchParams(qs ?? '') };
}

const norm = (to: string) => to.replace(/^#?\/?/, '');
/** In-app route history, so the back arrow can tell whether history.back() lands where it should. */
const visited: string[] = [norm(location.hash)];

export function useRoute() {
  const [r, setR] = useState(parseHash());
  useEffect(() => {
    const f = () => {
      const cur = norm(location.hash);
      if (visited[visited.length - 2] === cur) visited.pop(); // browser/hardware back
      else if (visited[visited.length - 1] !== cur) visited.push(cur);
      setR(parseHash());
      window.scrollTo(0, 0);
    };
    addEventListener('hashchange', f);
    return () => removeEventListener('hashchange', f);
  }, []);
  return r;
}

export const go = (to: string) => { location.hash = '#/' + norm(to); };

/** Tab switches replace the current entry, so hardware back never walks through tab hops. */
export const goTab = (to: string) => {
  const target = '#/' + norm(to);
  if (location.hash === target || (target === '#/' && !location.hash)) return;
  location.replace(target);
};

/**
 * Deterministic back: always lands on the screen's logical parent. If the
 * previous in-app page IS that parent, use history.back() (keeps the stack
 * clean); otherwise replace the current entry with the parent.
 */
export const back = (parent = '') => {
  const p = norm(parent);
  if (visited.length > 1 && visited[visited.length - 2] === p) history.back();
  else { visited[visited.length - 1] = p; location.replace('#/' + p); }
};

import { useEffect, useRef } from 'react';
import * as THREE from 'three';

/** Procedural red-onion skin: vertical veins, darker base, paler shoulders, dry golden neck. */
function onionTexture(): THREE.CanvasTexture {
  const W = 1024, H = 1024;
  const c = document.createElement('canvas');
  c.width = W; c.height = H;
  const g = c.getContext('2d')!;
  // v = 0 at the root (canvas bottom), v = 1 at the neck tip (canvas top).
  const grad = g.createLinearGradient(0, H, 0, 0);
  grad.addColorStop(0.0, '#2a0a1b');
  grad.addColorStop(0.18, '#4e1433');
  grad.addColorStop(0.45, '#7d2451');
  grad.addColorStop(0.66, '#9b3a68');
  grad.addColorStop(0.78, '#b56787');
  grad.addColorStop(0.86, '#c9a07f');
  grad.addColorStop(1.0, '#e2c49a');
  g.fillStyle = grad;
  g.fillRect(0, 0, W, H);
  let seed = 7;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  // Veins: slightly wavy vertical strokes, alternating darker and lighter.
  for (let k = 0; k < 64; k++) {
    const x0 = (k / 64) * W + rnd() * 10;
    const dark = k % 2 === 0;
    g.strokeStyle = dark ? `rgba(40,6,24,${0.18 + rnd() * 0.2})` : `rgba(255,220,235,${0.08 + rnd() * 0.1})`;
    g.lineWidth = 1 + rnd() * (dark ? 3 : 2);
    g.beginPath();
    for (let y = H; y >= H * 0.12; y -= 16) {
      const x = x0 + Math.sin(y / 90 + k) * 4;
      if (y === H) g.moveTo(x, y); else g.lineTo(x, y);
    }
    g.stroke();
  }
  // Papery speckle and a few bruise-free highlights.
  for (let i = 0; i < 9000; i++) {
    g.fillStyle = `rgba(${rnd() < 0.5 ? '255,235,240' : '30,5,15'},${rnd() * 0.06})`;
    g.fillRect(rnd() * W, rnd() * H, 2, 2);
  }
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.wrapS = THREE.RepeatWrapping;
  t.anisotropy = 8;
  return t;
}

function onionProfile(): THREE.Vector2[] {
  const pts: THREE.Vector2[] = [];
  pts.push(new THREE.Vector2(0.0001, -0.9));
  pts.push(new THREE.Vector2(0.16, -0.9)); // root plate
  for (let i = 0; i <= 40; i++) {
    const a = -Math.PI / 2 + (i / 40) * (Math.PI / 2 + 1.05);
    const r = Math.cos(a) * 1.02 * (1 + 0.04 * Math.sin(a * 3));
    const y = Math.sin(a) * 0.86 + (a > 0 ? Math.sin(a) * 0.06 : 0);
    pts.push(new THREE.Vector2(Math.max(0.12, r), y));
  }
  const last = pts[pts.length - 1];
  for (let i = 1; i <= 20; i++) {
    const s = i / 20;
    pts.push(new THREE.Vector2(0.018 + (last.x - 0.018) * Math.pow(1 - s, 1.7), last.y + s * 0.62));
  }
  pts.push(new THREE.Vector2(0.0001, last.y + 0.64));
  return pts;
}

export function Onion3D({ className }: { className?: string }) {
  const host = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = host.current!;
    const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' });
    renderer.setPixelRatio(Math.min(devicePixelRatio, innerWidth < 768 ? 1.5 : 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.05;
    el.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 50);
    camera.position.set(0, 0.25, 6.2);

    const onion = new THREE.Group();
    const map = onionTexture();
    const bulb = new THREE.Mesh(
      new THREE.LatheGeometry(onionProfile(), 128),
      new THREE.MeshPhysicalMaterial({ map, roughness: 0.42, clearcoat: 0.55, clearcoatRoughness: 0.35, sheen: 0.8, sheenColor: new THREE.Color('#f3b8cf'), sheenRoughness: 0.5 }),
    );
    onion.add(bulb);
    // Dry neck tail.
    const tail = new THREE.CatmullRomCurve3([new THREE.Vector3(0, 1.4, 0), new THREE.Vector3(0.04, 1.62, 0.02), new THREE.Vector3(0.12, 1.8, 0.05), new THREE.Vector3(0.24, 1.9, 0.02)]);
    const dry = new THREE.MeshStandardMaterial({ color: '#c8a46f', roughness: 0.9 });
    onion.add(new THREE.Mesh(new THREE.TubeGeometry(tail, 24, 0.025, 8), dry));
    // Root tuft.
    let seed = 3;
    const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
    const rootMat = new THREE.MeshStandardMaterial({ color: '#d8c29a', roughness: 1 });
    for (let i = 0; i < 46; i++) {
      const a = rnd() * Math.PI * 2, r0 = rnd() * 0.12, len = 0.18 + rnd() * 0.32;
      const p0 = new THREE.Vector3(Math.cos(a) * r0, -0.9, Math.sin(a) * r0);
      const p1 = new THREE.Vector3(Math.cos(a) * (r0 + len * 0.6), -0.95 - len * 0.35, Math.sin(a) * (r0 + len * 0.6));
      const p2 = new THREE.Vector3(Math.cos(a) * (r0 + len), -0.98 - len * 0.5 + rnd() * 0.1, Math.sin(a) * (r0 + len));
      onion.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.QuadraticBezierCurve3(p0, p1, p2), 8, 0.006, 4), rootMat));
    }
    onion.rotation.z = -0.12;
    scene.add(onion);

    scene.add(new THREE.AmbientLight('#ffe9f1', 0.35));
    const key = new THREE.DirectionalLight('#fff1dd', 2.4); key.position.set(-3, 4, 4); scene.add(key);
    const rim = new THREE.DirectionalLight('#e6ae45', 2.2); rim.position.set(3, 1.5, -3); scene.add(rim);
    const fill = new THREE.DirectionalLight('#b04a86', 0.9); fill.position.set(3, -2, 3); scene.add(fill);

    // Floating dry-skin flakes.
    const flakes = new THREE.BufferGeometry();
    const N = 140, pos = new Float32Array(N * 3);
    for (let i = 0; i < N; i++) { pos[i * 3] = (rnd() - 0.5) * 9; pos[i * 3 + 1] = (rnd() - 0.5) * 6; pos[i * 3 + 2] = (rnd() - 0.5) * 4 - 1; }
    flakes.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    const flakeMesh = new THREE.Points(flakes, new THREE.PointsMaterial({ color: '#e6ae45', size: 0.025, transparent: true, opacity: 0.55 }));
    scene.add(flakeMesh);

    const size = () => {
      const w = el.clientWidth, h = el.clientHeight;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      const s = w < 768 ? 0.78 : 1;
      onion.scale.setScalar(s);
    };
    size();
    const ro = new ResizeObserver(size); ro.observe(el);

    let px = 0, py = 0;
    const onMove = (e: PointerEvent) => { px = (e.clientX / innerWidth - 0.5) * 2; py = (e.clientY / innerHeight - 0.5) * 2; };
    addEventListener('pointermove', onMove);

    let visible = true, raf = 0;
    const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting; if (visible && !raf) loop(); }, { threshold: 0 });
    io.observe(el);
    const clock = new THREE.Clock();
    const loop = () => {
      raf = 0;
      if (!visible) return;
      const t = clock.getElapsedTime();
      if (!reduce) {
        onion.rotation.y = t * 0.28;
        onion.position.y = Math.sin(t * 0.9) * 0.06;
        onion.rotation.x += (py * 0.18 - onion.rotation.x) * 0.05;
        onion.rotation.z += (-0.12 - px * 0.1 - onion.rotation.z) * 0.05;
        flakeMesh.rotation.y = t * 0.02;
        flakeMesh.position.y = Math.sin(t * 0.3) * 0.1;
      }
      renderer.render(scene, camera);
      raf = requestAnimationFrame(loop);
    };
    loop();
    return () => {
      cancelAnimationFrame(raf); io.disconnect(); ro.disconnect(); removeEventListener('pointermove', onMove);
      renderer.dispose(); map.dispose(); el.removeChild(renderer.domElement);
    };
  }, []);
  return <div ref={host} className={className} aria-hidden="true" />;
}

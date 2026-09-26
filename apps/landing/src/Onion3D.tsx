import { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';

/**
 * Hero onion: a photogrammetry scan ("Yellow Onion", Poly Haven, CC0) with its skin
 * recoloured to red onion. PBR material lit by a soft studio environment plus a gold rim.
 * On phones the canvas is a band above the headline, so no text sits over the bulb.
 */
export function Onion3D({ className }: { className?: string }) {
  const host = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = host.current!;
    const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' });
    renderer.setPixelRatio(Math.min(devicePixelRatio, innerWidth < 768 ? 1.5 : 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.0;
    el.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const pmrem = new THREE.PMREMGenerator(renderer);
    const env = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    scene.environment = env;
    scene.environmentIntensity = 0.55;

    const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 50);
    camera.position.set(0, 0.15, 6);

    const rig = new THREE.Group(); // position + scale per breakpoint
    const spin = new THREE.Group(); // animated rotation
    rig.add(spin);
    scene.add(rig);

    const key = new THREE.DirectionalLight('#fff3e6', 2.2); key.position.set(-3, 4, 4); scene.add(key);
    const rim = new THREE.DirectionalLight('#e6ae45', 3.2); rim.position.set(3.5, 1.5, -3); scene.add(rim);
    const fill = new THREE.DirectionalLight('#c06090', 0.6); fill.position.set(2, -2, 3); scene.add(fill);

    let disposed = false;
    new GLTFLoader().load(new URL('./onion3d/onion.gltf', location.href).href, (gltf) => {
      if (disposed) return;
      const model = gltf.scene;
      // Centre and normalise to ~1.7 units.
      const box = new THREE.Box3().setFromObject(model);
      const size = box.getSize(new THREE.Vector3());
      const centre = box.getCenter(new THREE.Vector3());
      model.position.sub(centre);
      const s = 1.7 / Math.max(size.x, size.y, size.z);
      const holder = new THREE.Group();
      holder.add(model);
      holder.scale.setScalar(s);
      model.traverse((o) => {
        const m = (o as THREE.Mesh).material as THREE.MeshStandardMaterial | undefined;
        if (m && 'roughness' in m) { m.envMapIntensity = 1; if (m.map) m.map.anisotropy = 8; }
      });
      spin.add(holder);
      el.dataset.ready = '1';
    });

    // Floating dry-skin flakes.
    let seed = 3;
    const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
    const flakes = new THREE.BufferGeometry();
    const N = 120, pos = new Float32Array(N * 3);
    for (let i = 0; i < N; i++) { pos[i * 3] = (rnd() - 0.5) * 9; pos[i * 3 + 1] = (rnd() - 0.5) * 6; pos[i * 3 + 2] = (rnd() - 0.5) * 4 - 1; }
    flakes.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    const flakeMat = new THREE.PointsMaterial({ color: '#e6ae45', size: 0.022, transparent: true, opacity: 0.5 });
    const flakeMesh = new THREE.Points(flakes, flakeMat);
    scene.add(flakeMesh);

    const layout = () => {
      const w = el.clientWidth, h = el.clientHeight;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      // Visible half-width at z=0, so the bulb can be placed relative to the frame edges.
      const halfH = Math.tan((camera.fov * Math.PI) / 360) * camera.position.z;
      const halfW = halfH * camera.aspect;
      if (w < 768) {
        // Phones: the canvas is its own band above the headline; bulb centred in it.
        rig.scale.setScalar(1.35);
        rig.position.set(0, -0.1, 0);
      } else {
        rig.scale.setScalar(1.2);
        rig.position.set(Math.min(0.35, halfW * 0.1), 0.12, 0);
      }
    };
    layout();
    const ro = new ResizeObserver(layout); ro.observe(el);

    let px = 0, py = 0;
    const onMove = (e: PointerEvent) => { px = (e.clientX / innerWidth - 0.5) * 2; py = (e.clientY / innerHeight - 0.5) * 2; };
    addEventListener('pointermove', onMove, { passive: true });

    let visible = true, raf = 0;
    const clock = new THREE.Clock();
    const loop = () => {
      raf = 0;
      if (!visible) return;
      const t = clock.getElapsedTime();
      if (!reduce) {
        spin.rotation.y = t * 0.3;
        spin.position.y = Math.sin(t * 0.9) * 0.05;
        spin.rotation.x += (py * 0.15 - spin.rotation.x) * 0.05;
        spin.rotation.z += (-0.1 - px * 0.08 - spin.rotation.z) * 0.05;
        flakeMesh.rotation.y = t * 0.02;
        flakeMesh.position.y = Math.sin(t * 0.3) * 0.1;
      } else {
        spin.rotation.set(0.05, 0.6, -0.1);
      }
      renderer.render(scene, camera);
      raf = requestAnimationFrame(loop);
    };
    const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting; if (visible && !raf) loop(); }, { threshold: 0 });
    io.observe(el);
    loop();
    return () => {
      disposed = true;
      cancelAnimationFrame(raf); io.disconnect(); ro.disconnect(); removeEventListener('pointermove', onMove);
      scene.traverse((o) => {
        const m = o as THREE.Mesh;
        m.geometry?.dispose();
        const mats = Array.isArray(m.material) ? m.material : m.material ? [m.material] : [];
        mats.forEach((mat) => { Object.values(mat).forEach((v) => { if (v instanceof THREE.Texture) v.dispose(); }); mat.dispose(); });
      });
      env.dispose(); pmrem.dispose(); renderer.dispose();
      el.removeChild(renderer.domElement);
    };
  }, []);
  return <div ref={host} className={className} aria-hidden="true" />;
}

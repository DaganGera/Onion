import { motion, useInView } from 'framer-motion';
import { useMemo, useRef, type ReactNode } from 'react';
import qrcode from 'qrcode-generator';
import { Onion3D } from './Onion3D';
import { FadingImages } from './FadingImages';
import { LiveDemo } from './LiveDemo';

const REPO = 'https://github.com/DaganGera/Onion';
const APK = `${REPO}/releases/latest/download/sama.apk`;
const APP = './app/';
const EASE = [0.22, 1, 0.36, 1] as const;

/* ---------- small pieces ---------- */

function ArrowUpRight({ className = 'h-4 w-4' }: { className?: string }) {
  return <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M7 17 17 7M8 7h9v9" /></svg>;
}
function Play({ className = 'h-4 w-4' }: { className?: string }) {
  return <svg className={className} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5.5v13a1 1 0 0 0 1.5.86l10.5-6.5a1 1 0 0 0 0-1.72L9.5 4.64A1 1 0 0 0 8 5.5Z" /></svg>;
}
function Download({ className = 'h-4 w-4' }: { className?: string }) {
  return <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 4v11m0 0-4.5-4.5M12 15l4.5-4.5M5 19h14" /></svg>;
}
function Mark({ className = 'h-7 w-7' }: { className?: string }) {
  return <img src="./icon.svg" alt="" className={className} />;
}

/** Word-by-word blur-in, as in the brief (IntersectionObserver via useInView). */
function BlurText({ text, className, delay = 100 }: { text: string; className?: string; delay?: number }) {
  const ref = useRef<HTMLHeadingElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.2 });
  const words = text.split(' ');
  return (
    <h1 ref={ref} className={className} aria-label={text}>
      {words.map((w, i) => (
        <motion.span key={i} aria-hidden="true" className="inline-block"
          initial={{ filter: 'blur(10px)', opacity: 0, y: 50 }}
          animate={inView ? { filter: ['blur(10px)', 'blur(5px)', 'blur(0px)'], opacity: [0, 0.5, 1], y: [50, -5, 0] } : undefined}
          transition={{ duration: 0.7, times: [0, 0.5, 1], delay: (i * delay) / 1000, ease: 'easeOut' }}>
          {w}{i < words.length - 1 ? ' ' : ''}
        </motion.span>
      ))}
    </h1>
  );
}

function FadeUp({ children, delay = 0, className }: { children: ReactNode; delay?: number; className?: string }) {
  return (
    <motion.div className={className} initial={{ filter: 'blur(10px)', opacity: 0, y: 20 }} whileInView={{ filter: 'blur(0px)', opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.2 }} transition={{ duration: 0.6, delay, ease: 'easeOut' }}>
      {children}
    </motion.div>
  );
}

function Badge({ tag, children }: { tag: string; children: ReactNode }) {
  return (
    <div className="liquid-glass inline-flex items-center gap-2 rounded-full py-1 pl-1 pr-3 text-xs sm:text-sm">
      <span className="rounded-full bg-white px-2.5 py-0.5 text-[11px] font-semibold text-[#1a0710] sm:text-xs">{tag}</span>
      <span className="text-white/90">{children}</span>
    </div>
  );
}

function SectionHead({ badge, title, sub }: { badge: string; title: string; sub?: string }) {
  return (
    <FadeUp className="mb-12 flex flex-col items-start gap-5 md:mb-16">
      <span className="liquid-glass rounded-full px-3.5 py-1 font-body text-xs text-white">{badge}</span>
      <h2 className="max-w-3xl font-heading text-5xl italic leading-[0.9] tracking-[-2px] text-white md:text-6xl lg:text-7xl">{title}</h2>
      {sub ? <p className="max-w-xl font-body text-base font-light text-white/85 md:text-lg">{sub}</p> : null}
    </FadeUp>
  );
}

/* ---------- sections ---------- */

function Nav() {
  const links = [['How it works', '#how'], ['Try it', '#demo'], ['Who uses it', '#who'], ['Download', '#get']];
  return (
    <header className="fixed inset-x-0 top-0 z-50 bg-gradient-to-b from-[#0b0507] from-55% via-[#0b0507]/70 to-transparent px-4 pb-8 pt-4 md:px-8 lg:px-16">
      <nav className="mx-auto flex max-w-7xl items-center justify-between gap-3" aria-label="Main">
        <a href="#top" className="liquid-glass flex h-12 items-center gap-2 rounded-full pl-2 pr-4">
          <Mark className="h-8 w-8" />
          <span className="font-body text-sm font-semibold tracking-[0.28em] text-white">SAMA</span>
        </a>
        <div className="liquid-glass hidden items-center gap-1 rounded-full p-1.5 md:flex">
          {links.map(([l, h]) => <a key={h} href={h} className="rounded-full px-3 py-2 font-body text-sm font-medium text-white/90 transition-colors hover:text-white">{l}</a>)}
          <a href={APK} className="btn-hover ml-1 inline-flex items-center gap-1.5 whitespace-nowrap rounded-full bg-white px-3.5 py-1.5 text-sm font-semibold text-[#1a0710]">
            Get the app <ArrowUpRight />
          </a>
        </div>
        <a href={APK} className="btn-hover inline-flex h-12 items-center gap-1.5 rounded-full bg-white px-4 text-sm font-semibold text-[#1a0710] md:hidden">
          Get app <Download />
        </a>
      </nav>
    </header>
  );
}

function Hero() {
  const stats = [
    ['0.56', 'onions off, on average, when counting 18 real lot photos (1 to 30 onions)'],
    ['0 KB', 'of your photos sent anywhere. The models run on the phone'],
    ['9', 'Indian languages, and it works with no signal at all'],
  ];
  return (
    <section id="top" className="relative flex min-h-[100svh] flex-col overflow-hidden bg-[radial-gradient(120%_80%_at_70%_30%,#4a1430_0%,#1c0812_55%,#0b0507_100%)]">
      <Onion3D className="absolute inset-x-0 top-0 z-0 h-[44svh] md:inset-0 md:left-[38%] md:h-auto" />
      <div className="pointer-events-none absolute inset-x-0 bottom-0 z-[1] h-64 bg-gradient-to-t from-[#0b0507] to-transparent" />
      <div className="relative z-10 mx-auto flex w-full max-w-7xl flex-1 flex-col justify-center px-4 pb-10 pt-[42svh] md:px-8 md:pt-32 lg:px-16">
        <FadeUp delay={0.2}><Badge tag="SIH 2026">PS SIH26031 · Department of Consumer Affairs</Badge></FadeUp>
        <BlurText text="Every onion lot, graded the same at every centre."
          className="mt-6 max-w-3xl font-heading text-[3.4rem] italic leading-[0.85] tracking-[-2px] text-white sm:text-7xl md:text-8xl lg:text-[6.5rem] lg:tracking-[-4px]" />
        <FadeUp delay={0.8} className="mt-6 max-w-xl">
          <p className="font-body text-base font-light text-white/90 md:text-lg">
            SAMA turns a phone camera into a grading instrument for buffer-stock procurement. Photograph the lot, get a size and defect reading for every bulb, a grade from the published rule pack, and a signed receipt the farmer can check.
          </p>
        </FadeUp>
        <FadeUp delay={1.1} className="mt-8 flex flex-wrap items-center gap-3">
          <a href={APK} className="liquid-glass-strong btn-hover inline-flex items-center gap-2 rounded-full px-5 py-3 font-body text-sm font-medium text-white">
            Download the APK <Download />
          </a>
          <a href="#demo" className="btn-hover inline-flex items-center gap-2 rounded-full px-3 py-3 font-body text-sm font-medium text-white">
            <span className="liquid-glass grid h-8 w-8 place-items-center rounded-full"><Play className="h-3.5 w-3.5" /></span> Try it in your browser
          </a>
        </FadeUp>
        <div className="mt-12 grid max-w-4xl gap-3 sm:grid-cols-3 md:mt-16">
          {stats.map(([n, l], i) => (
            <FadeUp key={n} delay={1.3 + i * 0.1}>
              <div className="liquid-glass h-full rounded-[1.25rem] p-5">
                <div className="font-heading text-4xl italic leading-none tracking-[-1px] text-white md:text-5xl">{n}</div>
                <p className="mt-3 font-body text-xs font-light leading-relaxed text-white/80 md:text-sm">{l}</p>
              </div>
            </FadeUp>
          ))}
        </div>
      </div>
      <FadeUp delay={1.6} className="relative z-10 border-t border-white/10">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-8 gap-y-2 px-4 py-5 md:px-8 lg:px-16">
          <span className="font-body text-xs text-white/60">Built on open standards</span>
          {['UNECE FFV-25', 'RFC 8785', 'RFC 6962', 'ONNX', 'WebCrypto'].map((s) => (
            <span key={s} className="font-heading text-xl italic text-white/90 md:text-2xl">{s}</span>
          ))}
        </div>
      </FadeUp>
    </section>
  );
}

function Capabilities() {
  const cards = [
    {
      n: '01', title: 'The instrument',
      body: 'A learned model finds each onion in the photo, even in a heap on a sack. A printed mat, an A4 sheet or a ₹5 coin sets the scale, so every bulb gets a diameter in millimetres, and a second model checks the skin for rot, black mould and sprouting.',
      tags: ['On-device ONNX', 'mm sizing', 'Defect check'],
    },
    {
      n: '02', title: 'The rulebook',
      body: 'Grades come from a versioned rule pack: Grade A, URS or refer, with the size window and defect limits written out in plain numbers. The same photo and the same pack always give the same answer, whoever holds the phone.',
      tags: ['Deterministic', 'Hashed packs', 'Refer, not guess'],
    },
    {
      n: '03', title: 'The receipt',
      body: 'Each lot ends in a signed receipt with a QR code. The farmer, the centre and an auditor can each check it offline. Receipts chain into a tamper-evident log, so a grade cannot be changed quietly after the fact.',
      tags: ['Ed25519 signature', 'QR verify', 'Merkle log'],
    },
  ];
  const photos = useMemo(() => ['./photos/grading', './photos/sorting', './photos/trolley', './photos/market'], []);
  return (
    <section id="how" className="relative overflow-hidden py-24 md:py-32">
      <FadingImages srcs={photos} className="absolute inset-0 z-0" />
      <div className="absolute inset-0 z-[1] bg-[#0b0507]/60" />
      <div className="absolute inset-x-0 top-0 z-[1] h-40 bg-gradient-to-b from-[#0b0507] to-transparent" />
      <div className="absolute inset-x-0 bottom-0 z-[1] h-40 bg-gradient-to-t from-[#0b0507] to-transparent" />
      <div className="relative z-10 mx-auto max-w-7xl px-4 md:px-8 lg:px-16">
        <SectionHead badge="How it works" title="An instrument, a rulebook and a receipt"
          sub="Grading disputes at procurement centres come from eyeballing. SAMA replaces the eyeball with a measurement, and the argument with a rule anyone can read." />
        <div className="grid gap-4 md:grid-cols-3">
          {cards.map((c, i) => (
            <FadeUp key={c.n} delay={i * 0.1}>
              <article className="liquid-glass flex h-full min-h-[340px] flex-col rounded-[1.25rem] p-6">
                <div className="flex items-start justify-between">
                  <span className="font-heading text-5xl italic leading-none text-white/90">{c.n}</span>
                  <span className="liquid-glass grid h-10 w-10 place-items-center rounded-full"><ArrowUpRight /></span>
                </div>
                <h3 className="mt-auto pt-10 font-heading text-3xl italic leading-none tracking-[-1px] text-white md:text-4xl">{c.title}</h3>
                <p className="mt-4 font-body text-sm font-light leading-relaxed text-white/90">{c.body}</p>
                <div className="mt-5 flex flex-wrap gap-2">
                  {c.tags.map((t) => <span key={t} className="liquid-glass rounded-full px-3 py-1 font-body text-[11px] text-white/90">{t}</span>)}
                </div>
              </article>
            </FadeUp>
          ))}
        </div>
      </div>
    </section>
  );
}

function Demo() {
  return (
    <section id="demo" className="relative py-24 md:py-32">
      <div className="mx-auto max-w-7xl px-4 md:px-8 lg:px-16">
        <SectionHead badge="Live · runs on your device" title="Count the onions, right here in your browser"
          sub="This is the same detection model the app ships, running in your browser through ONNX Runtime Web. Your photo never leaves this page." />
        <FadeUp><LiveDemo /></FadeUp>
      </div>
    </section>
  );
}

function UseCases() {
  const rows = [
    ['Procurement centre', 'NAFED or NCCF buyer, Lasalgaon', 'Photographs a 40-bag lot on the mat. SAMA sizes every bulb in each tray and reports the Grade A share under the current pack. The farmer gets a signed receipt on the spot and can show it at any other centre.'],
    ['Primary trader', 'Commission agent at an APMC yard', 'Checks a farmer’s lot before the auction and knows whether it clears the 45–65 mm window, so the price talk starts from a number instead of a handful of onions.'],
    ['Secondary buyer', 'Wholesaler or cold-store operator', 'Scans the receipt QR on arrival. The signature and log entry confirm the grade was not edited after purchase. A spot re-scan flags lots that have rotted in transit.'],
    ['Consumer side', 'Fair-price shop or retail audit', 'A shopkeeper or inspector checks that subsidised stock sold as Grade A still matches the receipt, using the same app and the same rule pack.'],
  ];
  return (
    <section id="who" className="relative py-24 md:py-32">
      <div className="mx-auto max-w-7xl px-4 md:px-8 lg:px-16">
        <SectionHead badge="Who uses it" title="One grade, from the farm gate to the shop shelf" />
        <div className="divide-y divide-white/10 border-y border-white/10">
          {rows.map(([who, eg, what], i) => (
            <FadeUp key={who} delay={i * 0.05}>
              <div className="grid gap-3 py-8 md:grid-cols-[1fr_2fr] md:gap-10">
                <div>
                  <h3 className="font-heading text-3xl italic leading-none text-white md:text-4xl">{who}</h3>
                  <p className="mt-2 font-body text-sm text-[var(--color-gold)]">{eg}</p>
                </div>
                <p className="font-body text-base font-light leading-relaxed text-white/85">{what}</p>
              </div>
            </FadeUp>
          ))}
        </div>
      </div>
    </section>
  );
}

function Get() {
  const qr = useMemo(() => {
    const q = qrcode(0, 'M');
    q.addData(APK);
    q.make();
    return q.createSvgTag({ cellSize: 4, margin: 0, scalable: true });
  }, []);
  const steps = ['Download sama.apk (about 42 MB) on the Android phone.', 'Open it and allow installing from this source when Android asks.', 'Open SAMA, pick your language and centre, and allow the camera.'];
  return (
    <section id="get" className="relative overflow-hidden bg-[radial-gradient(70%_60%_at_85%_100%,#4a1430_0%,transparent_70%)] py-24 md:py-32">
      <div className="mx-auto max-w-7xl px-4 md:px-8 lg:px-16">
        <SectionHead badge="Get SAMA" title="Install it, or open it in the browser" />
        <div className="grid gap-4 lg:grid-cols-[1.3fr_1fr]">
          <FadeUp>
            <div className="liquid-glass flex h-full flex-col gap-8 rounded-[1.25rem] p-6 sm:flex-row sm:items-center md:p-8">
              <div className="hidden w-40 shrink-0 rounded-2xl bg-[var(--color-paper)] sm:block p-3 [&_svg]:h-auto [&_svg]:w-full" aria-label="QR code linking to the APK download" role="img" dangerouslySetInnerHTML={{ __html: qr }} />
              <div className="flex flex-col gap-5">
                <h3 className="font-heading text-4xl italic leading-none text-white">Android app</h3>
                <ol className="flex flex-col gap-2 font-body text-sm font-light text-white/85">
                  {steps.map((s, i) => <li key={i} className="flex gap-3"><span className="font-heading text-lg italic leading-5 text-[var(--color-gold)]">{i + 1}</span>{s}</li>)}
                </ol>
                <a href={APK} className="btn-hover inline-flex w-fit items-center gap-2 rounded-full bg-white px-5 py-3 font-body text-sm font-semibold text-[#1a0710]">
                  Download the APK <Download />
                </a>
              </div>
            </div>
          </FadeUp>
          <FadeUp delay={0.1}>
            <div className="liquid-glass flex h-full flex-col justify-between gap-6 rounded-[1.25rem] p-6 md:p-8">
              <div>
                <h3 className="font-heading text-4xl italic leading-none text-white">Web app</h3>
                <p className="mt-4 font-body text-sm font-light leading-relaxed text-white/85">
                  The full app in any modern browser, phone or laptop. Add it to the home screen and it keeps working offline after the first load.
                </p>
              </div>
              <a href={APP} className="liquid-glass-strong btn-hover inline-flex w-fit items-center gap-2 rounded-full px-5 py-3 font-body text-sm font-medium text-white">
                Open the web app <ArrowUpRight />
              </a>
            </div>
          </FadeUp>
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="border-t border-white/10">
      <div className="mx-auto flex max-w-7xl flex-col gap-6 px-4 py-10 font-body text-xs font-light text-white/60 md:flex-row md:items-start md:justify-between md:px-8 lg:px-16">
        <div className="flex items-center gap-3">
          <Mark className="h-9 w-9" />
          <div>
            <div className="text-sm font-semibold tracking-[0.28em] text-white">SAMA</div>
            <div>सम · the same grade at every centre</div>
          </div>
        </div>
        <p className="max-w-xl leading-relaxed">
          A Smart India Hackathon 2026 prototype by team AlgoRangersV1, not an official Government of India service. Grades follow the rule packs published in the repository. Demo photos: Zenodo 10.5281/zenodo.20254934, CC BY 4.0. Background photos from Wikimedia Commons: Nishaexport (CC BY-SA 3.0), John Hoey (CC BY 2.0), Ravi Dwivedi (CC BY-SA 4.0), McKay Savage (CC BY 2.0). 3D onion: Kuutti Siitonen, Poly Haven (CC0), recoloured.
        </p>
        <a href={REPO} className="inline-flex items-center gap-1 text-white/85 hover:text-white">Source on GitHub <ArrowUpRight className="h-3.5 w-3.5" /></a>
      </div>
    </footer>
  );
}

export function App() {
  return (
    <motion.main initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.4, ease: EASE }}>
      <Nav />
      <Hero />
      <Capabilities />
      <Demo />
      <UseCases />
      <Get />
      <Footer />
    </motion.main>
  );
}

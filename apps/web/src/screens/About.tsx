import { t } from '../lib/i18n';
import { TopBar } from '../components/ui';

/** Plain-language account of what the app does and does not do. Mirrors docs/LIMITATIONS.md. */
export function About() {
  return (
    <>
      <TopBar title={t('ab.title', 'How it works & limits')} />
      <main class="page">
        <section class="section">
          <h2>{t('ab.h1', 'Three parts')}</h2>
          <p><b>{t('ab.i', 'The instrument.')}</b> {t('ab.i.p', 'The phone measures each visible onion: size in millimetres against a calibration sheet, and the share of its visible surface with blackening, rot, sunburn, spots, sprouting or peeled skin. Every number carries an uncertainty.')}</p>
          <p><b>{t('ab.r', 'The rulebook.')}</b> {t('ab.r.p', 'A rule pack turns measurements into Grade A, URS, Reject or “needs human check”. Anything within measuring error of a limit goes to a person, not to a coin flip. Packs are versioned and hashed, so a lot can be re-graded under any norm.')}</p>
          <p><b>{t('ab.c', 'The receipt.')}</b> {t('ab.c.p', 'The result is signed on the phone. Its QR code lets anyone check it on another phone, offline, by re-running the same grading on the same measurements.')}</p>
        </section>
        <section class="section">
          <h2>{t('ab.h2', 'Honest limits')}</h2>
          <ul class="small" style={{ margin: 0, paddingLeft: '1.2em', display: 'grid', gap: 8 }}>
            <li>{t('ab.l1', 'Only the visible surface is measured. Shake the tray and look again; hidden faces stay hidden.')}</li>
            <li>{t('ab.l2', 'The colour model has not yet been checked against graders on field photos. Accuracy numbers will appear only after that study.')}</li>
            <li>{t('ab.l3', 'White onions on a white sheet, piled onions, and patterned backgrounds are measured badly. Use the printed mat or a plain dark cloth and a single layer.')}</li>
            <li>{t('ab.l4', 'The dry root plate and neck can be mistaken for sunburn. Cuts are not measured by this version.')}</li>
            <li>{t('ab.l5', 'Weights are estimated from size with an assumed density until a kitchen-scale fit is loaded.')}</li>
            <li>{t('ab.l6', 'The receipt is tamper-evident, not tamper-proof. It cannot prove the photographed onions came from the sacks sold.')}</li>
            <li>{t('ab.l7', 'All procurement limits come from press reports; no official circular was found. The meaning of “URS” is unconfirmed.')}</li>
          </ul>
        </section>
        <p class="note">{t('ab.src', 'Demo photos: Zenodo 10.5281/zenodo.20254934, CC-BY 4.0. Code: open source. Built for Smart India Hackathon 2026, problem statement 26031.')}</p>
      </main>
    </>
  );
}

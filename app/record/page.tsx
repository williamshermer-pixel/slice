/**
 * THE RECORD — measured results, including the withdrawn ones.
 *
 * PLATE & LEDGER, third register: the CORRECTION. A conservation ledger does
 * not erase a wrong entry, it strikes it and records why. Every retracted
 * result on this page is struck rather than deleted, because in ink detection
 * the retraction is the useful part — anyone repeating our method needs to
 * know which of our own findings did not survive its own control.
 */

export const metadata = {
  title: "The Record — Slice",
  description:
    "Measured ink-detection results on the Herculaneum scrolls, including two withdrawn findings and the controls that killed them.",
};

function Row({
  label,
  children,
  struck = false,
}: {
  label: string;
  children: React.ReactNode;
  struck?: boolean;
}) {
  return (
    <div className="ledger-row">
      <span
        className={`ledger-label ${
          struck
            ? "line-through decoration-papyrus/70 decoration-1"
            : ""
        }`}
      >
        {label}
      </span>
      {/* Only the CLAIM is struck. The cause of death is the correction —
          the living part of the entry — and stays legible. */}
      <span className={`ledger-value text-[13px] ${struck ? "text-ash" : ""}`}>
        {children}
      </span>
    </div>
  );
}

function Section({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mt-12 border-t border-rule pt-5">
      <p className="eyebrow mb-1">{eyebrow}</p>
      <h2 className="font-display text-[1.7rem] leading-tight tracking-tight text-papyrus">
        {title}
      </h2>
      <div className="mt-3 max-w-[74ch] space-y-3 text-[13px] leading-relaxed text-papyrus">
        {children}
      </div>
    </section>
  );
}

export default function RecordPage() {
  return (
    <main className="mx-auto max-w-[1240px] px-6 py-7">
      <header className="mb-7 flex items-end justify-between gap-6 border-b border-rule pb-4">
        <div>
          <p className="eyebrow mb-1">Herculaneum · ink detection</p>
          <h1 className="font-display text-[2.6rem] leading-none tracking-tight text-papyrus">
            The Record
          </h1>
          <p className="caption mt-1 text-[13px]">
            What was measured, what it means, and the two findings we withdrew.
          </p>
        </div>
        <nav className="flex gap-2">
          <a href="/" className="btn">
            Viewer
          </a>
          <a
            href="https://github.com/williamshermer-pixel/slice"
            className="btn"
            rel="noreferrer"
          >
            Source
          </a>
        </nav>
      </header>

      {/* ---- the reveal -------------------------------------------------
          The one animated element on the site, and it is the specimen
          itself: an instrument trace sweeps the band and the ink the tuned
          model reads surfaces out of the sheet. Real data, both frames. */}
      <figure className="mb-10">
        <div className="plate relative overflow-hidden">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/reveal-sheet.png"
            alt="A band of carbonized papyrus from PHerc0139, micro-CT, depth-averaged."
            className="block h-[200px] w-full object-cover md:h-[240px]"
          />
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/reveal-ink.png"
            alt="The same band as the tuned model reads it: ink probability."
            className="reveal-ink absolute inset-0 h-full w-full object-cover"
            aria-hidden
          />
          <span className="reveal-trace" aria-hidden />
          <span className="eyebrow absolute left-2.5 top-2 z-[1] text-papyrus/80">
            the sheet
          </span>
          <span className="eyebrow absolute right-2.5 top-2 z-[1] text-ochre">
            the ink
          </span>
        </div>
        <figcaption className="caption mt-2 text-[12.5px] leading-relaxed">
          A 9 × 3.5 mm band of Philodemus, <em>On Gods</em> — unread for two
          thousand years — seen twice: the carbonized sheet, and the ink the
          tuned model reads on it. Both frames are real output of the tools in
          this repository; nothing is illustrated.
        </figcaption>
      </figure>

      {/* ---- the assay -------------------------------------------------
          One thesis figure, oversized: the depth-band fix is the result the
          rest of the page hangs from. Everything else is a quiet ledger. */}
      <div className="grid gap-8 md:grid-cols-[1.2fr_1fr]">
        <div className="border-t border-rule pt-3">
          <p className="eyebrow mb-2">The one-line result</p>
          <p className="font-display leading-none tracking-tight text-papyrus">
            <span className="text-[3.4rem] text-ash line-through decoration-1 decoration-ash/70">
              0.654
            </span>
            <span className="mx-3 text-[2rem] text-ash">→</span>
            <span className="text-[4.6rem] text-ochre">0.944</span>
          </p>
          <p className="caption mt-2 max-w-[46ch] text-[13px] leading-relaxed">
            Agreement with known Scroll 1 letters, before and after one change:
            reading depth layers 27–89 instead of the middle of the sheet. The
            model was never the problem. The depth was.
          </p>
        </div>
        <div className="ledger self-end">
          <Row label="detector vs same-condition blank">
            <span className="whitespace-nowrap">AUC 0.961</span>
          </Row>
          <Row label="lost book · windows / survivors">
            <span className="whitespace-nowrap">78 / 0</span>
          </Row>
          <Row label="mechanisms tested, deaths understood">18</Row>
          <Row label="withdrawn by our own controls">2</Row>
        </div>
      </div>

      {/* ---- the finding that transfers -------------------------------- */}
      <Section eyebrow="Finding · reusable" title="The ink is not in the middle of the sheet">
        <p>
          Our maps of Scroll 1 were blobs for a full day. The cause was not the
          model, the oversampling, or the scale prior — it was reading{" "}
          <strong className="text-papyrus">the wrong 62 layers</strong>. We took
          them from the centre of the 116-layer surface stack. The ink sits off
          centre, at roughly layers{" "}
          <span className="text-ochre">27 through 89</span>. Reading that band
          instead, with no other change, moved agreement with the published map
          from AUC 0.654 to <span className="text-ochre">0.944</span> and turned
          blobs into letterforms.
        </p>
        <p className="text-ash">
          Depth dominated; model choice was second and blending third. If you are
          getting mush from a working ink model, sweep the depth band before
          anything else — and sweep it{" "}
          <em className="font-display">per scroll</em>, since the band is a
          property of how the segment was flattened.
        </p>
      </Section>

      {/* ---- the plate ------------------------------------------------- */}
      <Section
        eyebrow="Plate I · PHerc0139, Philodemus On Gods (unread)"
        title="A calibrated search, and an honest silence"
      >
        <p>
          Five GPUs mapped every segment of an unread book with a model
          fine-tuned on that scribe&apos;s own hand, hunting ink the published
          maps never called. One candidate appeared, in the title segment. It
          died to its own control. The value is that the silence is{" "}
          <em className="font-display">calibrated</em>: we measured what the
          instrument would have seen.
        </p>
      </Section>

      <figure className="mt-4">
        <div className="plate">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/evidence-hunt.png"
            alt="Four panels: the papyrus, the published ink calls, our tuned map, and the detector's hits on known letters; below, the score separation between known letters and blank sheet of the same condition."
            className="block w-full"
          />
        </div>
        <figcaption className="caption mt-2 text-[12.5px] leading-relaxed">
          A1 the papyrus, depth-averaged. A2 the published calls, binarized at
          publication. A3 our tuned map of the same patch. A4 the detector on his
          known letters — 16 of 17 found. Below: letter-scale score at known
          letters (ochre) against blank sheet of the same condition beside them
          (grey). Note A2 and A3 honestly — at this scribe&apos;s 1.09 mm hand
          neither map resolves a letterform, only letter-sized mass.
        </figcaption>
      </figure>

      <div className="mt-6 grid gap-x-10 gap-y-1 md:grid-cols-2">
        <div className="ledger">
          <Row label="our maps vs his published calls">AUC 0.919–0.928</Row>
          <Row label="letter-scale detector, uncontrolled">AUC 0.981</Row>
          <Row label="same-condition control">AUC 0.961</Row>
          <Row label="letters vs blank sheet beside them">3.8×</Row>
        </div>
        <div className="ledger">
          <Row label="per-letter detection">77.7%</Row>
          <Row label="power at five hidden letters">99%</Row>
          <Row label="windows searched">78</Row>
          <Row label="candidates surviving the null">0</Row>
        </div>
      </div>

      {/* ---- the corrections ------------------------------------------ */}
      <Section eyebrow="Corrections · struck, not erased" title="Two of our own findings did not survive">
        <p>
          Both were killed by a{" "}
          <strong className="text-papyrus">spatial null</strong>: roll our own
          map so its histogram and autocorrelation are unchanged but its
          registration to the papyrus is destroyed, then re-run the search. If
          the rolled copies score the same, the finding was a property of the
          statistics, not the sheet.
        </p>
        <div className="ledger mt-4">
          <Row label="differential, 9 of 22 segments (Jul 29)" struck>
            23 of 24 rolls reproduced it — p up to 0.92
          </Row>
          <Row label="&quot;the Zone&quot;, w028 margin cluster" struck>
            artifact of the wrong depth band
          </Row>
          <Row label="two whisper candidates (Jul 29 04:00)" struck>
            scored with Scroll 1&apos;s ruler on a scribe writing ⅓ the size
          </Row>
        </div>
        <p className="mt-4 text-ash">
          The cause of the first was a{" "}
          <em className="font-display">relative</em> threshold. &quot;The top 4%
          of our map&quot; selects 4% of the pixels whether or not any ink is
          present, so in a blank margin it returns the noisiest 4% and those
          cluster into letter-sized shapes by chance. The replacement uses an
          absolute floor calibrated on that scribe&apos;s known ink, and every
          survivor must clear a spatial null before it is reported.
        </p>
      </Section>

      {/* ---- the confound --------------------------------------------- */}
      <Section eyebrow="Control · the standing failure mode" title="Nearly everything that works is measuring preservation">
        <p>
          Text sits on well-preserved sheet. So &quot;this papyrus looks
          good&quot; correlates with &quot;there is writing here&quot; without
          any of it being about ink, and every strong result this project
          produced for weeks was that confound in a new costume — one candidate
          scored r = +0.444 on held-out data and 0.209 on blank papyrus.
        </p>
        <p>
          The control that settles it is to draw the null from blank sheet{" "}
          <em className="font-display">inside the text block</em> — same sheet,
          same damage exposure, same distance from the good fibres — instead of
          from distant margins. Our letter-scale detector holds up under it
          (0.961 against 0.964), which is the first clean separation of ink from
          condition in this work.
        </p>
      </Section>

      {/* ---- hands ---------------------------------------------------- */}
      <Section eyebrow="Method · per-scribe calibration" title="The library had more than one scribe, and the ruler is not shared">
        <p>
          Letter-size and line-pitch gates must be measured per scroll. Applying
          one scroll&apos;s hand to another manufactures candidates: at
          PHerc0139&apos;s true scale, our earlier &quot;letters&quot; were
          2–4 letters tall, which is a damage patch, not writing.
        </p>
        <div className="ledger mt-4">
          <Row label="Scroll 1 · letter height">3.00 mm</Row>
          <Row label="Scroll 1 · line pitch">6.18 mm</Row>
          <Row label="PHerc0139 · letter height (measured, 180 components)">
            1.09 mm
          </Row>
          <Row label="PHerc0139 · line pitch">4.57 mm</Row>
        </div>
        <p className="mt-4 text-ash">
          A third the size — and below what a model emitting predictions on a
          0.29 mm grid can resolve into shapes. That is why this book returns
          letter-sized mass rather than letterforms, and it is a resolution
          ceiling rather than a rendering failure.
        </p>
      </Section>

      {/* ---- what cannot be fixed ------------------------------------- */}
      <Section eyebrow="Physics · check this before trusting any scroll" title="Some scans never sampled the ink">
        <p>
          The ink layer is about 15 µm. A feature needs roughly three voxels to
          be resolved at all. Divide and check before a scroll enters any split:
        </p>
        <div className="ledger mt-4">
          <Row label="PHerc0172 · 7.91 µm/voxel · 53 segments">
            1.9 voxels — blind
          </Row>
          <Row label="PHerc1447 · 8.64 µm/voxel">1.7 voxels — blind</Row>
          <Row label="PHerc0139 / 0814 / 1667 / Paris 4 · 2.258 µm">
            6.6 voxels
          </Row>
          <Row label="native surface volumes, 17 segments · 1.129 µm">
            13.3 voxels
          </Row>
        </div>
        <p className="mt-4 text-ash">
          On the blind scrolls the ink is not faint — it was never recorded, so
          no method recovers it from this data. PHerc0172 therefore makes an
          unusually strong negative control: anything that correlates there is
          not measuring ink.
        </p>
      </Section>

      {/* ---- the deliverable ------------------------------------------ */}
      <Section
        eyebrow="Deliverable · villa #192 / #193"
        title="3D ink labels with the quality measured in, not assumed"
      >
        <p>
          Issue #192 asks for ink labels representing{" "}
          <em className="font-display">only the detectable ink patterns</em>,
          in true 3D — its stated fear being models that learn the{" "}
          <em className="font-display">surface</em> rather than the ink. The
          campaign above is exactly the machinery that concern requires, so its
          output now ships as the labels themselves: plain zarr v2, one window
          per directory, on the surface volume&apos;s own grid.
        </p>
        <div className="ledger mt-4">
          <Row label="label / codes">0 unlabelled · 1 ink · 2 certified blank</Row>
          <Row label="ink floor">calibrated at 0.2% FPR on known-blank sheet</Row>
          <Row label="surface-confound control">
            AUC 0.96–0.99 curated · 0.84 auto-grown (in every .zattrs)
          </Row>
          <Row label="depth">measured band z27..z89 — never full-stack projection</Row>
          <Row label="negatives">≥1.5 mm from any call, outside model spillover</Row>
          <Row label="format">zarr v2 / zlib · conf/ carries raw probability</Row>
        </div>
        <p className="mt-4 text-ash">
          Generator and pair-fetcher are in the repo
          (<span className="text-ochre">tools/make_labels_3d.py</span>,{" "}
          <span className="text-ochre">tools/fetch_pair.py</span>); sample
          windows in <span className="text-ochre">samples/labels3d/</span>.
          Scroll data is never redistributed — the image half of each pair is
          fetched from the public bucket on your machine. Windows on request:
          generation costs about one GPU-minute each.
        </p>
      </Section>

      {/* ---- reproduce ------------------------------------------------ */}
      <Section eyebrow="Reproduce" title="Everything here is scripted">
        <p className="text-ash">
          MIT licensed. The tools stream the public bucket directly; the search
          runs on a laptop, the mapping wants one GPU-hour.
        </p>
        <pre className="mt-3 overflow-x-auto border border-rule bg-panel p-3 text-[12px] leading-relaxed text-ash">
{`tools/pod_final.py              production renderer (z27..z89, TTA, Hann)
tools/calibrate_floor.py        absolute floor on a scribe's known ink
tools/letterscale_0139.py       letter-scale detector + statistical power
tools/condition_control_0139.py ink vs preservation — the control
tools/hunt_0139.py              the search + mandatory spatial null
tools/test_differential.py      gate calibration harness (7 checks)`}
        </pre>
        <p className="mt-3">
          Written up in{" "}
          <span className="text-ochre">findings/CALIBRATED_HUNT.md</span>, with
          the standing rules in <span className="text-ochre">CRITERIA.md</span>:
          never tune and test on the same data; every correlation gets a spatial
          null; the blank-papyrus control goes inside the objective, not after
          it; publishing a negative is a result.
        </p>
      </Section>

      <footer className="mt-14 border-t border-rule pt-4">
        <p className="caption text-[12px]">
          Scroll data © Vesuvius Challenge, CC BY-NC 4.0. This tool redistributes
          none of it — every read is a direct, anonymous request to the public
          bucket from your browser.
        </p>
      </footer>
    </main>
  );
}

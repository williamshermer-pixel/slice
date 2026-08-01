import Link from "next/link";

/**
 * The front door.
 *
 * This used to be the CT viewer, which meant the submission link landed a
 * reader on a raw cross-section of an unread scroll — a grey blob in which
 * letters cannot appear at all, by geometry. The work is the labels and the
 * audit; the viewer is where you go to check them.
 */

function Stat({ n, children }: { n: string; children: React.ReactNode }) {
  return (
    <div className="border-t border-rule pt-2">
      <p className="font-display text-[1.9rem] leading-none text-papyrus">{n}</p>
      <p className="caption mt-1 text-[12px]">{children}</p>
    </div>
  );
}

export default function Home() {
  return (
    <main className="mx-auto max-w-[1240px] px-6 py-10">
      <header className="max-w-[70ch]">
        <p className="eyebrow mb-2">PHerc0139 · Herculaneum · ink detection</p>
        <h1 className="font-display text-[3.2rem] leading-[1.05] tracking-tight text-papyrus">
          Ink labels, and a second scan that checks them
        </h1>
        <p className="mt-4 text-[14px] leading-relaxed text-papyrus">
          Ready-to-run 3D ink label pairs for training, with depth recovered per
          pixel rather than projected across layers. This scroll was scanned at
          two X-ray energies and an ink map was published from each, so every
          label can be asked a question one map cannot answer: does the other
          scan agree?
        </p>
        <p className="mt-3 text-[13px] leading-relaxed text-ash">
          We ran that check against our own 28 pairs before anything else. It
          flagged five, including one we had shipped as certified blank that
          both maps call ink over 86.5% of.
        </p>
      </header>

      <div className="mt-8 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
        <Stat n="28">
          image/label pairs, plain zarr, nothing to preprocess
        </Stat>
        <Stat n="5">
          of our own pairs flagged by the cross-scan audit
        </Stat>
        <Stat n="58.9%">
          median agreement between the two published maps
        </Stat>
        <Stat n="37">
          segments with a disagreement map you can browse
        </Stat>
      </div>

      <div className="mt-10 grid gap-4 lg:grid-cols-3">
        <Link
          href="/qc"
          className="block border border-rule bg-panel p-5 hover:border-ochre"
        >
          <p className="eyebrow mb-1">Start here</p>
          <p className="font-display text-[1.5rem] leading-tight text-papyrus">
            Where the scans disagree
          </p>
          <p className="caption mt-2 text-[12px]">
            All 37 segments. Click any disagreement to open that exact spot on
            the papyrus, or work down the ranked queue of the largest ones.
          </p>
        </Link>

        <Link
          href="/record"
          className="block border border-rule bg-panel p-5 hover:border-ochre"
        >
          <p className="eyebrow mb-1">The findings</p>
          <p className="font-display text-[1.5rem] leading-tight text-papyrus">
            The record
          </p>
          <p className="caption mt-2 text-[12px]">
            What was measured, the calibration results, both negative searches,
            and the catalog of bugs we found in our own instrument.
          </p>
        </Link>

        <Link
          href="/viewer"
          className="block border border-rule bg-panel p-5 hover:border-ochre"
        >
          <p className="eyebrow mb-1">Look at the data</p>
          <p className="font-display text-[1.5rem] leading-tight text-papyrus">
            CT viewer
          </p>
          <p className="caption mt-2 text-[12px]">
            Micro-CT streamed from the public bucket, nothing downloaded. On
            PHerc0139 sheets the labels can be overlaid on the papyrus.
          </p>
        </Link>
      </div>

      <p className="mt-10 max-w-[74ch] border-t border-rule pt-4 text-[12px] leading-relaxed text-ash">
        Two bounds travel with every number here. The two ink recipes are
        plausibly entangled through training data, so agreement may partly be
        shared model lineage rather than shared ink; and 1.1 µm data is cleaner
        than 2.4 µm by the project&apos;s own measurement, so some disagreement
        is resolution rather than error. This is cross-energy and cross-recipe,
        not independent. Code MIT ·{" "}
        <a
          className="text-ochre underline"
          href="https://github.com/williamshermer-pixel/slice"
        >
          repository
        </a>{" "}
        · scroll data CC BY-NC 4.0, © Vesuvius Challenge.
      </p>
    </main>
  );
}

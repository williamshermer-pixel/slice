import DepthSheet from "@/components/DepthSheet";
import SignOut from "@/components/SignOut";

export const metadata = { title: "The Lab — Slice" };

export default function LabPage() {
  return (
    <main className="mx-auto max-w-[1240px] px-6 py-7">
      <header className="mb-6 flex items-end justify-between gap-6 border-b border-rule pb-4">
        <div>
          <p className="eyebrow mb-1">Restricted</p>
          <h1 className="font-display text-[2.6rem] leading-none tracking-tight text-papyrus">
            The Lab
          </h1>
          <p className="caption mt-1 text-[13px]">
            Depth contact sheet. Every layer of a tile at once, because the chunk
            already contains them all.
          </p>
        </div>
        <nav className="flex gap-2">
          <a href="/" className="btn">
            Viewer
          </a>
          <SignOut />
        </nav>
      </header>

      <section className="mb-7 border border-rule bg-panel px-4 py-3">
        <p className="eyebrow mb-1.5">Where the letters are</p>
        <p className="caption text-[13px] leading-relaxed">
          Raw scroll volumes cut perpendicular through the windings, so every sheet is
          edge-on and no amount of contrast recovers a letter — the geometry is wrong,
          not the settings. Letters only exist on a <em>flattened</em> sheet. Of the
          fourteen scrolls in the bucket, only Scroll 1 has surface volumes; the
          thirteen unread ones carry <span className="font-mono text-ash">mesh/</span>{" "}
          segments and nothing flattened. That gap is why they are still unread.
        </p>
      </section>

      <DepthSheet />
    </main>
  );
}

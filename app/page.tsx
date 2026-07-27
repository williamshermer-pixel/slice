import { Suspense } from "react";
import SliceViewer from "@/components/SliceViewer";

export default function Page() {
  return (
    <main>
      <Suspense
        fallback={
          <div className="mx-auto max-w-6xl px-5 py-8 font-mono text-xs text-ash">
            Loading viewer…
          </div>
        }
      >
        <SliceViewer />
      </Suspense>
    </main>
  );
}

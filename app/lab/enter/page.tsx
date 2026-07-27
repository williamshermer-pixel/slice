"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

function Gate() {
  const router = useRouter();
  const params = useSearchParams();
  const unset = params.get("reason") === "unset";
  const next = params.get("next") ?? "/lab";

  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/lab", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      if (res.ok) {
        router.replace(next);
        router.refresh();
        return;
      }
      const body = (await res.json()) as { error?: string };
      setError(body.error ?? "Could not sign in.");
    } catch {
      setError("Could not reach the server.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6">
      <p className="eyebrow mb-2">Restricted</p>
      <h1 className="font-display text-[2.4rem] leading-none text-papyrus">The Lab</h1>
      <p className="caption mt-2 text-[13px]">
        The bench behind the viewer. The viewer itself is open to anyone — this is
        the part with the sharp tools.
      </p>

      {unset ? (
        <div className="mt-7 border border-ochre/40 bg-ochre/5 px-3 py-3 font-mono text-[11px] leading-relaxed text-ochre">
          <p className="mb-1.5 font-semibold">LAB_PASSWORD is not set.</p>
          <p className="text-ash">
            The lab fails closed, so it is unreachable until a passphrase exists. Set
            one in <span className="text-papyrus">.env.local</span> locally, or in the
            deployment&apos;s environment variables, then reload.
          </p>
        </div>
      ) : (
        <form onSubmit={submit} className="mt-7">
          <label className="eyebrow mb-1.5 block" htmlFor="pw">
            Passphrase
          </label>
          <input
            id="pw"
            type="password"
            autoFocus
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full border border-rule bg-panel px-3 py-2 font-mono text-sm text-papyrus outline-none focus:border-ochre"
          />
          <button type="submit" disabled={busy || !password} className="btn mt-3 w-full">
            {busy ? "Checking…" : "Enter"}
          </button>
          {error && <p className="mt-2 font-mono text-[11px] text-ochre">{error}</p>}
        </form>
      )}

      <a href="/" className="caption mt-8 text-[13px] underline decoration-rule underline-offset-4">
        Back to the viewer
      </a>
    </div>
  );
}

export default function Page() {
  return (
    <Suspense fallback={null}>
      <Gate />
    </Suspense>
  );
}

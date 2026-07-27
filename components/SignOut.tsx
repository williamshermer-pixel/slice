"use client";

import { useRouter } from "next/navigation";

export default function SignOut() {
  const router = useRouter();
  return (
    <button
      className="btn"
      onClick={async () => {
        await fetch("/api/lab", { method: "DELETE" });
        router.replace("/lab/enter");
        router.refresh();
      }}
    >
      Leave
    </button>
  );
}

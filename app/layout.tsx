import type { Metadata } from "next";
import { Instrument_Serif, JetBrains_Mono } from "next/font/google";
import "./globals.css";

/**
 * Two faces, no sans. The chrome here is a readout, not an app, so the mono
 * carries the interface and the serif is reserved for the plate — titles,
 * specimen designations and the big telemetry numerals. Instrument Serif has
 * the high-contrast look of an engraved atlas caption, which is the register
 * this whole thing is written in.
 */
const instrumentSerif = Instrument_Serif({
  subsets: ["latin"],
  weight: "400",
  style: ["normal", "italic"],
  variable: "--font-instrument-serif",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Slice — Herculaneum ink labels, audited",
  description:
    "3D ink label pairs for PHerc0139 with a cross-scan audit: where two scans at different X-ray energies disagree about ink. Plus a browser-native micro-CT viewer.",
};

/**
 * Every surface reachable from every page. Without this the site was a CT
 * viewer with the actual work — the record and the cross-scan QC overlay —
 * sitting at URLs nobody could discover from the front door.
 */
const NAV = [
  { href: "/qc", label: "Where the scans disagree" },
  { href: "/record", label: "The record" },
  { href: "/", label: "CT viewer" },
  { href: "/lab", label: "Depth lab" },
];

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${instrumentSerif.variable} ${jetbrainsMono.variable}`}>
      <body className="bg-void text-papyrus antialiased">
        <nav className="border-b border-rule bg-panel/60">
          <div className="mx-auto flex max-w-[1240px] flex-wrap items-baseline gap-x-5 gap-y-1 px-6 py-2">
            <a
              href="/qc"
              className="font-display text-[15px] tracking-tight text-papyrus"
            >
              Slice
            </a>
            {NAV.map((n) => (
              <a
                key={n.href}
                href={n.href}
                className="font-mono text-[11px] uppercase tracking-wider text-ash hover:text-ochre"
              >
                {n.label}
              </a>
            ))}
            <a
              href="https://github.com/williamshermer-pixel/slice"
              className="ml-auto font-mono text-[11px] uppercase tracking-wider text-ash hover:text-ochre"
            >
              repo ↗
            </a>
          </div>
        </nav>
        {children}
      </body>
    </html>
  );
}

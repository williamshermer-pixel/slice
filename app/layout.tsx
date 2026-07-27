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
  title: "Slice — Herculaneum scroll viewer",
  description:
    "Browser-native viewer for Herculaneum scroll micro-CT volumes. Streams OME-Zarr chunks directly from the Vesuvius Challenge public bucket.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${instrumentSerif.variable} ${jetbrainsMono.variable}`}>
      <body className="bg-void text-papyrus antialiased">{children}</body>
    </html>
  );
}

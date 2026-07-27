# Citation and data attribution

This project reads data published by the Vesuvius Challenge. It redistributes
none of it — the browser fetches chunks directly from the public bucket — but
the data is the substance of the work and is cited here in the form the
publishers ask for.

## The scan data

> Giorgio Angelotti, Stephen Parsons, Sean Johnson, Elian Rafael Dal Prà,
> Johannes Rudolph, Paul Tafforeau, Alessandro Mirone, Paul Henderson, Hendrik
> Schilling, Forrest McDonald, David Josey, Youssef Nader, C. Seth Parker,
> W. Brent Seales. *Vesuvius Challenge - CT Scans of Herculaneum Papyri*.
> Vesuvius Challenge.

## EduceLab-Scrolls

Scrolls 1–4 and Fragments 1–6 scanned at Diamond Light Source before 2025
belong to the legacy **EduceLab-Scrolls** dataset. This project reads Scroll 1
(`PHercParis4`) — its surface volumes, segment meshes and published ink
detection — so the EduceLab-Scrolls attribution applies:

- The source of the data is cited as `EduceLab-Scrolls`.
- Reference:

> Parsons, S., Parker, C. S., Chapman, C., Hayashida, M., & Seales, W. B.
> (2023). *EduceLab-Scrolls: Verifiable Recovery of Text from Herculaneum
> Papyri using X-ray CT*. ArXiv [Cs.CV].
> https://doi.org/10.48550/arXiv.2304.02084

- Methods language, where applicable: "Data used in the preparation of this
  article were obtained from the EduceLab-Scrolls dataset [above citation]."

Scrolls 1–4 and Fragments 1–6 scanned at DLS before 2025 are copyright
EduceLab / The University of Kentucky. Permission to use them under the terms
above is granted to Vesuvius Challenge.

## Licences

| | |
| --- | --- |
| **This code** | MIT (see `LICENSE`) |
| **Scroll data** | CC BY-NC 4.0 unless otherwise noted for specific assets |

CC BY-NC 4.0 is **non-commercial**. This viewer is free and open source, and
carries no advertising, payment or commercial use of the data, which keeps it
inside those terms. Anyone forking it should keep that in mind before putting
it behind a paywall.

## What this project does and does not redistribute

- **Does not** copy, mirror, cache server-side, or re-host any scan data. Reads
  are issued by the visitor's own browser directly against the public bucket.
- **Does** display that data, and lets a user export a PNG of what they are
  looking at and their own ink labels as TIFF. Exported PNGs carry the scroll,
  slice, crop, display window and LUT burned into the caption so a shared image
  can be traced back to its source and settings.
- Labels a user paints are their own work; the manifest records exactly which
  volume, level, layer and crop they belong to.

## Sources

- Data and licensing: https://scrollprize.org/data
- Prizes and rules: https://scrollprize.org/prizes
- Open problems: https://scrollprize.org/2026_open_problems

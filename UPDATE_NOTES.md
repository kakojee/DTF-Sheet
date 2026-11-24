# Update notes — contiguous row-tail and earlier-gap fill

- Retains the current light UI, upload handling, 300 DPI output, 23-inch roll, 89.9-inch limit and 0.5-inch clearance.
- Adds a row-run packing candidate that does not reserve unused cells in a design group's partial final row.
- The next design may use an open interval in the latest row, or fill an earlier row when the complete requested group fits there.
- When only part of the latest row's space is used, the design continues at the same horizontal anchor in rows below. A fresh-row alternative is also tested so a narrow tail does not force a long, inefficient column.
- Uses a one-design lookahead to compare orientation and row placement choices before committing to the layout.
- Retains rectangular group packing as an alternative; the app compares sheet length, unused row space and rotation count.
- All placements remain separate rectangles with the configured 0.5-inch clearance. Artwork is not resized, recolored, redrawn or trimmed; only exact 90-degree rotation is allowed.
- This remains a bounded heuristic, not a mathematical guarantee of the global optimum. Verify previews and every per-design quantity before printing.

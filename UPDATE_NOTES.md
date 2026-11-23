# Packing engine update

This build keeps the existing kakojee Print Nest light theme and branding, and replaces the previous shelf-only placement routine with a grouped rectangular free-space packer.

## What changed
- Identical copies stay together in a rectangular group on each sheet.
- Each group can use the original artwork orientation or an exact 90-degree rotation.
- The packer can place a later group into a usable rectangular cavity beside or below an earlier group, instead of treating every row as one full-width shelf.
- A 0.5-inch clearance is reserved between separate groups and between copies.
- Oversized orders are split across multiple sheets automatically. The complete order is tried first; when it does not fit, quantities are budgeted per sheet and each proposed sheet is validated against the actual dimensions.
- The multi-sheet allocator no longer repeatedly runs a deep binary-search packing routine for every design. Intermediate allocation uses area budgeting, followed by exact packing validation.
- Artwork is not resized, trimmed, recolored, or resampled. Rotation is an exact 90-degree transpose.

## Fixed production settings
- Roll width: 23 inches
- Maximum sheet length: 89.9 inches
- Gap: 0.5 inch
- Export: transparent PNG at 300 DPI

## Important
This is a bounded heuristic, not a mathematically guaranteed global optimum. Always review every sheet preview and verify the quantities and cutting clearances before printing. The test benchmark used synthetic artwork dimensions; actual order speed and sheet count depend on the uploaded PNG dimensions and quantities.

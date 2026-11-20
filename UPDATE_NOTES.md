# Packing algorithm update

This version keeps the current light-theme interface and replaces the original one-design-per-row shelf routine with an orientation-aware grouped row packer.

- Evaluates original and exact 90-degree orientations for each uploaded design (up to 12 designs in exhaustive orientation combinations).
- Keeps copies of each design contiguous as runs.
- Fills available row width with other design runs when they fit.
- Uses a common row boundary and 0.5-inch gap between rows to retain straight transverse cutting lanes.
- Compares several row-order strategies and chooses the shortest valid candidate under the 89.9-inch limit.
- Does not resize, recolor, redraw, or trim source artwork.

This is a heuristic, not a globally optimal nesting solver. Always inspect the preview and verify dimensions/copy counts before production. The Krema reference sheet is a design/production reference, not a machine-learning training process.

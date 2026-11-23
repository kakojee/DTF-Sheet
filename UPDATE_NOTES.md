# Packing performance update

- Replaced the Cartesian-product search across every design's block layouts with a bounded coordinate-descent search.
- Keeps a small, diverse set of row/column and orientation candidates per design.
- Uses two refinement passes and three shelf-ordering strategies, so runtime grows much more predictably with the number of designs.
- Caches repeated packing requests made during multi-sheet quantity searches.
- Preserves original PNG pixels, exact 90-degree rotations, 23-inch roll width, 89.9-inch maximum sheet length, and 0.5-inch gaps.
- This remains a cut-aware heuristic, not a globally optimal nesting solver. Review every sheet before production.

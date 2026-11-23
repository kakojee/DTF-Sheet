# Stability and interface update

## Crash and memory protections
- Uploaded PNGs are inspected as compressed bytes; full-resolution RGBA artwork is decoded one design at a time only during rendering.
- Packing uses dimensions and 90-degree orientation flags, not retained copies of each decoded image.
- Production sheets render on a disk-backed memory-mapped canvas rather than a 746 MB in-RAM RGBA canvas.
- Preview images are rendered independently at display resolution; the app never opens a full-resolution output PNG to make a preview.
- Old result/session keys are cleared on app build change and before a new generation begins.
- PNG files are not recompressed when placed into the ZIP archive.
- Inputs are capped at 35 megapixels per design and 100 megapixels total to avoid worker memory exhaustion.

## Interface
- Updated responsive light interface with a refined dark workspace rail, clearer typography, quieter production metrics, compact design cards and a dedicated output section.
- Quantity editing is inside a form to avoid reprocessing all 31 uploads on every quantity keystroke.

## Production rules retained
- 23-inch width, 89.9-inch maximum length, 0.5-inch spacing, transparent PNG at 300 DPI.
- Original artwork pixels are preserved; only exact 90-degree rotations are permitted.
- Multi-sheet generation remains enabled.

# Upload-total limit correction and interface refinement

## Upload handling
- Removed the incorrect 100-megapixel aggregate hard stop. A batch with 130.4 MP across multiple designs is no longer blocked just because the combined total exceeds 100 MP.
- Kept a 35-megapixel per-file decode ceiling to limit peak memory while a single PNG is opened. This is a per-design safeguard, not a combined-order limit.
- Larger combined batches now show an informational notice and continue; source artwork is not rescaled.
- If any upload is rejected, generation is disabled so the app cannot silently omit one or more designs.
- Increased the per-file upload cap to 200 MB.

## Interface
- Updated uploaded-file chips to use a light surface and readable dark text.
- Retained the modern light workspace and navy navigation.

## Production settings retained
- 23-inch roll width, 89.9-inch sheet limit, 0.5-inch cut clearance, 300 DPI transparent PNG.
- Original artwork pixels are preserved; only exact 90-degree rotation is permitted.

# kakojee Print Nest

Responsive Streamlit DTF gangsheet generator.

## Production defaults
- Roll width: 23 inches
- Maximum sheet length: 89.9 inches
- Gap: 0.5 inch
- Export: transparent PNG at 300 DPI
- Input: PNG only

Artwork pixels and canvas dimensions are preserved. The app may rotate artwork by exactly 90 degrees; it does not resize, recolor, redraw, or trim logos. Missing DPI metadata is assumed to be 300 DPI with a warning.

The packing engine groups identical copies, compares horizontal and vertical group layouts, and automatically splits orders across multiple sheets. Its search is deliberately bounded for responsive generation on larger orders. It is a production-oriented heuristic, not a guarantee of globally optimal nesting. Inspect previews, dimensions, quantities, and cutting lanes before printing.

## Deploy
Replace the root-level `app.py` in the existing GitHub repository with this package's `app.py`. Keep the existing Streamlit app and URL. Existing `requirements.txt` and `.streamlit/config.toml` are included for reference.

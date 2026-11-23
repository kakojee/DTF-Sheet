# Automatic multi-sheet update

This version adds automatic order splitting while retaining the light theme and grouped, cut-aware packing logic.

- The app first attempts to fit the complete order on one 23-inch-wide sheet.
- If it cannot, it creates additional sheets, each with a maximum length of 89.9 inches.
- It places as many copies of a design as fit in a grouped block, then tries other designs in remaining space before closing that sheet.
- Remaining quantities continue onto subsequent sheets until every requested copy is placed.
- The preview shows every generated sheet, with a separate PNG download for each and one ZIP download containing all sheets.
- Artwork is not resized, cropped, recolored, or redrawn. Only exact 90-degree rotation is allowed.
- The 0.5-inch spacing and transparent 300 DPI PNG export are retained.

The layout remains a heuristic optimizer, not a mathematical guarantee of the globally minimum film usage. Inspect every sheet and verify the displayed copy counts before printing.

## Deployment
Replace the existing root-level `app.py` in the GitHub repository with `kakojee_Print_Nest/app.py` from this package. Keep the current `requirements.txt` and `.streamlit/config.toml`. Commit the change and allow Streamlit Community Cloud to redeploy.

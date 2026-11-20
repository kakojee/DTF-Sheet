# Packing algorithm update

This version replaces the previous per-row placement heuristic with a group-first block packer.

- Each uploaded design's requested copies are arranged into one contiguous rectangular group.
- The app evaluates original and exact 90-degree artwork orientations.
- It tests multiple column/row shapes for each design group.
- It compares multiple shelf arrangements of those groups across the 23-inch roll.
- Each shelf has a common height and shelves are separated by a full 0.5-inch transverse lane.
- A 0.5-inch gap is retained between copies inside a group and between groups.
- Original artwork pixels are not resized, cropped, recolored, or redrawn.

This is a bounded heuristic optimizer, not a mathematically guaranteed global optimum. Inspect the preview and count check before production.

## Deployment
Replace the existing root-level `app.py` in the GitHub repository with this package's `kakojee_Print_Nest/app.py`. Keep the existing `requirements.txt` and `.streamlit/config.toml` (they are included here as matching copies). Commit the change and allow Streamlit Community Cloud to redeploy.

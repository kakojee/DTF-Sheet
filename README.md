# kakojee Print Nest

Minimal, responsive DTF gangsheet web app.

Upload transparent PNGs, enter quantities, generate a grouped gangsheet, preview it, and download a transparent PNG.

## Run
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy
Upload the files in this folder to the root of your existing GitHub repository. Configure Streamlit Community Cloud to run `app.py`.

No Supabase, login, or secrets are required.

## Production defaults
- Roll width: 23 inches
- Maximum length: 89.9 inches
- Spacing: 0.5 inches
- Export: transparent PNG at 300 DPI

Artwork is not resized, cropped, recolored, or redrawn. Exact 90-degree rotation is allowed. PNGs without reliable DPI metadata are interpreted using 300 DPI; verify intended physical size before printing.

The group-first packing algorithm compares multiple group shapes, orientations, and shelf arrangements. It prioritizes contiguous design groups and clear transverse cutting lanes, then sheet length. It is a heuristic, not a guaranteed global optimum; always inspect the preview and copy counts before production.

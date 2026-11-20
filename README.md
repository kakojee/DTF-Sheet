# PrintNest — DTF Gangsheet Studio

A public-access Streamlit web app prototype for PNG-only DTF gangsheet preparation. No staff login or Supabase connection is required. Anyone with the deployed app URL can use it.

## Production defaults
- 23-inch roll width
- 89.9-inch maximum sheet length
- 0.5-inch spacing
- Transparent PNG output at 300 DPI
- Source artwork pixels are preserved; no resizing, recoloring, redrawing, or trimming
- Optional lossless 90-degree rotation

## Run locally

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Deploy publicly

1. Create a GitHub repository and upload this folder.
2. Visit https://share.streamlit.io/ and sign in with GitHub.
3. Create an app, select the repository and branch, and set the main file path to `app.py`.
4. Deploy. Streamlit will provide a public URL.
5. Share that URL with staff. No Supabase credentials or secrets are needed.

## Important limitations
- Anyone who has the public URL can use the app; it has no login or access restrictions. Do not upload confidential customer artwork if public access is not acceptable.
- Uploaded files and generated sheets are processed in the app session; this version does not maintain a shared order archive or cloud storage. Download each sheet you need to keep.
- The packing engine is a grouped shelf heuristic with straight, full-width row lanes. It is not a globally optimal nesting solver and does not yet reproduce every manual production decision. Inspect the preview before printing.
- PNGs without embedded DPI metadata are interpreted at 300 DPI. This does not change pixels, but physical size depends on how the file was exported from CorelDRAW.
- Run a real print test and verify dimensions, counts, transparency, spacing, and maximum length before production.

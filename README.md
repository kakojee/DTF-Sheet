# kakojee Print Nest

Open-access Streamlit app for creating DTF gangsheet PNGs from transparent PNG artwork.

## Production rules
- 23-inch roll width
- 89.9-inch maximum sheet length
- 0.5-inch spacing
- 300 DPI transparent PNG export
- Original artwork pixels and dimensions are preserved; exact 90-degree rotation is allowed

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy
Replace the root-level `app.py` in the existing GitHub repository with this version and commit the change. Keep the existing `requirements.txt` and `.streamlit/config.toml`; Streamlit Community Cloud will redeploy the app.

The packing algorithm is a bounded heuristic. Inspect previews and copy counts before production.

# PrintNest — DTF Gangsheet

Responsive, open-access Streamlit app for transparent PNG gangsheet production. Designed for phones, tablets and desktop browsers.

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy / update on Streamlit Community Cloud
Upload the contents of this folder to the root of your GitHub repository and set the main file path to `app.py`. Commit updates to GitHub; Streamlit should redeploy automatically.

No Supabase, login, or secrets are required.

## Production defaults
- Roll width: 23 inches
- Maximum length: 89.9 inches
- Spacing: 0.5 inches
- Transparent PNG output at 300 DPI

Artwork is not resized. PNGs without reliable DPI metadata are interpreted using 300 DPI; verify intended physical size before printing. Always inspect the preview and copy counts before production.

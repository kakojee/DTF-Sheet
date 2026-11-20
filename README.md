# kakojee Print Nest

Minimal, responsive DTF gangsheet web app. No logo and no tagline.

Upload transparent PNGs, enter quantities, generate a grouped gangsheet, preview it, and download a transparent PNG.

## Run
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy
Upload the files in this folder to the root of your GitHub repository. Configure Streamlit Community Cloud to run `app.py`.

No Supabase, login, or secrets are required.

## Fixed production defaults
- Roll width: 23 inches
- Maximum length: 89.9 inches
- Spacing: 0.5 inches
- Export: transparent PNG at 300 DPI

Artwork is not resized. PNGs without reliable DPI metadata are interpreted using 300 DPI; verify intended physical size before printing.

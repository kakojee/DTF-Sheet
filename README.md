# PrintNest — DTF Gangsheet

Open-access Streamlit app for arranging transparent PNG artwork into a DTF gangsheet.

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on Streamlit Community Cloud
Upload the contents of this folder to the root of a GitHub repository, then create a Streamlit app from that repository with main file path `app.py`.

No Supabase, login, or secrets are required.

## Production defaults
- Roll width: 23 inches
- Maximum length: 89.9 inches
- Spacing: 0.5 inches
- Transparent PNG output at 300 DPI

Artwork is not resized. PNGs without reliable DPI metadata are interpreted using 300 DPI; verify intended physical size before printing.

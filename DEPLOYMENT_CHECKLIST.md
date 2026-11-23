# Deployment checklist

1. Extract this ZIP.
2. In your existing GitHub repository, replace the root-level `app.py` with `kakojee_Print_Nest/app.py`.
3. Replace `.streamlit/config.toml` with the included file.
4. Keep your existing `requirements.txt` unless the repository file is older than the included version.
5. Commit the changes and wait for Streamlit Community Cloud to redeploy.
6. If the app does not refresh, use Manage app → Reboot.
7. Test a small order first, then upload the larger order again.

The upload fix removes the combined 100-megapixel block. A single artwork file is still limited to 35 megapixels per PNG to keep peak image-decoding memory bounded.

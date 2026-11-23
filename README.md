# kakojee Print Nest

Minimal, responsive DTF gangsheet web app.

Upload transparent PNGs, enter quantities, and generate grouped gangsheet(s). If the complete order will not fit within one 23 × 89.9-inch sheet, the app automatically creates additional sheets, previews each one, and provides individual PNG downloads plus one ZIP containing every sheet.

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

The group-first packing algorithm compares multiple group shapes, orientations, and shelf arrangements. When an order exceeds one sheet, it carries remaining quantities to additional sheets and tries other design groups in available space before closing each sheet. It prioritizes contiguous design groups and clear transverse cutting lanes. This is a heuristic, not a guaranteed global optimum; always inspect every sheet preview and copy count before production.

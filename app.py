import io, os, json, math, uuid, hashlib
from datetime import datetime, timezone
from typing import List, Dict, Tuple

import streamlit as st
from PIL import Image, ImageOps

APP_TITLE = "kakojee Print Nest"
ROLL_WIDTH_IN = 23.0
MAX_LENGTH_IN = 89.9
GAP_IN = 0.5
DEFAULT_DPI = 300

st.set_page_config(page_title=APP_TITLE, layout="wide")

def px(inches: float, dpi: int) -> int:
    return int(round(inches * dpi))


def load_logo(upload, qty: int, idx: int) -> Dict:
    raw = upload.getvalue()
    im = Image.open(io.BytesIO(raw))
    if im.format != "PNG":
        raise ValueError("Only PNG files are accepted.")
    im = im.convert("RGBA")
    dpi_meta = im.info.get("dpi")
    if dpi_meta and dpi_meta[0] and dpi_meta[0] > 20:
        embedded_dpi = int(round(float(dpi_meta[0])))
        if embedded_dpi == DEFAULT_DPI:
            dpi_note = f"Embedded DPI detected: {embedded_dpi}"
        else:
            dpi_note = (f"Embedded DPI is {embedded_dpi}, not 300. Pixels will be preserved and the output is 300 DPI, "
                        "so the physical print size will follow pixels ÷ 300. Verify the intended size before printing.")
    else:
        dpi_note = "No reliable DPI metadata found; assumed 300 DPI. Confirm this matches the export size in CorelDRAW."
    # The output sheet is 300 DPI. Preserve the full source canvas and pixel dimensions;
    # therefore the output physical size is source pixels divided by 300.
    w_in, h_in = im.width / DEFAULT_DPI, im.height / DEFAULT_DPI
    return {"id": idx, "name": upload.name, "image": im, "qty": int(qty), "dpi": DEFAULT_DPI,
            "wpx": im.width, "hpx": im.height, "w_in": w_in, "h_in": h_in,
            "dpi_note": dpi_note, "hash": hashlib.sha256(raw).hexdigest()}


def oriented(item: Dict, rotate: bool) -> Tuple[Image.Image, float, float]:
    im = item["image"]
    if rotate:
        # Exact 90-degree transpose: no resampling or scaling.
        im = im.transpose(Image.Transpose.ROTATE_90)
        return im, item["h_in"], item["w_in"]
    return im, item["w_in"], item["h_in"]


def make_instances(items: List[Dict]) -> List[Dict]:
    out = []
    for item in items:
        for n in range(item["qty"]):
            out.append({"item": item, "copy": n + 1})
    return out


def shelf_pack(items: List[Dict], dpi: int, gap_in: float, roll_w: float, max_len: float):
    """Cut-friendly grouped shelf rows. Each row has one orientation per design;
    rows remain full-width-separated by a clear transverse cutting lane."""
    roll_px = px(roll_w, dpi)
    gap_px = px(gap_in, dpi)
    max_h_px = px(max_len, dpi)
    # Candidate row groups: group by design and orientation, then choose orientation
    # that yields fewer rows / less height while preserving contiguous same-design blocks.
    groups = []
    for item in items:
        for rotate in (False, True):
            _, wi, hi = oriented(item, rotate)
            groups.append({"item": item, "rotate": rotate, "w": px(wi, dpi), "h": px(hi, dpi), "count": item["qty"]})
    # For each logo choose orientation based on estimated shelf height and row capacity.
    chosen = []
    for item in items:
        opts = [g for g in groups if g["item"]["id"] == item["id"]]
        scored = []
        for g in opts:
            if g["w"] > roll_px:
                score = float("inf")
            else:
                per_row = max(1, (roll_px + gap_px) // (g["w"] + gap_px))
                rows = math.ceil(g["count"] / per_row)
                score = rows * g["h"] + max(0, rows - 1) * gap_px
            scored.append((score, g))
        best = min(scored, key=lambda x: x[0])[1]
        if not math.isfinite(min(scored, key=lambda x: x[0])[0]):
            raise ValueError(f"{item['name']} is wider than the 23-inch roll in both orientations. Check the PNG export size.")
        chosen.append(best)
    # Group largest total row height first; rows are not interlocked.
    chosen.sort(key=lambda g: (-(g["h"] * math.ceil(g["count"] / max(1, (roll_px + gap_px)//(g["w"]+gap_px)))), -g["h"]))
    rows = []
    for g in chosen:
        remaining = g["count"]
        while remaining:
            cap = max(1, (roll_px + gap_px) // (g["w"] + gap_px))
            n = min(remaining, cap)
            row_w = n * g["w"] + (n - 1) * gap_px
            rows.append({"item": g["item"], "rotate": g["rotate"], "n": n, "w": row_w, "h": g["h"], "placements": []})
            remaining -= n
    # Fill unused horizontal room with smaller groups only if the same row height
    # accommodates them and a full 0.5in gap remains. This preserves straight lanes.
    # Existing row is kept as a distinct cutting section; do not mix different heights.
    rows.sort(key=lambda r: (-r["h"], -r["w"]))
    y = 0
    placed = []
    for ridx, row in enumerate(rows):
        if y + row["h"] > max_h_px:
            raise ValueError(f"Layout exceeds the 89.9-inch maximum. Current estimate: {(y + row['h'])/dpi:.2f} inches. Reduce quantities or review logo dimensions.")
        x = 0
        im, _, _ = oriented(row["item"], row["rotate"])
        for c in range(row["n"]):
            placed.append({"image": im, "x": x, "y": y, "w": im.width, "h": im.height,
                           "name": row["item"]["name"], "copy": c + 1, "rotate": row["rotate"]})
            x += im.width + gap_px
        row["placements"] = placed[-row["n"]:]
        row["y"] = y
        y += row["h"] + gap_px
    canvas_h = max(1, y - gap_px)
    if canvas_h > max_h_px:
        raise ValueError("Layout is longer than the allowed roll length.")
    return placed, canvas_h, rows, roll_px


def render_sheet(placements, height, width, dpi):
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for p in placements:
        canvas.alpha_composite(p["image"], (p["x"], p["y"]))
    buf = io.BytesIO()
    canvas.save(buf, format="PNG", dpi=(dpi, dpi), optimize=True)
    buf.seek(0)
    return canvas, buf


def main_app():
    st.markdown("""<style>
    :root { color-scheme: light; }
    html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"] { background:#f4f6fa; color:#172033; }
    .stApp { background:#f4f6fa; color:#172033; }
    .block-container { padding:1.35rem 2rem 3rem; max-width:1440px; }
    .stApp p, .stApp label, .stApp li, .stApp [data-testid="stMarkdownContainer"] { color:#172033; }
    h1,h2,h3,h4 { color:#101828 !important; letter-spacing:-0.02em; }
    h1 { font-size:clamp(1.65rem, 3vw, 2.35rem) !important; }
    [data-testid="stCaptionContainer"] p { color:#475467 !important; }
    [data-testid="stSidebar"] { background:#101827; }
    [data-testid="stSidebar"] * { color:#f8fafc !important; }
    .workspace-head { padding:0 0 14px; margin:0 0 18px; border-bottom:1px solid #e4e7ec; }
    .workspace-head h1 { margin:0; color:#101828 !important; font-weight:650; }
    .stTextInput input, .stNumberInput input, .stTextArea textarea, [data-baseweb="select"] > div, [data-testid="stFileUploader"] section { background:#fff !important; color:#172033 !important; border-color:#98a2b3 !important; }
    input, textarea { color:#172033 !important; }
    [data-testid="stFileUploader"] label, [data-testid="stFileUploader"] small { color:#344054 !important; }
    [data-testid="stFileUploader"] section { border:1.5px dashed #98a2b3 !important; border-radius:14px !important; padding:1rem !important; background:#fff !important; }
    .stButton button, .stDownloadButton button { color:#fff !important; background:#175cd3 !important; border:1px solid #175cd3 !important; border-radius:11px; font-weight:650; min-height:46px; padding:.55rem 1rem; white-space:normal; }
    .stButton button:hover, .stDownloadButton button:hover { background:#1849a9 !important; border-color:#1849a9 !important; }
    [data-testid="stAlert"] p { color:#172033 !important; }
    [data-testid="stMetric"] { background:#fff; border:1px solid #d0d5dd; border-radius:13px; padding:12px 14px; box-shadow:0 2px 8px rgba(16,24,40,.035); }
    [data-testid="stMetricLabel"], [data-testid="stMetricValue"] { color:#172033 !important; }
    div[data-testid="stExpander"] { background:#fff; border:1px solid #d0d5dd; border-radius:13px; }
    div[data-testid="stExpander"] summary, div[data-testid="stExpander"] summary * { color:#172033 !important; }
    [data-testid="stImage"] img { max-width:100%; height:auto; border-radius:10px; }
    @media (max-width:768px) {
      .block-container { padding:.85rem .8rem 2rem; }
      .workspace-head { padding-bottom:12px; margin-bottom:14px; }
      h2 { font-size:1.35rem !important; } h3 { font-size:1.15rem !important; }
      [data-testid="stMetric"] { padding:10px; }
      [data-testid="stMetricLabel"] { font-size:.78rem !important; }
      [data-testid="stMetricValue"] { font-size:1.25rem !important; }
      .stButton button, .stDownloadButton button { width:100%; min-height:50px; font-size:1rem; }
      [data-testid="stFileUploader"] section { padding:.75rem .55rem !important; }
      [data-testid="stSidebar"] { min-width:min(82vw, 320px); }
      [data-testid="stImage"], [data-testid="stImage"] img { width:100% !important; height:auto !important; }
      div[data-testid="stExpander"] summary { padding:.65rem .25rem; }
    }
    @media (max-width:420px) {
      .block-container { padding-left:.6rem; padding-right:.6rem; }
      .stApp p, .stApp label { font-size:.94rem; }
    }
    </style>""", unsafe_allow_html=True)
    with st.sidebar:
        st.markdown("# kakojee Print Nest")
        page = st.radio("Workspace", ["New gangsheet", "Production rules", "About & setup"])
    if page == "Production rules":
        st.title("Production rules")
        st.info("These are the current fixed defaults. They are intentionally visible so staff can check them before production.")
        c1,c2,c3 = st.columns(3)
        c1.metric("Roll width", "23 in")
        c2.metric("Maximum length", "89.9 in")
        c3.metric("Logo spacing", "0.5 in")
        st.write("Output: transparent PNG · 300 DPI. Artwork is never resized, recolored, redrawn, or trimmed. 90° rotation is allowed without resampling.")
    elif page == "About & setup":
        st.title("About this app")
        st.write("This is an open-access prototype. Anyone with the app link can upload PNGs, enter quantities, generate a grouped gangsheet, and download a transparent PNG.")
        st.warning("The current optimizer prioritizes grouped designs and straight cutting lanes. It is a heuristic, not a guaranteed globally optimal nesting solver. Review the preview before printing.")
        st.write("No sign-in is required. Orders and output files are not saved to a shared database or cloud archive; each user downloads the generated sheet.")
    else:
        st.markdown("<div class='workspace-head'><h1>New gangsheet</h1></div>", unsafe_allow_html=True)
        with st.expander("Production settings", expanded=True):
            a,b,c,d = st.columns(4)
            a.metric("Roll width", "23 in")
            b.metric("Max roll length", "89.9 in")
            c.metric("Spacing", "0.5 in")
            d.metric("Export", "PNG · 300 DPI")
        uploads = st.file_uploader("Upload logo PNG files", type=["png"], accept_multiple_files=True, help="Use transparent PNG exports at the intended physical size. Original pixels are preserved.")
        if uploads:
            st.markdown("### Set print quantities")
            st.caption("On phones, logo cards stack vertically. On computers, they display side by side.")
            items = []
            cols = st.columns(2)
            for i, up in enumerate(uploads):
                with cols[i % 2]:
                    try:
                        base = load_logo(up, 1, i)
                        st.image(base["image"], caption=up.name, width=240)
                        qty = st.number_input(f"Quantity · {up.name}", min_value=1, max_value=500, value=1, step=1, key=f"qty_{i}")
                        base["qty"] = int(qty)
                        items.append(base)
                        st.caption(f"{base['wpx']} × {base['hpx']} px · approx. {base['w_in']:.2f} × {base['h_in']:.2f} in @ {base['dpi']} DPI")
                        if "assumed" in base["dpi_note"].lower():
                            st.warning(base["dpi_note"])
                        else:
                            st.caption(base["dpi_note"])
                    except Exception as e:
                        st.error(f"{up.name}: {e}")
            if items:
                total = sum(x["qty"] for x in items)
                st.caption(f"{len(items)} designs · {total} total copies")
                if st.button("Generate gangsheet", type="primary", use_container_width=True):
                    try:
                        with st.spinner("Calculating a grouped, cut-friendly layout…"):
                            placements, hpx, rows, wpx = shelf_pack(items, DEFAULT_DPI, GAP_IN, ROLL_WIDTH_IN, MAX_LENGTH_IN)
                            canvas, out = render_sheet(placements, hpx, wpx, DEFAULT_DPI)
                        st.session_state.last_sheet = out.getvalue()
                        st.session_state.last_meta = {"width": wpx/DEFAULT_DPI, "height": hpx/DEFAULT_DPI,
                            "copies": total, "rows": len(rows), "placements": placements, "items": items}
                        st.success("Gangsheet generated. Check the preview and copy counts before printing.")
                    except Exception as e:
                        st.error(str(e))
        if st.session_state.get("last_sheet"):
            meta = st.session_state.last_meta
            st.markdown("---")
            st.subheader("Gangsheet preview")
            st.caption(f"{meta['width']:.2f} × {meta['height']:.2f} inches · {meta['copies']} copies · {meta['rows']} grouped rows · 300 DPI")
            preview = Image.open(io.BytesIO(st.session_state.last_sheet))
            st.image(preview, caption="Transparent background · original artwork dimensions preserved", use_container_width=True)
            st.download_button("Download production PNG", data=st.session_state.last_sheet,
                file_name=f"dtf_gangsheet_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png",
                mime="image/png", type="primary", use_container_width=True)
            st.markdown("### Copy-count check")
            for item in meta["items"]:
                st.write(f"- {item['name']}: **{item['qty']}** copies")
            st.caption("Always inspect the downloaded sheet and verify dimensions/counts before sending it to print.")


main_app()

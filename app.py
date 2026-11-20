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
    """Orientation-aware grouped shelf packer with straight transverse cut lanes.

    Each design remains a contiguous run within a row. Rows may contain multiple
    design runs, but only when the row can accommodate them side-by-side. Every
    row has one common top/bottom boundary, leaving a clear horizontal lane
    between rows. The algorithm evaluates all orientation combinations for up
    to 10 designs and several row-order strategies, then selects the shortest
    valid sheet with a small penalty for fragmented design runs.
    """
    roll_px, gap_px, max_h_px = px(roll_w, dpi), px(gap_in, dpi), px(max_len, dpi)
    if len(items) > 12:
        # Avoid exponential search for very large uploads; use deterministic
        # greedy orientation evaluation for the common practical case.
        orientation_sets = [None]
    else:
        import itertools
        orientation_sets = list(itertools.product((False, True), repeat=len(items)))

    def build_candidate(rotations, strategy):
        groups = []
        for item, rotate in zip(items, rotations):
            im, wi, hi = oriented(item, rotate)
            w, h = im.width, im.height
            if w > roll_px:
                return None
            cap = max(1, (roll_px + gap_px) // (w + gap_px))
            groups.append({"item": item, "rotate": rotate, "image": im,
                           "w": w, "h": h, "remaining": int(item["qty"]),
                           "cap": cap})

        # Row construction: place whole contiguous runs, then use remaining
        # row width for another design where possible. Several orderings are
        # tried to avoid a single greedy ordering dominating the result.
        if strategy == 0:
            ordered = sorted(groups, key=lambda g: (-g["h"], -g["w"], g["item"]["id"]))
        elif strategy == 1:
            ordered = sorted(groups, key=lambda g: (-(g["w"] * g["h"]), -g["h"]))
        elif strategy == 2:
            ordered = sorted(groups, key=lambda g: (g["h"], -g["w"]))
        else:
            ordered = sorted(groups, key=lambda g: (-g["w"], -g["h"]))

        rows = []
        # Repeatedly start a row with the next unplaced design run, then fill
        # the remaining width with the best-fitting next design run(s).
        while any(g["remaining"] > 0 for g in ordered):
            available = [g for g in ordered if g["remaining"] > 0]
            first = available[0]
            row = {"height": first["h"], "segments": [], "used": 0}
            def add_run(g):
                space = roll_px - row["used"]
                count = min(g["remaining"], g["cap"], max(0, (space + gap_px) // (g["w"] + gap_px)))
                if count <= 0:
                    return False
                row["segments"].append((g, int(count)))
                row["used"] += int(count) * g["w"] + (len(row["segments"]) - 1) * gap_px
                row["height"] = max(row["height"], g["h"])
                g["remaining"] -= int(count)
                return True
            add_run(first)
            # Fill the remainder using designs that fit. Prefer similar heights
            # to avoid deep unused pockets under short artwork.
            while True:
                candidates = [g for g in ordered if g["remaining"] > 0 and
                              row["used"] + gap_px + g["w"] <= roll_px]
                if not candidates:
                    break
                candidates.sort(key=lambda g: (-(min(g["h"], row["height"]) / max(g["h"], row["height"])),
                                               -(g["w"] * min(g["remaining"], g["cap"]))))
                if not add_run(candidates[0]):
                    break
            rows.append(row)

        # Place rows in descending height order to keep the sheet compact.
        rows.sort(key=lambda r: (-r["height"], -r["used"]))
        y = 0
        placements = []
        row_meta = []
        for row in rows:
            if y + row["height"] > max_h_px:
                return None
            x = 0
            row_placements = []
            for g, count in row["segments"]:
                for copy_no in range(count):
                    p = {"image": g["image"], "x": x, "y": y, "w": g["w"], "h": g["h"],
                         "name": g["item"]["name"], "copy": copy_no + 1, "rotate": g["rotate"]}
                    placements.append(p)
                    row_placements.append(p)
                    x += g["w"] + gap_px
                # retain one clear 0.5in lane between design runs and copies
            row_meta.append({"y": y, "h": row["height"], "w": row["used"], "placements": row_placements})
            y += row["height"] + gap_px
        canvas_h = max(1, y - gap_px)
        if canvas_h > max_h_px:
            return None
        # Score rewards shorter sheets, then fewer distinct runs/rows with low
        # horizontal fill penalty. No artwork is scaled or cropped.
        run_count = sum(len(r["segments"]) for r in rows)
        unused_area = sum(max(0, roll_px - r["used"]) * r["height"] for r in rows)
        score = canvas_h + run_count * gap_px * 0.03 + unused_area / max(1, roll_px) * 0.015
        return score, placements, canvas_h, row_meta

    best = None
    if orientation_sets == [None]:
        # For many designs, independently choose the orientation with the
        # smaller height-per-copy estimate, then run the same row packer.
        rotations = []
        for item in items:
            options = []
            for rot in (False, True):
                im, _, _ = oriented(item, rot)
                if im.width <= roll_px:
                    cap = max(1, (roll_px + gap_px) // (im.width + gap_px))
                    options.append((math.ceil(item["qty"] / cap) * im.height, rot))
            if not options:
                raise ValueError(f"{item['name']} is wider than the 23-inch roll in both orientations.")
            rotations.append(min(options)[1])
        orientation_sets = [tuple(rotations)]

    for rotations in orientation_sets:
        for strategy in range(4):
            result = build_candidate(rotations, strategy)
            if result is not None and (best is None or result[0] < best[0]):
                best = result
    if best is None:
        raise ValueError("No cut-friendly layout fits under the 89.9-inch maximum. Reduce quantities or review artwork dimensions.")
    _, placements, canvas_h, rows = best
    return placements, canvas_h, rows, roll_px
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
    :root { color-scheme: light !important; }
    html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"],
    [data-testid="stMainBlockContainer"] { background:#F7F8FC !important; color:#172033 !important; }
    header[data-testid="stHeader"] { background:#FFFFFF !important; border-bottom:1px solid #E4E7EC !important; }
    [data-testid="stToolbar"] { background:transparent !important; }
    .block-container { padding:1.35rem 2rem 3rem; max-width:1440px; }
    .stApp, .stApp p, .stApp label, .stApp li, .stApp span,
    [data-testid="stMarkdownContainer"], [data-testid="stMarkdownContainer"] p { color:#172033; }
    h1,h2,h3,h4 { color:#101828 !important; letter-spacing:-.02em; }
    h1 { font-size:clamp(1.65rem, 3vw, 2.35rem) !important; }
    [data-testid="stCaptionContainer"] p, .stCaption { color:#475467 !important; }
    [data-testid="stSidebar"] { background:#101827 !important; border-right:1px solid #D0D5DD; }
    [data-testid="stSidebar"] * { color:#F8FAFC !important; }
    [data-testid="stSidebar"] h1 { font-size:clamp(1.25rem, 2vw, 1.65rem) !important; line-height:1.2 !important; white-space:nowrap; letter-spacing:-.04em; }
    [data-testid="stSidebar"] [data-testid="stRadio"] label { font-size:.98rem !important; }
    .workspace-head { padding:0 0 14px; margin:0 0 18px; border-bottom:1px solid #E4E7EC; }
    .workspace-head h1 { margin:0; color:#101828 !important; font-weight:650; }
    /* Inputs and upload controls */
    .stTextInput input, .stNumberInput input, .stTextArea textarea,
    [data-baseweb="select"] > div, [data-testid="stFileUploader"] section,
    [data-testid="stFileUploader"] section * { background:#FFFFFF !important; color:#172033 !important; }
    input, textarea { color:#172033 !important; }
    [data-testid="stFileUploader"] label, [data-testid="stFileUploader"] small,
    [data-testid="stFileUploader"] [data-testid="stMarkdownContainer"] { color:#344054 !important; }
    [data-testid="stFileUploader"] section { border:1.5px dashed #98A2B3 !important; border-radius:14px !important; padding:1rem !important; background:#FFFFFF !important; }
    [data-testid="stFileUploader"] button, [data-testid="stFileUploaderDropzone"] button,
    [data-testid="stFileUploader"] button * { background:#175CD3 !important; color:#FFFFFF !important; border-color:#175CD3 !important; }
    [data-testid="stFileUploader"] button { border-radius:10px !important; font-weight:650 !important; }
    .stButton button, .stDownloadButton button { color:#FFFFFF !important; background:#175CD3 !important; border:1px solid #175CD3 !important; border-radius:11px; font-weight:650; min-height:46px; padding:.55rem 1rem; white-space:normal; }
    .stButton button *, .stDownloadButton button * { color:#FFFFFF !important; }
    .stButton button:hover, .stDownloadButton button:hover { background:#1849A9 !important; border-color:#1849A9 !important; }
    [data-testid="stAlert"], [data-testid="stAlert"] * { color:#172033 !important; }
    [data-testid="stMetric"] { background:#FFFFFF !important; border:1px solid #D0D5DD; border-radius:13px; padding:12px 14px; box-shadow:0 2px 8px rgba(16,24,40,.035); }
    [data-testid="stMetricLabel"], [data-testid="stMetricValue"] { color:#172033 !important; }
    div[data-testid="stExpander"] { background:#FFFFFF !important; border:1px solid #D0D5DD; border-radius:13px; overflow:hidden; }
    div[data-testid="stExpander"] details, div[data-testid="stExpander"] summary,
    div[data-testid="stExpander"] summary *, div[data-testid="stExpander"] [data-testid="stExpanderDetails"] { background:#FFFFFF !important; color:#172033 !important; }
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
      [data-testid="stSidebar"] h1 { white-space:normal; }
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
        st.warning("The optimizer evaluates horizontal and exact 90° vertical orientations, groups identical copies into contiguous runs, combines compatible runs across rows, and keeps clear 0.5-inch transverse gaps. It is a cut-aware heuristic, not a guaranteed globally optimal nesting solver. Review the preview and copy counts before printing.")
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
                        with st.spinner("Comparing orientations and cut-friendly grouped layouts…"):
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

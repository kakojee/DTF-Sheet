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
    """Group-first, cut-aware block packer.

    Each design is first made into one contiguous rectangular block of copies.
    The block can use either exact artwork orientation and a range of grid
    shapes (columns x rows). The block choices are then compared in several
    shelf arrangements. This avoids scattering identical copies and gives
    straight, full-width transverse cut lanes between shelf rows.
    """
    import itertools

    roll_px, gap_px, max_h_px = px(roll_w, dpi), px(gap_in, dpi), px(max_len, dpi)

    # Build possible contiguous group-block shapes for each uploaded design.
    choices_by_item = []
    for item in items:
        options = []
        for rotate in (False, True):
            im, _, _ = oriented(item, rotate)
            w, h = im.size
            if w > roll_px:
                continue
            max_cols = min(int(item["qty"]), (roll_px + gap_px) // (w + gap_px))
            for cols in range(1, max_cols + 1):
                rows = math.ceil(int(item["qty"]) / cols)
                bw = cols * w + (cols - 1) * gap_px
                bh = rows * h + (rows - 1) * gap_px
                if bw <= roll_px and bh <= max_h_px:
                    options.append({"item": item, "rotate": rotate, "image": im,
                                    "w": w, "h": h, "cols": cols, "rows": rows,
                                    "bw": bw, "bh": bh})
        if not options:
            raise ValueError(f"{item['name']} cannot fit within the 23-inch roll in either orientation.")
        # Remove duplicate block geometries for the same orientation.
        seen = set(); unique = []
        for op in options:
            key = (op["rotate"], op["cols"], op["rows"], op["bw"], op["bh"])
            if key not in seen:
                seen.add(key); unique.append(op)
        choices_by_item.append(unique)

    # Bound the search for unusually large jobs while retaining a diverse set
    # of tall, wide and balanced group shapes.
    combination_count = math.prod(len(x) for x in choices_by_item)
    if combination_count > 150000:
        reduced = []
        for options in choices_by_item:
            options = sorted(options, key=lambda o: (o["bh"] + 0.12 * o["bw"],
                                                       abs(o["bw"] - 0.72 * roll_px)))
            keep = options[:10]
            # Keep the most horizontal and most vertical alternatives too.
            keep.extend([min(options, key=lambda o: o["bw"]),
                         min(options, key=lambda o: o["bh"])])
            unique = []; seen = set()
            for op in keep:
                key = (op["rotate"], op["cols"], op["rows"])
                if key not in seen:
                    seen.add(key); unique.append(op)
            reduced.append(unique)
        choices_by_item = reduced

    def pack_blocks(blocks, strategy):
        if strategy == 0:
            ordered = sorted(blocks, key=lambda b: (-b["bh"], -b["bw"]))
        elif strategy == 1:
            ordered = sorted(blocks, key=lambda b: (-(b["bw"] * b["bh"]), -b["bh"]))
        elif strategy == 2:
            ordered = sorted(blocks, key=lambda b: (-b["bw"], -b["bh"]))
        elif strategy == 3:
            ordered = sorted(blocks, key=lambda b: (b["bh"], -b["bw"]))
        else:
            ordered = sorted(blocks, key=lambda b: (-min(b["bw"], b["bh"]), -max(b["bw"], b["bh"])))

        shelves = []
        for block in ordered:
            fits = []
            for idx, shelf in enumerate(shelves):
                needed = gap_px + block["bw"]
                if shelf["used"] + needed <= roll_px:
                    new_h = max(shelf["h"], block["bh"])
                    # Prefer the shelf that adds the least height and leaves
                    # the most regular, compact group row.
                    fits.append((new_h - shelf["h"], roll_px - shelf["used"] - needed, idx))
            if fits:
                _, _, idx = min(fits)
                shelf = shelves[idx]
                shelf["blocks"].append(block)
                shelf["used"] += gap_px + block["bw"]
                shelf["h"] = max(shelf["h"], block["bh"])
            else:
                shelves.append({"blocks": [block], "used": block["bw"], "h": block["bh"]})

        total_h = sum(sh["h"] for sh in shelves) + gap_px * max(0, len(shelves) - 1)
        if total_h > max_h_px:
            return None
        # Strongly prioritize compact sheet length, then orderly shelves and
        # lower unused shelf area. This is a heuristic objective, not a proof
        # of globally optimal nesting.
        unused = sum(max(0, roll_px - sh["used"]) * sh["h"] for sh in shelves)
        score = total_h + len(shelves) * gap_px * 0.025 + (unused / roll_px) * 0.012
        return score, total_h, shelves

    best = None
    for selected in itertools.product(*choices_by_item):
        for strategy in range(5):
            result = pack_blocks(selected, strategy)
            if result is not None and (best is None or result[0] < best[0]):
                best = (result[0], result[1], result[2], selected)

    if best is None:
        raise ValueError("No grouped, cut-friendly layout fits under the 89.9-inch maximum. Reduce quantities or review artwork dimensions.")

    _, canvas_h, shelves, selected = best
    placements, row_meta = [], []
    y = 0
    for shelf in shelves:
        x = 0
        shelf_placements = []
        for block in shelf["blocks"]:
            item = block["item"]
            for n in range(int(item["qty"])):
                col = n % block["cols"]
                row = n // block["cols"]
                px0 = x + col * (block["w"] + gap_px)
                py0 = y + row * (block["h"] + gap_px)
                placement = {"image": block["image"], "x": px0, "y": py0,
                             "w": block["w"], "h": block["h"],
                             "name": item["name"], "copy": n + 1,
                             "rotate": block["rotate"]}
                placements.append(placement)
                shelf_placements.append(placement)
            x += block["bw"] + gap_px
        row_meta.append({"y": y, "h": shelf["h"], "w": shelf["used"],
                         "placements": shelf_placements})
        y += shelf["h"] + gap_px
    return placements, canvas_h, row_meta, roll_px

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

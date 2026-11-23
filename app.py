import io, os, json, math, uuid, hashlib, zipfile
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


def shelf_pack(items: List[Dict], dpi: int, gap_in: float, roll_w: float, max_len: float, quick: bool = False):
    """Cut-aware group packing using a MaxRects free-space search.

    Each uploaded design remains a rectangular group of identical copies. The
    group may use either exact artwork orientation and different row/column
    counts. Groups are placed as rectangles into available free rectangles,
    allowing a shorter group to leave usable space beside/below it for another
    complete group. A clearance strip is reserved around every group so that
    groups do not touch and remain practical to separate with scissors.
    """
    roll_px, gap_px, max_h_px = px(roll_w, dpi), px(gap_in, dpi), px(max_len, dpi)

    def make_options(item):
        options = []
        qty = int(item["qty"])
        for rotate in (False, True):
            im, _, _ = oriented(item, rotate)
            w, h = im.size
            if w > roll_px or h > max_h_px:
                continue
            max_cols = min(qty, max(1, (roll_px + gap_px) // (w + gap_px)))
            for cols in range(1, max_cols + 1):
                rows = math.ceil(qty / cols)
                bw = cols * w + (cols - 1) * gap_px
                bh = rows * h + (rows - 1) * gap_px
                if bw <= roll_px and bh <= max_h_px:
                    options.append({"item": item, "rotate": rotate, "image": im,
                                    "w": w, "h": h, "cols": cols, "rows": rows,
                                    "bw": bw, "bh": bh,
                                    "area": bw * bh})
        if not options:
            raise ValueError(f"{item['name']} cannot fit within the 23-inch roll in either orientation.")
        # Keep a diverse set of block shapes. Include short, narrow, and balanced
        # blocks instead of only choosing the smallest-height arrangement.
        ranked_sets = [
            sorted(options, key=lambda o: (o["bh"], o["bw"])),
            sorted(options, key=lambda o: (o["bw"], o["bh"])),
        ] if quick else [
            sorted(options, key=lambda o: (o["bh"], o["bw"])),
            sorted(options, key=lambda o: (o["bw"], o["bh"])),
            sorted(options, key=lambda o: (abs(o["bw"] / max(1, o["bh"]) - 1.0), o["area"])),
            sorted(options, key=lambda o: (o["area"], o["bh"])),
            sorted(options, key=lambda o: (o["rotate"], o["bh"], o["bw"])),
            sorted(options, key=lambda o: (not o["rotate"], o["bh"], o["bw"])),
        ]
        chosen, seen = [], set()
        for ranked in ranked_sets:
            for op in (ranked[0], ranked[len(ranked)//2]):
                key = (op["rotate"], op["cols"])
                if key not in seen:
                    chosen.append(op); seen.add(key)
        # Add a few intermediate column counts to give the optimizer useful
        # alternatives without exploding search time on large quantities.
        for op in sorted(options, key=lambda o: (o["bh"] + 0.18 * o["bw"], o["area"])):
            key = (op["rotate"], op["cols"])
            if key not in seen:
                chosen.append(op); seen.add(key)
            if len(chosen) >= 8:
                break
        return chosen[:2] if quick else chosen[:8]

    choices_by_item = [make_options(item) for item in items]

    def maxrects_pack(selected, order_strategy):
        blocks = list(selected)
        if order_strategy == 0:
            blocks.sort(key=lambda b: (-max(b["bw"], b["bh"]), -b["area"]))
        elif order_strategy == 1:
            blocks.sort(key=lambda b: (-b["area"], -max(b["bw"], b["bh"])))
        elif order_strategy == 2:
            blocks.sort(key=lambda b: (-b["bh"], -b["bw"]))
        elif order_strategy == 3:
            blocks.sort(key=lambda b: (-b["bw"], -b["bh"]))
        elif order_strategy == 4:
            blocks.sort(key=lambda b: (-(b["bw"] * b["bh"]), b["bh"]))

        # Free rectangles include the required clearance to the right and below.
        free = [(0, 0, roll_px + gap_px, max_h_px + gap_px)]
        placed = []
        for block in blocks:
            rw, rh = block["bw"] + gap_px, block["bh"] + gap_px
            candidates = []
            for fi, (fx, fy, fw, fh) in enumerate(free):
                if rw <= fw and rh <= fh:
                    dw, dh = fw - rw, fh - rh
                    if order_strategy % 2:
                        score = (min(dw, dh), max(dw, dh), fy + rh, fx)
                    else:
                        score = (fy + rh, min(dw, dh), max(dw, dh), fx)
                    candidates.append((score, fi, fx, fy))
            if not candidates:
                return None
            _, _, x, y = min(candidates, key=lambda c: c[0])
            placed.append((block, x, y))
            used_w, used_h = rw, rh

            # MaxRects split: retain all residual rectangles, then remove
            # contained duplicates. This makes cavities available to later groups.
            new_free = []
            for fx, fy, fw, fh in free:
                if x >= fx + fw or x + used_w <= fx or y >= fy + fh or y + used_h <= fy:
                    new_free.append((fx, fy, fw, fh)); continue
                if x > fx:
                    new_free.append((fx, fy, x - fx, fh))
                if x + used_w < fx + fw:
                    new_free.append((x + used_w, fy, fx + fw - (x + used_w), fh))
                if y > fy:
                    new_free.append((fx, fy, fw, y - fy))
                if y + used_h < fy + fh:
                    new_free.append((fx, y + used_h, fw, fy + fh - (y + used_h)))
            pruned = []
            for i, rect in enumerate(new_free):
                rx, ry, rw0, rh0 = rect
                contained = False
                for j, other in enumerate(new_free):
                    if i == j: continue
                    ox, oy, ow, oh = other
                    if rx >= ox and ry >= oy and rx + rw0 <= ox + ow and ry + rh0 <= oy + oh:
                        contained = True; break
                if not contained and rw0 > 0 and rh0 > 0:
                    pruned.append(rect)
            free = sorted(pruned, key=lambda r: r[2] * r[3], reverse=True)[:40 if quick else 100]

        content_h = max(y + block["bh"] for block, x, y in placed)
        content_w = max(x + block["bw"] for block, x, y in placed)
        if content_h > max_h_px:
            return None
        # Reward compact height, then lower occupied bounding-box area and
        # fewer fragmented free pockets. Keep the score in pixel-height units.
        occupied_area = sum(b["area"] for b, _, _ in placed)
        bbox_waste = max(0, content_w * content_h - occupied_area)
        score = content_h + (bbox_waste / max(1, roll_px)) * 0.025
        placements, groups = [], []
        for block, x, y in placed:
            item = block["item"]
            group_placements = []
            for n in range(int(item["qty"])):
                col, row = n % block["cols"], n // block["cols"]
                px0 = x + col * (block["w"] + gap_px)
                py0 = y + row * (block["h"] + gap_px)
                p = {"image": block["image"], "x": px0, "y": py0,
                     "w": block["w"], "h": block["h"], "name": item["name"],
                     "copy": n + 1, "rotate": block["rotate"]}
                placements.append(p); group_placements.append(p)
            groups.append({"x": x, "y": y, "w": block["bw"], "h": block["bh"],
                           "name": item["name"], "placements": group_placements})
        return score, content_h, placements, groups

    def evaluate(selected):
        best = None
        for strategy in range(1 if quick else 3):
            result = maxrects_pack(selected, strategy)
            if result is not None and (best is None or result[0] < best[0]):
                best = result
        return best

    # Seed with the most compact-height option, then coordinate-refine the
    # group shapes. The search is bounded and scales with designs, not the
    # Cartesian product of every design's possible arrangements.
    selected = [min(opts, key=lambda o: (o["bh"] + 0.10 * o["bw"], o["area"]))
                for opts in choices_by_item]
    best = evaluate(selected)
    if best is None:
        # Try a width-oriented seed if the first compact-height seed fails.
        selected = [min(opts, key=lambda o: (o["bw"] + 0.10 * o["bh"], o["area"]))
                    for opts in choices_by_item]
        best = evaluate(selected)
    for _pass in range(0 if quick else 1):
        changed = False
        for idx, options in enumerate(choices_by_item):
            current = selected[idx]
            local_best = best
            chosen = current
            for option in options:
                if option is current: continue
                trial = list(selected); trial[idx] = option
                result = evaluate(trial)
                if result is not None and (local_best is None or result[0] < local_best[0]):
                    local_best, chosen = result, option
            if chosen is not current:
                selected[idx] = chosen; best = local_best; changed = True
        if not changed: break

    if best is None:
        raise ValueError("No grouped, cut-friendly layout fits under the 89.9-inch maximum. Reduce quantities or review artwork dimensions.")
    _, canvas_h, placements, groups = best
    # Keep legacy row metadata key for compatibility with the preview layer.
    row_meta = [{"y": g["y"], "h": g["h"], "w": g["w"], "placements": g["placements"]}
                for g in groups]
    return placements, canvas_h, row_meta, roll_px
def pack_multiple_sheets(items: List[Dict], dpi: int, gap_in: float, roll_w: float, max_len: float):
    """Split oversized orders into cut-aware sheets without repeated deep searches.

    The complete order is optimised first. If it does not fit, quantities are
    allocated to each next sheet using an area budget, then each proposed sheet
    is validated by the full grouped MaxRects packer. This avoids the old
    per-design binary-search loop, which reran the optimizer hundreds of times
    on large orders.
    """
    ordered = sorted(items, key=lambda it: (-(it["w_in"] * it["h_in"] * it["qty"]),
                                           -max(it["w_in"], it["h_in"])))
    remaining = {int(item["id"]): int(item["qty"]) for item in ordered}
    full_order = [dict(item) for item in ordered]
    try:
        full = shelf_pack(full_order, dpi, gap_in, roll_w, max_len)
    except ValueError:
        full = None
    if full is not None:
        placements, height, rows, width = full
        return [{"placements": placements, "height": height, "rows": rows,
                 "width": width, "items": full_order}]

    usable_area = roll_w * max_len
    gap_area = gap_in
    sheets = []
    # Start high to minimise sheet count; lower the target only when the
    # actual geometry/cutting constraints show that the proposed groups do
    # not fit. The final packing is always checked against exact pixel bounds.
    fill_targets = (0.94, 0.88, 0.82, 0.76, 0.70, 0.64, 0.58)

    while any(q > 0 for q in remaining.values()):
        chosen_items = None
        chosen_pack = None
        for fill in fill_targets:
            budget = usable_area * fill
            used = 0.0
            candidate = []
            # Larger total-demand designs are considered first, while the
            # remaining budget is also offered to smaller designs afterwards.
            for item in ordered:
                q_left = remaining[int(item["id"])]
                if q_left <= 0:
                    continue
                unit_area = (item["w_in"] + gap_area) * (item["h_in"] + gap_area)
                take = min(q_left, int((budget - used) // max(unit_area, 1e-9)))
                if take > 0:
                    part = dict(item); part["qty"] = take
                    candidate.append(part)
                    used += take * unit_area
            if not candidate:
                # A single copy is the guaranteed-progress fallback.
                item = next(it for it in ordered if remaining[int(it["id"])] > 0)
                part = dict(item); part["qty"] = 1
                candidate = [part]
            try:
                packed = shelf_pack(candidate, dpi, gap_in, roll_w, max_len)
            except ValueError:
                packed = None
            if packed is not None:
                chosen_items, chosen_pack = candidate, packed
                break

        if chosen_items is None:
            # If the area estimates were too optimistic for this order, place
            # one copy at a time until a valid sheet is found; never resize art.
            item = next(it for it in ordered if remaining[int(it["id"])] > 0)
            chosen_items = [dict(item)]; chosen_items[0]["qty"] = 1
            try:
                chosen_pack = shelf_pack(chosen_items, dpi, gap_in, roll_w, max_len)
            except ValueError as exc:
                raise ValueError(f"{item['name']} cannot fit within a 23-inch roll in either orientation.") from exc

        placements, height, rows, width = chosen_pack
        sheets.append({"placements": placements, "height": height, "rows": rows,
                       "width": width, "items": list(chosen_items)})
        for part in chosen_items:
            remaining[int(part["id"])] -= int(part["qty"])

    return sheets

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
        st.warning("The optimizer evaluates horizontal and exact 90° vertical orientations, groups identical copies into contiguous runs, combines compatible runs across rows, keeps clear 0.5-inch transverse gaps, and automatically splits oversized orders across multiple sheets and tries other designs in leftover space before closing each sheet. It is a cut-aware heuristic, not a guaranteed globally optimal nesting solver. Review the preview and copy counts before printing.")
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
                        with st.spinner("Optimizing grouped layouts and splitting into sheets when needed…"):
                            packed_sheets = pack_multiple_sheets(items, DEFAULT_DPI, GAP_IN, ROLL_WIDTH_IN, MAX_LENGTH_IN)
                            sheet_bytes = []
                            for sheet in packed_sheets:
                                _, out = render_sheet(sheet["placements"], sheet["height"], sheet["width"], DEFAULT_DPI)
                                sheet_bytes.append(out.getvalue())
                            zip_buffer = io.BytesIO()
                            with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                                for i, data in enumerate(sheet_bytes, start=1):
                                    zf.writestr(f"kakojee_gangsheet_{i:02d}.png", data)
                            st.session_state.last_sheets = sheet_bytes
                            st.session_state.last_sheets_meta = packed_sheets
                            st.session_state.last_sheets_zip = zip_buffer.getvalue()
                            st.session_state.last_order_items = items
                        st.success(f"Order arranged into {len(packed_sheets)} sheet(s). Each sheet is within the 89.9-inch maximum.")
                    except Exception as e:
                        st.error(str(e))
        if st.session_state.get("last_sheets"):
            sheets_data = st.session_state.last_sheets
            sheets_meta = st.session_state.last_sheets_meta
            st.markdown("---")
            st.subheader("Gangsheet previews")
            st.caption(f"{len(sheets_data)} production sheet(s) · transparent PNG · 300 DPI · original artwork dimensions preserved")
            if len(sheets_data) > 1:
                st.info("The order did not fit on one sheet. It has been automatically split across multiple sheets; download the ZIP to get all sheets together.")
            st.download_button("Download ALL sheets (ZIP)", data=st.session_state.last_sheets_zip,
                file_name=f"kakojee_gangsheets_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                mime="application/zip", type="primary", use_container_width=True)
            for i, (data, meta) in enumerate(zip(sheets_data, sheets_meta), start=1):
                with st.expander(f"Sheet {i} · {meta['width']/DEFAULT_DPI:.2f} × {meta['height']/DEFAULT_DPI:.2f} inches · {sum(x['qty'] for x in meta['items'])} copies", expanded=(i == 1)):
                    preview = Image.open(io.BytesIO(data))
                    st.image(preview, caption=f"Sheet {i} · transparent background · original artwork dimensions preserved", use_container_width=True)
                    st.download_button(f"Download Sheet {i} PNG", data=data,
                        file_name=f"kakojee_gangsheet_{i:02d}.png", mime="image/png",
                        key=f"download_sheet_{i}", use_container_width=True)
                    st.markdown("**Copy-count check**")
                    for item in meta["items"]:
                        st.write(f"- {item['name']}: **{item['qty']}** copies")
            st.caption("Verify each sheet's preview, dimensions and copy counts before printing. A cut-aware heuristic is used; it does not guarantee a globally optimal nesting solution.")


main_app()

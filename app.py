import io, os, json, math, uuid, hashlib, zipfile
from datetime import datetime, timezone
from typing import List, Dict, Tuple

import streamlit as st
from PIL import Image, ImageOps

APP_TITLE = "kakojee Print Nest"
APP_BUILD = "2026.11.24-space-aware-side-lanes-04"
ROLL_WIDTH_IN = 23.0
MAX_LENGTH_IN = 89.9
GAP_IN = 0.5
DEFAULT_DPI = 300

st.set_page_config(page_title=APP_TITLE, layout="wide")

def px(inches: float, dpi: int) -> int:
    return int(round(inches * dpi))


@st.cache_data(show_spinner=False, max_entries=100)
def inspect_png(raw: bytes, filename: str) -> Dict:
    """Read dimensions and make a small preview without retaining decoded art.

    Only the original compressed PNG bytes are kept for packing/rendering.
    This avoids keeping 31+ full-resolution RGBA images alive in a Streamlit
    session while staff edit quantities.
    """
    try:
        with Image.open(io.BytesIO(raw)) as source:
            if source.format != "PNG":
                raise ValueError("Only PNG files are accepted.")
            width, height = source.size
            if width <= 0 or height <= 0:
                raise ValueError("This PNG has invalid dimensions.")
            if width * height > 35_000_000:
                raise ValueError(
                    f"{filename} is very large ({width:,} × {height:,} px). "
                    "Please check the CorelDRAW export dimensions before uploading."
                )
            dpi_meta = source.info.get("dpi")
            if dpi_meta and dpi_meta[0] and float(dpi_meta[0]) > 20:
                embedded_dpi = int(round(float(dpi_meta[0])))
                if embedded_dpi == DEFAULT_DPI:
                    dpi_note = f"Embedded DPI detected: {embedded_dpi}"
                else:
                    dpi_note = (
                        f"Embedded DPI is {embedded_dpi}, not 300. Pixels will be preserved; "
                        "physical output size follows pixels ÷ 300. Verify intended size before printing."
                    )
            else:
                dpi_note = (
                    "No reliable DPI metadata found; assumed 300 DPI. "
                    "Confirm this matches the export size in CorelDRAW."
                )
            # Make a small upload-list thumbnail. The full-size decoded image is
            # discarded as soon as this function returns.
            preview = source.convert("RGBA")
            preview.thumbnail((220, 150), Image.Resampling.LANCZOS)
            thumb_buffer = io.BytesIO()
            preview.save(thumb_buffer, format="PNG", optimize=False, compress_level=1)
            preview.close()
            return {
                "wpx": int(width), "hpx": int(height),
                "w_in": width / DEFAULT_DPI, "h_in": height / DEFAULT_DPI,
                "dpi_note": dpi_note,
                "thumbnail": thumb_buffer.getvalue(),
                "hash": hashlib.sha256(raw).hexdigest(),
            }
    except (Image.UnidentifiedImageError, OSError) as exc:
        raise ValueError(f"{filename} is not a readable PNG file.") from exc


def load_logo(upload, qty: int, idx: int) -> Dict:
    raw = upload.getvalue()
    meta = inspect_png(raw, upload.name)
    return {
        "id": idx, "name": upload.name, "raw": raw,
        "qty": int(qty), "dpi": DEFAULT_DPI, **meta,
    }


def oriented_size(item: Dict, rotate: bool) -> Tuple[int, int]:
    """Return pixel dimensions for the original or exact 90-degree orientation."""
    if rotate:
        return int(item["hpx"]), int(item["wpx"])
    return int(item["wpx"]), int(item["hpx"])

def make_instances(items: List[Dict]) -> List[Dict]:
    out = []
    for item in items:
        for n in range(item["qty"]):
            out.append({"item": item, "copy": n + 1})
    return out


def _maxrects_group_pack(items: List[Dict], dpi: int, gap_in: float, roll_w: float, max_len: float, quick: bool = False):
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
            w, h = oriented_size(item, rotate)
            if w > roll_px or h > max_h_px:
                continue
            max_cols = min(qty, max(1, (roll_px + gap_px) // (w + gap_px)))
            for cols in range(1, max_cols + 1):
                rows = math.ceil(qty / cols)
                bw = cols * w + (cols - 1) * gap_px
                bh = rows * h + (rows - 1) * gap_px
                if bw <= roll_px and bh <= max_h_px:
                    options.append({"item": item, "rotate": rotate,
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
            # Avoid quadratic containment pruning. With many uploaded designs,
            # the previous nested comparison could dominate runtime. Free
            # rectangles are safe residual regions even when some are contained;
            # de-duplicate them and retain candidates by area, width and height.
            unique = list(dict.fromkeys(
                rect for rect in new_free if rect[2] > 0 and rect[3] > 0
            ))
            cap_each = 12 if quick else 24
            keep = {}
            for key_fn in (
                lambda r: r[2] * r[3],
                lambda r: r[2],
                lambda r: r[3],
            ):
                for rect in sorted(unique, key=key_fn, reverse=True)[:cap_each]:
                    keep[rect] = rect
            free = list(keep.values())

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
                p = {"item_id": item["id"], "x": px0, "y": py0,
                     "w": block["w"], "h": block["h"], "name": item["name"],
                     "copy": n + 1, "rotate": block["rotate"]}
                placements.append(p); group_placements.append(p)
            groups.append({"x": x, "y": y, "w": block["bw"], "h": block["bh"],
                           "name": item["name"], "placements": group_placements})
        return score, content_h, placements, groups

    def evaluate(selected):
        best = None
        for strategy in range(1 if quick else 2):
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
            # Only test a small, diverse subset of alternatives per design.
            # The full option list is retained for initial candidate generation,
            # but evaluating every option for every logo multiplies pack passes.
            for option in options[:4]:
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

def _row_interval_pack(items: List[Dict], dpi: int, gap_in: float, roll_w: float, max_len: float, quick: bool = False):
    """Pack repeated logos as contiguous runs, then reuse the final row's open end.

    Unlike rectangular group packing, this does not reserve the empty cells in a
    group's final partial row. The next design can occupy that tail. If it needs
    another row, it continues at the same x anchor, leaving the opposite side
    available for the next design. Every placement remains a separate rectangle
    with the configured clearance; no artwork pixels are changed.
    """
    roll_px = px(roll_w, dpi)
    gap_px = px(gap_in, dpi)
    max_h_px = px(max_len, dpi)

    def clone_rows(rows):
        return [
            {
                "y": row["y"], "h": row["h"],
                "placements": list(row["placements"]),
            }
            for row in rows
        ]

    def free_intervals(row):
        occupied = sorted(row["placements"], key=lambda p: (p["x"], p["w"]))
        intervals = []
        cursor = 0
        for p in occupied:
            left = max(0, int(p["x"]) - gap_px)
            if left > cursor:
                intervals.append((cursor, left))
            cursor = max(cursor, int(p["x"]) + int(p["w"]) + gap_px)
        if cursor < roll_px:
            intervals.append((cursor, roll_px))
        return intervals

    def row_used_right(row):
        return max((int(p["x"]) + int(p["w"]) for p in row["placements"]), default=0)

    def state_metrics(rows):
        if not rows:
            return 0, 0.0, 0
        height = max(row["y"] + row["h"] for row in rows)
        free_area = 0
        for row in rows:
            free_width = sum(hi - lo for lo, hi in free_intervals(row))
            free_area += free_width * row["h"]
        rotated_ids = {
            p["item_id"] for row in rows for p in row["placements"] if p.get("rotate")
        }
        return height, free_area / max(1, roll_px), len(rotated_ids)

    def state_score(rows):
        height, free_equiv, rotated_count = state_metrics(rows)
        # Sheet length is the primary objective. The secondary term favours
        # layouts that use open row ends, while a tiny rotation tie-breaker
        # avoids turning artwork unless the layout actually benefits.
        return height + 0.28 * free_equiv + (0.02 * dpi * rotated_count), height, free_equiv, rotated_count

    def add_item_variants(rows, item, rotate, max_variants=5):
        """Return several safe ways to place one design as a contiguous run.

        The full-quantity fit options may use an open interval on any existing
        row. Partial use is allowed on the current bottom row; overflow then
        continues at the same x anchor in rows below. A fresh-row option is
        always retained so a tiny tail cannot force a long, inefficient column.
        """
        w, h = oriented_size(item, rotate)
        qty = int(item["qty"])
        if w > roll_px or h > max_h_px or qty < 1:
            return []

        variants = []

        def build_from(row_index, lo, hi):
            """Fill one aligned lane through every compatible existing row.

            A logo does not need all of its copies to fit in a single row gap.
            The same x-anchor is reused on later rows, and a small design may
            stack vertically inside a taller row. This is the key side-lane
            behaviour: e.g. one small logo can occupy the open right edge of
            each row of a large repeated design instead of being pushed to the
            bottom as a separate block.
            """
            trial = clone_rows(rows)
            anchor_x = int(lo)
            seed_capacity = int((hi - anchor_x + gap_px) // (w + gap_px))
            if seed_capacity <= 0:
                return None

            remaining = qty
            copy_number = 1

            # Reuse this aligned x lane across existing rows. Each row is
            # checked independently, so no copy is placed through an occupied
            # interval. Existing row height can hold more than one smaller
            # copy vertically when the 0.5-inch clearance permits it.
            for current_index in range(row_index, len(trial)):
                row = trial[current_index]
                if int(row["h"]) < h:
                    continue

                row_capacities = []
                for left, right in free_intervals(row):
                    if int(left) <= anchor_x and int(right) >= anchor_x + w:
                        row_capacities.append(
                            int((int(right) - anchor_x + gap_px) // (w + gap_px))
                        )
                if not row_capacities:
                    continue

                # Use the actual capacity of each row independently. A narrow
                # seed gap must not cap wider side lanes farther down the sheet:
                # the logo stays left-aligned, but each row can use all of its
                # usable width (for example 1 copy in one row, 3 in the next).
                columns = max(row_capacities)
                vertical_slots = int((int(row["h"]) + gap_px) // (h + gap_px))
                for slot in range(vertical_slots):
                    if remaining <= 0:
                        break
                    y = int(row["y"]) + slot * (h + gap_px)
                    batch = min(remaining, columns)
                    for col in range(batch):
                        x = anchor_x + col * (w + gap_px)
                        row["placements"].append({
                            "item_id": int(item["id"]), "x": x, "y": y,
                            "w": int(w), "h": int(h), "name": item["name"],
                            "copy": copy_number, "rotate": bool(rotate),
                        })
                        copy_number += 1
                    remaining -= batch
                if remaining <= 0:
                    break

            # If the aligned side lanes do not hold the full quantity, continue
            # below the existing layout at the same anchor. This preserves a
            # visible group while still using any earlier space first.
            while remaining > 0:
                next_y = max(r["y"] + r["h"] for r in trial) + gap_px
                new_row = {"y": next_y, "h": h, "placements": []}
                trial.append(new_row)
                continuation_capacity = int(
                    (roll_px - anchor_x + gap_px) // (w + gap_px)
                )
                if continuation_capacity <= 0:
                    anchor_x = 0
                    continuation_capacity = int((roll_px + gap_px) // (w + gap_px))
                if continuation_capacity <= 0:
                    return None
                batch = min(remaining, continuation_capacity)
                for col in range(batch):
                    x = anchor_x + col * (w + gap_px)
                    new_row["placements"].append({
                        "item_id": int(item["id"]), "x": x, "y": int(new_row["y"]),
                        "w": int(w), "h": int(h), "name": item["name"],
                        "copy": copy_number, "rotate": bool(rotate),
                    })
                    copy_number += 1
                remaining -= batch
            return trial

        # Try usable spaces across the whole placed layout, not only the last
        # row. Equivalent lane anchors are deduplicated: an earlier row with
        # the same x/capacity can feed that lane through all following rows.
        seed_specs = []
        seen_seeds = set()
        for row_index, row in enumerate(rows):
            if int(row["h"]) < h:
                continue
            for lo, hi in free_intervals(row):
                capacity = int((hi - lo + gap_px) // (w + gap_px))
                if capacity <= 0:
                    continue
                signature = (int(lo), capacity)
                if signature in seen_seeds:
                    continue
                seen_seeds.add(signature)
                seed_specs.append((row_index, int(lo), int(hi), capacity))

        # Bound candidate generation on large orders while retaining narrow
        # side lanes as well as wider cavities. Earlier anchors can exploit
        # more existing rows; wider lanes are preferred within the same row.
        seed_specs.sort(key=lambda seed: (seed[0], -seed[3], seed[1]))
        seed_limit = 24 if quick else 48
        for row_index, lo, hi, _capacity in seed_specs[:seed_limit]:
            trial = build_from(row_index, lo, hi)
            if trial is not None:
                variants.append(trial)

        # Fresh-row alternative: preserve older spaces only when using them
        # would make the current design less efficient or harder to cut.
        next_y = max((r["y"] + r["h"] for r in rows), default=0)
        if rows:
            next_y += gap_px
        fresh = clone_rows(rows)
        fresh_row = {"y": next_y, "h": h, "placements": []}
        fresh.append(fresh_row)
        full_capacity = int((roll_px + gap_px) // (w + gap_px))
        remaining = qty
        copy_number = 1
        while remaining > 0:
            current = fresh[-1]
            batch = min(remaining, full_capacity)
            for j in range(batch):
                x = j * (w + gap_px)
                current["placements"].append({
                    "item_id": int(item["id"]), "x": x, "y": int(current["y"]),
                    "w": int(w), "h": int(h), "name": item["name"],
                    "copy": copy_number, "rotate": bool(rotate),
                })
                copy_number += 1
            remaining -= batch
            if remaining > 0:
                fresh.append({
                    "y": current["y"] + current["h"] + gap_px,
                    "h": h, "placements": [],
                })
        variants.append(fresh)

        # Remove duplicate placements and keep a small, diverse candidate set.
        unique = {}
        for trial in variants:
            signature = tuple(sorted(
                (p["item_id"], p["copy"], p["x"], p["y"], p["rotate"])
                for row in trial for p in row["placements"]
            ))
            unique[signature] = trial
        ranked = sorted(unique.values(), key=state_score)
        return ranked[:max_variants]

    def orientation_options(item):
        opts = []
        for rotate in (False, True):
            w, h = oriented_size(item, rotate)
            if w <= roll_px and h <= max_h_px:
                opts.append(rotate)
        return opts

    def estimated(item):
        qty = int(item["qty"])
        options = []
        for rotate in orientation_options(item):
            w, h = oriented_size(item, rotate)
            cap = int((roll_px + gap_px) // (w + gap_px))
            rows_needed = math.ceil(qty / max(1, cap))
            est_len = rows_needed * h + max(0, rows_needed - 1) * gap_px
            options.append((est_len, h, w))
        if not options:
            raise ValueError(f"{item['name']} cannot fit within the 23-inch roll in either orientation.")
        best_len = min(x[0] for x in options)
        area_demand = int(item["wpx"]) * int(item["hpx"]) * qty
        return best_len, area_demand, max(int(item["wpx"]), int(item["hpx"])), min(int(item["wpx"]), int(item["hpx"]))

    # Several bounded design orders prevent the upload order from dictating the
    # sheet. Large groups are normally placed first; smaller logos then use the
    # partial final rows and open side lanes where their dimensions permit.
    indexed = list(enumerate(items))
    estimates = {int(it["id"]): estimated(it) for it in items}
    order_specs = [
        lambda pair: pair[0],
        lambda pair: (-estimates[int(pair[1]["id"])][1], -estimates[int(pair[1]["id"])][0]),
        lambda pair: (-estimates[int(pair[1]["id"])][0], -estimates[int(pair[1]["id"])][1]),
    ]
    if not quick:
        order_specs.extend([
            lambda pair: (-estimates[int(pair[1]["id"])][2], -estimates[int(pair[1]["id"])][3]),
            lambda pair: (-int(pair[1]["qty"]), -estimates[int(pair[1]["id"])][1]),
            lambda pair: (estimates[int(pair[1]["id"])][1], estimates[int(pair[1]["id"])][0]),
        ])

    orderings = []
    seen_orders = set()
    for spec in order_specs:
        ordered = [pair[1] for pair in sorted(indexed, key=spec)]
        signature = tuple(int(x["id"]) for x in ordered)
        if signature not in seen_orders:
            orderings.append(ordered)
            seen_orders.add(signature)

    best_state = None
    best_key = None
    for ordered in orderings:
        rows = []
        failed = False
        for item_index, item in enumerate(ordered):
            best_trial = None
            best_trial_key = None
            for rotate in orientation_options(item):
                variants = add_item_variants(rows, item, rotate, max_variants=(3 if quick else 5))
                for trial_rows in variants:
                    current_key = state_score(trial_rows)
                    projected_key = current_key
                    # One-step lookahead compares the next logo against every
                    # promising open interval, not only the most recent row.
                    if item_index + 1 < len(ordered):
                        next_item = ordered[item_index + 1]
                        future_keys = []
                        for next_rotate in orientation_options(next_item):
                            future_rows_list = add_item_variants(
                                trial_rows, next_item, next_rotate,
                                max_variants=(2 if quick else 3),
                            )
                            future_keys.extend(state_score(fr) for fr in future_rows_list)
                        if future_keys:
                            projected_key = min(future_keys)
                    key = (projected_key[0], current_key[0],
                           projected_key[1], projected_key[2], projected_key[3])
                    if best_trial_key is None or key < best_trial_key:
                        best_trial, best_trial_key = trial_rows, key
            if best_trial is None:
                failed = True
                break
            rows = best_trial
        if failed or not rows:
            continue
        height = max(r["y"] + r["h"] for r in rows)
        if height > max_h_px:
            continue
        key = state_score(rows)
        if best_key is None or key < best_key:
            best_state, best_key = rows, key

    if best_state is None:
        return None

    placements = [p for row in best_state for p in row["placements"]]
    height = max(row["y"] + row["h"] for row in best_state)
    row_meta = [
        {"y": row["y"], "h": row["h"], "w": max((p["x"] + p["w"] for p in row["placements"]), default=0),
         "placements": row["placements"]}
        for row in best_state
    ]
    return placements, height, row_meta, roll_px


def _layout_quality(pack_result, roll_px: int, dpi: int):
    """Compare layouts by length first, then unused horizontal pockets and rotation."""
    placements, height, _rows, _width = pack_result
    by_y = {}
    for p in placements:
        row = by_y.setdefault(int(p["y"]), {"h": 0, "placements": []})
        row["h"] = max(row["h"], int(p["h"]))
        row["placements"].append(p)
    free_area = 0
    for row in by_y.values():
        occupied = sorted(row["placements"], key=lambda p: p["x"])
        cursor = 0
        free_width = 0
        for p in occupied:
            left = max(0, int(p["x"]) - px(0.5, dpi))
            if left > cursor:
                free_width += left - cursor
            cursor = max(cursor, int(p["x"]) + int(p["w"]) + px(0.5, dpi))
        if cursor < roll_px:
            free_width += roll_px - cursor
        free_area += free_width * row["h"]
    free_equiv = free_area / max(1, roll_px)
    rotated = len({p["item_id"] for p in placements if p.get("rotate")})
    return (height + 0.28 * free_equiv + 0.02 * dpi * rotated, height, free_equiv, rotated)


def shelf_pack(items: List[Dict], dpi: int, gap_in: float, roll_w: float, max_len: float, quick: bool = False):
    """Choose between contiguous row-tail filling and rectangular group packing."""
    roll_px = px(roll_w, dpi)
    candidates = []
    try:
        row_result = _row_interval_pack(items, dpi, gap_in, roll_w, max_len, quick=quick)
        if row_result is not None:
            candidates.append(row_result)
    except ValueError:
        pass
    # For larger orders, keep the alternative search bounded. The row-run
    # method is the primary production strategy and has predictable run time.
    try:
        use_quick = quick or len(items) > 16
        group_result = _maxrects_group_pack(items, dpi, gap_in, roll_w, max_len, quick=use_quick)
        if group_result is not None:
            candidates.append(group_result)
    except ValueError:
        pass
    if not candidates:
        raise ValueError("No grouped, cut-friendly layout fits under the 89.9-inch maximum. Reduce quantities or review artwork dimensions.")
    return min(candidates, key=lambda result: _layout_quality(result, roll_px, dpi))

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
        full_quick = shelf_pack(full_order, dpi, gap_in, roll_w, max_len, quick=True)
    except ValueError:
        full_quick = None
    if full_quick is not None:
        # Run the deeper arrangement search only once for a sheet that fits.
        try:
            full = shelf_pack(full_order, dpi, gap_in, roll_w, max_len)
        except ValueError:
            full = full_quick
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
                packed = shelf_pack(candidate, dpi, gap_in, roll_w, max_len, quick=True)
            except ValueError:
                packed = None
            if packed is not None:
                # Refine only the candidate that passed the quick feasibility
                # check; do not repeat the deep search for every fill target.
                try:
                    refined = shelf_pack(candidate, dpi, gap_in, roll_w, max_len)
                except ValueError:
                    refined = packed
                chosen_items, chosen_pack = candidate, refined
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

def make_preview_background(size: Tuple[int, int], tile: int = 22) -> Image.Image:
    """Create a subtle checkerboard so transparent artwork is visible."""
    from PIL import ImageDraw
    preview = Image.new("RGBA", size, (247, 248, 250, 255))
    draw = ImageDraw.Draw(preview)
    for y in range(0, size[1], tile):
        for x in range(0, size[0], tile):
            if ((x // tile) + (y // tile)) % 2:
                draw.rectangle((x, y, min(x + tile - 1, size[0]-1), min(y + tile - 1, size[1]-1)),
                               fill=(235, 238, 243, 255))
    return preview


def render_sheet(placements, height, width, dpi, items_by_id):
    """Render exact production pixels on a disk-backed canvas.

    A full 23 × 89.9 inch RGBA sheet at 300 DPI is about 746 MB uncompressed.
    It is never decoded from the finished PNG for previewing. Instead, this
    creates a small preview directly from each source PNG placement.
    """
    import mmap
    import tempfile

    width, height = int(width), int(height)
    byte_count = width * height * 4
    if width <= 0 or height <= 0:
        raise ValueError("The generated sheet has invalid dimensions.")

    # Keep previews modest on both desktop and mobile while preserving the
    # production export at its untouched 300-DPI pixel dimensions.
    scale = min(1050 / width, 1750 / height, 1.0)
    preview_size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
    preview = make_preview_background(preview_size)
    with tempfile.TemporaryFile() as backing:
        backing.truncate(byte_count)
        mapped = mmap.mmap(backing.fileno(), byte_count, access=mmap.ACCESS_WRITE)
        canvas = None
        try:
            canvas = Image.frombuffer("RGBA", (width, height), mapped,
                                      "raw", "RGBA", 0, 1)
            # Decode one source logo at a time, place all of its copies, then
            # release it before moving to the next design.
            by_item = {}
            for placement in placements:
                by_item.setdefault(int(placement["item_id"]), []).append(placement)

            for item_id, group in by_item.items():
                item = items_by_id[item_id]
                with Image.open(io.BytesIO(item["raw"])) as source:
                    source.load()
                    artwork = source.convert("RGBA")
                rotate = bool(group[0]["rotate"])
                if rotate:
                    rotated = artwork.transpose(Image.Transpose.ROTATE_90)
                    artwork.close()
                    artwork = rotated

                preview_art = None
                try:
                    for placement in group:
                        x, y = int(placement["x"]), int(placement["y"])
                        canvas.alpha_composite(artwork, (x, y))
                        if preview_art is None:
                            p_size = (max(1, int(round(artwork.width * scale))),
                                      max(1, int(round(artwork.height * scale))))
                            preview_art = artwork.resize(p_size, Image.Resampling.LANCZOS)
                        preview.alpha_composite(
                            preview_art,
                            (int(round(x * scale)), int(round(y * scale)))
                        )
                finally:
                    if preview_art is not None:
                        preview_art.close()
                    artwork.close()

            output = io.BytesIO()
            canvas.save(output, format="PNG", dpi=(dpi, dpi),
                        optimize=False, compress_level=1)
            png_bytes = output.getvalue()
            preview_output = io.BytesIO()
            preview.save(preview_output, format="PNG", optimize=False, compress_level=1)
            preview_bytes = preview_output.getvalue()
            return png_bytes, preview_bytes
        finally:
            if canvas is not None:
                canvas.close()
            mapped.close()
            preview.close()


def main_app():
    # Clear previous-build state once so large PIL objects left by older builds
    # are not retained in an existing Streamlit session after deployment.
    if st.session_state.get("_app_build") != APP_BUILD:
        for key in list(st.session_state.keys()):
            if key.startswith(("last_", "qty_")) or key in {"_generated_order_signature"}:
                del st.session_state[key]
        st.session_state["_app_build"] = APP_BUILD

    st.markdown("""<style>
    :root { color-scheme: light; }
    html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
      background:#F5F7FA !important; color:#182230 !important;
    }
    header[data-testid="stHeader"] { background:#F5F7FA !important; }
    [data-testid="stToolbar"] { background:transparent !important; }
    .block-container { max-width:1440px; padding:1.6rem 2.1rem 3rem; }
    .stApp, .stApp p, .stApp label, .stApp li,
    [data-testid="stMarkdownContainer"], [data-testid="stMarkdownContainer"] p { color:#344054; }
    h1,h2,h3,h4 { color:#101828 !important; letter-spacing:-.035em; }
    h1 { font-size:clamp(1.8rem,3vw,2.45rem) !important; font-weight:720 !important; }
    h2 { font-size:1.45rem !important; font-weight:680 !important; }
    h3 { font-size:1.12rem !important; font-weight:650 !important; }
    [data-testid="stCaptionContainer"] p, .stCaption { color:#667085 !important; }
    /* Refined dark workspace rail */
    [data-testid="stSidebar"] { background:#111C2E !important; border-right:1px solid #26364C; }
    [data-testid="stSidebar"] * { color:#E7EDF5 !important; }
    [data-testid="stSidebar"] > div:first-child { padding-top:1.25rem; }
    .brand-lockup { padding:.35rem .25rem 1.35rem; border-bottom:1px solid rgba(255,255,255,.12); margin-bottom:1.1rem; }
    .brand-kicker { color:#91A5BF !important; font-size:.68rem; font-weight:750; letter-spacing:.16em; text-transform:uppercase; margin-bottom:.55rem; }
    .brand-name { color:#FFFFFF !important; font-size:1.55rem; font-weight:720; line-height:1.06; letter-spacing:-.045em; }
    .brand-name span { color:#B9C9DC !important; display:block; font-weight:520; margin-top:.2rem; }
    .brand-foot { color:#91A5BF !important; font-size:.72rem; letter-spacing:.08em; margin-top:.85rem; }
    [data-testid="stSidebar"] [data-testid="stRadio"] label { font-size:.94rem !important; }
    [data-testid="stSidebar"] [data-testid="stRadio"] label p { color:#E7EDF5 !important; }
    [data-testid="stSidebar"] [data-testid="stRadio"] [aria-checked="true"] + div { color:#FFFFFF !important; }
    [data-testid="stSidebar"] p, [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p { color:#B8C5D6 !important; }
    [data-testid="stSidebar"] [data-testid="stRadio"] label p { color:#E7EDF5 !important; }
    /* Header and section rhythm */
    .page-eyebrow { color:#64748B !important; font-size:.72rem; font-weight:750; letter-spacing:.14em; text-transform:uppercase; margin:0 0 .5rem; }
    .page-title { font-size:clamp(1.9rem,3.4vw,2.65rem); color:#101828 !important; font-weight:760; line-height:1.05; letter-spacing:-.055em; margin:0; }
    .page-subtitle { color:#667085 !important; font-size:1rem; margin:.65rem 0 1.35rem; line-height:1.5; }
    .section-kicker { color:#667085 !important; font-size:.72rem; font-weight:750; letter-spacing:.12em; text-transform:uppercase; margin-bottom:.35rem; }
    .soft-panel { background:#FFFFFF; border:1px solid #E4E7EC; border-radius:17px; padding:1.1rem 1.2rem; box-shadow:0 5px 18px rgba(16,24,40,.035); }
    /* Streamlit metrics as quiet information cards */
    [data-testid="stMetric"] { background:#FFFFFF !important; border:1px solid #E4E7EC; border-radius:14px; padding:13px 15px; box-shadow:0 4px 14px rgba(16,24,40,.025); }
    [data-testid="stMetricLabel"] { color:#667085 !important; font-size:.78rem !important; }
    [data-testid="stMetricValue"] { color:#101828 !important; font-size:1.45rem !important; font-weight:700 !important; }
    /* Upload area and form inputs */
    [data-testid="stFileUploader"] section { background:#FFFFFF !important; border:1.5px dashed #AAB7C7 !important; border-radius:16px !important; padding:1.15rem !important; }
    [data-testid="stFileUploader"] section *, [data-testid="stFileUploader"] label,
    [data-testid="stFileUploader"] small { color:#344054 !important; }
    [data-testid="stFileUploader"] button { background:#243B5A !important; color:#FFFFFF !important; border:1px solid #243B5A !important; border-radius:9px !important; font-weight:650 !important; }
    [data-testid="stFileUploader"] button * { color:#FFFFFF !important; }
    /* Keep uploaded-file chips light and legible in Streamlit's uploader. */
    [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"],
    [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] > div,
    [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] > div > div {
      background:#F8FAFC !important; color:#344054 !important; border-color:#D0D5DD !important;
    }
    [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] *,
    [data-testid="stFileUploader"] [data-testid="stFileUploaderFileName"],
    [data-testid="stFileUploader"] [data-testid="stFileUploaderFileName"] * {
      color:#344054 !important;
    }
    input, textarea, [data-baseweb="input"] input { color:#182230 !important; }
    [data-testid="stNumberInput"] button { color:#344054 !important; background:#F8FAFC !important; }
    .stButton button, .stDownloadButton button, [data-testid="stFormSubmitButton"] button {
      background:#24466F !important; color:#FFFFFF !important; border:1px solid #24466F !important;
      border-radius:10px !important; min-height:45px; font-weight:680 !important; padding:.55rem 1rem;
      box-shadow:0 2px 5px rgba(18,47,78,.12); transition:background .15s ease, transform .15s ease;
    }
    .stButton button *, .stDownloadButton button *, [data-testid="stFormSubmitButton"] button * { color:#FFFFFF !important; }
    .stButton button:hover, .stDownloadButton button:hover, [data-testid="stFormSubmitButton"] button:hover {
      background:#183654 !important; border-color:#183654 !important; transform:translateY(-1px);
    }
    [data-testid="stAlert"] { border-radius:12px !important; }
    [data-testid="stAlert"] * { color:#182230 !important; }
    div[data-testid="stExpander"] { background:#FFFFFF !important; border:1px solid #E4E7EC; border-radius:14px; overflow:hidden; }
    div[data-testid="stExpander"] details, div[data-testid="stExpander"] summary,
    div[data-testid="stExpander"] summary *, div[data-testid="stExpander"] [data-testid="stExpanderDetails"] {
      background:#FFFFFF !important; color:#182230 !important;
    }
    [data-testid="stImage"] img { border-radius:9px; max-width:100%; height:auto; }
    [data-testid="stHorizontalBlock"] { gap:1rem; }
    @media (max-width:900px) {
      .block-container { padding:1.15rem 1rem 2.2rem; }
      .page-subtitle { font-size:.94rem; }
      [data-testid="stMetric"] { padding:10px 11px; }
      [data-testid="stMetricValue"] { font-size:1.18rem !important; }
    }
    @media (max-width:600px) {
      .block-container { padding:.85rem .7rem 2rem; }
      .brand-name { font-size:1.35rem; }
      .stButton button, .stDownloadButton button, [data-testid="stFormSubmitButton"] button { width:100%; min-height:48px; }
      [data-testid="stFileUploader"] section { padding:.8rem .6rem !important; }
      [data-testid="stHorizontalBlock"] { gap:.55rem; }
    }

    /* Consistent light controls: explicitly style BaseWeb wrappers as well as inputs.
       This prevents inherited dark browser/Streamlit styles from turning quantity fields black. */
    .stApp, .stApp * { color-scheme: light; }
    [data-testid="stNumberInput"], [data-testid="stTextInput"],
    [data-testid="stTextArea"], [data-testid="stSelectbox"],
    [data-testid="stMultiSelect"], [data-testid="stDateInput"] { color-scheme: light !important; }

    [data-testid="stNumberInput"] [data-baseweb="input"],
    [data-testid="stTextInput"] [data-baseweb="input"],
    [data-testid="stTextArea"] [data-baseweb="textarea"],
    [data-testid="stDateInput"] [data-baseweb="input"],
    [data-testid="stSelectbox"] [data-baseweb="select"] > div,
    [data-testid="stMultiSelect"] [data-baseweb="select"] > div {
      background:#FFFFFF !important;
      color:#182230 !important;
      border:1px solid #CBD5E1 !important;
      border-radius:10px !important;
      box-shadow:none !important;
    }
    [data-testid="stNumberInput"] [data-baseweb="input"] > div,
    [data-testid="stTextInput"] [data-baseweb="input"] > div,
    [data-testid="stDateInput"] [data-baseweb="input"] > div,
    [data-testid="stTextArea"] [data-baseweb="textarea"] > div {
      background:#FFFFFF !important;
      color:#182230 !important;
    }
    [data-testid="stNumberInput"] input,
    [data-testid="stTextInput"] input,
    [data-testid="stDateInput"] input,
    [data-testid="stTextArea"] textarea,
    [data-testid="stSelectbox"] input,
    [data-testid="stMultiSelect"] input,
    input[type="number"], input[type="text"], textarea {
      background:transparent !important;
      color:#182230 !important;
      -webkit-text-fill-color:#182230 !important;
      caret-color:#24466F !important;
      opacity:1 !important;
    }
    [data-testid="stNumberInput"] input::placeholder,
    [data-testid="stTextInput"] input::placeholder,
    [data-testid="stTextArea"] textarea::placeholder {
      color:#98A2B3 !important;
      -webkit-text-fill-color:#98A2B3 !important;
      opacity:1 !important;
    }
    [data-testid="stNumberInput"] [data-baseweb="input"]:focus-within,
    [data-testid="stTextInput"] [data-baseweb="input"]:focus-within,
    [data-testid="stTextArea"] [data-baseweb="textarea"]:focus-within,
    [data-testid="stDateInput"] [data-baseweb="input"]:focus-within,
    [data-testid="stSelectbox"] [data-baseweb="select"] > div:focus-within {
      border-color:#4776A8 !important;
      box-shadow:0 0 0 3px rgba(71,118,168,.15) !important;
    }
    [data-testid="stNumberInput"] button {
      background:#F1F5F9 !important;
      color:#344054 !important;
      border:0 !important;
      border-left:1px solid #E2E8F0 !important;
      border-radius:0 !important;
      box-shadow:none !important;
      min-height:unset !important;
      transform:none !important;
    }
    [data-testid="stNumberInput"] button:hover { background:#E8EEF5 !important; }
    [data-testid="stNumberInput"] button svg { color:#344054 !important; fill:#344054 !important; }

    /* Upload dropzone and the uploaded-file list are both light, readable surfaces. */
    [data-testid="stFileUploader"] { color:#344054 !important; }
    [data-testid="stFileUploader"] section {
      background:#F8FAFC !important;
      border:1.5px dashed #9FB0C4 !important;
      border-radius:16px !important;
      color:#344054 !important;
    }
    [data-testid="stFileUploader"] section * { color:#344054 !important; }
    [data-testid="stFileUploader"] section button {
      background:#24466F !important;
      color:#FFFFFF !important;
      border:1px solid #24466F !important;
      border-radius:9px !important;
    }
    [data-testid="stFileUploader"] section button * { color:#FFFFFF !important; }
    [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"],
    [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] > div,
    [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] > div > div,
    [data-testid="stFileUploader"] [data-testid="stFileUploaderFileName"],
    [data-testid="stFileUploader"] [class*="uploadedFile"],
    [data-testid="stFileUploader"] [class*="UploadedFile"],
    [data-testid="stFileUploader"] [role="listitem"],
    [data-testid="stFileUploader"] section ~ div,
    [data-testid="stFileUploader"] section ~ div > div {
      background:#F1F5F9 !important;
      color:#243447 !important;
      border-color:#D7E0EA !important;
      border-radius:9px !important;
    }
    [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] *,
    [data-testid="stFileUploader"] [data-testid="stFileUploaderFileName"] *,
    [data-testid="stFileUploader"] [class*="uploadedFile"] *,
    [data-testid="stFileUploader"] [class*="UploadedFile"] *,
    [data-testid="stFileUploader"] [role="listitem"] * {
      color:#243447 !important;
      -webkit-text-fill-color:#243447 !important;
    }
    [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] button,
    [data-testid="stFileUploader"] [role="listitem"] button {
      background:#FFFFFF !important;
      color:#344054 !important;
      border:1px solid #CBD5E1 !important;
      box-shadow:none !important;
      min-height:unset !important;
      transform:none !important;
    }

    /* Quiet, consistent cards for each design's quantity and preview. */
    [data-testid="stVerticalBlockBorderWrapper"] {
      background:#FFFFFF !important;
      border:1px solid #E2E8F0 !important;
      border-radius:15px !important;
      box-shadow:0 4px 14px rgba(16,24,40,.035) !important;
      padding:.15rem !important;
    }
    [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stCaptionContainer"] p {
      color:#667085 !important;
    }
    [data-testid="stNumberInput"] label,
    [data-testid="stTextInput"] label,
    [data-testid="stSelectbox"] label {
      color:#475467 !important;
      font-weight:600 !important;
    }
    .stButton button, .stDownloadButton button, [data-testid="stFormSubmitButton"] button {
      background:#24466F !important;
      color:#FFFFFF !important;
      border:1px solid #24466F !important;
      border-radius:11px !important;
      box-shadow:0 3px 8px rgba(36,70,111,.16) !important;
    }
    .stButton button *, .stDownloadButton button *, [data-testid="stFormSubmitButton"] button * {
      color:#FFFFFF !important;
    }
    .stButton button:focus-visible, .stDownloadButton button:focus-visible,
    [data-testid="stFormSubmitButton"] button:focus-visible {
      outline:3px solid rgba(71,118,168,.3) !important;
      outline-offset:2px !important;
    }
    @media (max-width:700px) {
      [data-testid="stVerticalBlockBorderWrapper"] { padding:.1rem !important; }
      [data-testid="stNumberInput"] input { font-size:16px !important; }
      [data-testid="stFileUploader"] section { padding:.85rem !important; }
    }

    </style>""", unsafe_allow_html=True)

    with st.sidebar:
        st.markdown("""<div class='brand-lockup'>
          <div class='brand-kicker'>DTF production workspace</div>
          <div class='brand-name'>kakojee <span>Print Nest</span></div>
          <div class='brand-foot'>PNG · 300 DPI · OPEN ACCESS</div>
        </div>""", unsafe_allow_html=True)
        page = st.radio("WORKSPACE", ["New gangsheet", "Production rules", "About & setup"], label_visibility="visible")
        st.markdown("<div style='height:1.2rem'></div>", unsafe_allow_html=True)
        st.caption("Production defaults are locked to your print workflow.")

    if page == "Production rules":
        st.markdown("<div class='page-eyebrow'>Reference</div><div class='page-title'>Production rules</div>", unsafe_allow_html=True)
        st.markdown("<p class='page-subtitle'>Your standard output settings, kept consistent across every order.</p>", unsafe_allow_html=True)
        a, b, c, d = st.columns(4)
        a.metric("Roll width", "23 in")
        b.metric("Maximum length", "89.9 in")
        c.metric("Cutting gap", "0.5 in")
        d.metric("Export quality", "300 DPI")
        st.markdown("### Artwork handling")
        st.write("Original PNG pixels are preserved. The app does not resize, recolor, redraw or trim artwork. Exact 90° rotation is allowed when it improves the layout.")
        st.info("PNG files without reliable DPI metadata are interpreted at 300 DPI. Confirm intended print dimensions before production.")

    elif page == "About & setup":
        st.markdown("<div class='page-eyebrow'>Workspace guide</div><div class='page-title'>About Print Nest</div>", unsafe_allow_html=True)
        st.markdown("<p class='page-subtitle'>An open-access DTF gangsheet workspace for preparing production-ready transparent PNGs.</p>", unsafe_allow_html=True)
        st.markdown("### How it works")
        st.write("Upload your transparent PNG artwork, enter the copy quantity for each design, and generate one or more sheets automatically. The app keeps identical designs in contiguous runs, fills usable ends of partial rows with the next design, evaluates exact 90° rotations and checks the sheet-length limit.")
        st.warning("The packing method keeps repeated designs together, but can use the open end of a partial row for the next design when dimensions allow. It preserves the 0.5-inch clearance and is a bounded heuristic, not a guaranteed global optimum. Always inspect the sheet previews and copy-count checks before printing.")
        st.write("No sign-in is required. Orders are processed in the active browser session; download your output before closing the page.")

    else:
        st.markdown("<div class='page-eyebrow'>Production workspace</div><div class='page-title'>Build your gangsheet</div><p class='page-subtitle'>Upload original-size PNG artwork, set quantities and prepare organised sheets for transfer printing.</p>", unsafe_allow_html=True)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Film width", "23 in")
        m2.metric("Sheet limit", "89.9 in")
        m3.metric("Cut clearance", "0.5 in")
        m4.metric("Export", "PNG · 300 DPI")

        st.markdown("<div style='height:.4rem'></div><div class='section-kicker'>01 · Artwork</div>", unsafe_allow_html=True)
        st.markdown("### Upload your designs")
        uploads = st.file_uploader(
            "Choose PNG files or drag them here",
            type=["png"], accept_multiple_files=True,
            help="Upload transparent PNG exports from CorelDRAW at the intended print size. Original pixel dimensions are preserved.",
            key="artwork_uploads",
        )

        items = []
        upload_errors = []
        if uploads:
            for i, upload in enumerate(uploads):
                try:
                    item = load_logo(upload, 1, i)
                    items.append(item)
                except Exception as exc:
                    upload_errors.append(f"{upload.name}: {exc}")
            if upload_errors:
                for message in upload_errors:
                    st.error(message)
                st.warning("Fix the rejected PNG file(s) before generating. The app will not silently omit artwork from your order.")

        total_decoded_pixels = sum(x["wpx"] * x["hpx"] for x in items)
        if items and total_decoded_pixels > 100_000_000:
            st.info(
                f"Large artwork batch: {total_decoded_pixels / 1_000_000:.1f} megapixels across {len(items)} designs. "
                "This combined total is not a reason to reduce artwork dimensions. Designs are inspected and rendered one at a time; larger orders may take longer."
            )

        generate_clicked = False
        if items and not upload_errors:
            st.markdown("<div style='height:.45rem'></div><div class='section-kicker'>02 · Quantities</div>", unsafe_allow_html=True)
            st.markdown("### Set print quantities")
            st.caption("Each design stays at its original pixel size. Quantities are applied when you press Generate gangsheet.")
            with st.form("gangsheet_order_form", clear_on_submit=False):
                columns = st.columns(2)
                for i, item in enumerate(items):
                    with columns[i % 2]:
                        with st.container(border=True):
                            image_col, details_col = st.columns([1, 2.4])
                            with image_col:
                                st.image(item["thumbnail"], width=112)
                            with details_col:
                                st.markdown(f"**{item['name']}**")
                                st.caption(f"{item['wpx']:,} × {item['hpx']:,} px · {item['w_in']:.2f} × {item['h_in']:.2f} in")
                                if "assumed" in item["dpi_note"].lower():
                                    st.caption("DPI assumed: 300 · verify size")
                                qty = st.number_input(
                                    "Copies", min_value=1, max_value=500, value=1, step=1,
                                    key=f"qty_{item['hash'][:16]}",
                                )
                            item["qty"] = int(qty)
                total_qty = sum(x["qty"] for x in items)
                st.markdown(f"**Order summary:** {len(items)} designs · {total_qty} total copies")
                generate_clicked = st.form_submit_button("Generate gangsheet", type="primary", use_container_width=True)

        if generate_clicked and items and not upload_errors:
            # Remove previous output before starting to avoid keeping old and new
            # full-resolution PNGs and ZIPs in the session at the same time.
            for key in ("last_sheet_pngs", "last_sheet_previews", "last_sheet_summaries", "last_sheets_zip"):
                st.session_state.pop(key, None)
            try:
                items_by_id = {int(item["id"]): item for item in items}
                with st.status("Preparing production sheets…", expanded=True) as status:
                    st.write("Planning grouped layouts and checking the roll-length limit…")
                    packed_sheets = pack_multiple_sheets(items, DEFAULT_DPI, GAP_IN, ROLL_WIDTH_IN, MAX_LENGTH_IN)
                    st.write(f"Layout planned: {len(packed_sheets)} sheet(s). Rendering at original pixel dimensions…")
                    sheet_pngs, sheet_previews, summaries = [], [], []
                    for sheet_index, sheet in enumerate(packed_sheets, start=1):
                        png_bytes, preview_bytes = render_sheet(
                            sheet["placements"], sheet["height"], sheet["width"], DEFAULT_DPI, items_by_id
                        )
                        sheet_pngs.append(png_bytes)
                        sheet_previews.append(preview_bytes)
                        summaries.append({
                            "width": int(sheet["width"]), "height": int(sheet["height"]),
                            "items": [{"name": x["name"], "qty": int(x["qty"])} for x in sheet["items"]],
                            "copy_count": sum(int(x["qty"]) for x in sheet["items"]),
                        })
                        st.write(f"Rendered sheet {sheet_index} of {len(packed_sheets)}.")

                    st.write("Preparing the combined download…")
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_STORED) as archive:
                        for i, data in enumerate(sheet_pngs, start=1):
                            archive.writestr(f"kakojee_gangsheet_{i:02d}.png", data)
                    st.session_state.last_sheet_pngs = sheet_pngs
                    st.session_state.last_sheet_previews = sheet_previews
                    st.session_state.last_sheet_summaries = summaries
                    st.session_state.last_sheets_zip = zip_buffer.getvalue()
                    status.update(label="Gangsheet generation complete", state="complete", expanded=False)
                st.success(f"Ready: {len(packed_sheets)} sheet(s) · {total_qty} requested copies accounted for.")
            except Exception as exc:
                st.error(f"The gangsheet could not be generated: {exc}")

        if st.session_state.get("last_sheet_pngs"):
            pngs = st.session_state.last_sheet_pngs
            previews = st.session_state.last_sheet_previews
            summaries = st.session_state.last_sheet_summaries
            total_copies = sum(x["copy_count"] for x in summaries)
            total_length = sum(x["height"] for x in summaries) / DEFAULT_DPI
            st.markdown("<div style='height:.6rem'></div><div class='section-kicker'>03 · Production output</div>", unsafe_allow_html=True)
            st.markdown("### Your gangsheet is ready")
            c1, c2, c3 = st.columns(3)
            c1.metric("Sheets", len(pngs))
            c2.metric("Copies accounted for", total_copies)
            c3.metric("Combined film length", f"{total_length:.2f} in")
            if len(pngs) > 1:
                st.info("The order was automatically divided across multiple sheets. Download the ZIP to receive every production PNG.")
            st.download_button(
                "Download all production sheets · ZIP",
                data=st.session_state.last_sheets_zip,
                file_name=f"kakojee_gangsheets_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                mime="application/zip", type="primary", use_container_width=True,
            )
            for i, (data, preview, summary) in enumerate(zip(pngs, previews, summaries), start=1):
                size_w = summary["width"] / DEFAULT_DPI
                size_h = summary["height"] / DEFAULT_DPI
                with st.expander(f"Sheet {i:02d}  ·  {size_w:.2f} × {size_h:.2f} in  ·  {summary['copy_count']} copies", expanded=(i == 1)):
                    st.image(preview, use_container_width=True)
                    st.download_button(
                        f"Download sheet {i:02d} · PNG", data=data,
                        file_name=f"kakojee_gangsheet_{i:02d}.png", mime="image/png",
                        key=f"download_sheet_{APP_BUILD}_{i}", use_container_width=True,
                    )
                    st.markdown("**Copy-count check**")
                    for item in summary["items"]:
                        st.write(f"{item['name']} — **{item['qty']}**")
            st.caption("Production PNGs are transparent, exported at 300 DPI and retain the original artwork pixels. Check every sheet before printing.")


main_app()

"""
Schritt 5: Template befuellen. Rein deterministisch, KEIN LLM, nichts wird gespeichert.
"""
import json
import sys

import pymupdf

FONT = "helv"


def put_text(page, rect, text, max_size=9.0, min_size=6.5, align=0, multiline=False):
    """Text in Box einpassen: Schrift verkleinern, mit Sicherheits-Mindestgrösse."""
    r = pymupdf.Rect(rect)
    size = max_size
    while size >= min_size:
        if multiline:
            ok = page.insert_textbox(r, text, fontsize=size, fontname=FONT, align=align) >= 0
        else:
            width = pymupdf.get_text_length(text, fontname=FONT, fontsize=size)
            ok = width <= r.width - 2
            if ok:
                y = r.y0 + (r.height + size * 0.7) / 2
                x = r.x0 + 1 if align == 0 else r.x0 + (r.width - width) / 2
                page.insert_text((x, y), text, fontsize=size, fontname=FONT)
        if ok:
            return True
        size -= 0.5
    return False


def fill(template_json, template_pdf, data, out_path):
    schema = json.load(open(template_json, encoding="utf-8"))
    doc = pymupdf.open(template_pdf)
    problems = []

    for f in schema["header_fields"]:
        value = (data.get("header") or {}).get(f["key"], "")
        if not value:
            continue
        page = doc[f["page"]]
        rect = pymupdf.Rect(f["rect"])
        if f["mode"] == "replace_placeholder":
            page.draw_rect(rect + (-2, -1, 2, 3), color=None, fill=(1, 1, 1))
            ok = put_text(page, rect, value, max_size=11, align=1)
        else:
            ok = put_text(page, rect, value, max_size=10)
        if not ok:
            problems.append(f"Kopffeld '{f['key']}' passt nicht in die Box")

    rows = schema["table"]["rows"]
    cols = schema["table"]["columns"]
    entries = data.get("rows", [])
    if len(entries) > len(rows):
        raise ValueError(f"{len(entries)} Eintraege, aber das Formular hat nur {len(rows)} Zeilen.")

    for row, entry in zip(rows, entries):
        page = doc[row["page"]]
        for c in cols:
            if c["type"] == "index":
                continue
            val = entry.get(c["key"])
            if val in (None, "", False):
                continue
            cell = pymupdf.Rect(c["x0"] + 1, row["y0"] + 1, c["x1"] - 1, row["y1"] - 1)
            if c["type"] == "checkbox":
                put_text(page, cell, "X", max_size=11, align=1)
                continue
            
            # Textfelder (wie 'stelle' oder 'firma') automatisch mit Umbruch behandeln, falls zu lang
            is_multiline_col = c["key"] in ["stelle", "firma", "bemerkungen", "kontaktperson"]
            ok = put_text(page, cell, str(val), max_size=8, min_size=6.5, multiline=is_multiline_col)
            
            if not ok:
                problems.append(f"Zeile {row['nr']}, {c['key']}: Text zu lang")

    for f in schema.get("free_text", []):
        value = (data.get("free_text") or {}).get(f["key"], "")
        if value and not put_text(doc[f["page"]], f["rect"], value, max_size=10, multiline=True):
            problems.append(f"Freitext '{f['key']}' zu lang")

    doc.save(out_path, garbage=4, deflate=True)
    return problems

"""
Template befuellen. Rein deterministisch, KEIN LLM, nichts wird auf Platte geschrieben
(das fertige PDF wird als Bytes im Arbeitsspeicher erzeugt).

Neu gegenueber v1:
- Einzeiliger Text ist in jeder Zelle vertikal mittig, mehrzeiliger Text als Block mittig
- Beliebig viele Eintraege: die Tabelle wird fortlaufend verlaengert (11, 12, ...), ohne Kopf
  zu wiederholen, wie im Original; Folgeseiten nur wenn die Seite voll ist
- Leere Zeilen im Formular bleiben leer, Eintraege rutschen nicht nach oben
- Platzhalter (__.__.____) und alte Nr. werden per Redaktion entfernt, nicht nur ueberdeckt
"""
import json

import pymupdf

FONT = "helv"


def _len(text, size):
    return pymupdf.get_text_length(text, fontname=FONT, fontsize=size)


def _wrap(text, width, size):
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if _len(trial, size) <= width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def put_text(page, rect, text, max_size=9.0, min_size=6.5, single_min=None, align=0, wrap_ok=False):
    """Text in Box einpassen. Erst einzeilig (bis single_min), dann umbrochen (bis min_size)."""
    text = str(text).strip()
    if not text:
        return True
    r = pymupdf.Rect(rect)
    avail = r.width - 2
    single_min = min_size if single_min is None else single_min

    size = max_size
    while size >= single_min - 1e-6:
        w = _len(text, size)
        if w <= avail:
            y = r.y0 + (r.height + size * 0.7) / 2
            x = r.x0 + 1 if align == 0 else r.x0 + (r.width - w) / 2
            page.insert_text((x, y), text, fontsize=size, fontname=FONT)
            return True
        size -= 0.5

    if not wrap_ok:
        return False

    size = min(max_size, 7.5)
    while size >= min_size - 1e-6:
        lines = _wrap(text, avail, size)
        lh = size * 1.15
        total = lh * len(lines)
        if all(_len(l, size) <= avail for l in lines) and total <= r.height - 2:
            y0 = r.y0 + (r.height - total) / 2
            for k, line in enumerate(lines):
                page.insert_text((r.x0 + 1, y0 + lh * k + size * 0.85), line, fontsize=size, fontname=FONT)
            return True
        size -= 0.5
    return False


def _has_content(entry):
    return any(v not in (None, "", False) for v in entry.values())


def _redact(page, rects):
    for r in rects:
        page.add_redact_annot(pymupdf.Rect(r))
    if rects:
        page.apply_redactions(
            images=pymupdf.PDF_REDACT_IMAGE_NONE,
            graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
        )


LINE = 0.48          # Linienstaerke wie im Original (gefuellte Rechtecke)
BOTTOM_MARGIN = 28   # unterer Rand fuer Folgezeilen
TOP_NEW_PAGE = 28    # oberer Rand auf zusaetzlichen Seiten
LABEL_TEXT = "Mitteilungen und Informationen:"


def _vline(page, x, y0, y1):
    page.draw_rect(pymupdf.Rect(x - LINE / 2, y0, x + LINE / 2, y1), color=None, fill=(0, 0, 0))


def _hline(page, y, x0, x1):
    page.draw_rect(pymupdf.Rect(x0, y - LINE / 2, x1, y + LINE / 2), color=None, fill=(0, 0, 0))


def build_pdf_bytes(template_json, template_pdf, data):
    """
    Gibt (pdf_bytes, probleme) zurueck.

    Aufbau wie im Original: Hauptseite mit Kopf und Zeilen 1 bis 8, danach Zeilen 9 und 10.
    Weitere Eintraege setzen die Tabelle einfach fort (Zeile 11, 12, ...) und laufen bei Bedarf
    auf Folgeseiten weiter, ohne Kopf zu wiederholen. 'Mitteilungen und Informationen' steht
    einmal, nach der letzten Zeile.
    """
    schema = json.load(open(template_json, encoding="utf-8"))
    tpl = pymupdf.open(template_pdf)
    base_rows = schema["table"]["rows"]
    cols = schema["table"]["columns"]
    xs = [c["x0"] for c in cols] + [cols[-1]["x1"]]
    entries = data.get("rows", [])
    problems = []

    filled = [i for i, e in enumerate(entries) if _has_content(e)]
    total = max(len(base_rows), (filled[-1] + 1) if filled else 0)
    extra = total - len(base_rows)

    doc = pymupdf.open()
    doc.insert_pdf(tpl)

    # Kopffelder (nur Hauptseite)
    header = data.get("header") or {}
    by_page = {}
    for f in schema["header_fields"]:
        if header.get(f["key"]):
            by_page.setdefault(f["page"], []).append(f)
    for pno, fields in by_page.items():
        page = doc[pno]
        _redact(page, [pymupdf.Rect(f["rect"]) + (-1, -1, 1, 1)
                       for f in fields if f["mode"] == "replace_placeholder"])
        for f in fields:
            value = header[f["key"]]
            if f["mode"] == "replace_placeholder":
                ok = put_text(page, f["rect"], value, max_size=11, align=1)
            else:
                ok = put_text(page, f["rect"], value, max_size=10, min_size=6.5)
            if not ok:
                problems.append(f"Kopffeld '{f['label']}' passt nicht in die Box")

    # Tabelle fortsetzen, falls mehr Eintraege als Zeilen im Original
    rows = [dict(r) for r in base_rows]
    last = base_rows[-1]
    row_h = sum(r["y1"] - r["y0"] for r in base_rows) / len(base_rows)
    cur_page, y = last["page"], last["y1"]
    mit_label_rect = None
    if extra > 0:
        for f in schema.get("free_text", []):
            hits = doc[f["page"]].search_for(LABEL_TEXT)
            if hits:
                mit_label_rect = (f["page"], hits[0])
                _redact(doc[f["page"]], [hits[0] + (-1, -1, 1, 1)])  # Label wandert ans Ende
    page_w, page_h = doc[cur_page].rect.width, doc[cur_page].rect.height
    for k in range(extra):
        if y + row_h > page_h - BOTTOM_MARGIN:
            doc.new_page(width=page_w, height=page_h)
            cur_page, y = len(doc) - 1, TOP_NEW_PAGE
            _hline(doc[cur_page], y, xs[0], xs[-1])
        page = doc[cur_page]
        y0, y1 = y, y + row_h
        for x in xs:
            _vline(page, x, y0, y1)
        _hline(page, y1, xs[0], xs[-1])
        nr = len(base_rows) + k + 1
        put_text(page, pymupdf.Rect(cols[0]["x0"] + 1, y0 + 1, cols[0]["x1"] - 1, y1 - 1),
                 str(nr), max_size=8, min_size=5, align=1)
        rows.append({"page": cur_page, "nr": nr, "y0": y0, "y1": y1})
        y = y1

    # Zeileninhalte
    for i, entry in enumerate(entries):
        if i >= len(rows) or not _has_content(entry):
            continue
        row = rows[i]
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
            wrap_ok = c["key"] in ("firma", "kontaktperson", "stelle", "bemerkungen")
            ok = put_text(page, cell, val, max_size=8, min_size=6.5,
                          single_min=7.0 if wrap_ok else 6.5, wrap_ok=wrap_ok)
            if not ok:
                problems.append(f"Bewerbung {i + 1}, {c['label']}: Text zu lang")

    # Freitext
    for f in schema.get("free_text", []):
        value = (data.get("free_text") or {}).get(f["key"], "")
        if extra > 0 and mit_label_rect:
            # Label und Textfeld nach der letzten Zeile (einmalig)
            if y + 8 + 60 > page_h - BOTTOM_MARGIN:
                doc.new_page(width=page_w, height=page_h)
                cur_page, y = len(doc) - 1, TOP_NEW_PAGE
            page = doc[cur_page]
            ly = y + 8
            page.insert_text((18.24, ly + 9.5), LABEL_TEXT, fontsize=10, fontname="hebo")
            box = pymupdf.Rect(xs[0], ly + 16, xs[-1], page_h - 25)
        else:
            page = doc[f["page"]]
            box = pymupdf.Rect(f["rect"])
        if value and page.insert_textbox(box, value, fontsize=10, fontname=FONT) < 0:
            problems.append(f"Freitext '{f['label']}' zu lang")

    return doc.tobytes(garbage=4, deflate=True), problems

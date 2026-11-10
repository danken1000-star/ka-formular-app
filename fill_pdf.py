"""
Template befuellen. Rein deterministisch, KEIN LLM, nichts wird auf Platte geschrieben
(das fertige PDF wird als Bytes im Arbeitsspeicher erzeugt).

Neu gegenueber v1:
- Einzeiliger Text ist in jeder Zelle vertikal mittig, mehrzeiliger Text als Block mittig
- Beliebig viele Eintraege: pro 10 Zeilen wird ein weiteres Blatt (2 Seiten) angehaengt,
  Nr.-Spalte wird dort fortlaufend nummeriert (11, 12, ...)
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


def build_pdf_bytes(template_json, template_pdf, data):
    """Gibt (pdf_bytes, probleme) zurueck."""
    schema = json.load(open(template_json, encoding="utf-8"))
    tpl = pymupdf.open(template_pdf)
    n_tpl_pages = len(tpl)
    rows = schema["table"]["rows"]
    cols = schema["table"]["columns"]
    per_sheet = len(rows)
    entries = data.get("rows", [])
    problems = []

    filled = [i for i, e in enumerate(entries) if _has_content(e)]
    sheets = max(1, -(-(filled[-1] + 1) // per_sheet)) if filled else 1

    doc = pymupdf.open()
    for _ in range(sheets):
        doc.insert_pdf(tpl)

    index_col = next((c for c in cols if c["type"] == "index"), None)
    header = data.get("header") or {}

    # Kopffelder auf jedem Blatt
    for s in range(sheets):
        off = s * n_tpl_pages
        by_page = {}
        for f in schema["header_fields"]:
            if header.get(f["key"]):
                by_page.setdefault(f["page"] + off, []).append(f)
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

    # Fortlaufende Nummern auf Folgeblaettern (11, 12, ...)
    if index_col:
        for s in range(1, sheets):
            by_page = {}
            for row in rows:
                by_page.setdefault(row["page"] + s * n_tpl_pages, []).append(row)
            for pno, rws in by_page.items():
                page = doc[pno]
                cells = [pymupdf.Rect(index_col["x0"] + 1.5, r["y0"] + 1.5, index_col["x1"] - 1.5, r["y1"] - 1.5) for r in rws]
                _redact(page, cells)
                for r, cell in zip(rws, cells):
                    put_text(page, cell, str(r["nr"] + s * per_sheet), max_size=7, min_size=5, align=1)

    # Tabellenzeilen
    for i, entry in enumerate(entries):
        if not _has_content(entry):
            continue
        s, local = divmod(i, per_sheet)
        row = rows[local]
        page = doc[row["page"] + s * n_tpl_pages]
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
            ok = put_text(page, cell, val, max_size=8, min_size=6.5, single_min=7.0 if wrap_ok else 6.5, wrap_ok=wrap_ok)
            if not ok:
                problems.append(f"Bewerbung {i + 1}, {c['label']}: Text zu lang")

    # Freitext (nur erstes Blatt)
    for f in schema.get("free_text", []):
        value = (data.get("free_text") or {}).get(f["key"], "")
        if value:
            page = doc[f["page"]]
            if page.insert_textbox(pymupdf.Rect(f["rect"]), value, fontsize=10, fontname=FONT) < 0:
                problems.append(f"Freitext '{f['label']}' zu lang")

    return doc.tobytes(garbage=4, deflate=True), problems

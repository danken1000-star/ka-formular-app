import json
import re
from pathlib import Path

import streamlit as st

from fill_pdf import build_pdf_bytes

st.set_page_config(page_title="KA Formular-Assistent", layout="wide")

st.title("📄 KA Formular-Assistent (Kompetenzzentrum Arbeit)")
st.write("Füllen Sie das starre PDF-Formular bequem digital aus, ganz ohne Medienbruch.")
st.warning(
    "Testversion: Bitte nur erfundene Daten eingeben. Die App speichert und protokolliert keine Eingaben, "
    "läuft aber in einer Testumgebung, die nicht für echte Personendaten vorgesehen ist."
)

TEMPLATE_JSON = "template.json"
TEMPLATE_PDF = "template_clean.pdf"

if not Path(TEMPLATE_JSON).exists() or not Path(TEMPLATE_PDF).exists():
    st.error("Template-Dateien fehlen im Ordner!")
    st.stop()

schema = json.loads(Path(TEMPLATE_JSON).read_text(encoding="utf-8"))
MIN_ROWS = len(schema["table"]["rows"])  # so viele Zeilen hat das Original
MAX_ROWS = 40
ART = {"schr.": "schr", "tel.": "tel", "pers.": "pers", "Spontan": "spontan", "Mail": "mail"}
DATE_RE = re.compile(r"^\d{1,2}\.\d{1,2}\.\d{4}$")

if "n_rows" not in st.session_state:
    st.session_state.n_rows = MIN_ROWS

st.subheader("1. Stammdaten")
c1, c2, c3, c4 = st.columns(4)
name = c1.text_input("Name, Vorname", placeholder="Muster Erika")
coach = c2.text_input("Coach / Jobcoach", placeholder="Beispiel Hans")
period_from = c3.text_input("Bewerbungen von", placeholder="TT.MM.JJJJ")
period_to = c4.text_input("Bewerbungen bis", placeholder="TT.MM.JJJJ")

st.subheader("2. Arbeitsbemühungen (Bewerbungen)")
rows_data = []
for i in range(st.session_state.n_rows):
    st.markdown(f"**Bewerbung Nr. {i + 1}**")
    rc1, rc2, rc3, rc4, rc5, rc6, rc7 = st.columns([1, 2, 1, 3, 1.5, 2, 1.5])
    datum = rc1.text_input(f"Datum {i + 1}", key=f"datum_{i}", placeholder="TT.MM.JJJJ")
    art = rc2.multiselect(f"Art {i + 1}", list(ART), key=f"art_{i}", placeholder="Auswählen")
    pensum_raw = rc3.text_input(f"Pensum {i + 1}", key=f"pensum_{i}", placeholder="100%").strip()
    pensum = f"{pensum_raw}%" if pensum_raw and not pensum_raw.endswith("%") else pensum_raw
    firma = rc4.text_input(f"Firma / Strasse, Ort {i + 1}", key=f"firma_{i}", placeholder="Beispiel AG, Musterstrasse 1, 3000 Bern")
    telefon = rc5.text_input(f"Telefon {i + 1}", key=f"telefon_{i}", placeholder="031 000 00 00")
    kontakt = rc6.text_input(f"Kontaktperson, Funktion {i + 1}", key=f"kontakt_{i}", placeholder="Frau Test, HR")
    stelle = rc7.text_input(f"Stelle als {i + 1}", key=f"stelle_{i}", placeholder="Sachbearbeiterin")
    bemerkungen = st.text_input(f"Bemerkungen Nr. {i + 1}", key=f"bem_{i}")

    row = {
        "datum": datum, "firma": firma, "telefon": telefon, "kontaktperson": kontakt,
        "stelle": stelle, "pensum": pensum, "bemerkungen": bemerkungen,
    }
    for label in art:
        row[ART[label]] = True
    rows_data.append(row)

b1, b2, _ = st.columns([2, 2, 6])
if b1.button("➕ Weitere Bewerbung hinzufügen", disabled=st.session_state.n_rows >= MAX_ROWS):
    st.session_state.n_rows += 1
    st.rerun()
if b2.button("➖ Letzte Zeile entfernen", disabled=st.session_state.n_rows <= MIN_ROWS):
    st.session_state.n_rows -= 1
    st.rerun()

st.subheader("3. Mitteilungen und Informationen")
mitteilungen = st.text_area("Mitteilungen", "")

st.divider()
bad_dates = [str(i + 1) for i, r in enumerate(rows_data) if r["datum"] and not DATE_RE.match(r["datum"].strip())]
if bad_dates:
    st.warning(f"Datumsformat bitte als TT.MM.JJJJ eingeben (Bewerbung Nr. {', '.join(bad_dates)}).")

data = {
    "header": {"period_from": period_from, "period_to": period_to, "name": name, "coach": coach},
    "rows": rows_data,
    "free_text": {"mitteilungen": mitteilungen},
}
try:
    pdf_bytes, problems = build_pdf_bytes(TEMPLATE_JSON, TEMPLATE_PDF, data)  # nur im Arbeitsspeicher
    if problems:
        st.warning("Hinweise zum PDF:\n\n" + "\n".join(f"- {p}" for p in problems))
    st.download_button(
        "📥 Fertiges PDF herunterladen", data=pdf_bytes,
        file_name="Arbeitsbemuehungen_ausgefuellt.pdf", mime="application/pdf", type="primary",
    )
except Exception as e:
    st.error(f"Fehler bei der Generierung: {e}")

import json
from pathlib import Path
import tempfile
import streamlit as st
from fill_pdf import fill

st.set_page_config(page_title="KA Formular-Assistent", layout="wide")

st.title("📄 KA Formular-Assistent (Kompetenzzentrum Arbeit)")
st.write("Füllen Sie das starre PDF-Formular bequem digital aus – ganz ohne Medienbruch.")

TEMPLATE_JSON = "template.json"
TEMPLATE_PDF = "template_clean.pdf"

if not Path(TEMPLATE_JSON).exists() or not Path(TEMPLATE_PDF).exists():
    st.error("Template-Dateien fehlen im Ordner!")
    st.stop()

schema = json.loads(Path(TEMPLATE_JSON).read_text(encoding="utf-8"))

with st.form("formular_form"):
    st.subheader("1. Stammdaten")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        name = st.text_input("Name, Vorname", "Muster Erika")
    with col2:
        coach = st.text_input("Coach / Jobcoach", "Fahrer Pitamber")
    with col3:
        period_from = st.text_input("Bewerbungen von", "01.11.2026")
    with col4:
        period_to = st.text_input("Bewerbungen bis", "30.11.2026")

    st.subheader("2. Arbeitsbemühungen (Bewerbungen)")
    
    rows_data = []
    cols_def = schema["table"]["columns"]

    for i, r_meta in enumerate(schema["table"]["rows"]):
        st.markdown(f"**Bewerbung Nr. {r_meta['nr']}**")
        rc1, rc2, rc3, rc4, rc5, rc6, rc7 = st.columns([1, 1, 1, 3, 1.5, 2, 1.5])
        
        with rc1:
            datum = st.text_input(f"Datum {i+1}", key=f"datum_{i}", placeholder="TT.MM.JJJJ")
        with rc2:
            art = st.selectbox(f"Art {i+1}", ["schr.", "tel.", "pers.", "Spontan", "Mail"], key=f"art_{i}")
        with rc3:
            pensum_raw = st.text_input(f"Pensum {i+1}", key=f"pensum_{i}", placeholder="100%")
            pensum_clean = pensum_raw.strip()
            if pensum_clean and not pensum_clean.endswith("%"):
                pensum = f"{pensum_clean}%"
            else:
                pensum = pensum_clean
        with rc4:
            firma = st.text_input(f"Firma / Ort {i+1}", key=f"firma_{i}")
        with rc5:
            telefon = st.text_input(f"Telefon {i+1}", key=f"telefon_{i}")
        with rc6:
            kontakt = st.text_input(f"Kontaktperson {i+1}", key=f"kontakt_{i}")
        with rc7:
            stelle = st.text_input(f"Stelle als {i+1}", key=f"stelle_{i}")

        bemerkungen = st.text_input(f"Bemerkungen Nr. {r_meta['nr']}", key=f"bem_{i}")

        row_dict = {
            "datum": datum,
            "firma": firma,
            "telefon": telefon,
            "kontaktperson": kontakt,
            "stelle": stelle,
            "pensum": pensum,
            "bemerkungen": bemerkungen,
        }
        if art == "schr.": row_dict["schr"] = True
        elif art == "tel.": row_dict["tel"] = True
        elif art == "pers.": row_dict["pers"] = True
        elif art == "Spontan": row_dict["spontan"] = True
        elif art == "Mail": row_dict["mail"] = True

        if datum or firma:
            rows_data.append(row_dict)

    st.subheader("3. Mitteilungen und Informationen")
    mitteilungen = st.text_area("Mitteilungen", "")

    submitted = st.form_submit_button("PDF generieren & herunterladen")

if submitted:
    data = {
        "header": {
            "period_from": period_from,
            "period_to": period_to,
            "name": name,
            "coach": coach,
        },
        "rows": rows_data,
        "free_text": {
            "mitteilungen": mitteilungen
        }
    }

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        out_path = tmp.name

    try:
        problems = fill(TEMPLATE_JSON, TEMPLATE_PDF, data, out_path)
        if problems:
            st.warning(f"PDF generiert, aber mit Hinweisen: {problems}")
        else:
            st.success("PDF erfolgreich und fehlerfrei generiert!")

        with open(out_path, "rb") as f:
            st.download_button(
                label="📥 Fertiges PDF herunterladen",
                data=f,
                file_name="Arbeitsbemuehungen_ausgefuellt.pdf",
                mime="application/pdf"
            )
    except Exception as e:
        st.error(f"Fehler bei der Generierung: {e}")

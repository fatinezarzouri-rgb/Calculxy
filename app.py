import re
import tempfile
from io import BytesIO

import fitz
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Pressio Extractor",
    layout="wide"
)

st.title("Extraction automatique Pf / Pl / EM depuis PDF")

st.write(
    """
Importer un PDF géotechnique contenant des logs pressiométriques.
L'application extrait automatiquement :

- Numéro de page
- Nom du sondage
- Profondeur
- Pf
- Pl
- EM

Puis exporte un fichier Excel.
"""
)


# ---------------------------------------------------
# EXTRACTION TEXTE PDF
# ---------------------------------------------------

def extract_text_from_pdf(uploaded_file):
    text_pages = []

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded_file.read())
        pdf_path = tmp.name

    doc = fitz.open(pdf_path)

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        text = page.get_text("text")

        text_pages.append({
            "page": page_num + 1,
            "text": text
        })

    doc.close()

    return text_pages


# ---------------------------------------------------
# EXTRACTION NOM SONDAGE
# ---------------------------------------------------

def extract_sondage(text):

    patterns = [
        r"(SP[_\- ]?[A-Za-z0-9_\-]+)",
        r"Sondage\s*[:\-]?\s*([A-Za-z0-9_\-]+)"
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            return match.group(1).replace(" ", "_")

    return "NON_DETECTE"


# ---------------------------------------------------
# EXTRACTION DONNEES PRESSIO
# ---------------------------------------------------

def extract_pressio_data(text, page_number):

    results = []

    sondage = extract_sondage(text)

    # Normalisation texte
    clean_text = text.replace(",", ".")

    lines = clean_text.splitlines()

    for line in lines:

        line = line.strip()

        # Cherche lignes numériques
        numbers = re.findall(r"\d+\.\d+|\d+", line)

        if len(numbers) >= 4:

            try:
                values = [float(x) for x in numbers[:4]]

                profondeur = values[0]
                pf = values[1]
                pl = values[2]
                em = values[3]

                # Filtres qualité
                if (
                    0 <= profondeur <= 100
                    and 0 <= pf <= 50
                    and 0 <= pl <= 100
                    and 0 <= em <= 10000
                ):

                    results.append({
                        "Page": page_number,
                        "Sondage": sondage,
                        "Profondeur (m)": profondeur,
                        "Pf (MPa)": pf,
                        "Pl (MPa)": pl,
                        "EM (MPa)": em
                    })

            except:
                pass

    return results


# ---------------------------------------------------
# MAIN
# ---------------------------------------------------

uploaded_file = st.file_uploader(
    "Importer un PDF",
    type=["pdf"]
)

if uploaded_file:

    with st.spinner("Extraction en cours..."):

        pages = extract_text_from_pdf(uploaded_file)

        all_results = []

        for page_data in pages:

            page_number = page_data["page"]
            text = page_data["text"]

            extracted = extract_pressio_data(text, page_number)

            all_results.extend(extracted)

        if len(all_results) == 0:

            st.error(
                "Aucune donnée détectée.\n\n"
                "Le PDF est peut-être scanné image."
            )

        else:

            df = pd.DataFrame(all_results)

            st.success(f"{len(df)} lignes extraites.")

            st.dataframe(
                df,
                use_container_width=True
            )

            # Export Excel
            output = BytesIO()

            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                df.to_excel(
                    writer,
                    index=False,
                    sheet_name="Pressio"
                )

            output.seek(0)

            st.download_button(
                label="Télécharger Excel",
                data=output,
                file_name="pressio_extraction.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

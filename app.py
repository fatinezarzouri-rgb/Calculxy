import re
from io import BytesIO

import pandas as pd
import pdfplumber
import streamlit as st


# =========================================
# EXTRACTION DES DONNÉES
# =========================================
def extract_pl_em_from_pdf(pdf_file):
    rows = []

    with pdfplumber.open(pdf_file) as pdf:

        for page_number, page in enumerate(pdf.pages, start=1):

            text = page.extract_text()

            if not text:
                continue

            lines = text.split("\n")

            for line in lines:

                # Extraire tous les nombres
                numbers = re.findall(r"\d+[.,]?\d*", line)

                # On cherche minimum 3 valeurs :
                # profondeur + pL + EM
                if len(numbers) >= 3:

                    try:
                        profondeur = float(numbers[0].replace(",", "."))
                        pl = float(numbers[-2].replace(",", "."))
                        em = float(numbers[-1].replace(",", "."))

                        rows.append({
                            "Page": page_number,
                            "Profondeur (m)": profondeur,
                            "pL": pl,
                            "EM": em,
                            "Ligne originale": line
                        })

                    except:
                        pass

    df = pd.DataFrame(rows)

    return df


# =========================================
# EXPORT EXCEL
# =========================================
def convert_to_excel(df):

    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Extraction")

    output.seek(0)

    return output


# =========================================
# INTERFACE STREAMLIT
# =========================================
st.set_page_config(
    page_title="Extracteur pL / EM",
    layout="centered"
)

st.title("📄 Extracteur pL / EM")

st.write(
    """
    Importe un PDF pressiométrique  
    puis télécharge automatiquement le fichier Excel.
    """
)

# =========================================
# IMPORT PDF
# =========================================
uploaded_pdf = st.file_uploader(
    "Importer un PDF",
    type=["pdf"]
)

# =========================================
# TRAITEMENT
# =========================================
if uploaded_pdf is not None:

    st.info("Extraction en cours...")

    df = extract_pl_em_from_pdf(uploaded_pdf)

    if df.empty:

        st.error("❌ Aucune donnée détectée.")

    else:

        st.success("✔️ Extraction terminée")

        # Affichage tableau
        st.dataframe(df, use_container_width=True)

        # Excel
        excel_file = convert_to_excel(df)

        st.download_button(
            label="📥 Télécharger Excel",
            data=excel_file,
            file_name="extraction_pL_EM.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

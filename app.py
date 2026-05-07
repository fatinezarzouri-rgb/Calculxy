import re
from io import BytesIO

import pandas as pd
import streamlit as st
from pypdf import PdfReader


# ==========================================
# EXTRACTION PDF
# ==========================================
def extract_pl_em(pdf_file):

    rows = []

    reader = PdfReader(pdf_file)

    for page_number, page in enumerate(reader.pages, start=1):

        text = page.extract_text()

        if not text:
            continue

        lines = text.split("\n")

        for line in lines:

            # Extraire tous les nombres
            numbers = re.findall(r"\d+[.,]?\d*", line)

            # minimum profondeur + pL + EM
            if len(numbers) >= 3:

                try:
                    profondeur = float(numbers[0].replace(",", "."))
                    pl = float(numbers[-2].replace(",", "."))
                    em = float(numbers[-1].replace(",", "."))

                    rows.append({
                        "Page": page_number,
                        "Profondeur": profondeur,
                        "pL": pl,
                        "EM": em,
                        "Texte": line
                    })

                except:
                    pass

    return pd.DataFrame(rows)


# ==========================================
# EXPORT EXCEL
# ==========================================
def to_excel(df):

    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)

    output.seek(0)

    return output


# ==========================================
# STREAMLIT UI
# ==========================================
st.set_page_config(page_title="Extracteur pL EM")

st.title("📄 Extracteur pL / EM")

uploaded_file = st.file_uploader(
    "Importer un PDF",
    type=["pdf"]
)

if uploaded_file is not None:

    st.info("Lecture du PDF...")

    df = extract_pl_em(uploaded_file)

    if df.empty:

        st.error("Aucune donnée trouvée")

    else:

        st.success("Extraction terminée ✔️")

        st.dataframe(df)

        excel = to_excel(df)

        st.download_button(
            label="📥 Télécharger Excel",
            data=excel,
            file_name="extraction_pL_EM.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

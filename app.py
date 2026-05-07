import re
from io import BytesIO

import fitz
import pandas as pd
import streamlit as st


def extract_pl_em_from_pdf(pdf_file):
    rows = []

    pdf_bytes = pdf_file.read()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    for page_index, page in enumerate(doc, start=1):
        text = page.get_text("text")

        for line in text.splitlines():
            line = line.strip()

            if not line:
                continue

            if "/" in line:
                continue

            nums = re.findall(r"\d+(?:[.,]\d+)?", line)

            if len(nums) < 3:
                continue

            values = [float(x.replace(",", ".")) for x in nums]

            for i in range(len(values) - 2):
                profondeur = values[i]
                pl = values[i + 1]
                em = values[i + 2]

                if 0 <= profondeur <= 100 and 0 < pl <= 20 and 0 < em <= 500:
                    rows.append({
                        "Page": page_index,
                        "Profondeur": profondeur,
                        "pL": pl,
                        "EM": em,
                        "Ligne": line
                    })
                    break

    df = pd.DataFrame(rows)

    if not df.empty:
        df = df.drop_duplicates(subset=["Page", "Profondeur", "pL", "EM"])

    return df


def to_excel(df):
    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="pL_EM")

    output.seek(0)
    return output


st.set_page_config(page_title="Extracteur pL / EM", layout="centered")

st.title("📄 Extracteur pL / EM")

uploaded_pdf = st.file_uploader("Importer un PDF", type=["pdf"])

if uploaded_pdf is not None:
    st.info("Extraction en cours...")

    df = extract_pl_em_from_pdf(uploaded_pdf)

    if df.empty:
        st.error("Aucune vraie valeur pL / EM trouvée.")
    else:
        st.success("Extraction terminée ✔️")
        st.dataframe(df, use_container_width=True)

        excel_file = to_excel(df)

        st.download_button(
            "📥 Télécharger Excel",
            data=excel_file,
            file_name="extraction_pL_EM.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

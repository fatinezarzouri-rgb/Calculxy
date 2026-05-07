import re
from io import BytesIO

import pandas as pd
import streamlit as st
import pytesseract
from pdf2image import convert_from_bytes


def extract_pl_em_from_pdf(pdf_file):
    rows = []

    pdf_bytes = pdf_file.read()
    images = convert_from_bytes(pdf_bytes, dpi=300)

    for page_num, image in enumerate(images, start=1):
        text = pytesseract.image_to_string(image, lang="eng")

        for line in text.splitlines():
            line = line.strip()

            if not line:
                continue

            if "date" in line.lower() or "/" in line:
                continue

            nums = re.findall(r"\d+(?:[.,]\d+)?", line)

            if len(nums) < 3:
                continue

            vals = [float(x.replace(",", ".")) for x in nums]

            for i in range(len(vals) - 2):
                profondeur = vals[i]
                pl = vals[i + 1]
                em = vals[i + 2]

                if 0 <= profondeur <= 40 and 0.1 <= pl <= 20 and 1 <= em <= 500:
                    rows.append({
                        "Page": page_num,
                        "Profondeur": profondeur,
                        "pL": pl,
                        "EM": em,
                        "Ligne OCR": line
                    })
                    break

    df = pd.DataFrame(rows)

    if not df.empty:
        df = df.drop_duplicates()

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
    st.info("Extraction OCR en cours...")

    df = extract_pl_em_from_pdf(uploaded_pdf)

    if df.empty:
        st.error("Aucune donnée trouvée.")
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

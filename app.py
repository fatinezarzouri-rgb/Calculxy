import re
from io import BytesIO

import fitz
import pandas as pd
import streamlit as st


st.set_page_config(page_title="PDF vers Excel", layout="wide")
st.title("Extraction des sondages PDF vers Excel")


def clean_number(value):
    return value.replace(" ", "").replace(",", ".")


def extract_data(text, page_number):
    sondage_match = re.search(r"Sondage\s*[:\-]?\s*([A-Za-z0-9_]+)", text)
    x_match = re.search(r"X\s*[:\-]?\s*([\d\s.,]+)", text)
    y_match = re.search(r"Y\s*[:\-]?\s*([\d\s.,]+)", text)

    if not sondage_match:
        return None

    return {
        "Page": page_number,
        "Nom sondage": sondage_match.group(1),
        "X": clean_number(x_match.group(1)) if x_match else "",
        "Y": clean_number(y_match.group(1)) if y_match else "",
    }


pdf_file = st.file_uploader("Importer un fichier PDF", type=["pdf"])

if pdf_file:
    try:
        doc = fitz.open(stream=pdf_file.read(), filetype="pdf")
        results = []

        progress = st.progress(0)

        for i, page in enumerate(doc):
            text = page.get_text()
            row = extract_data(text, i + 1)

            if row:
                results.append(row)

            progress.progress((i + 1) / len(doc))

        if results:
            df = pd.DataFrame(results)
            st.success(f"{len(df)} sondages trouvés")
            st.dataframe(df, width="stretch")

            output = BytesIO()

            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="Sondages")

            output.seek(0)

            st.download_button(
                label="Télécharger Excel",
                data=output,
                file_name="sondages.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        else:
            st.warning("Aucun sondage trouvé dans le PDF.")

    except Exception as e:
        st.error("Erreur pendant le traitement du PDF")
        st.code(str(e))

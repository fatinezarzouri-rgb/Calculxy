import re
from io import BytesIO

import fitz
import pandas as pd
import streamlit as st


st.set_page_config(page_title="PDF vers Excel")

st.title("Extraction PDF vers Excel")


def clean_number(value):
    value = value.replace(" ", "")
    value = value.replace(",", ".")

    try:
        return float(value)
    except:
        return None


def extract_data(text):

    sondage = None
    x = None
    y = None

    sondage_match = re.search(
        r"Sondage\s*:\s*([A-Za-z0-9_\-]+)",
        text
    )

    if sondage_match:
        sondage = sondage_match.group(1)

    x_match = re.search(
        r"X\s*:\s*([\d\s,\.]+)",
        text
    )

    y_match = re.search(
        r"Y\s*:\s*([\d\s,\.]+)",
        text
    )

    if x_match:
        x = clean_number(x_match.group(1))

    if y_match:
        y = clean_number(y_match.group(1))

    return {
        "Nom sondage": sondage,
        "X": x,
        "Y": y
    }


uploaded_pdf = st.file_uploader(
    "Importer le PDF",
    type=["pdf"]
)

if uploaded_pdf:

    try:

        pdf_bytes = uploaded_pdf.read()

        doc = fitz.open(
            stream=pdf_bytes,
            filetype="pdf"
        )

        results = []

        progress = st.progress(0)

        for i, page in enumerate(doc):

            text = page.get_text()

            row = extract_data(text)

            row["Page"] = i + 1

            if row["Nom sondage"]:
                results.append(row)

            progress.progress((i + 1) / len(doc))

        if results:

            df = pd.DataFrame(results)

            st.success(f"{len(df)} sondages trouvés")

            st.dataframe(df, width="stretch")

            output = BytesIO()

            with pd.ExcelWriter(
                output,
                engine="openpyxl"
            ) as writer:

                df.to_excel(
                    writer,
                    index=False
                )

            output.seek(0)

            st.download_button(
                label="Télécharger Excel",
                data=output,
                file_name="sondages.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        else:
            st.warning("Aucune donnée trouvée")

    except Exception as e:

        st.error("Erreur")

        st.code(str(e))

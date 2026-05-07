import re
import gc
from io import BytesIO

import fitz
import pandas as pd
import pytesseract
import streamlit as st
from PIL import Image


st.set_page_config(page_title="PDF OCR vers Excel", layout="wide")
st.title("Extraction OCR PDF vers Excel")


def clean_number(value):
    if not value:
        return None
    value = value.replace(" ", "").replace(",", ".")
    try:
        return float(value)
    except ValueError:
        return None


def extract_data(text):
    sondage_match = re.search(r"Sondage\s*[:\-]?\s*([A-Za-z0-9_\-]+)", text, re.I)
    x_match = re.search(r"X\s*[:\-]?\s*([\d\s]+[,\.]\d+)", text, re.I)
    y_match = re.search(r"Y\s*[:\-]?\s*([\d\s]+[,\.]\d+)", text, re.I)

    return {
        "Nom sondage": sondage_match.group(1) if sondage_match else None,
        "X": clean_number(x_match.group(1)) if x_match else None,
        "Y": clean_number(y_match.group(1)) if y_match else None,
    }


def ocr_page(page):
    pix = page.get_pixmap(dpi=120)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    text = pytesseract.image_to_string(
        img,
        lang="eng",
        config="--psm 6"
    )

    del pix
    del img
    gc.collect()

    return text


def create_excel(data):
    df = pd.DataFrame(data)
    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Sondages")

    output.seek(0)
    return output, df


uploaded_pdf = st.file_uploader("Importer le PDF", type=["pdf"])

if uploaded_pdf:
    try:
        doc = fitz.open(stream=uploaded_pdf.getvalue(), filetype="pdf")

        results = []
        total_pages = len(doc)

        st.info(f"PDF chargé : {total_pages} pages")
        progress = st.progress(0)

        for i in range(total_pages):
            page = doc.load_page(i)

            text = ocr_page(page)
            row = extract_data(text)
            row["Page"] = i + 1

            if row["Nom sondage"] or row["X"] or row["Y"]:
                results.append(row)

            progress.progress((i + 1) / total_pages)

            del page
            gc.collect()

        doc.close()

        if results:
            excel_file, df = create_excel(results)

            st.success(f"{len(df)} lignes trouvées")
            st.dataframe(df, width="stretch")

            st.download_button(
                "Télécharger Excel",
                excel_file,
                file_name="sondages.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.warning("Aucune donnée trouvée.")

    except Exception as e:
        st.error("Erreur pendant le traitement")
        st.code(str(e))

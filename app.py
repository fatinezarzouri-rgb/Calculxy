import re
from io import BytesIO

import fitz
import pandas as pd
import streamlit as st
from PIL import Image
import pytesseract


st.set_page_config(page_title="PDF vers Excel", layout="wide")
st.title("Extraction sondages PDF → Excel")


def extract_from_text(text, page_num):
    results = []

    sondages = re.findall(r"Sondage\s*[:\-]?\s*([A-Za-z0-9_]+)", text)
    coords = re.findall(
        r"Coordonnées\s*:\s*X\s*[:=]?\s*([\d\s.,]+)\s*Y\s*[:=]?\s*([\d\s.,]+)",
        text,
        re.IGNORECASE
    )

    for i, sondage in enumerate(sondages):
        x, y = None, None

        if i < len(coords):
            x = coords[i][0].replace(" ", "").replace(",", ".")
            y = coords[i][1].replace(" ", "").replace(",", ".")

        results.append({
            "Page": page_num,
            "Nom sondage": sondage,
            "X": x,
            "Y": y
        })

    return results


def ocr_page(page):
    pix = page.get_pixmap(dpi=180)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    return pytesseract.image_to_string(img, lang="eng")


uploaded_file = st.file_uploader("Importer le PDF", type=["pdf"])

if uploaded_file:
    try:
        pdf_bytes = uploaded_file.getvalue()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        st.info(f"PDF chargé : {len(doc)} pages")

        all_results = []
        progress = st.progress(0)

        for index, page in enumerate(doc):
            page_num = index + 1

            text = page.get_text()

            if len(text.strip()) < 50:
                text = ocr_page(page)

            rows = extract_from_text(text, page_num)
            all_results.extend(rows)

            progress.progress(page_num / len(doc))

        if all_results:
            df = pd.DataFrame(all_results)
            st.success(f"{len(df)} sondages trouvés")
            st.dataframe(df)

            output = BytesIO()
            df.to_excel(output, index=False, engine="openpyxl")
            output.seek(0)

            st.download_button(
                "Télécharger Excel",
                output,
                file_name="sondages.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.warning("Aucun sondage trouvé.")

    except Exception as e:
        st.error("Erreur pendant le traitement du PDF")
        st.code(str(e))

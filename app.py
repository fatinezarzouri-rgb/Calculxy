import re
from io import BytesIO

import fitz
import pandas as pd
import pytesseract
import streamlit as st
from PIL import Image


st.set_page_config(page_title="PDF vers Excel", layout="wide")

st.title("Extraction PDF vers Excel")
st.write("Importer un PDF scanné/non sélectionnable pour extraire le nom du sondage, X et Y.")


def clean_number(value):
    if not value:
        return None

    value = value.replace(" ", "")
    value = value.replace(",", ".")

    try:
        return float(value)
    except ValueError:
        return None


def pdf_to_images(pdf_file):
    doc = fitz.open(stream=pdf_file.getvalue(), filetype="pdf")
    images = []

    for page in doc:
        pix = page.get_pixmap(dpi=200)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        images.append(img)

    return images


def extract_data(text):
    sondage = None
    x = None
    y = None

    sondage_match = re.search(
        r"Sondage\s*[:\-]?\s*([A-Za-z0-9_\-]+)",
        text,
        re.IGNORECASE
    )

    if sondage_match:
        sondage = sondage_match.group(1)

    x_match = re.search(
        r"X\s*[:\-]?\s*([\d\s]+[,\.]\d+)",
        text,
        re.IGNORECASE
    )

    y_match = re.search(
        r"Y\s*[:\-]?\s*([\d\s]+[,\.]\d+)",
        text,
        re.IGNORECASE
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


def create_excel(data):
    df = pd.DataFrame(data)

    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Sondages")

    output.seek(0)
    return output


uploaded_pdf = st.file_uploader("Importer le PDF", type=["pdf"])

if uploaded_pdf:
    try:
        results = []

        with st.spinner("Traitement du PDF en cours..."):
            images = pdf_to_images(uploaded_pdf)

            progress = st.progress(0)

            for i, image in enumerate(images, start=1):
                text = pytesseract.image_to_string(image, lang="eng")

                row = extract_data(text)
                row["Page"] = i

                if row["Nom sondage"] or row["X"] or row["Y"]:
                    results.append(row)

                progress.progress(i / len(images))

        if results:
            df = pd.DataFrame(results)

            st.success(f"{len(df)} résultat(s) trouvé(s)")
            st.dataframe(df, width="stretch")

            excel_file = create_excel(results)

            st.download_button(
                label="Télécharger Excel",
                data=excel_file,
                file_name="sondages.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.warning("Aucune donnée trouvée.")

    except Exception as e:
        st.error("Erreur pendant le traitement du PDF")
        st.code(str(e))

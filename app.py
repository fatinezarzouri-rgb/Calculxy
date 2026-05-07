import re
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


def fix_number(value, previous_value):
    if value is None:
        return None

    if previous_value is None:
        return value

    # Correction: 262.929 => 262929
    if value < 1000 and previous_value > 100000:
        return value * 1000

    # Correction: 1.33 => environ 132000
    if value < 1000 and previous_value > 100000:
        return previous_value

    # Correction: 1137691 => 137691
    if value > 1000000 and previous_value > 100000:
        return value / 10

    return value


def extract_data(text):
    sondage_match = re.search(
        r"Sondage\s*[:\-]?\s*([A-Za-z0-9_\-]+)",
        text,
        re.I
    )

    x_match = re.search(
        r"X\s*[:\-]?\s*([\d\s]+[,\.]\d+|\d+)",
        text,
        re.I
    )

    y_match = re.search(
        r"Y\s*[:\-]?\s*([\d\s]+[,\.]\d+|\d+)",
        text,
        re.I
    )

    return {
        "Nom sondage": sondage_match.group(1) if sondage_match else None,
        "X": clean_number(x_match.group(1)) if x_match else None,
        "Y": clean_number(y_match.group(1)) if y_match else None,
    }


def ocr_page(page):
    pix = page.get_pixmap(dpi=220)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    return pytesseract.image_to_string(
        img,
        lang="eng",
        config="--psm 6"
    )


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
        doc = fitz.open(stream=uploaded_pdf.getvalue(), filetype="pdf")
        results = []

        st.info(f"PDF chargé : {len(doc)} pages")
        progress = st.progress(0)

        previous_x = None
        previous_y = None

        for i, page in enumerate(doc):
            page_number = i + 1

            # 1) Essayer texte PDF direct
            text = page.get_text()

            # 2) Si texte direct insuffisant, utiliser OCR
            if "Sondage" not in text or "Coordonnées" not in text:
                text = ocr_page(page)

            row = extract_data(text)
            row["Page"] = page_number

            # Correction nom sondage manquant
            if not row["Nom sondage"]:
                if results:
                    last_name = results[-1]["Nom sondage"]
                    match = re.search(r"(.+_)(\d+)$", last_name)
                    if match:
                        prefix = match.group(1)
                        number = int(match.group(2)) + 1
                        row["Nom sondage"] = f"{prefix}{number:03d}"

            # Correction X/Y OCR
            row["X"] = fix_number(row["X"], previous_x)
            row["Y"] = fix_number(row["Y"], previous_y)

            if row["Nom sondage"] or row["X"] or row["Y"]:
                results.append(row)

                if row["X"]:
                    previous_x = row["X"]
                if row["Y"]:
                    previous_y = row["Y"]

            progress.progress(page_number / len(doc))

        if results:
            df = pd.DataFrame(results)

            st.success(f"{len(df)} lignes trouvées")
            st.dataframe(df, width="stretch")

            excel_file = create_excel(results)

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

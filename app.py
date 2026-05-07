import re
import tempfile
from io import BytesIO

import fitz
import pandas as pd
import pytesseract
import streamlit as st
from PIL import Image


st.set_page_config(page_title="Extraction Pf Pl EM", layout="wide")

st.title("Extraction Pf / Pl / EM depuis PDF scanné")
st.write("Importer un PDF image. L'application utilise OCR puis exporte Excel.")


def pdf_to_images(uploaded_file, zoom=3):
    images = []

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded_file.read())
        pdf_path = tmp.name

    doc = fitz.open(pdf_path)

    for i in range(len(doc)):
        page = doc.load_page(i)
        matrix = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=matrix, alpha=False)

        img = Image.frombytes(
            "RGB",
            [pix.width, pix.height],
            pix.samples
        )

        images.append((i + 1, img))

    doc.close()
    return images


def ocr_image(image):
    text = pytesseract.image_to_string(
        image,
        lang="fra+eng",
        config="--psm 6"
    )
    return text


def extract_sondage(text):
    patterns = [
        r"(SP[_\-\s]*Ret[_\-\s]*\d+)",
        r"(SP[_\-\s]*[A-Za-z0-9]+[_\-\s]*\d+)",
        r"Sondage\s*[:\-]?\s*([A-Za-z0-9_\-\s]+)"
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return re.sub(r"\s+", "_", match.group(1)).strip("_")

    return "NON_DETECTE"


def clean_number(value):
    value = value.replace(",", ".")
    value = value.replace("O", "0")
    value = value.replace("o", "0")
    return float(value)


def extract_pressio_data(text, page_number):
    results = []
    sondage = extract_sondage(text)

    text = text.replace(",", ".")
    lines = text.splitlines()

    for line in lines:
        line = line.strip()

        numbers = re.findall(r"\d+\.\d+|\d+", line)

        if len(numbers) >= 4:
            try:
                profondeur = clean_number(numbers[0])
                pf = clean_number(numbers[1])
                pl = clean_number(numbers[2])
                em = clean_number(numbers[3])

                if (
                    0 <= profondeur <= 100
                    and 0 <= pf <= 50
                    and 0 <= pl <= 100
                    and 0 <= em <= 10000
                ):
                    results.append({
                        "Page": page_number,
                        "Sondage": sondage,
                        "Profondeur (m)": profondeur,
                        "Pf (MPa)": pf,
                        "Pl (MPa)": pl,
                        "EM (MPa)": em
                    })

            except Exception:
                continue

    return results


uploaded_file = st.file_uploader("Importer le PDF scanné", type=["pdf"])

if uploaded_file:
    with st.spinner("OCR en cours..."):
        pages = pdf_to_images(uploaded_file)
        all_results = []

        for page_number, image in pages:
            text = ocr_image(image)
            data = extract_pressio_data(text, page_number)
            all_results.extend(data)

    if not all_results:
        st.error("Aucune donnée détectée. Essaie un scan plus clair ou vérifie les tableaux.")
    else:
        df = pd.DataFrame(all_results)

        st.success(f"{len(df)} lignes détectées.")
        st.data_editor(df, use_container_width=True, num_rows="dynamic")

        output = BytesIO()

        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Extraction")

        output.seek(0)

        st.download_button(
            "Télécharger Excel",
            data=output,
            file_name="extraction_pf_pl_em.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

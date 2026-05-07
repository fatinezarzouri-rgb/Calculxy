import re
import fitz  # PyMuPDF
import pytesseract
import pandas as pd
from PIL import Image
import streamlit as st
from io import BytesIO


def pdf_to_images(pdf_file):
    doc = fitz.open(stream=pdf_file.read(), filetype="pdf")
    images = []

    for page in doc:
        pix = page.get_pixmap(dpi=300)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        images.append(img)

    return images


def clean_number(value):
    value = value.replace(" ", "").replace(",", ".")
    return float(value)


def extract_data(text):
    sondage = None
    x = None
    y = None

    sondage_match = re.search(r"Sondage\s*:\s*([A-Za-z0-9_\-]+)", text)
    if sondage_match:
        sondage = sondage_match.group(1)

    x_match = re.search(r"X\s*:\s*([\d\s]+[,\.]\d+)", text)
    y_match = re.search(r"Y\s*:\s*([\d\s]+[,\.]\d+)", text)

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


st.title("Extraction PDF vers Excel")
st.write("Importer un PDF scanné/non sélectionnable pour extraire le nom du sondage, X et Y.")

uploaded_pdf = st.file_uploader("Importer le PDF", type=["pdf"])

if uploaded_pdf:
    results = []

    images = pdf_to_images(uploaded_pdf)

    for i, image in enumerate(images, start=1):
        text = pytesseract.image_to_string(image, lang="fra+eng")
        row = extract_data(text)
        row["Page"] = i

        if row["Nom sondage"] or row["X"] or row["Y"]:
            results.append(row)

    if results:
        df = pd.DataFrame(results)
        st.dataframe(df)

        excel_file = create_excel(results)

        st.download_button(
            label="Télécharger Excel",
            data=excel_file,
            file_name="sondages.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.warning("Aucune donnée trouvée.")

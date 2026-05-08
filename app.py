import re
from io import BytesIO

import fitz
import pandas as pd
import pytesseract
import streamlit as st
from PIL import Image


st.set_page_config(page_title="PDF OCR vers Excel", layout="wide")
st.title("Extraction corrigée PDF OCR vers Excel")


def clean_number(value):
    if not value:
        return None

    value = str(value)
    value = value.replace(" ", "")
    value = value.replace(",", ".")

    try:
        return float(value)
    except ValueError:
        return None


def extract_data(text):
    sondage_match = re.search(
        r"Sondage\s*[:\-]?\s*([A-Za-z0-9_\-]+)",
        text,
        re.I
    )

    x_match = re.search(
        r"X\s*[:\-]?\s*([\d\s.,]+)",
        text,
        re.I
    )

    y_match = re.search(
        r"Y\s*[:\-]?\s*([\d\s.,]+)",
        text,
        re.I
    )

    return {
        "Nom sondage": sondage_match.group(1) if sondage_match else None,
        "X": clean_number(x_match.group(1)) if x_match else None,
        "Y": clean_number(y_match.group(1)) if y_match else None,
        "Texte OCR": text
    }


def ocr_header(page):
    rect = page.rect

    crop = fitz.Rect(
        rect.width * 0.25,
        rect.height * 0.08,
        rect.width * 0.98,
        rect.height * 0.24
    )

    pix = page.get_pixmap(
        matrix=fitz.Matrix(3, 3),
        clip=crop
    )

    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    text = pytesseract.image_to_string(
        img,
        lang="eng",
        config="--psm 6"
    )

    return text


def fix_name(name, previous_name):
    if name and re.search(r"_\d+$", name):
        return name

    if previous_name:
        match = re.search(r"(.+_)(\d+)$", previous_name)
        if match:
            prefix = match.group(1)
            number = int(match.group(2)) + 1
            return f"{prefix}{number:03d}"

    return name


def generate_candidates(value):
    if value is None:
        return []

    candidates = [value]

    if value < 1000:
        candidates.append(value * 1000)

    if value > 1000000:
        txt = str(value).replace(".", "")
        if len(txt) >= 7:
            try:
                candidates.append(float(txt[1:-2] + "." + txt[-2:]))
            except ValueError:
                pass

        candidates.append(value / 10)

    if 200000 <= value <= 210000:
        candidates.append(value + 90000)

    return candidates


def fix_by_neighbors(values, min_value, max_value):
    fixed = values.copy()

    for i, value in enumerate(values):
        candidates = generate_candidates(value)

        valid_candidates = [
            c for c in candidates
            if c is not None and min_value <= c <= max_value
        ]

        if not valid_candidates:
            fixed[i] = value
            continue

        prev_val = None
        next_val = None

        for j in range(i - 1, -1, -1):
            if fixed[j] is not None and min_value <= fixed[j] <= max_value:
                prev_val = fixed[j]
                break

        for j in range(i + 1, len(values)):
            if values[j] is not None and min_value <= values[j] <= max_value:
                next_val = values[j]
                break

        if prev_val is not None and next_val is not None:
            target = (prev_val + next_val) / 2
            fixed[i] = min(valid_candidates, key=lambda x: abs(x - target))

        elif prev_val is not None:
            fixed[i] = min(valid_candidates, key=lambda x: abs(x - prev_val))

        elif next_val is not None:
            fixed[i] = min(valid_candidates, key=lambda x: abs(x - next_val))

        else:
            fixed[i] = valid_candidates[0]

    return fixed


def detect_errors(df):
    errors = []

    for _, row in df.iterrows():
        err = ""

        if pd.isna(row["Nom sondage"]) or row["Nom sondage"] == "":
            err += "Nom manquant; "

        if pd.isna(row["X"]) or row["X"] < 200000 or row["X"] > 400000:
            err += "X suspect; "

        if pd.isna(row["Y"]) or row["Y"] < 100000 or row["Y"] > 200000:
            err += "Y suspect; "

        errors.append(err)

    df["Erreur"] = errors
    return df


def create_excel(df):
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

        progress = st.progress(0)
        st.info(f"PDF chargé : {len(doc)} pages")

        previous_name = None

        for i, page in enumerate(doc):
            text = ocr_header(page)
            row = extract_data(text)

            row["Page"] = i + 1
            row["Nom sondage"] = fix_name(row["Nom sondage"], previous_name)

            if row["Nom sondage"]:
                previous_name = row["Nom sondage"]

            results.append(row)

            progress.progress((i + 1) / len(doc))

        df = pd.DataFrame(results)

        df["X"] = fix_by_neighbors(df["X"].tolist(), 200000, 400000)
        df["Y"] = fix_by_neighbors(df["Y"].tolist(), 100000, 200000)

        df = detect_errors(df)

        display_df = df.drop(columns=["Texte OCR"], errors="ignore")

        st.success("Extraction terminée")
        edited_df = st.data_editor(display_df, width="stretch", num_rows="dynamic")

        errors_left = edited_df[edited_df["Erreur"] != ""]

        if len(errors_left) == 0:
            final_df = edited_df.drop(columns=["Erreur"], errors="ignore")
            excel_file = create_excel(final_df)

            st.download_button(
                "Télécharger Excel corrigé",
                excel_file,
                file_name="sondages_corriges.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.warning(f"{len(errors_left)} ligne(s) encore suspecte(s). Corrige-les dans le tableau.")

    except Exception as e:
        st.error("Erreur pendant le traitement")
        st.code(str(e))

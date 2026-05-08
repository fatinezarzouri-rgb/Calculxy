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

    value = str(value).replace(" ", "").replace(",", ".")

    try:
        return float(value)
    except ValueError:
        return None


def normalize_sondage_name(value):
    if not value:
        return None

    value = value.strip()
    value = value.replace(" ", "")
    value = value.replace("-", "_")
    value = value.replace("__", "_")

    value = value.replace("5P", "SP")
    value = value.replace("S0", "SP")
    value = value.replace("§P", "SP")

    match = re.search(r"(SP_[A-Za-z0-9]+_\d{1,4})", value, re.I)

    if not match:
        return None

    name = match.group(1)
    parts = name.split("_")

    if len(parts) == 3:
        return f"{parts[0].upper()}_{parts[1]}_{parts[2].zfill(3)}"

    return name


def extract_data(text):
    text_clean = text.replace("\n", " ")
    text_clean = re.sub(r"\s+", " ", text_clean)

    sondage = None

    patterns = [
        r"Sondage\s*[:\-]?\s*([A-Za-z0-9_\-\s]{5,50})",
        r"(SP\s*[_\- ]\s*[A-Za-z0-9]+\s*[_\- ]\s*\d{1,4})",
        r"(S\s*P\s*[_\- ]\s*[A-Za-z0-9]+\s*[_\- ]\s*\d{1,4})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text_clean, re.I)
        if match:
            sondage = normalize_sondage_name(match.group(1))
            if sondage:
                break

    x_match = re.search(
        r"\bX\s*[:\-]?\s*([\d\s]+[,\.]\d+|\d+)",
        text_clean,
        re.I
    )

    y_match = re.search(
        r"\bY\s*[:\-]?\s*([\d\s]+[,\.]\d+|\d+)",
        text_clean,
        re.I
    )

    return {
        "Nom sondage": sondage,
        "X": clean_number(x_match.group(1)) if x_match else None,
        "Y": clean_number(y_match.group(1)) if y_match else None,
    }


def ocr_header(page, dpi=400, psm=6):
    rect = page.rect

    zone_haut = fitz.Rect(
        rect.width * 0.18,
        rect.height * 0.06,
        rect.width * 0.98,
        rect.height * 0.26
    )

    pix = page.get_pixmap(dpi=dpi, clip=zone_haut)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    text = pytesseract.image_to_string(
        img,
        lang="eng",
        config=f"--psm {psm}"
    )

    return text


def redetect_page(page):
    best_row = None
    best_score = -1

    attempts = [
        (300, 6),
        (400, 6),
        (450, 6),
        (500, 6),
        (600, 6),
        (400, 4),
        (500, 4),
    ]

    for dpi, psm in attempts:
        text = ocr_header(page, dpi=dpi, psm=psm)
        row = extract_data(text)

        score = 0

        if row["Nom sondage"]:
            score += 2

        if row["X"] and 200000 <= row["X"] <= 400000:
            score += 1

        if row["Y"] and 100000 <= row["Y"] <= 200000:
            score += 1

        if score > best_score:
            best_score = score
            best_row = row

        if score == 4:
            return row

    return best_row


def detect_errors(df):
    df = df.copy()
    df["Erreur"] = ""

    for idx, row in df.iterrows():

        if pd.isna(row["Nom sondage"]) or row["Nom sondage"] == "":
            df.at[idx, "Erreur"] += "Nom manquant; "

        if pd.isna(row["X"]):
            df.at[idx, "Erreur"] += "X manquant; "
        elif row["X"] < 200000 or row["X"] > 400000:
            df.at[idx, "Erreur"] += "X suspect; "

        if pd.isna(row["Y"]):
            df.at[idx, "Erreur"] += "Y manquant; "
        elif row["Y"] < 100000 or row["Y"] > 200000:
            df.at[idx, "Erreur"] += "Y suspect; "

    return df


def create_excel(df):
    output = BytesIO()

    df = df.drop(columns=["Erreur"], errors="ignore")

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Sondages")

    output.seek(0)
    return output


uploaded_pdf = st.file_uploader("Importer le PDF", type=["pdf"])

if uploaded_pdf:
    pdf_bytes = uploaded_pdf.getvalue()

    if "df_result" not in st.session_state:
        st.session_state.df_result = None

    if st.button("Extraire le PDF"):
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            results = []

            st.info(f"PDF chargé : {len(doc)} pages")
            progress = st.progress(0)

            for i, page in enumerate(doc):
                page_number = i + 1

                text = ocr_header(page, dpi=400, psm=6)
                row = extract_data(text)
                row["Page"] = page_number

                if row["Nom sondage"] or row["X"] or row["Y"]:
                    results.append(row)

                progress.progress(page_number / len(doc))

            if results:
                df = pd.DataFrame(results)
                df = detect_errors(df)
                st.session_state.df_result = df
                st.rerun()
            else:
                st.warning("Aucune donnée trouvée.")

        except Exception as e:
            st.error("Erreur pendant le traitement")
            st.code(str(e))

    if st.session_state.df_result is not None:
        df = st.session_state.df_result.copy()
        error_rows = df[df["Erreur"] != ""]

        st.success(f"{len(df)} lignes trouvées")

        if len(error_rows) > 0:
            st.warning(f"{len(error_rows)} ligne(s) problématique(s).")

            st.dataframe(error_rows, width="stretch")

            if st.button("Corriger / redétecter les lignes problématiques"):
                try:
                    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                    progress_fix = st.progress(0)

                    error_indexes = list(error_rows.index)

                    for count, idx in enumerate(error_indexes, start=1):
                        page_number = int(df.at[idx, "Page"])
                        page = doc[page_number - 1]

                        new_row = redetect_page(page)

                        if new_row:
                            df.at[idx, "Nom sondage"] = new_row["Nom sondage"]
                            df.at[idx, "X"] = new_row["X"]
                            df.at[idx, "Y"] = new_row["Y"]

                        progress_fix.progress(count / len(error_indexes))

                    df = detect_errors(df)
                    st.session_state.df_result = df
                    st.rerun()

                except Exception as e:
                    st.error("Erreur pendant la correction")
                    st.code(str(e))

        edited_df = st.data_editor(
            st.session_state.df_result,
            width="stretch",
            num_rows="dynamic"
        )

        edited_df = detect_errors(edited_df)
        st.session_state.df_result = edited_df

        errors_remaining = edited_df[edited_df["Erreur"] != ""]

        if len(errors_remaining) == 0:
            excel_file = create_excel(edited_df)

            st.download_button(
                label="Télécharger Excel validé",
                data=excel_file,
                file_name="sondages_valides.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.error(f"{len(errors_remaining)} ligne(s) restent à corriger.")

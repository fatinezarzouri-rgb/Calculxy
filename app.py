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


def extract_data(text):
    text_clean = text.replace("\n", " ")

    sondage_patterns = [
        r"Sondage\s*[:\-]?\s*([A-Z]{2}_[A-Za-z]+_\d{3})",
        r"Sondage\s*[:\-]?\s*([A-Z]{2}[_\-][A-Za-z0-9]+[_\-]\d+)",
        r"(SP[_\-][A-Za-z0-9]+[_\-]\d{3})",
        r"(SP\s*[_\-]\s*[A-Za-z0-9]+\s*[_\-]\s*\d{3})",
    ]

    sondage = None

    for pattern in sondage_patterns:
        match = re.search(pattern, text_clean, re.I)
        if match:
            sondage = match.group(1)
            sondage = sondage.replace(" ", "")
            sondage = sondage.replace("-", "_")
            break

    x_match = re.search(
        r"X\s*[:\-]?\s*([\d\s]+[,\.]\d+|\d+)",
        text_clean,
        re.I
    )

    y_match = re.search(
        r"Y\s*[:\-]?\s*([\d\s]+[,\.]\d+|\d+)",
        text_clean,
        re.I
    )

    return {
        "Nom sondage": sondage,
        "X": clean_number(x_match.group(1)) if x_match else None,
        "Y": clean_number(y_match.group(1)) if y_match else None,
    }


def fix_missing_name(results):
    if not results:
        return None

    last_name = results[-1].get("Nom sondage")

    if not last_name:
        return None

    match = re.search(r"(.+_)(\d+)$", last_name)

    if not match:
        return None

    prefix = match.group(1)
    number = int(match.group(2)) + 1

    return f"{prefix}{number:03d}"


def ocr_page(page, dpi=220, psm=6):
    pix = page.get_pixmap(dpi=dpi)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    text = pytesseract.image_to_string(
        img,
        lang="eng",
        config=f"--psm {psm}"
    )

    return text


def redetect_page(page):
    attempts = [
        {"dpi": 260, "psm": 6},
        {"dpi": 300, "psm": 6},
        {"dpi": 300, "psm": 4},
        {"dpi": 350, "psm": 6},
    ]

    best_row = None
    best_score = -1

    for attempt in attempts:
        text = ocr_page(
            page,
            dpi=attempt["dpi"],
            psm=attempt["psm"]
        )

        row = extract_data(text)

        score = 0

        if row["Nom sondage"]:
            score += 1

        if row["X"] and 200000 <= row["X"] <= 400000:
            score += 1

        if row["Y"] and 100000 <= row["Y"] <= 200000:
            score += 1

        if score > best_score:
            best_score = score
            best_row = row

    return best_row


def detect_errors(df):
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


def get_error_rows(df):
    return df[df["Erreur"] != ""]


def create_excel(df):
    output = BytesIO()

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

                text = ocr_page(page)
                row = extract_data(text)
                row["Page"] = page_number

                if row["Nom sondage"] or row["X"] or row["Y"]:
                    results.append(row)

                progress.progress(page_number / len(doc))

            if results:
                df = pd.DataFrame(results)
                df = detect_errors(df)
                st.session_state.df_result = df
            else:
                st.warning("Aucune donnée trouvée.")

        except Exception as e:
            st.error("Erreur pendant le traitement")
            st.code(str(e))

    if st.session_state.df_result is not None:

        df = st.session_state.df_result.copy()
        error_rows = get_error_rows(df)

        st.success(f"{len(df)} lignes trouvées")

        if len(error_rows) > 0:
            st.warning(f"{len(error_rows)} ligne(s) problématique(s) détectée(s).")

            st.dataframe(error_rows, width="stretch")

            if st.button("Corriger / redétecter seulement les lignes problématiques"):
                try:
                    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

                    progress_fix = st.progress(0)

                    error_indexes = list(error_rows.index)

                    for count, idx in enumerate(error_indexes, start=1):
                        page_number = int(df.at[idx, "Page"])
                        page = doc[page_number - 1]

                        new_row = redetect_page(page)

                        if new_row["Nom sondage"]:
                            df.at[idx, "Nom sondage"] = new_row["Nom sondage"]

                        if new_row["X"]:
                            df.at[idx, "X"] = new_row["X"]

                        if new_row["Y"]:
                            df.at[idx, "Y"] = new_row["Y"]

                        progress_fix.progress(count / len(error_indexes))

                    df = detect_errors(df)
                    st.session_state.df_result = df

                    st.success("Redétection terminée.")

                except Exception as e:
                    st.error("Erreur pendant la redétection")
                    st.code(str(e))

        edited_df = st.data_editor(
            st.session_state.df_result,
            width="stretch",
            num_rows="dynamic"
        )

        edited_df = detect_errors(edited_df)
        errors_remaining = get_error_rows(edited_df)

        if len(errors_remaining) == 0:
            final_df = edited_df.drop(columns=["Erreur"], errors="ignore")

            excel_file = create_excel(final_df)

            st.download_button(
                label="Télécharger Excel validé",
                data=excel_file,
                file_name="sondages_valides.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.error(f"{len(errors_remaining)} ligne(s) à corriger avant téléchargement.")

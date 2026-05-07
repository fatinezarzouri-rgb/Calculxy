import re
from io import BytesIO
from pathlib import Path

import fitz
import pandas as pd
import pytesseract
import streamlit as st
from PIL import Image, ImageFilter

st.set_page_config(page_title="Extraction X Y des sondages", layout="wide")


def render_page(doc, page_index: int, zoom: float = 3.0):
    page = doc[page_index]
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)


def ocr_variants(crop: Image.Image):
    gray = crop.convert("L")
    return [
        gray,
        gray.resize((gray.width * 3, gray.height * 3)),
        gray.point(lambda p: 255 if p > 185 else 0).resize((gray.width * 3, gray.height * 3)),
        gray.point(lambda p: 255 if p > 160 else 0).resize((gray.width * 3, gray.height * 3)),
        gray.filter(ImageFilter.SHARPEN).resize((gray.width * 4, gray.height * 4)),
    ]


def detect_sondage(page_img: Image.Image):
    w, h = page_img.size

    # bloc "Date / Sondage / Machine / Profondeur"
    crops = [
        (0.34, 0.66, 0.16, 0.25),
        (0.32, 0.68, 0.15, 0.26),
        (0.30, 0.70, 0.15, 0.27),
    ]

    for bx1, bx2, by1, by2 in crops:
        crop = page_img.crop((int(w * bx1), int(h * by1), int(w * bx2), int(h * by2)))

        for img in ocr_variants(crop):
            for psm in [6, 11]:
                txt = pytesseract.image_to_string(img, config=f"--psm {psm}")
                txt = txt.replace("\n", " ")
                txt = re.sub(r"\s+", " ", txt)

                m = re.search(r"Sondage\s*:\s*([A-Za-z0-9_\-/]+)", txt, flags=re.IGNORECASE)
                if m:
                    return m.group(1).strip()

                m = re.search(r"(SP[_\-]?(?:Rem|Reta)[_\-]?\d+)", txt, flags=re.IGNORECASE)
                if m:
                    return m.group(1).strip()

    return ""


def detect_xy(page_img: Image.Image):
    w, h = page_img.size

    # bloc en haut à droite : Coordonnées / X / Y
    crops = [
        (0.78, 0.98, 0.15, 0.24),
        (0.76, 0.98, 0.14, 0.25),
        (0.74, 0.99, 0.14, 0.26),
    ]

    best_x = ""
    best_y = ""

    for bx1, bx2, by1, by2 in crops:
        crop = page_img.crop((int(w * bx1), int(h * by1), int(w * bx2), int(h * by2)))

        for img in ocr_variants(crop):
            for psm in [6, 11]:
                txt = pytesseract.image_to_string(img, config=f"--psm {psm}")
                txt = txt.replace("\n", " ")
                txt = re.sub(r"\s+", " ", txt)

                if not best_x:
                    m = re.search(r"X\s*:\s*([0-9]+[.,][0-9]+)", txt, flags=re.IGNORECASE)
                    if m:
                        best_x = m.group(1).strip()

                if not best_y:
                    m = re.search(r"Y\s*:\s*([0-9]+[.,][0-9]+)", txt, flags=re.IGNORECASE)
                    if m:
                        best_y = m.group(1).strip()

                # secours si OCR mange le X: ou Y:
                if not best_x:
                    nums = re.findall(r"([0-9]{5,7}[.,][0-9]+)", txt)
                    if len(nums) >= 1:
                        best_x = nums[0]

                if not best_y:
                    nums = re.findall(r"([0-9]{5,7}[.,][0-9]+)", txt)
                    if len(nums) >= 2:
                        best_y = nums[1]

                if best_x and best_y:
                    return best_x, best_y

    return best_x, best_y


def extract_xy(pdf_bytes: bytes):
    tmp = Path("tmp_xy.pdf")
    tmp.write_bytes(pdf_bytes)
    doc = fitz.open(str(tmp))

    rows = []
    undetected = []

    for i in range(len(doc)):
        img = render_page(doc, i, zoom=3.0)

        sondage = detect_sondage(img)
        x_val, y_val = detect_xy(img)

        if not sondage or not x_val or not y_val:
            undetected.append(i + 1)

        rows.append({
            "Sondage": sondage if sondage else f"PAGE_{i+1:03d}",
            "X": x_val,
            "Y": y_val,
            "Page": i + 1,
        })

    df = pd.DataFrame(rows)

    if not df.empty:
        df = df.sort_values("Page").drop_duplicates(subset=["Sondage"], keep="first")
        df = df[["Sondage", "X", "Y", "Page"]]

    return df, undetected


def to_excel_bytes(df: pd.DataFrame):
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Sondages_XY")
    bio.seek(0)
    return bio.getvalue()


st.title("Extraction X Y des sondages")

pdf_file = st.file_uploader("", type=["pdf"])

if st.button("Lancer l'extraction", type="primary"):
    if pdf_file is None:
        st.error("Charge d'abord le PDF.")
    else:
        try:
            with st.spinner("Extraction en cours..."):
                df, undetected = extract_xy(pdf_file.read())

            if undetected:
                st.warning(f"Pages à vérifier manuellement : {undetected}")

            if df.empty:
                st.warning("Aucune donnée détectée.")
            else:
                st.success(f"Extraction terminée : {len(df)} sondage(s)")
                st.dataframe(df, use_container_width=True)

                st.download_button(
                    "Télécharger l'Excel",
                    data=to_excel_bytes(df),
                    file_name="sondages_xy.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

        except Exception as e:
            st.exception(e)

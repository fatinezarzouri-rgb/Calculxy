import re
from io import BytesIO
from pathlib import Path

import fitz
import pandas as pd
import pytesseract
import streamlit as st
from PIL import Image, ImageFilter

st.set_page_config(page_title="Extraction X Y des sondages", layout="wide")


def render_page(doc, page_index: int, zoom: float = 4.5):
    page = doc[page_index]
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)


def ocr_variants(crop: Image.Image):
    gray = crop.convert("L")
    return [
        gray,
        gray.resize((gray.width * 3, gray.height * 3)),
        gray.point(lambda p: 255 if p > 190 else 0).resize((gray.width * 3, gray.height * 3)),
        gray.point(lambda p: 255 if p > 165 else 0).resize((gray.width * 3, gray.height * 3)),
        gray.filter(ImageFilter.SHARPEN).resize((gray.width * 4, gray.height * 4)),
    ]


def normalize_num(s: str) -> str:
    s = s.strip().replace(" ", "")
    if "." in s and "," not in s:
        s = s.replace(".", ",")
    return s


def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def detect_sondage(page_img: Image.Image):
    w, h = page_img.size

    crops = [
        (0.33, 0.67, 0.16, 0.24),
        (0.31, 0.69, 0.15, 0.25),
        (0.30, 0.70, 0.15, 0.26),
    ]

    for bx1, bx2, by1, by2 in crops:
        crop = page_img.crop((int(w * bx1), int(h * by1), int(w * bx2), int(h * by2)))

        for img in ocr_variants(crop):
            for psm in [6, 11]:
                txt = pytesseract.image_to_string(img, config=f"--psm {psm}")
                txt = clean_text(txt.replace("\n", " "))

                m = re.search(r"Sondage\s*:\s*([A-Za-z0-9_\-/]+)", txt, flags=re.IGNORECASE)
                if m:
                    return m.group(1).strip()

                m = re.search(r"(SP[_\-]?(?:Rem|Reta)[_\-]?\d+)", txt, flags=re.IGNORECASE)
                if m:
                    return m.group(1).strip()

                m = re.search(r"(T\d+\-[A-Za-z0-9\-\+]+)", txt, flags=re.IGNORECASE)
                if m:
                    return m.group(1).strip()

    return ""


def read_line_value(page_img: Image.Image, boxes, letter: str) -> str:
    w, h = page_img.size
    best = ""

    for bx1, bx2, by1, by2 in boxes:
        crop = page_img.crop((int(w * bx1), int(h * by1), int(w * bx2), int(h * by2)))

        for img in ocr_variants(crop):
            for psm in [7, 6]:
                txt = pytesseract.image_to_string(img, config=f"--psm {psm}")
                txt = clean_text(txt.replace("\n", " "))

                # cas normal : X : 306065,10
                m = re.search(rf"{letter}\s*:\s*([0-9]{{5,7}}[.,][0-9]+)", txt, flags=re.IGNORECASE)
                if m:
                    return normalize_num(m.group(1))

                # secours : X 306065,10
                m = re.search(rf"{letter}\s*([0-9]{{5,7}}[.,][0-9]+)", txt, flags=re.IGNORECASE)
                if m:
                    return normalize_num(m.group(1))

                # secours final : un seul grand nombre dans la ligne
                nums = re.findall(r"([0-9]{5,7}[.,][0-9]+)", txt)
                if len(nums) == 1:
                    best = normalize_num(nums[0])

    return best


def detect_xy(page_img: Image.Image):
    # X et Y lus chacun dans sa propre ligne
    x_line_boxes = [
        (0.84, 0.985, 0.165, 0.195),
        (0.82, 0.985, 0.160, 0.198),
        (0.80, 0.99, 0.158, 0.200),
    ]

    y_line_boxes = [
        (0.84, 0.985, 0.190, 0.220),
        (0.82, 0.985, 0.185, 0.223),
        (0.80, 0.99, 0.183, 0.225),
    ]

    x_val = read_line_value(page_img, x_line_boxes, "X")
    y_val = read_line_value(page_img, y_line_boxes, "Y")

    return x_val, y_val


def extract_xy(pdf_bytes: bytes):
    tmp = Path("tmp_xy.pdf")
    tmp.write_bytes(pdf_bytes)
    doc = fitz.open(str(tmp))

    rows = []
    undetected = []

    for i in range(len(doc)):
        img = render_page(doc, i, zoom=4.5)

        sondage = detect_sondage(img)
        x_val, y_val = detect_xy(img)

        if not sondage or not x_val or not y_val:
            undetected.append(i + 1)

        rows.append({
            "Sondage": sondage if sondage else f"PAGE_{i+1:03d}",
            "X": x_val,
            "Y": y_val,
        })

    df = pd.DataFrame(rows)

    if not df.empty:
        df = df.drop_duplicates(subset=["Sondage"], keep="first")
        df = df[["Sondage", "X", "Y"]]

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

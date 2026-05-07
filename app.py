import re
import shutil
from io import BytesIO
from pathlib import Path

import fitz
import pandas as pd
import streamlit as st
from PIL import Image, ImageFilter

st.set_page_config(page_title="Extraction X Y des sondages", layout="wide")


# =========================================================
# OCR DISPONIBLE OU PAS
# =========================================================
OCR_AVAILABLE = shutil.which("tesseract") is not None

if OCR_AVAILABLE:
    import pytesseract


# =========================================================
# RENDER PAGE
# =========================================================
def render_page(doc, page_index: int, zoom: float = 3.0):
    page = doc[page_index]
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)


# =========================================================
# EXTRACTION TEXTE DIRECTE
# =========================================================
def extract_xy_from_text(page):
    text = page.get_text("text")

    sondage = ""
    x_val = ""
    y_val = ""

    m = re.search(r"Sondage\s*:\s*([A-Za-z0-9_\-/]+)", text, flags=re.IGNORECASE)
    if m:
        sondage = m.group(1).strip()

    if not sondage:
        m = re.search(r"(SP[_\-]?(?:Rem|Reta)[_\-]?\d+)", text, flags=re.IGNORECASE)
        if m:
            sondage = m.group(1).strip()

    m = re.search(r"X\s*:\s*([0-9]+[.,][0-9]+)", text, flags=re.IGNORECASE)
    if m:
        x_val = m.group(1).strip()

    m = re.search(r"Y\s*:\s*([0-9]+[.,][0-9]+)", text, flags=re.IGNORECASE)
    if m:
        y_val = m.group(1).strip()

    return {
        "Sondage": sondage,
        "X": x_val,
        "Y": y_val,
        "mode": "texte"
    }


# =========================================================
# EXTRACTION OCR
# =========================================================
def extract_xy_by_ocr(page_img: Image.Image):
    if not OCR_AVAILABLE:
        return {"Sondage": "", "X": "", "Y": "", "mode": "ocr_indisponible"}

    w, h = page_img.size

    crops = [
        (0.33, 0.96, 0.14, 0.26),
        (0.30, 0.96, 0.12, 0.28),
        (0.36, 0.98, 0.13, 0.27),
    ]

    best = {"Sondage": "", "X": "", "Y": "", "mode": "ocr"}

    for bx1, bx2, by1, by2 in crops:
        crop = page_img.crop((int(w * bx1), int(h * by1), int(w * bx2), int(h * by2)))
        gray = crop.convert("L")

        variants = [
            gray,
            gray.resize((gray.width * 3, gray.height * 3)),
            gray.point(lambda p: 255 if p > 180 else 0).resize((gray.width * 3, gray.height * 3)),
            gray.point(lambda p: 255 if p > 150 else 0).resize((gray.width * 3, gray.height * 3)),
            gray.filter(ImageFilter.SHARPEN).resize((gray.width * 4, gray.height * 4)),
        ]

        for img in variants:
            for psm in [6, 11]:
                txt = pytesseract.image_to_string(img, config=f"--psm {psm}")
                txt = txt.replace("\n", " ")
                txt = re.sub(r"\s+", " ", txt)

                if not best["Sondage"]:
                    m = re.search(r"Sondage\s*:\s*([A-Za-z0-9_\-/]+)", txt, flags=re.IGNORECASE)
                    if not m:
                        m = re.search(r"(SP[_\-]?(?:Rem|Reta)[_\-]?\d+)", txt, flags=re.IGNORECASE)
                    if not m:
                        m = re.search(r"(T\d+\-[A-Za-z0-9\-\+]+)", txt, flags=re.IGNORECASE)
                    if m:
                        best["Sondage"] = m.group(1).strip()

                if not best["X"]:
                    m = re.search(r"X\s*:\s*([0-9]+[.,][0-9]+)", txt, flags=re.IGNORECASE)
                    if m:
                        best["X"] = m.group(1).strip()

                if not best["Y"]:
                    m = re.search(r"Y\s*:\s*([0-9]+[.,][0-9]+)", txt, flags=re.IGNORECASE)
                    if m:
                        best["Y"] = m.group(1).strip()

                if best["Sondage"] and best["X"] and best["Y"]:
                    return best

    return best


# =========================================================
# HYBRIDE
# =========================================================
def extract_xy_hybrid(pdf_bytes: bytes):
    tmp = Path("tmp_xy.pdf")
    tmp.write_bytes(pdf_bytes)
    doc = fitz.open(str(tmp))

    rows = []
    undetected = []
    scan_without_ocr = []

    for i in range(len(doc)):
        page = doc[i]

        # 1) tentative texte direct
        row = extract_xy_from_text(page)

        # 2) si incomplet -> OCR
        if not row["Sondage"] or not row["X"] or not row["Y"]:
            page_img = render_page(doc, i, zoom=3.0)
            row_ocr = extract_xy_by_ocr(page_img)

            if row_ocr["mode"] == "ocr_indisponible":
                scan_without_ocr.append(i + 1)
            else:
                if row_ocr["Sondage"]:
                    row["Sondage"] = row_ocr["Sondage"]
                if row_ocr["X"]:
                    row["X"] = row_ocr["X"]
                if row_ocr["Y"]:
                    row["Y"] = row_ocr["Y"]
                row["mode"] = row_ocr["mode"]

        if not row["Sondage"] or not row["X"] or not row["Y"]:
            undetected.append(i + 1)

        rows.append({
            "Sondage": row["Sondage"] if row["Sondage"] else f"PAGE_{i+1:03d}",
            "X": row["X"],
            "Y": row["Y"],
            "Page": i + 1,
            "Mode": row["mode"],
        })

    df = pd.DataFrame(rows)

    if not df.empty:
        df = df.sort_values("Page").drop_duplicates(subset=["Sondage"], keep="first")
        df = df[["Sondage", "X", "Y", "Page", "Mode"]]

    return df, undetected, scan_without_ocr


def to_excel_bytes(df: pd.DataFrame):
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Sondages_XY")
    bio.seek(0)
    return bio.getvalue()


# =========================================================
# UI
# =========================================================
st.title("Extraction X Y des sondages")

pdf_file = st.file_uploader("", type=["pdf"])

if st.button("Lancer l'extraction", type="primary"):
    if pdf_file is None:
        st.error("Charge d'abord le PDF.")
    else:
        try:
            with st.spinner("Extraction en cours..."):
                df, undetected, scan_without_ocr = extract_xy_hybrid(pdf_file.read())

            if scan_without_ocr:
                st.warning(
                    f"PDF scanné détecté sur certaines pages, mais OCR non disponible sur ce serveur : {scan_without_ocr}"
                )

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

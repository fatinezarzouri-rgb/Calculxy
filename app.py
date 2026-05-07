import re
import tempfile
from io import BytesIO

import cv2
import fitz
import numpy as np
import pandas as pd
import pytesseract
import streamlit as st
from PIL import Image


st.set_page_config(page_title="Extraction Pf Pl EM par couleur", layout="wide")
st.title("Extraction Pf / Pl / EM depuis PDF scanné")

st.write(
    "Méthode : détection des nombres par couleur + position verticale pour calculer la profondeur."
)


def pdf_to_images(uploaded_file, zoom=3):
    images = []

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded_file.read())
        pdf_path = tmp.name

    doc = fitz.open(pdf_path)

    for i in range(len(doc)):
        page = doc.load_page(i)
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        images.append((i + 1, img))

    doc.close()
    return images


def ocr_text(img):
    return pytesseract.image_to_string(img, lang="fra+eng")


def extract_sondage(img):
    text = ocr_text(img)
    match = re.search(r"(SP[_\-\s]*[A-Za-z]+[_\-\s]*\d+)", text, re.IGNORECASE)
    if match:
        return re.sub(r"\s+", "_", match.group(1))
    return "NON_DETECTE"


def color_mask(rgb_img, color_type):
    bgr = cv2.cvtColor(np.array(rgb_img), cv2.COLOR_RGB2BGR)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)

    if color_type == "red":
        mask1 = cv2.inRange(hsv, np.array([0, 60, 60]), np.array([12, 255, 255]))
        mask2 = cv2.inRange(hsv, np.array([165, 60, 60]), np.array([180, 255, 255]))
        mask = cv2.bitwise_or(mask1, mask2)

    elif color_type == "blue":
        mask = cv2.inRange(hsv, np.array([85, 40, 40]), np.array([140, 255, 255]))

    else:
        mask = np.zeros(hsv.shape[:2], dtype=np.uint8)

    kernel = np.ones((2, 2), np.uint8)
    mask = cv2.dilate(mask, kernel, iterations=1)
    return mask


def extract_numbers_from_zone(img, x1, x2, y1, y2, color_type):
    crop = img.crop((x1, y1, x2, y2))
    mask = color_mask(crop, color_type)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    boxes = []

    for c in contours:
        x, y, w, h = cv2.boundingRect(c)

        if w >= 3 and h >= 6:
            boxes.append([x, y, x + w, y + h])

    if not boxes:
        return []

    boxes = sorted(boxes, key=lambda b: b[1])

    groups = []

    for box in boxes:
        added = False
        for g in groups:
            gy1 = min(b[1] for b in g)
            gy2 = max(b[3] for b in g)

            if abs(((box[1] + box[3]) / 2) - ((gy1 + gy2) / 2)) < 20:
                g.append(box)
                added = True
                break

        if not added:
            groups.append([box])

    results = []

    for g in groups:
        gx1 = max(min(b[0] for b in g) - 8, 0)
        gy1 = max(min(b[1] for b in g) - 8, 0)
        gx2 = min(max(b[2] for b in g) + 8, crop.width)
        gy2 = min(max(b[3] for b in g) + 8, crop.height)

        number_img = crop.crop((gx1, gy1, gx2, gy2))

        gray = cv2.cvtColor(np.array(number_img), cv2.COLOR_RGB2GRAY)
        gray = cv2.resize(gray, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
        _, thresh = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY_INV)

        text = pytesseract.image_to_string(
            thresh,
            config="--psm 7 -c tessedit_char_whitelist=0123456789."
        )

        text = text.strip().replace(",", ".")
        match = re.search(r"\d+\.\d+|\d+", text)

        if match:
            value = float(match.group())
            y_center = y1 + (gy1 + gy2) / 2

            results.append({
                "value": value,
                "y": y_center
            })

    results = sorted(results, key=lambda r: r["y"])
    return results


def y_to_depth(y, y_depth_0, y_depth_max, max_depth):
    return round((y - y_depth_0) / (y_depth_max - y_depth_0) * max_depth, 2)


uploaded_file = st.file_uploader("Importer PDF scanné", type=["pdf"])

if uploaded_file:
    zoom = st.sidebar.slider("Qualité image PDF", 2, 5, 3)
    pages = pdf_to_images(uploaded_file, zoom=zoom)

    page_numbers = [p[0] for p in pages]
    selected_page = st.sidebar.selectbox("Page à régler", page_numbers)

    page_img = dict(pages)[selected_page]
    width, height = page_img.size

    st.sidebar.write(f"Image : {width} x {height}")

    y_top = st.sidebar.slider("Y profondeur 0 m", 0, height, int(height * 0.20))
    y_bottom = st.sidebar.slider("Y profondeur max", 0, height, int(height * 0.94))
    max_depth = st.sidebar.number_input("Profondeur max affichée", value=16.0)

    st.sidebar.subheader("Zones colonnes")
    pf_x1 = st.sidebar.slider("Pf X début", 0, width, int(width * 0.50))
    pf_x2 = st.sidebar.slider("Pf X fin", 0, width, int(width * 0.63))

    pl_x1 = st.sidebar.slider("Pl X début", 0, width, int(width * 0.64))
    pl_x2 = st.sidebar.slider("Pl X fin", 0, width, int(width * 0.78))

    em_x1 = st.sidebar.slider("EM X début", 0, width, int(width * 0.79))
    em_x2 = st.sidebar.slider("EM X fin", 0, width, int(width * 0.95))

    preview = np.array(page_img).copy()

    cv2.rectangle(preview, (pf_x1, y_top), (pf_x2, y_bottom), (255, 0, 0), 3)
    cv2.rectangle(preview, (pl_x1, y_top), (pl_x2, y_bottom), (0, 0, 255), 3)
    cv2.rectangle(preview, (em_x1, y_top), (em_x2, y_bottom), (255, 0, 0), 3)

    st.image(preview, caption="Réglage des zones", use_container_width=True)

    if st.button("Extraire tout le PDF"):
        rows = []

        with st.spinner("Extraction en cours..."):
            for page_number, img in pages:
                sondage = extract_sondage(img)

                pf_values = extract_numbers_from_zone(
                    img, pf_x1, pf_x2, y_top, y_bottom, "red"
                )
                pl_values = extract_numbers_from_zone(
                    img, pl_x1, pl_x2, y_top, y_bottom, "blue"
                )
                em_values = extract_numbers_from_zone(
                    img, em_x1, em_x2, y_top, y_bottom, "red"
                )

                n = max(len(pf_values), len(pl_values), len(em_values))

                for i in range(n):
                    y_ref = None

                    if i < len(pf_values):
                        y_ref = pf_values[i]["y"]
                    elif i < len(pl_values):
                        y_ref = pl_values[i]["y"]
                    elif i < len(em_values):
                        y_ref = em_values[i]["y"]

                    profondeur = y_to_depth(y_ref, y_top, y_bottom, max_depth)

                    rows.append({
                        "Page": page_number,
                        "Sondage": sondage,
                        "Profondeur (m)": profondeur,
                        "Pf (MPa)": pf_values[i]["value"] if i < len(pf_values) else None,
                        "Pl (MPa)": pl_values[i]["value"] if i < len(pl_values) else None,
                        "EM (MPa)": em_values[i]["value"] if i < len(em_values) else None,
                    })

        df = pd.DataFrame(rows)

        st.success(f"{len(df)} lignes extraites.")
        edited_df = st.data_editor(df, use_container_width=True, num_rows="dynamic")

        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            edited_df.to_excel(writer, index=False, sheet_name="Extraction")

        output.seek(0)

        st.download_button(
            "Télécharger Excel",
            data=output,
            file_name="extraction_pf_pl_em.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

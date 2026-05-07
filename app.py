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


st.set_page_config(page_title="Extraction Pf Pl EM", layout="wide")
st.title("Extraction Sondage | Profondeur | Pf | Pl | EM")


def pdf_to_images(uploaded_file, zoom=4):
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


def extract_sondage(img):
    header = img.crop((0, 0, img.width, int(img.height * 0.18)))
    text = pytesseract.image_to_string(header, lang="fra+eng")

    m = re.search(r"Sondage\s*[:\-]?\s*([A-Za-z0-9_\-]+)", text, re.IGNORECASE)
    if m:
        return m.group(1)

    return "NON_DETECTE"


def ocr_numbers(img):
    gray = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
    gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)

    data = pytesseract.image_to_data(
        gray,
        lang="fra+eng",
        config="--psm 6 -c tessedit_char_whitelist=0123456789.",
        output_type=pytesseract.Output.DICT,
    )

    numbers = []
    scale = 3

    for i, txt in enumerate(data["text"]):
        txt = txt.strip().replace(",", ".")

        if re.fullmatch(r"\d+(\.\d+)?", txt):
            x = data["left"][i] / scale
            y = data["top"][i] / scale
            w = data["width"][i] / scale
            h = data["height"][i] / scale

            numbers.append({
                "value": float(txt),
                "x": x + w / 2,
                "y": y + h / 2,
            })

    return numbers


def detect_depth_axis(img, x1, x2, y1, y2):
    crop = img.crop((x1, y1, x2, y2))
    nums = ocr_numbers(crop)

    points = []

    for n in nums:
        v = n["value"]
        if float(v).is_integer() and 0 <= v <= 50:
            points.append({
                "depth": float(v),
                "y": y1 + n["y"],
            })

    points = sorted(points, key=lambda p: p["y"])

    clean = []
    for p in points:
        if not clean or abs(clean[-1]["y"] - p["y"]) > 18:
            clean.append(p)

    return clean


def interpolate_depth(y, axis_points):
    axis_points = sorted(axis_points, key=lambda p: p["y"])

    for i in range(len(axis_points) - 1):
        a = axis_points[i]
        b = axis_points[i + 1]

        if a["y"] <= y <= b["y"]:
            ratio = (y - a["y"]) / (b["y"] - a["y"])
            depth = a["depth"] + ratio * (b["depth"] - a["depth"])
            return round(depth, 1)

    return None


def extract_param_column(img, x1, x2, y1, y2, min_value, max_value):
    crop = img.crop((x1, y1, x2, y2))
    nums = ocr_numbers(crop)

    result = []

    for n in nums:
        value = n["value"]

        if min_value <= value <= max_value:
            result.append({
                "value": value,
                "y": y1 + n["y"],
            })

    return sorted(result, key=lambda n: n["y"])


def group_same_y(pf_values, pl_values, em_values, tolerance):
    all_y = []

    for v in pf_values:
        all_y.append(v["y"])
    for v in pl_values:
        all_y.append(v["y"])
    for v in em_values:
        all_y.append(v["y"])

    all_y = sorted(all_y)
    groups = []

    for y in all_y:
        placed = False

        for g in groups:
            if abs(np.mean(g) - y) <= tolerance:
                g.append(y)
                placed = True
                break

        if not placed:
            groups.append([y])

    rows = []

    def nearest_value(values, gy):
        if not values:
            return None

        best = min(values, key=lambda v: abs(v["y"] - gy))

        if abs(best["y"] - gy) <= tolerance:
            return best["value"]

        return None

    for g in groups:
        gy = float(np.mean(g))

        pf = nearest_value(pf_values, gy)
        pl = nearest_value(pl_values, gy)
        em = nearest_value(em_values, gy)

        if pf is not None and pl is not None and em is not None:
            rows.append({
                "y": gy,
                "Pf": pf,
                "Pl": pl,
                "EM": em,
            })

    return rows


uploaded_file = st.file_uploader("Importer le PDF", type=["pdf"])

if uploaded_file:
    pages = pdf_to_images(uploaded_file, zoom=4)
    first_img = pages[0][1]
    W, H = first_img.size

    st.sidebar.header("Réglage axe profondeur")
    depth_x1 = st.sidebar.number_input("Axe profondeur X début", value=int(W * 0.06))
    depth_x2 = st.sidebar.number_input("Axe profondeur X fin", value=int(W * 0.15))
    y_top = st.sidebar.number_input("Y début zone données", value=int(H * 0.20))
    y_bottom = st.sidebar.number_input("Y fin zone données", value=int(H * 0.96))

    st.sidebar.header("Réglage colonnes")
    pf_x1 = st.sidebar.number_input("Pf X début", value=int(W * 0.50))
    pf_x2 = st.sidebar.number_input("Pf X fin", value=int(W * 0.63))

    pl_x1 = st.sidebar.number_input("Pl X début", value=int(W * 0.63))
    pl_x2 = st.sidebar.number_input("Pl X fin", value=int(W * 0.78))

    em_x1 = st.sidebar.number_input("EM X début", value=int(W * 0.78))
    em_x2 = st.sidebar.number_input("EM X fin", value=int(W * 0.94))

    tolerance_y = st.sidebar.number_input("Tolérance même niveau Y", value=35)

    preview = np.array(first_img).copy()

    cv2.rectangle(preview, (int(depth_x1), int(y_top)), (int(depth_x2), int(y_bottom)), (0, 255, 0), 5)
    cv2.rectangle(preview, (int(pf_x1), int(y_top)), (int(pf_x2), int(y_bottom)), (255, 0, 0), 5)
    cv2.rectangle(preview, (int(pl_x1), int(y_top)), (int(pl_x2), int(y_bottom)), (0, 0, 255), 5)
    cv2.rectangle(preview, (int(em_x1), int(y_top)), (int(em_x2), int(y_bottom)), (255, 0, 0), 5)

    st.image(preview, caption="Vérifier les zones : axe profondeur / Pf / Pl / EM", use_container_width=True)

    if st.button("Extraire Excel"):
        final_rows = []

        for page_number, img in pages:
            sondage = extract_sondage(img)

            axis_points = detect_depth_axis(
                img,
                int(depth_x1),
                int(depth_x2),
                int(y_top),
                int(y_bottom),
            )

            pf_values = extract_param_column(
                img,
                int(pf_x1),
                int(pf_x2),
                int(y_top),
                int(y_bottom),
                0,
                20,
            )

            pl_values = extract_param_column(
                img,
                int(pl_x1),
                int(pl_x2),
                int(y_top),
                int(y_bottom),
                0,
                20,
            )

            em_values = extract_param_column(
                img,
                int(em_x1),
                int(em_x2),
                int(y_top),
                int(y_bottom),
                0,
                10000,
            )

            grouped = group_same_y(
                pf_values,
                pl_values,
                em_values,
                tolerance=int(tolerance_y),
            )

            for g in grouped:
                depth = interpolate_depth(g["y"], axis_points)

                if depth is not None:
                    final_rows.append({
                        "Sondage": sondage,
                        "Profondeur": depth,
                        "Pf": g["Pf"],
                        "Pl": g["Pl"],
                        "EM": g["EM"],
                    })

        df = pd.DataFrame(final_rows)

        df = df.sort_values(["Sondage", "Profondeur"]).reset_index(drop=True)

        edited_df = st.data_editor(
            df,
            use_container_width=True,
            num_rows="dynamic",
        )

        output = BytesIO()

        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            edited_df.to_excel(writer, index=False, sheet_name="Extraction")

        output.seek(0)

        st.download_button(
            "Télécharger Excel",
            data=output,
            file_name="extraction_sondages.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

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


st.set_page_config(page_title="Extraction Pressiomètre", layout="wide")
st.title("Extraction automatique Sondage | Profondeur | Pf | Pl | EM")


def pdf_to_images(uploaded_file, zoom=4):
    images = []

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded_file.read())
        path = tmp.name

    doc = fitz.open(path)

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

    m = re.search(r"(SP[_\-]?[A-Za-z]+[_\-]?\d+)", text, re.IGNORECASE)
    if m:
        return m.group(1)

    return "NON_DETECTE"


def number_ocr(crop):
    gray = cv2.cvtColor(np.array(crop), cv2.COLOR_RGB2GRAY)
    gray = cv2.resize(gray, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)

    data = pytesseract.image_to_data(
        gray,
        lang="eng",
        config="--psm 6 -c tessedit_char_whitelist=0123456789.",
        output_type=pytesseract.Output.DICT,
    )

    out = []
    scale = 4

    for i, txt in enumerate(data["text"]):
        txt = txt.strip().replace(",", ".")

        if re.fullmatch(r"\d+(\.\d+)?", txt):
            x = data["left"][i] / scale
            y = data["top"][i] / scale
            w = data["width"][i] / scale
            h = data["height"][i] / scale

            out.append({
                "value": float(txt),
                "x": x + w / 2,
                "y": y + h / 2,
            })

    return out


def get_color_mask(img, color):
    arr = np.array(img)
    hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)

    if color == "red":
        m1 = cv2.inRange(hsv, np.array([0, 50, 40]), np.array([15, 255, 255]))
        m2 = cv2.inRange(hsv, np.array([160, 50, 40]), np.array([180, 255, 255]))
        return cv2.bitwise_or(m1, m2)

    if color == "blue":
        return cv2.inRange(hsv, np.array([85, 40, 30]), np.array([140, 255, 255]))

    return np.zeros(hsv.shape[:2], dtype=np.uint8)


def detect_graph_area(img):
    w, h = img.size

    # Pour ce type de feuille : zone utile sous l'entête
    y_top = int(h * 0.20)
    y_bottom = int(h * 0.96)

    # Colonnes basées sur la mise en page réelle du pressiomètre
    depth_zone = (int(w * 0.06), int(w * 0.16), y_top, y_bottom)
    pf_zone = (int(w * 0.50), int(w * 0.64), y_top, y_bottom)
    pl_zone = (int(w * 0.64), int(w * 0.78), y_top, y_bottom)
    em_zone = (int(w * 0.78), int(w * 0.95), y_top, y_bottom)

    return depth_zone, pf_zone, pl_zone, em_zone


def extract_depth_axis(img, zone):
    x1, x2, y1, y2 = zone
    crop = img.crop((x1, y1, x2, y2))
    nums = number_ocr(crop)

    points = []

    for n in nums:
        v = n["value"]
        if float(v).is_integer() and 0 <= v <= 30:
            points.append({
                "depth": float(v),
                "y": y1 + n["y"],
            })

    points = sorted(points, key=lambda p: p["y"])

    cleaned = []
    for p in points:
        if not cleaned or abs(cleaned[-1]["y"] - p["y"]) > 25:
            cleaned.append(p)

    return cleaned


def interpolate_depth(y, axis_points):
    axis_points = sorted(axis_points, key=lambda p: p["y"])

    for i in range(len(axis_points) - 1):
        a = axis_points[i]
        b = axis_points[i + 1]

        if a["y"] <= y <= b["y"]:
            r = (y - a["y"]) / (b["y"] - a["y"])
            depth = a["depth"] + r * (b["depth"] - a["depth"])
            return round(depth, 1)

    return None


def extract_colored_numbers(img, zone, color, min_val, max_val):
    x1, x2, y1, y2 = zone
    crop = img.crop((x1, y1, x2, y2))

    mask = get_color_mask(crop, color)
    white = np.ones_like(np.array(crop)) * 255
    white[mask > 0] = np.array(crop)[mask > 0]

    color_only = Image.fromarray(white.astype(np.uint8))
    nums = number_ocr(color_only)

    result = []

    for n in nums:
        if min_val <= n["value"] <= max_val:
            result.append({
                "value": n["value"],
                "y": y1 + n["y"],
            })

    return sorted(result, key=lambda p: p["y"])


def group_values(pf, pl, em, tolerance=45):
    all_y = [v["y"] for v in pf] + [v["y"] for v in pl] + [v["y"] for v in em]
    all_y = sorted(all_y)

    groups = []

    for y in all_y:
        added = False

        for g in groups:
            if abs(np.mean(g) - y) <= tolerance:
                g.append(y)
                added = True
                break

        if not added:
            groups.append([y])

    def nearest(values, gy):
        if not values:
            return None

        item = min(values, key=lambda v: abs(v["y"] - gy))

        if abs(item["y"] - gy) <= tolerance:
            return item["value"]

        return None

    rows = []

    for g in groups:
        gy = float(np.mean(g))

        pfi = nearest(pf, gy)
        pli = nearest(pl, gy)
        emi = nearest(em, gy)

        if pfi is not None and pli is not None and emi is not None:
            rows.append({
                "y": gy,
                "Pf": pfi,
                "Pl": pli,
                "EM": emi,
            })

    return rows


uploaded_file = st.file_uploader("Importer PDF scanné", type=["pdf"])

if uploaded_file:
    pages = pdf_to_images(uploaded_file, zoom=4)

    final_rows = []
    preview_rows = []

    with st.spinner("Extraction automatique en cours..."):
        for page_number, img in pages:
            sondage = extract_sondage(img)

            depth_zone, pf_zone, pl_zone, em_zone = detect_graph_area(img)

            axis = extract_depth_axis(img, depth_zone)

            pf_values = extract_colored_numbers(
                img, pf_zone, color="red", min_val=0, max_val=20
            )

            pl_values = extract_colored_numbers(
                img, pl_zone, color="blue", min_val=0, max_val=20
            )

            em_values = extract_colored_numbers(
                img, em_zone, color="red", min_val=0, max_val=10000
            )

            groups = group_values(pf_values, pl_values, em_values, tolerance=45)

            for g in groups:
                depth = interpolate_depth(g["y"], axis)

                if depth is not None:
                    final_rows.append({
                        "Sondage": sondage,
                        "Profondeur": depth,
                        "Pf": g["Pf"],
                        "Pl": g["Pl"],
                        "EM": g["EM"],
                    })

            if page_number == 1:
                preview = np.array(img).copy()

                for z, color in [
                    (depth_zone, (0, 255, 0)),
                    (pf_zone, (255, 0, 0)),
                    (pl_zone, (0, 0, 255)),
                    (em_zone, (255, 0, 0)),
                ]:
                    x1, x2, y1, y2 = z
                    cv2.rectangle(preview, (x1, y1), (x2, y2), color, 5)

                st.image(preview, caption="Preview détection automatique page 1", use_container_width=True)

    if not final_rows:
        st.error("Aucune donnée détectée. Le scan est peut-être trop flou ou la mise en page différente.")
    else:
        df = pd.DataFrame(final_rows)
        df = df.sort_values(["Sondage", "Profondeur"]).reset_index(drop=True)

        st.success(f"{len(df)} lignes extraites.")

        edited_df = st.data_editor(
            df,
            use_container_width=True,
            num_rows="dynamic"
        )

        output = BytesIO()

        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            edited_df.to_excel(writer, index=False, sheet_name="Extraction")

        output.seek(0)

        st.download_button(
            "Télécharger Excel",
            data=output,
            file_name="extraction_pressiometre.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

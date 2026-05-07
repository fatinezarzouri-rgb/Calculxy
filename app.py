import re
import tempfile
from io import BytesIO

import cv2
import easyocr
import fitz
import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image


st.set_page_config(page_title="Extraction Pressiomètre", layout="wide")
st.title("Extraction automatique Pf / Pl / EM")


reader = easyocr.Reader(["en"], gpu=False)


def pdf_to_images(uploaded_file, zoom=4):
    pages = []

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded_file.read())
        path = tmp.name

    doc = fitz.open(path)

    for i in range(len(doc)):
        page = doc.load_page(i)

        pix = page.get_pixmap(
            matrix=fitz.Matrix(zoom, zoom),
            alpha=False
        )

        img = Image.frombytes(
            "RGB",
            [pix.width, pix.height],
            pix.samples
        )

        pages.append((i + 1, img))

    doc.close()

    return pages


def easyocr_numbers(img):
    arr = np.array(img)

    results = reader.readtext(
        arr,
        detail=1,
        paragraph=False
    )

    out = []

    for r in results:
        box, text, conf = r

        text = text.replace(",", ".").strip()

        if re.fullmatch(r"\d+(\.\d+)?", text):
            try:
                value = float(text)

                xs = [p[0] for p in box]
                ys = [p[1] for p in box]

                out.append({
                    "value": value,
                    "x": np.mean(xs),
                    "y": np.mean(ys),
                })

            except:
                pass

    return out


def extract_sondage(img):
    arr = np.array(img)

    results = reader.readtext(arr, detail=0)

    text = " ".join(results)

    m = re.search(r"(SP[_\-]?[A-Za-z]+[_\-]?\d+)", text)

    if m:
        return m.group(1)

    return "NON_DETECTE"


def get_values_in_zone(values, x1, x2, y1, y2, vmin, vmax):
    out = []

    for v in values:
        if (
            x1 <= v["x"] <= x2
            and y1 <= v["y"] <= y2
            and vmin <= v["value"] <= vmax
        ):
            out.append(v)

    return sorted(out, key=lambda v: v["y"])


def group_triplets(pf, pl, em, tolerance=35):
    rows = []

    for p in pf:
        y = p["y"]

        pl_match = min(pl, key=lambda v: abs(v["y"] - y), default=None)
        em_match = min(em, key=lambda v: abs(v["y"] - y), default=None)

        if pl_match and em_match:
            if (
                abs(pl_match["y"] - y) <= tolerance
                and abs(em_match["y"] - y) <= tolerance
            ):
                rows.append({
                    "y": np.mean([y, pl_match["y"], em_match["y"]]),
                    "Pf": p["value"],
                    "Pl": pl_match["value"],
                    "EM": em_match["value"],
                })

    return rows


def depth_from_y(y, y0, y16):
    depth = (y - y0) / (y16 - y0) * 16
    return round(depth, 1)


uploaded_file = st.file_uploader(
    "Importer PDF",
    type=["pdf"]
)

if uploaded_file:

    pages = pdf_to_images(uploaded_file, zoom=4)

    first_img = pages[0][1]

    W, H = first_img.size

    st.sidebar.header("Calibration")

    y0 = st.sidebar.number_input(
        "Y du 0m",
        value=920
    )

    y16 = st.sidebar.number_input(
        "Y du 16m",
        value=2890
    )

    pf_x1 = st.sidebar.number_input(
        "Pf X début",
        value=1200
    )

    pf_x2 = st.sidebar.number_input(
        "Pf X fin",
        value=1500
    )

    pl_x1 = st.sidebar.number_input(
        "Pl X début",
        value=1500
    )

    pl_x2 = st.sidebar.number_input(
        "Pl X fin",
        value=1800
    )

    em_x1 = st.sidebar.number_input(
        "EM X début",
        value=1800
    )

    em_x2 = st.sidebar.number_input(
        "EM X fin",
        value=2200
    )

    tolerance = st.sidebar.number_input(
        "Tolérance Y",
        value=35
    )

    preview = np.array(first_img).copy()

    cv2.rectangle(
        preview,
        (pf_x1, y0),
        (pf_x2, y16),
        (255, 0, 0),
        4
    )

    cv2.rectangle(
        preview,
        (pl_x1, y0),
        (pl_x2, y16),
        (0, 0, 255),
        4
    )

    cv2.rectangle(
        preview,
        (em_x1, y0),
        (em_x2, y16),
        (255, 0, 0),
        4
    )

    st.image(preview, use_container_width=True)

    if st.button("Extraire Excel"):

        final_rows = []

        for page_number, img in pages:

            sondage = extract_sondage(img)

            values = easyocr_numbers(img)

            pf = get_values_in_zone(
                values,
                pf_x1,
                pf_x2,
                y0,
                y16,
                0,
                20
            )

            pl = get_values_in_zone(
                values,
                pl_x1,
                pl_x2,
                y0,
                y16,
                0,
                20
            )

            em = get_values_in_zone(
                values,
                em_x1,
                em_x2,
                y0,
                y16,
                0,
                10000
            )

            triplets = group_triplets(
                pf,
                pl,
                em,
                tolerance
            )

            for t in triplets:

                final_rows.append({
                    "Sondage": sondage,
                    "Profondeur": depth_from_y(
                        t["y"],
                        y0,
                        y16
                    ),
                    "Pf": t["Pf"],
                    "Pl": t["Pl"],
                    "EM": t["EM"],
                })

        df = pd.DataFrame(final_rows)

        if df.empty:
            st.error("Aucune donnée détectée.")
        else:

            df = df.sort_values(
                ["Sondage", "Profondeur"]
            ).reset_index(drop=True)

            st.data_editor(
                df,
                use_container_width=True,
                num_rows="dynamic"
            )

            output = BytesIO()

            with pd.ExcelWriter(
                output,
                engine="openpyxl"
            ) as writer:

                df.to_excel(
                    writer,
                    index=False,
                    sheet_name="Extraction"
                )

            output.seek(0)

            st.download_button(
                "Télécharger Excel",
                data=output,
                file_name="extraction_pressio.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

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


st.set_page_config(
    page_title="Extraction Pressiomètre",
    layout="wide"
)

st.title("Extraction automatique Pf / Pl / EM")


@st.cache_resource
def load_reader():
    return easyocr.Reader(["en"], gpu=False)


reader = load_reader()


def pdf_to_images(uploaded_file, zoom=4):

    pages = []

    with tempfile.NamedTemporaryFile(
        delete=False,
        suffix=".pdf"
    ) as tmp:

        tmp.write(uploaded_file.read())
        pdf_path = tmp.name

    doc = fitz.open(pdf_path)

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


def extract_sondage(img):

    arr = np.array(img)

    results = reader.readtext(
        arr,
        detail=0
    )

    text = " ".join(results)

    text = text.replace(" ", "_")

    m = re.search(
        r"(SP[_\-]?[A-Za-z]+[_\-]?\d+)",
        text
    )

    if m:
        return m.group(1)

    return "NON_DETECTE"


def extract_all_numbers(img):

    arr = np.array(img)

    results = reader.readtext(
        arr,
        detail=1,
        paragraph=False
    )

    values = []

    for r in results:

        box, text, conf = r

        text = text.strip().replace(",", ".")

        if re.fullmatch(r"\d+(\.\d+)?", text):

            try:

                value = float(text)

                xs = [p[0] for p in box]
                ys = [p[1] for p in box]

                values.append({
                    "value": value,
                    "x": np.mean(xs),
                    "y": np.mean(ys),
                })

            except:
                pass

    return values


def get_zone_values(
    values,
    x1,
    x2,
    y1,
    y2,
    min_value,
    max_value
):

    out = []

    for v in values:

        if (
            x1 <= v["x"] <= x2
            and y1 <= v["y"] <= y2
            and min_value <= v["value"] <= max_value
        ):

            out.append(v)

    return sorted(out, key=lambda v: v["y"])


def group_triplets(
    pf_values,
    pl_values,
    em_values,
    tolerance=35
):

    rows = []

    for pf in pf_values:

        y = pf["y"]

        pl_match = min(
            pl_values,
            key=lambda v: abs(v["y"] - y),
            default=None
        )

        em_match = min(
            em_values,
            key=lambda v: abs(v["y"] - y),
            default=None
        )

        if pl_match and em_match:

            if (
                abs(pl_match["y"] - y) <= tolerance
                and abs(em_match["y"] - y) <= tolerance
            ):

                rows.append({
                    "y": np.mean([
                        pf["y"],
                        pl_match["y"],
                        em_match["y"]
                    ]),
                    "Pf": pf["value"],
                    "Pl": pl_match["value"],
                    "EM": em_match["value"],
                })

    return rows


def depth_from_y(
    y,
    y0,
    y16
):

    depth = (
        (y - y0)
        / (y16 - y0)
    ) * 16

    return round(depth, 1)


uploaded_file = st.file_uploader(
    "Importer PDF",
    type=["pdf"]
)

if uploaded_file:

    pages = pdf_to_images(
        uploaded_file,
        zoom=4
    )

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

    st.image(
        preview,
        use_container_width=True
    )

    if st.button("Extraire Excel"):

        final_rows = []

        for page_number, img in pages:

            sondage = extract_sondage(img)

            values = extract_all_numbers(img)

            pf_values = get_zone_values(
                values,
                pf_x1,
                pf_x2,
                y0,
                y16,
                0,
                20
            )

            pl_values = get_zone_values(
                values,
                pl_x1,
                pl_x2,
                y0,
                y16,
                0,
                20
            )

            em_values = get_zone_values(
                values,
                em_x1,
                em_x2,
                y0,
                y16,
                0,
                10000
            )

            rows = group_triplets(
                pf_values,
                pl_values,
                em_values,
                tolerance
            )

            for r in rows:

                final_rows.append({
                    "Sondage": sondage,
                    "Profondeur": depth_from_y(
                        r["y"],
                        y0,
                        y16
                    ),
                    "Pf": r["Pf"],
                    "Pl": r["Pl"],
                    "EM": r["EM"],
                })

        df = pd.DataFrame(final_rows)

        if df.empty:

            st.error(
                "Aucune donnée détectée."
            )

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

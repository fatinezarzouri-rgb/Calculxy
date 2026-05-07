import re
from io import BytesIO
from pathlib import Path

import cv2
import fitz
import numpy as np
import pandas as pd
import pytesseract
import streamlit as st
from PIL import Image

st.set_page_config(page_title="Extraction pressiométrique OCR", layout="wide")


# =========================================================
# OUTILS
# =========================================================
def clean_text(s: str) -> str:
    rep = {
        "é": "e", "è": "e", "ê": "e", "ë": "e",
        "à": "a", "â": "a",
        "î": "i", "ï": "i",
        "ô": "o",
        "ù": "u", "û": "u",
        "ç": "c",
    }
    s = s.lower()
    for a, b in rep.items():
        s = s.replace(a, b)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def parse_num(s: str):
    s = s.replace(",", ".").replace(" ", "").replace(">", "")
    try:
        return float(s)
    except Exception:
        return None


def is_num_like(s: str) -> bool:
    s = s.strip().replace(",", ".")
    return bool(re.fullmatch(r">?\s*-?\d+(?:\.\d+)?", s))


def render_page(doc, page_index: int, zoom: float = 3.0):
    page = doc[page_index]
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    return arr


# =========================================================
# OCR BOXES
# =========================================================
def ocr_boxes(arr: np.ndarray):
    rgb = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB) if arr.shape[2] == 3 else arr
    data = pytesseract.image_to_data(
        rgb,
        config="--psm 6",
        output_type=pytesseract.Output.DICT
    )

    boxes = []
    n = len(data["text"])
    for i in range(n):
        txt = str(data["text"][i]).strip()
        conf = data["conf"][i]
        if not txt:
            continue

        x = int(data["left"][i])
        y = int(data["top"][i])
        w = int(data["width"][i])
        h = int(data["height"][i])

        boxes.append({
            "text": txt,
            "x0": x,
            "y0": y,
            "x1": x + w,
            "y1": y + h,
            "x": x + w / 2,
            "y": y + h / 2,
            "w": w,
            "h": h,
            "conf": conf,
        })
    return boxes


# =========================================================
# NOM DU SONDAGE
# =========================================================
def detect_sondage_name(arr: np.ndarray):
    h, w = arr.shape[:2]

    # plusieurs crops en haut de page
    boxes = [
        (0.22, 0.80, 0.10, 0.26),
        (0.25, 0.75, 0.12, 0.24),
        (0.28, 0.70, 0.10, 0.22),
    ]

    patterns = [
        r"Sondage\s*:\s*([A-Za-z0-9_\-/]+)",
        r"Sondage\s+([A-Za-z0-9_\-/]+)",
        r"(SP[_\-]?(?:Rem|Reta)[_\-]?\d+)",
        r"(T\d+\-SCP\-EXE\-\d+)",
        r"(T\d+\-[A-Za-z0-9\-]+)",
    ]

    for bx1, bx2, by1, by2 in boxes:
        x1 = int(w * bx1)
        x2 = int(w * bx2)
        y1 = int(h * by1)
        y2 = int(h * by2)

        crop = arr[y1:y2, x1:x2]
        gray = Image.fromarray(crop).convert("L")
        variants = [
            gray.resize((gray.width * 2, gray.height * 2)),
            gray.point(lambda p: 255 if p > 170 else 0).resize((gray.width * 3, gray.height * 3)),
            gray.point(lambda p: 255 if p > 145 else 0).resize((gray.width * 3, gray.height * 3)),
        ]

        for img in variants:
            for psm in [6, 11, 12]:
                txt = pytesseract.image_to_string(img, config=f"--psm {psm}")
                txt = txt.replace("\n", " ")
                for pat in patterns:
                    m = re.search(pat, txt, flags=re.IGNORECASE)
                    if m:
                        return m.group(1).strip()

    return ""


# =========================================================
# AXE DES PROFONDEURS
# =========================================================
def detect_depth_ticks(boxes):
    """
    Cherche les graduations 0,1,2,3... sur l'axe vertical.
    """
    ticks = []
    for b in boxes:
        txt = b["text"].replace(",", ".").strip()
        if re.fullmatch(r"\d+(?:\.\d+)?", txt):
            val = float(txt)
            if 0 <= val <= 100:
                ticks.append({"x": b["x"], "y": b["y"], "depth": val})

    if not ticks:
        return []

    # priorité aux graduations les plus à gauche
    min_x = min(t["x"] for t in ticks)
    band = [t for t in ticks if t["x"] <= min_x + 120]
    band = sorted(band, key=lambda z: z["y"])

    # garder monotone
    clean = []
    for t in band:
        if not clean:
            clean.append(t)
        else:
            if abs(t["y"] - clean[-1]["y"]) > 5 and t["depth"] >= clean[-1]["depth"]:
                clean.append(t)

    return clean


def interpolate_depth(y_value, ticks):
    if len(ticks) < 2:
        return None

    ticks = sorted(ticks, key=lambda z: z["y"])

    if y_value <= ticks[0]["y"]:
        t1, t2 = ticks[0], ticks[1]
    elif y_value >= ticks[-1]["y"]:
        t1, t2 = ticks[-2], ticks[-1]
    else:
        t1, t2 = None, None
        for i in range(len(ticks) - 1):
            if ticks[i]["y"] <= y_value <= ticks[i + 1]["y"]:
                t1, t2 = ticks[i], ticks[i + 1]
                break
        if t1 is None:
            return None

    if abs(t2["y"] - t1["y"]) < 1e-6:
        return round(t1["depth"], 1)

    ratio = (y_value - t1["y"]) / (t2["y"] - t1["y"])
    d = t1["depth"] + ratio * (t2["depth"] - t1["depth"])
    return round(d, 1)


# =========================================================
# PF / PL / EM
# =========================================================
def detect_headers(boxes):
    headers = {"PF": None, "PL": None, "EM": None}

    for b in boxes:
        t = clean_text(b["text"])

        if t in ["pf", "pfo"] or "fluage" in t:
            if headers["PF"] is None:
                headers["PF"] = b

        if t in ["pl"] or "limite" in t:
            if headers["PL"] is None:
                headers["PL"] = b

        if t in ["em"] or "module" in t:
            if headers["EM"] is None:
                headers["EM"] = b

    return headers


def collect_values_under_header(boxes, header_box, x_tol=70, y_gap=10):
    if header_box is None:
        return []

    hx = header_box["x"]
    hy = header_box["y"]

    vals = []
    for b in boxes:
        if b["y"] > hy + y_gap and abs(b["x"] - hx) <= x_tol:
            if is_num_like(b["text"]):
                num = parse_num(b["text"])
                if num is not None:
                    vals.append({
                        "y": b["y"],
                        "value": num,
                        "raw": b["text"]
                    })

    vals = sorted(vals, key=lambda z: z["y"])

    clean = []
    for v in vals:
        if not clean or abs(v["y"] - clean[-1]["y"]) > 4:
            clean.append(v)

    return clean


def merge_pf_pl_em(pf_vals, pl_vals, em_vals, ticks, y_tol=10):
    pts = []

    for v in pf_vals:
        pts.append({"kind": "PF", **v})
    for v in pl_vals:
        pts.append({"kind": "PL", **v})
    for v in em_vals:
        pts.append({"kind": "EM", **v})

    pts = sorted(pts, key=lambda z: z["y"])

    groups = []
    for p in pts:
        if not groups or abs(p["y"] - groups[-1]["y_ref"]) > y_tol:
            groups.append({"y_ref": p["y"], "PF": None, "PL": None, "EM": None})
        g = groups[-1]
        g[p["kind"]] = p["value"]

    rows = []
    for g in groups:
        depth = interpolate_depth(g["y_ref"], ticks)
        if depth is None:
            continue

        if g["PF"] is None and g["PL"] is None and g["EM"] is None:
            continue

        rows.append({
            "Profondeur (m)": depth,
            "PF": g["PF"],
            "PL": g["PL"],
            "EM": g["EM"]
        })

    return rows


# =========================================================
# EXTRACTION PAGE
# =========================================================
def extract_page(page, page_num, doc):
    arr = render_page(doc, page_num - 1, zoom=3.0)
    boxes = ocr_boxes(arr)

    sondage = detect_sondage_name(arr)
    if not sondage:
        sondage = f"PAGE_{page_num:03d}"

    ticks = detect_depth_ticks(boxes)
    headers = detect_headers(boxes)

    pf_vals = collect_values_under_header(boxes, headers["PF"], x_tol=80)
    pl_vals = collect_values_under_header(boxes, headers["PL"], x_tol=80)
    em_vals = collect_values_under_header(boxes, headers["EM"], x_tol=100)

    rows = merge_pf_pl_em(pf_vals, pl_vals, em_vals, ticks, y_tol=10)

    out = []
    for r in rows:
        out.append({
            "Sondage": sondage,
            **r
        })
    return out


# =========================================================
# PDF COMPLET
# =========================================================
def extract_pdf(pdf_bytes: bytes):
    tmp = Path("tmp_scan_pressio.pdf")
    tmp.write_bytes(pdf_bytes)

    doc = fitz.open(str(tmp))
    rows = []

    for i in range(len(doc)):
        rows.extend(extract_page(doc[i], i + 1, doc))

    return pd.DataFrame(rows)


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Pressiometrique")
    bio.seek(0)
    return bio.getvalue()


# =========================================================
# UI
# =========================================================
st.title("Extraction pressiométrique OCR")

pdf_file = st.file_uploader("", type=["pdf"])

if st.button("Lancer l'extraction", type="primary"):
    if pdf_file is None:
        st.error("Charge d'abord le PDF.")
    else:
        try:
            with st.spinner("Extraction OCR en cours..."):
                df = extract_pdf(pdf_file.read())

            if df.empty:
                st.warning("Aucune donnée détectée.")
            else:
                st.success(f"Extraction terminée : {len(df)} lignes")
                st.dataframe(df, use_container_width=True)

                st.download_button(
                    "Télécharger l'Excel",
                    data=to_excel_bytes(df),
                    file_name="pressiometrique_ocr.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
        except Exception as e:
            st.exception(e)

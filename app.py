import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import streamlit as st
import easyocr
import numpy as np
from PIL import Image


st.set_page_config(page_title="TEST OCR")

st.title("TEST EASYOCR")


@st.cache_resource
def load_reader():
    return easyocr.Reader(
        ["en"],
        gpu=False
    )


reader = load_reader()

st.success("EasyOCR chargé avec succès")


uploaded = st.file_uploader(
    "Upload image",
    type=["png", "jpg", "jpeg"]
)

if uploaded:

    image = Image.open(uploaded).convert("RGB")

    st.image(image)

    arr = np.array(image)

    results = reader.readtext(
        arr,
        detail=1
    )

    st.write(results)

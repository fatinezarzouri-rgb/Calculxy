import streamlit as st
import easyocr

st.title("TEST OK")

reader = easyocr.Reader(["en"], gpu=False)

st.success("EasyOCR chargé")

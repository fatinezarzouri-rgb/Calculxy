import re
from io import BytesIO

import fitz
import pandas as pd
import pytesseract
import streamlit as st
from PIL import Image, ImageFilter, ImageEnhance


st.set_page_config(page_title="PDF OCR vers Excel", layout="wide")
st.title("Extraction OCR PDF vers Excel - Version Améliorée")


def preprocess_image(img):
    """Améliore l'image pour un meilleur OCR"""
    # Conversion en niveaux de gris
    if img.mode != "L":
        img = img.convert("L")
    
    # Augmentation du contraste
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2.0)
    
    # Réduction du bruit
    img = img.filter(ImageFilter.MedianFilter(size=3))
    
    # Binarisation
    img = img.point(lambda x: 0 if x < 180 else 255)
    
    return img


def clean_number(value):
    """Nettoie les nombres (gère espaces, virgules, points)"""
    if not value or pd.isna(value):
        return None
    
    value = str(value).strip()
    
    # Supprime tout sauf chiffres, points, virgules, signes moins
    value = re.sub(r"[^\d,\.\-]", "", value)
    
    # Remplace virgule par point
    value = value.replace(",", ".")
    
    # Supprime les points de milliers (ex: 123.456,78 -> 123456.78)
    if value.count(".") > 1:
        parts = value.split(".")
        value = "".join(parts[:-1]) + "." + parts[-1]
    
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def extract_sondage_name(text):
    """Extrait le nom du sondage avec plusieurs patterns"""
    patterns = [
        r"Sondage\s*[:\-]?\s*([A-Za-z0-9_\-]+(?:Z)?)",
        r"Sondage\s*:\s*([A-Za-z0-9_\-]+)",
        r"SP_[A-Za-z0-9_\-]+",
        r"SP_Rem_\d{3}[A-Z]?",
        r"SP_Reta_\d{3}[A-Z]?",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            # Si c'est un pattern simple qui capture tout
            if match.group(0).startswith(("SP_", "Sondage")):
                if "Sondage" in match.group(0) and len(match.groups()) > 0:
                    return match.group(1)
                return match.group(0)
            return match.group(0)
    
    return None


def extract_coordinates(text):
    """Extrait les coordonnées X et Y"""
    x_val = None
    y_val = None
    
    # Pattern pour X (gère espaces, virgules, points)
    x_patterns = [
        r"X\s*[:\-]?\s*([\d\s]+(?:[,\.]\d+)?)",
        r"X\s*=\s*([\d\s]+(?:[,\.]\d+)?)",
        r"X\s*:\s*([\d\s]+(?:[,\.]\d+)?)",
    ]
    
    # Pattern pour Y
    y_patterns = [
        r"Y\s*[:\-]?\s*([\d\s]+(?:[,\.]\d+)?)",
        r"Y\s*=\s*([\d\s]+(?:[,\.]\d+)?)",
        r"Y\s*:\s*([\d\s]+(?:[,\.]\d+)?)",
    ]
    
    for pattern in x_patterns:
        x_match = re.search(pattern, text, re.I)
        if x_match:
            x_val = clean_number(x_match.group(1))
            if x_val and 200000 <= x_val <= 400000:
                break
    
    for pattern in y_patterns:
        y_match = re.search(pattern, text, re.I)
        if y_match:
            y_val = clean_number(y_match.group(1))
            if y_val and 100000 <= y_val <= 200000:
                break
    
    return x_val, y_val


def extract_data_advanced(text, page_num):
    """Version améliorée de l'extraction des données"""
    
    # Extraction du nom du sondage
    sondage_name = extract_sondage_name(text)
    
    # Recherche des coordonnées sur toute la page
    x_val, y_val = extract_coordinates(text)
    
    # Si pas trouvé, cherche dans les 3000 derniers caractères (où sont les coordonnées)
    if not x_val or not y_val:
        text_end = text[-3000:] if len(text) > 3000 else text
        x_val, y_val = extract_coordinates(text_end)
    
    return {
        "Nom sondage": sondage_name,
        "X": x_val,
        "Y": y_val,
        "Page": page_num,
    }


def ocr_page_advanced(page, dpi=300, psm=6):
    """OCR améliorée avec prétraitement"""
    # Récupération de l'image
    pix = page.get_pixmap(dpi=dpi)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    
    # Prétraitement
    img = preprocess_image(img)
    
    # OCR avec configuration optimisée
    custom_config = f"--psm {psm} --oem 3 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_:,.- "
    
    text = pytesseract.image_to_string(
        img,
        lang="eng+fra",
        config=custom_config
    )
    
    return text


def extract_all_pages(doc):
    """Extrait toutes les pages avec OCR améliorée"""
    results = []
    total_pages = len(doc)
    
    progress = st.progress(0)
    status_text = st.empty()
    
    last_valid_name = None
    
    for i, page in enumerate(doc):
        page_num = i + 1
        status_text.text(f"Traitement page {page_num}/{total_pages}...")
        
        # Plusieurs tentatives avec différents paramètres OCR
        best_result = None
        best_score = -1
        
        attempts = [
            {"dpi": 300, "psm": 6},  # Bloc de texte uniforme
            {"dpi": 350, "psm": 4},  # Texte à une seule colonne
            {"dpi": 280, "psm": 3},  # Bloc automatique
        ]
        
        for attempt in attempts:
            text = ocr_page_advanced(page, dpi=attempt["dpi"], psm=attempt["psm"])
            result = extract_data_advanced(text, page_num)
            
            # Score basé sur la qualité de l'extraction
            score = 0
            if result["Nom sondage"]:
                score += 2
            if result["X"] and 200000 <= result["X"] <= 400000:
                score += 3
            if result["Y"] and 100000 <= result["Y"] <= 200000:
                score += 3
            
            if score > best_score:
                best_score = score
                best_result = result
        
        # Si on a trouvé un nom valide, on le garde
        if best_result and best_result["Nom sondage"]:
            last_valid_name = best_result["Nom sondage"]
            results.append(best_result)
        elif last_valid_name:
            # Utilise le dernier nom valide et incrémente
            match = re.search(r"(\d+)$", last_valid_name)
            if match:
                num = int(match.group(1)) + 1
                new_name = re.sub(r"\d+$", f"{num:03d}", last_valid_name)
                best_result["Nom sondage"] = new_name
                results.append(best_result)
            else:
                results.append(best_result)
        else:
            results.append(best_result)
        
        progress.progress((i + 1) / total_pages)
    
    status_text.text("Extraction terminée !")
    
    return results


def validate_coordinates(x, y):
    """Valide les coordonnées"""
    x_valid = x is not None and 200000 <= x <= 400000
    y_valid = y is not None and 100000 <= y <= 200000
    return x_valid, y_valid


def detect_errors_advanced(df):
    """Détection améliorée des erreurs"""
    df["Erreur"] = ""
    
    for idx, row in df.iterrows():
        errors = []
        
        # Vérification nom sondage
        if pd.isna(row.get("Nom sondage")) or not row.get("Nom sondage"):
            errors.append("Nom manquant")
        elif not re.match(r"^SP_[A-Za-z]+_\d{3}[A-Z]?$", str(row["Nom sondage"])):
            errors.append("Nom suspect")
        
        # Vérification X
        if pd.isna(row.get("X")):
            errors.append("X manquant")
        elif not (200000 <= row["X"] <= 400000):
            errors.append(f"X suspect ({row['X']})")
        
        # Vérification Y
        if pd.isna(row.get("Y")):
            errors.append("Y manquant")
        elif not (100000 <= row["Y"] <= 200000):
            errors.append(f"Y suspect ({row['Y']})")
        
        df.at[idx, "Erreur"] = "; ".join(errors) if errors else ""
    
    return df


def manual_fix_page(doc, page_num):
    """Correction manuelle guidée d'une page"""
    page = doc[page_num - 1]
    text = ocr_page_advanced(page)
    
    st.write(f"### Page {page_num} - Résultat OCR brut :")
    st.text_area("Texte OCR", text[:2000], height=200)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        nom = st.text_input("Nom du sondage", key=f"nom_{page_num}")
    with col2:
        x_val = st.number_input("X", value=0.0, format="%.2f", key=f"x_{page_num}")
    with col3:
        y_val = st.number_input("Y", value=0.0, format="%.2f", key=f"y_{page_num}")
    
    if st.button(f"Valider page {page_num}", key=f"valider_{page_num}"):
        return {
            "Nom sondage": nom if nom else None,
            "X": x_val if x_val != 0 else None,
            "Y": y_val if y_val != 0 else None,
            "Page": page_num,
        }
    
    return None


uploaded_pdf = st.file_uploader("Importer le PDF des sondages", type=["pdf"])

if uploaded_pdf:
    pdf_bytes = uploaded_pdf.getvalue()
    
    if "df_result" not in st.session_state:
        st.session_state.df_result = None
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🚀 Extraire automatiquement", use_container_width=True):
            try:
                doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                results = extract_all_pages(doc)
                
                if results:
                    df = pd.DataFrame(results)
                    df = detect_errors_advanced(df)
                    st.session_state.df_result = df
                    st.success(f"✅ Extraction terminée : {len(df)} lignes trouvées")
                else:
                    st.warning("⚠️ Aucune donnée trouvée")
            except Exception as e:
                st.error(f"❌ Erreur : {str(e)}")
    
    if st.session_state.df_result is not None:
        df = st.session_state.df_result.copy()
        
        # Affichage du tableau éditable
        st.subheader("📊 Résultats de l'extraction")
        
        edited_df = st.data_editor(
            df,
            use_container_width=True,
            num_rows="dynamic",
            column_config={
                "Nom sondage": st.column_config.TextColumn("Nom sondage", required=True),
                "X": st.column_config.NumberColumn("X", format="%.2f", min_value=200000, max_value=400000),
                "Y": st.column_config.NumberColumn("Y", format="%.2f", min_value=100000, max_value=200000),
                "Page": st.column_config.NumberColumn("Page", format="%d"),
                "Erreur": st.column_config.TextColumn("Erreurs", disabled=True),
            }
        )
        
        # Revalider après édition
        edited_df = detect_errors_advanced(edited_df)
        errors_remaining = edited_df[edited_df["Erreur"] != ""]
        
        # Statistiques
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total sondages", len(edited_df))
        with col2:
            st.metric("Sans erreur", len(edited_df) - len(errors_remaining))
        with col3:
            st.metric("Avec erreurs", len(errors_remaining))
        
        if len(errors_remaining) > 0:
            st.warning(f"⚠️ {len(errors_remaining)} ligne(s) à corriger")
            st.dataframe(errors_remaining[["Page", "Erreur"]], use_container_width=True)
        
        # Export Excel
        final_df = edited_df.drop(columns=["Erreur"], errors="ignore")
        
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            final_df.to_excel(writer, index=False, sheet_name="Sondages")
            
            # Ajout d'une feuille de synthèse
            summary = pd.DataFrame({
                "Statistique": ["Total sondages", "Pages traitées", "Date extraction"],
                "Valeur": [len(final_df), final_df["Page"].max() if not final_df.empty else 0, pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")]
            })
            summary.to_excel(writer, index=False, sheet_name="Synthèse")
        
        output.seek(0)
        
        st.download_button(
            label="📥 Télécharger Excel",
            data=output,
            file_name="sondages_extraits.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

import re
from io import BytesIO

import fitz
import pandas as pd
import pytesseract
import streamlit as st
from PIL import Image, ImageFilter, ImageEnhance


st.set_page_config(page_title="PDF OCR vers Excel", layout="wide")
st.title("Extraction OCR PDF vers Excel - Version Optimisée")


def preprocess_image(img):
    """Améliore l'image pour un meilleur OCR"""
    if img.mode != "L":
        img = img.convert("L")
    
    # Augmentation du contraste
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2.5)
    
    # Réduction du bruit
    img = img.filter(ImageFilter.MedianFilter(size=3))
    
    # Binarisation adaptative
    img = img.point(lambda x: 0 if x < 200 else 255)
    
    # Agrandissement léger pour meilleure reconnaissance
    width, height = img.size
    img = img.resize((int(width * 1.5), int(height * 1.5)), Image.Resampling.LANCZOS)
    
    return img


def clean_number(value):
    """Nettoie les nombres (gère espaces, virgules, points)"""
    if not value or pd.isna(value):
        return None
    
    value = str(value).strip()
    
    # Supprime tout sauf chiffres, points, virgules
    value = re.sub(r"[^\d,\.]", "", value)
    
    # Remplace virgule par point
    value = value.replace(",", ".")
    
    # Supprime les points de milliers
    if value.count(".") > 1:
        parts = value.split(".")
        value = "".join(parts[:-1]) + "." + parts[-1]
    
    try:
        num = float(value)
        return num
    except (ValueError, TypeError):
        return None


def extract_sondage_name_optimized(text):
    """Extrait le nom du sondage de façon optimisée"""
    if not text:
        return None
    
    text_clean = text.replace('\n', ' ').replace('\r', ' ')
    
    # Patterns prioritaires (les plus spécifiques d'abord)
    patterns = [
        # Pattern exact du PDF
        r"Sondage\s*:\s*([A-Za-z]+_[A-Za-z]+_\d{3}[A-Z]?)",
        r"Sondage\s+:\s+([A-Za-z]+_[A-Za-z]+_\d{3}[A-Z]?)",
        r"Sondage\s*:\s*(SP_[A-Za-z0-9_\-]+)",
        r"Sondage\s*=\s*([A-Za-z0-9_\-]+)",
        
        # Pattern SP_XXX
        r"\b(SP_Rem_\d{3}[A-Z]?)\b",
        r"\b(SP_Reta_\d{3}[A-Z]?)\b",
        r"\b(SP_[A-Za-z]+_\d{3}[A-Z]?)\b",
        
        # Pattern général
        r"([A-Za-z]+_\d{3}[A-Z]?)",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text_clean, re.IGNORECASE)
        if match:
            name = match.group(1) if match.groups() else match.group(0)
            name = name.strip()
            if len(name) >= 5 and re.match(r"[A-Za-z_]+_\d{3}", name, re.I):
                return name
    
    return None


def extract_coordinates_optimized(text):
    """Extrait les coordonnées X et Y de façon optimisée"""
    x_val = None
    y_val = None
    
    # Nettoyer le texte
    text_clean = text.replace('\n', ' ').replace('\r', ' ')
    
    # Chercher les coordonnées ensemble d'abord
    coord_match = re.search(r"Coordonnées\s*:\s*X\s*:\s*([\d\s,\.]+)\s*Y\s*:\s*([\d\s,\.]+)", text_clean, re.I)
    if coord_match:
        x_val = clean_number(coord_match.group(1))
        y_val = clean_number(coord_match.group(2))
        if x_val and y_val and 200000 <= x_val <= 400000 and 100000 <= y_val <= 200000:
            return x_val, y_val
    
    # Patterns pour X
    x_patterns = [
        r"X\s*:\s*([\d\s]+(?:[,\.]\d+)?)",
        r"X\s*=\s*([\d\s]+(?:[,\.]\d+)?)",
        r"X\s*([\d\s]+(?:[,\.]\d+)?)",
        r"\bX\s*:\s*([\d\s,\.]+?)(?:\s|$)",
    ]
    
    # Patterns pour Y
    y_patterns = [
        r"Y\s*:\s*([\d\s]+(?:[,\.]\d+)?)",
        r"Y\s*=\s*([\d\s]+(?:[,\.]\d+)?)",
        r"Y\s*([\d\s]+(?:[,\.]\d+)?)",
        r"\bY\s*:\s*([\d\s,\.]+?)(?:\s|$)",
    ]
    
    for pattern in x_patterns:
        x_match = re.search(pattern, text_clean, re.I)
        if x_match:
            x_val = clean_number(x_match.group(1))
            if x_val and 200000 <= x_val <= 400000:
                break
    
    for pattern in y_patterns:
        y_match = re.search(pattern, text_clean, re.I)
        if y_match:
            y_val = clean_number(y_match.group(1))
            if y_val and 100000 <= y_val <= 200000:
                break
    
    return x_val, y_val


def extract_data_optimized(text, page_num, last_valid_name=None):
    """Version optimisée de l'extraction des données"""
    
    # Extraction du nom du sondage
    sondage_name = extract_sondage_name_optimized(text)
    
    # Si nom trouvé, le nettoyer
    if sondage_name:
        # Supprimer les caractères indésirables
        sondage_name = re.sub(r'[^\w_\-]', '', sondage_name)
    
    # Extraction des coordonnées
    x_val, y_val = extract_coordinates_optimized(text)
    
    # Si toujours pas de coordonnées, chercher dans les 2000 derniers caractères
    if not x_val or not y_val:
        text_end = text[-2000:] if len(text) > 2000 else text
        x_val, y_val = extract_coordinates_optimized(text_end)
    
    return {
        "Nom sondage": sondage_name,
        "X": x_val,
        "Y": y_val,
        "Page": page_num,
    }


def ocr_page_optimized(page, dpi=300, psm=6):
    """OCR optimisée avec prétraitement - Version corrigée"""
    # Récupération de l'image en niveaux de gris
    pix = page.get_pixmap(dpi=dpi, colorspace="gray")
    img = Image.frombytes("L", [pix.width, pix.height], pix.samples)
    
    # Prétraitement
    img = preprocess_image(img)
    
    # Configuration OCR simplifiée et CORRECTE
    # Le problème était le tiret dans whitelist
    custom_config = f"--psm {psm} --oem 3"
    
    text = pytesseract.image_to_string(
        img,
        lang="fra+eng",
        config=custom_config
    )
    
    return text


def generate_missing_name(results, page_num):
    """Génère un nom pour les sondages manquants"""
    # Chercher le dernier nom valide
    for r in reversed(results):
        if r.get("Nom sondage") and re.match(r"SP_[A-Za-z]+_\d{3}", r["Nom sondage"]):
            last_name = r["Nom sondage"]
            match = re.search(r"(SP_[A-Za-z]+_)(\d{3})", last_name)
            if match:
                prefix = match.group(1)
                num = int(match.group(2)) + 1
                return f"{prefix}{num:03d}"
    
    # Si aucun trouvé, utiliser les patterns de la page
    return f"SP_Sondage_{page_num:03d}"


def extract_all_pages_optimized(doc):
    """Extrait toutes les pages avec OCR optimisée"""
    results = []
    total_pages = len(doc)
    
    progress = st.progress(0)
    status_text = st.empty()
    
    for i, page in enumerate(doc):
        page_num = i + 1
        status_text.text(f"Traitement page {page_num}/{total_pages}...")
        
        # Tentatives OCR avec différents paramètres
        best_result = None
        best_score = -1
        
        # Adapter les tentatives selon la page
        if page_num <= 10:
            attempts = [{"dpi": 350, "psm": 6}, {"dpi": 300, "psm": 4}]
        else:
            attempts = [{"dpi": 300, "psm": 6}, {"dpi": 350, "psm": 6}]
        
        for attempt in attempts:
            try:
                text = ocr_page_optimized(page, dpi=attempt["dpi"], psm=attempt["psm"])
                result = extract_data_optimized(text, page_num)
                
                # Score amélioré
                score = 0
                if result["Nom sondage"] and len(result["Nom sondage"]) >= 5:
                    score += 3
                if result["X"] and 200000 <= result["X"] <= 400000:
                    score += 3
                if result["Y"] and 100000 <= result["Y"] <= 200000:
                    score += 3
                
                # Bonus si le nom correspond aux patterns attendus
                if result["Nom sondage"] and re.match(r"SP_(?:Rem|Reta)_\d{3}", result["Nom sondage"]):
                    score += 2
                
                if score > best_score:
                    best_score = score
                    best_result = result
            except Exception as e:
                st.warning(f"Erreur sur page {page_num}: {str(e)}")
                continue
        
        # Post-traitement
        if best_result:
            # Nettoyer le nom
            if best_result["Nom sondage"]:
                # Corriger les erreurs OCR courantes
                name = best_result["Nom sondage"]
                name = name.replace("S P", "SP").replace("S_P", "SP")
                name = name.replace("0", "O")  # Ne pas confondre 0 et O
                best_result["Nom sondage"] = name
            
            # Validation des coordonnées
            if best_result["X"] and (best_result["X"] < 200000 or best_result["X"] > 400000):
                best_result["X"] = None
            if best_result["Y"] and (best_result["Y"] < 100000 or best_result["Y"] > 200000):
                best_result["Y"] = None
            
            results.append(best_result)
        else:
            results.append({
                "Nom sondage": None,
                "X": None,
                "Y": None,
                "Page": page_num,
            })
        
        progress.progress((i + 1) / total_pages)
    
    # Deuxième passe : générer les noms manquants
    for i, result in enumerate(results):
        if not result["Nom sondage"]:
            result["Nom sondage"] = generate_missing_name(results[:i], result["Page"])
    
    status_text.text("Extraction terminée !")
    
    return results


def detect_errors_minimal(df):
    """Détection minimaliste des erreurs (plus tolérante)"""
    df["Erreur"] = ""
    
    for idx, row in df.iterrows():
        errors = []
        
        # Vérification du nom (plus tolérante)
        nom = row.get("Nom sondage")
        if pd.isna(nom) or not nom:
            errors.append("Nom manquant")
        elif len(str(nom)) < 4:
            errors.append("Nom suspect")
        
        # Vérification X (plus tolérante)
        x_val = row.get("X")
        if pd.isna(x_val):
            errors.append("X manquant")
        elif not (150000 <= x_val <= 450000):  # Plage élargie
            errors.append("X suspect")
        
        # Vérification Y (plus tolérante)
        y_val = row.get("Y")
        if pd.isna(y_val):
            errors.append("Y manquant")
        elif not (80000 <= y_val <= 220000):  # Plage élargie
            errors.append("Y suspect")
        
        df.at[idx, "Erreur"] = "; ".join(errors) if errors else ""
    
    return df


# Interface Streamlit
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
                results = extract_all_pages_optimized(doc)
                
                if results:
                    df = pd.DataFrame(results)
                    df = detect_errors_minimal(df)
                    st.session_state.df_result = df
                    
                    # Statistiques
                    errors_count = len(df[df["Erreur"] != ""])
                    st.success(f"✅ Extraction terminée : {len(df)} lignes trouvées, {errors_count} erreurs")
                else:
                    st.warning("⚠️ Aucune donnée trouvée")
            except Exception as e:
                st.error(f"❌ Erreur : {str(e)}")
    
    if st.session_state.df_result is not None:
        df = st.session_state.df_result.copy()
        
        st.subheader("📊 Résultats de l'extraction")
        
        # Édition manuelle
        edited_df = st.data_editor(
            df,
            use_container_width=True,
            num_rows="dynamic",
            column_config={
                "Nom sondage": st.column_config.TextColumn("Nom sondage", required=True),
                "X": st.column_config.NumberColumn("X", format="%.2f"),
                "Y": st.column_config.NumberColumn("Y", format="%.2f"),
                "Page": st.column_config.NumberColumn("Page", format="%d"),
                "Erreur": st.column_config.TextColumn("Erreurs", disabled=True),
            }
        )
        
        # Revalidation
        edited_df = detect_errors_minimal(edited_df)
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
            
            # Synthèse
            if not final_df.empty:
                summary = pd.DataFrame({
                    "Statistique": ["Total sondages", "Pages traitées", "Date extraction"],
                    "Valeur": [
                        len(final_df),
                        final_df["Page"].max(),
                        pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
                    ]
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

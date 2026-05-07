import streamlit as st
import pandas as pd
import pdfplumber
import re
from io import BytesIO
from PIL import Image
import pytesseract
import pdf2image

st.set_page_config(
    page_title="Extraction Géotechnique",
    page_icon="🏗️",
    layout="wide"
)

st.title("🏗️ Application d'Extraction Géotechnique")
st.markdown("### Extraction automatique des valeurs pL et EM depuis PDF (avec OCR)")
st.markdown("---")

def extract_from_pdf_with_ocr(pdf_file):
    """Extraction avec OCR pour les PDF scannés"""
    all_data = []
    current_sondage = None
    
    try:
        # Convertir le PDF en images
        images = pdf2image.convert_from_bytes(pdf_file.read(), dpi=200)
        
        for page_num, image in enumerate(images, 1):
            # Appliquer OCR sur l'image
            text = pytesseract.image_to_string(image, lang='fra+eng')
            
            # Chercher le nom du sondage
            sondage_pattern = r'(SP[-_]?[Rr]eta[-_]?\d{3})'
            sondage_match = re.search(sondage_pattern, text)
            if sondage_match:
                current_sondage = sondage_match.group(1)
            
            # Chercher les lignes de données
            # Pattern pour trouver les valeurs (profondeur, pL, EM)
            lines = text.split('\n')
            
            for line in lines:
                # Chercher des motifs avec 3 nombres
                numbers = re.findall(r'\b(\d+\.?\d*)\b', line)
                
                if len(numbers) >= 3:
                    try:
                        profondeur = float(numbers[0])
                        # Filtrer profondeur plausible
                        if 0 <= profondeur <= 50:
                            # Chercher pL (entre 0.5 et 50) et EM (>10)
                            for i in range(len(numbers) - 1):
                                val1 = float(numbers[i])
                                val2 = float(numbers[i + 1])
                                
                                if 0.5 <= val1 <= 50 and val2 > 10:
                                    if current_sondage:
                                        all_data.append({
                                            'Sondage': current_sondage,
                                            'Profondeur (m)': profondeur,
                                            'pL (MPa)': val1,
                                            'EM (MPa)': val2
                                        })
                                        break
                                
                                if val1 > 10 and 0.5 <= val2 <= 50:
                                    if current_sondage:
                                        all_data.append({
                                            'Sondage': current_sondage,
                                            'Profondeur (m)': profondeur,
                                            'pL (MPa)': val2,
                                            'EM (MPa)': val1
                                        })
                                        break
                    except (ValueError, IndexError):
                        continue
            
            # Si pas de sondage trouvé, utiliser un nom par défaut
            if not current_sondage:
                current_sondage = f"SP_Page{page_num}"
        
        # Nettoyer les données
        if all_data:
            df = pd.DataFrame(all_data)
            df = df.drop_duplicates(subset=['Sondage', 'Profondeur (m)'])
            df = df.sort_values(['Sondage', 'Profondeur (m)'])
            return df
        
        return pd.DataFrame()
        
    except Exception as e:
        st.error(f"Erreur OCR: {str(e)}")
        return pd.DataFrame()

def extract_from_pdf_text(pdf_file):
    """Extraction depuis PDF texte (sans OCR)"""
    all_data = []
    current_sondage = None
    
    with pdfplumber.open(pdf_file) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            text = page.extract_text()
            
            if text:
                # Chercher sondage
                sondage_match = re.search(r'(SP[-_]?[Rr]eta[-_]?\d{3})', text)
                if sondage_match:
                    current_sondage = sondage_match.group(1)
                
                # Extraire tableaux
                tables = page.extract_tables()
                for table in tables:
                    if table:
                        for row in table:
                            if row:
                                row_text = ' '.join([str(cell) if cell else '' for cell in row])
                                numbers = re.findall(r'(\d+\.?\d*)', row_text)
                                
                                if len(numbers) >= 3:
                                    try:
                                        profondeur = float(numbers[0])
                                        if 0 <= profondeur <= 50:
                                            for i in range(1, len(numbers)-1):
                                                val1 = float(numbers[i])
                                                val2 = float(numbers[i+1])
                                                
                                                if 0.5 <= val1 <= 50 and val2 > 10:
                                                    if current_sondage:
                                                        all_data.append({
                                                            'Sondage': current_sondage,
                                                            'Profondeur (m)': profondeur,
                                                            'pL (MPa)': val1,
                                                            'EM (MPa)': val2
                                                        })
                                                        break
                                    except:
                                        pass
    
    if all_data:
        df = pd.DataFrame(all_data)
        df = df.drop_duplicates()
        return df
    return pd.DataFrame()

def extract_from_excel(excel_file):
    """Extraction depuis Excel"""
    try:
        df = pd.read_excel(excel_file)
        df.columns = df.columns.str.strip()
        
        # Détection auto des colonnes
        mapping = {}
        for col in df.columns:
            col_lower = col.lower()
            if 'sondage' in col_lower or 'forage' in col_lower:
                mapping['Sondage'] = col
            elif 'profondeur' in col_lower or 'depth' in col_lower or 'prof' in col_lower:
                mapping['Profondeur (m)'] = col
            elif 'pl' in col_lower or 'pL' in col:
                mapping['pL (MPa)'] = col
            elif 'em' in col_lower or 'EM' in col:
                mapping['EM (MPa)'] = col
        
        if len(mapping) == 4:
            result = pd.DataFrame({
                'Sondage': df[mapping['Sondage']],
                'Profondeur (m)': pd.to_numeric(df[mapping['Profondeur (m)']], errors='coerce'),
                'pL (MPa)': pd.to_numeric(df[mapping['pL (MPa)']], errors='coerce'),
                'EM (MPa)': pd.to_numeric(df[mapping['EM (MPa)']], errors='coerce')
            }).dropna()
            return result
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Erreur Excel: {str(e)}")
        return pd.DataFrame()

# Sidebar
with st.sidebar:
    st.header("📁 Import des fichiers")
    
    uploaded_files = st.file_uploader(
        "Choisir des fichiers (PDF ou Excel)",
        type=['pdf', 'xlsx', 'xls'],
        accept_multiple_files=True
    )
    
    st.markdown("---")
    
    # Option OCR
    use_ocr = st.checkbox("🔍 Activer l'OCR (pour PDF scannés)", value=True)
    
    st.markdown("---")
    st.markdown("### 📋 Instructions")
    st.info("""
    **Pour PDF scannés:**
    - Activez l'OCR
    - L'application reconnaît automatiquement le texte
    
    **Pour Excel:**
    - Colonnes automatiquement détectées
    """)

# Stockage
if 'extracted_data' not in st.session_state:
    st.session_state.extracted_data = {}

# Traitement
if uploaded_files:
    for file in uploaded_files:
        file_key = file.name
        
        if file_key not in st.session_state.extracted_data:
            with st.spinner(f"📊 Analyse de {file.name}..."):
                try:
                    if file.name.lower().endswith('.pdf'):
                        if use_ocr:
                            # Réinitialiser le pointeur du fichier
                            file.seek(0)
                            df = extract_from_pdf_with_ocr(file)
                        else:
                            file.seek(0)
                            df = extract_from_pdf_text(file)
                    else:
                        df = extract_from_excel(file)
                    
                    if not df.empty:
                        st.session_state.extracted_data[file_key] = df
                        st.success(f"✅ {file.name}: {len(df)} lignes extraites")
                        
                        # Aperçu
                        with st.expander(f"Aperçu de {file.name}"):
                            st.dataframe(df.head())
                    else:
                        st.warning(f"⚠️ {file.name}: Aucune donnée trouvée")
                        
                        if use_ocr:
                            st.info("💡 Essayez de désactiver l'OCR ou vérifiez le format du PDF")
                        
                except Exception as e:
                    st.error(f"❌ Erreur: {str(e)}")

# Affichage des résultats
if st.session_state.extracted_data:
    st.markdown("## 📊 Résultats de l'extraction")
    
    # Sélection
    selected = st.selectbox(
        "Sélectionner un fichier",
        list(st.session_state.extracted_data.keys())
    )
    
    if selected:
        df = st.session_state.extracted_data[selected]
        
        # Tableau principal
        st.subheader("📋 Données extraites")
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        # Par sondage
        sondages = df['Sondage'].unique()
        
        if len(sondages) > 0:
            st.subheader("📈 Visualisation par sondage")
            
            for sondage in sondages:
                with st.expander(f"Sondage: {sondage}"):
                    sondage_df = df[df['Sondage'] == sondage].sort_values('Profondeur (m)')
                    
                    col1, col2 = st.columns([2, 1])
                    with col1:
                        st.dataframe(sondage_df, hide_index=True, use_container_width=True)
                    with col2:
                        st.metric("Mesures", len(sondage_df))
                        st.metric("Profondeur max", f"{sondage_df['Profondeur (m)'].max():.1f}m")
                    
                    # Graphique
                    st.line_chart(sondage_df.set_index('Profondeur (m)')[['pL (MPa)', 'EM (MPa)']])
        
        # Export
        st.markdown("---")
        csv = df.to_csv(index=False)
        st.download_button(
            label="📥 Télécharger CSV",
            data=csv,
            file_name="extraction_geotech.csv",
            mime="text/csv",
            use_container_width=True
        )

else:
    st.info("👈 **Importez un fichier PDF (même scanné) ou Excel**")
    
    with st.expander("ℹ️ Comment ça marche"):
        st.markdown("""
        **Avec OCR activé:**
        - Convertit chaque page du PDF en image
        - Reconnaît le texte automatiquement
        - Extrait les valeurs de profondeur, pL et EM
        
        **Formats reconnus:**
        - PDF texte: extraction directe plus rapide
        - PDF scanné: nécessite l'OCR (plus lent)
        - Excel: lecture directe
        """)

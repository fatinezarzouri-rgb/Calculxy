import streamlit as st
import pandas as pd
import pdfplumber
import re
import numpy as np
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
st.markdown("### Extraction des valeurs pL et EM avec interpolation des profondeurs")
st.markdown("---")

def interpoler_profondeur(profondeur):
    """Arrondit la profondeur à 1 chiffre après la virgule"""
    return round(profondeur, 1)

def extraire_donnees_propres(df):
    """Nettoie et structure les données correctement"""
    if df.empty:
        return df
    
    # Liste pour stocker les données propres
    donnees_propres = []
    
    # Grouper par sondage
    for sondage in df['Sondage'].unique():
        sondage_df = df[df['Sondage'] == sondage].copy()
        
        # Trier par profondeur
        sondage_df = sondage_df.sort_values('Profondeur (m)')
        
        # Interpolation des profondeurs manquantes
        profondeurs_attendues = np.arange(1.5, 16.0, 1.5)  # 1.5, 3.0, 4.5, ..., 15.0
        profondeurs_existantes = sondage_df['Profondeur (m)'].values
        
        # Pour chaque profondeur attendue
        for prof_attendue in profondeurs_attendues:
            # Chercher la valeur la plus proche
            idx_proche = np.abs(profondeurs_existantes - prof_attendue).argmin()
            prof_proche = profondeurs_existantes[idx_proche]
            ecart = abs(prof_proche - prof_attendue)
            
            # Si l'écart est acceptable (<= 0.5m), on prend cette valeur
            if ecart <= 0.5:
                ligne = sondage_df.iloc[idx_proche]
                donnees_propres.append({
                    'Sondage': sondage,
                    'Profondeur (m)': interpoler_profondeur(prof_attendue),
                    'pL (MPa)': round(ligne['pL (MPa)'], 2),
                    'EM (MPa)': round(ligne['EM (MPa)'], 1)
                })
    
    return pd.DataFrame(donnees_propres)

def extract_from_pdf_optimized(pdf_file):
    """Extraction optimisée depuis PDF"""
    all_data = []
    current_sondage = None
    
    try:
        # Essayer d'abord sans OCR (texte direct)
        with pdfplumber.open(pdf_file) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                text = page.extract_text()
                
                if text:
                    # Chercher sondage
                    sondage_match = re.search(r'(SP[-_]?[Rr]eta[-_]?\d{3})', text)
                    if sondage_match:
                        current_sondage = sondage_match.group(1)
                    
                    # Chercher les lignes avec 3 nombres
                    lines = text.split('\n')
                    for line in lines:
                        numbers = re.findall(r'\b(\d+\.?\d*)\b', line)
                        
                        # Chercher spécifiquement les profondeurs 1.5, 3.0, 4.5, etc.
                        if len(numbers) >= 3:
                            try:
                                for i in range(len(numbers) - 2):
                                    val1 = float(numbers[i])
                                    val2 = float(numbers[i+1])
                                    val3 = float(numbers[i+2])
                                    
                                    # Vérifier si val1 est une profondeur typique
                                    if val1 in [1.5, 3.0, 4.5, 6.0, 7.5, 9.0, 10.5, 12.0, 13.5, 15.0]:
                                        # Vérifier pl et em
                                        if 0.5 <= val2 <= 50 and 10 <= val3 <= 3000:
                                            if current_sondage:
                                                all_data.append({
                                                    'Sondage': current_sondage,
                                                    'Profondeur (m)': val1,
                                                    'pL (MPa)': val2,
                                                    'EM (MPa)': val3
                                                })
                                                break
                                        elif 0.5 <= val3 <= 50 and 10 <= val2 <= 3000:
                                            if current_sondage:
                                                all_data.append({
                                                    'Sondage': current_sondage,
                                                    'Profondeur (m)': val1,
                                                    'pL (MPa)': val3,
                                                    'EM (MPa)': val2
                                                })
                                                break
                            except:
                                pass
        
        # Si rien trouvé, essayer avec OCR
        if not all_data:
            st.info("Extraction OCR en cours...")
            pdf_file.seek(0)
            images = pdf2image.convert_from_bytes(pdf_file.read(), dpi=300)
            
            for page_num, image in enumerate(images, 1):
                text = pytesseract.image_to_string(image, lang='fra+eng', config='--psm 6')
                
                sondage_match = re.search(r'(SP[-_]?[Rr]eta[-_]?\d{3})', text)
                if sondage_match:
                    current_sondage = sondage_match.group(1)
                
                # Chercher les motifs spécifiques comme "1.5 1.17 25.1"
                pattern = r'(\d+\.?\d*)\s+(\d+\.?\d*)\s+(\d+\.?\d*)'
                matches = re.findall(pattern, text)
                
                for match in matches:
                    try:
                        prof = float(match[0])
                        val2 = float(match[1])
                        val3 = float(match[2])
                        
                        if prof in [1.5, 3.0, 4.5, 6.0, 7.5, 9.0, 10.5, 12.0, 13.5, 15.0]:
                            if 0.5 <= val2 <= 50 and 10 <= val3 <= 3000:
                                if current_sondage:
                                    all_data.append({
                                        'Sondage': current_sondage,
                                        'Profondeur (m)': prof,
                                        'pL (MPa)': val2,
                                        'EM (MPa)': val3
                                    })
                            elif 0.5 <= val3 <= 50 and 10 <= val2 <= 3000:
                                if current_sondage:
                                    all_data.append({
                                        'Sondage': current_sondage,
                                        'Profondeur (m)': prof,
                                        'pL (MPa)': val3,
                                        'EM (MPa)': val2
                                    })
                    except:
                        pass
    
    except Exception as e:
        st.error(f"Erreur: {str(e)}")
    
    if all_data:
        df = pd.DataFrame(all_data)
        df = df.drop_duplicates(subset=['Sondage', 'Profondeur (m)'])
        return df
    
    return pd.DataFrame()

def extract_from_excel_simple(excel_file):
    """Extraction simple depuis Excel - une seule feuille avec 4 colonnes"""
    try:
        df = pd.read_excel(excel_file)
        
        # Nettoyer les colonnes
        df.columns = df.columns.str.strip()
        
        # Chercher les colonnes
        colonnes_trouvees = {}
        for col in df.columns:
            col_lower = col.lower()
            if 'sondage' in col_lower or 'forage' in col_lower:
                colonnes_trouvees['Sondage'] = col
            elif 'profondeur' in col_lower or 'depth' in col_lower or 'prof' in col_lower:
                colonnes_trouvees['Profondeur (m)'] = col
            elif 'pl' in col_lower:
                colonnes_trouvees['pL (MPa)'] = col
            elif 'em' in col_lower:
                colonnes_trouvees['EM (MPa)'] = col
        
        if len(colonnes_trouvees) == 4:
            result = pd.DataFrame({
                'Sondage': df[colonnes_trouvees['Sondage']],
                'Profondeur (m)': pd.to_numeric(df[colonnes_trouvees['Profondeur (m)']], errors='coerce'),
                'pL (MPa)': pd.to_numeric(df[colonnes_trouvees['pL (MPa)']], errors='coerce'),
                'EM (MPa)': pd.to_numeric(df[colonnes_trouvees['EM (MPa)']], errors='coerce')
            }).dropna()
            
            # Arrondir profondeur à 1 décimale
            result['Profondeur (m)'] = result['Profondeur (m)'].apply(lambda x: round(x, 1))
            result['pL (MPa)'] = result['pL (MPa)'].apply(lambda x: round(x, 2))
            result['EM (MPa)'] = result['EM (MPa)'].apply(lambda x: round(x, 1))
            
            return result
        
        return pd.DataFrame()
        
    except Exception as e:
        st.error(f"Erreur Excel: {str(e)}")
        return pd.DataFrame()

def generate_excel_single_sheet(data_dict):
    """Génère un Excel avec une seule feuille et 4 colonnes"""
    output = BytesIO()
    
    # Combiner toutes les données
    all_data = []
    for source, df in data_dict.items():
        if not df.empty:
            all_data.append(df)
    
    if all_data:
        final_df = pd.concat(all_data, ignore_index=True)
        final_df = final_df.sort_values(['Sondage', 'Profondeur (m)'])
        
        # Sauvegarder en Excel
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            final_df.to_excel(writer, sheet_name='Données_Geotechniques', index=False)
    
    output.seek(0)
    return output

# Sidebar
with st.sidebar:
    st.header("📁 Import des fichiers")
    
    uploaded_files = st.file_uploader(
        "Choisir des fichiers (PDF ou Excel)",
        type=['pdf', 'xlsx', 'xls'],
        accept_multiple_files=True
    )
    
    st.markdown("---")
    st.markdown("### 📋 Format de sortie")
    st.info("""
    **Excel généré:**
    - Une seule feuille
    - 4 colonnes: 
      - Sondage
      - Profondeur (m)
      - pL (MPa)
      - EM (MPa)
    """)

# Stockage
if 'extracted_data' not in st.session_state:
    st.session_state.extracted_data = {}

# Traitement
if uploaded_files:
    for file in uploaded_files:
        file_key = file.name
        
        if file_key not in st.session_state.extracted_data:
            with st.spinner(f"📊 Extraction de {file.name}..."):
                try:
                    if file.name.lower().endswith('.pdf'):
                        file.seek(0)
                        df = extract_from_pdf_optimized(file)
                    else:
                        df = extract_from_excel_simple(file)
                    
                    if not df.empty:
                        # Nettoyage final
                        df = df.sort_values(['Sondage', 'Profondeur (m)'])
                        st.session_state.extracted_data[file_key] = df
                        st.success(f"✅ {file.name}: {len(df)} lignes extraites")
                    else:
                        st.warning(f"⚠️ {file.name}: Aucune donnée trouvée")
                        
                except Exception as e:
                    st.error(f"❌ Erreur: {str(e)}")

# Affichage
if st.session_state.extracted_data:
    st.markdown("## 📊 Résultats de l'extraction")
    
    # Sélection
    selected = st.selectbox(
        "Sélectionner un fichier",
        list(st.session_state.extracted_data.keys())
    )
    
    if selected:
        df = st.session_state.extracted_data[selected]
        
        # Afficher les données
        st.subheader("📋 Données extraites (4 colonnes)")
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        # Visualisation
        st.subheader("📈 Graphiques")
        
        for sondage in df['Sondage'].unique():
            with st.expander(f"Sondage: {sondage}"):
                sondage_df = df[df['Sondage'] == sondage].sort_values('Profondeur (m)')
                
                col1, col2 = st.columns(2)
                with col1:
                    st.write("**pL (MPa)**")
                    st.line_chart(sondage_df.set_index('Profondeur (m)')['pL (MPa)'])
                
                with col2:
                    st.write("**EM (MPa)**")
                    st.line_chart(sondage_df.set_index('Profondeur (m)')['EM (MPa)'])
        
        # Export Excel (une seule feuille)
        st.markdown("---")
        st.subheader("💾 Export")
        
        excel_file = generate_excel_single_sheet(st.session_state.extracted_data)
        st.download_button(
            label="📥 Télécharger Excel (4 colonnes)",
            data=excel_file,
            file_name="donnees_geotechniques.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
        
        # Statistiques
        with st.expander("📊 Statistiques"):
            st.write("**Résumé par sondage:**")
            summary = df.groupby('Sondage').agg({
                'Profondeur (m)': ['min', 'max', 'count'],
                'pL (MPa)': ['min', 'max', 'mean'],
                'EM (MPa)': ['min', 'max', 'mean']
            }).round(2)
            st.dataframe(summary)

else:
    st.info("👈 **Importez un fichier PDF ou Excel**")
    
    with st.expander("📖 Format Excel attendu"):
        example = pd.DataFrame({
            'Sondage': ['SP_Reta_043', 'SP_Reta_043', 'SP_Reta_044'],
            'Profondeur (m)': [1.5, 3.0, 1.5],
            'pL (MPa)': [1.17, 1.36, 1.85],
            'EM (MPa)': [25.1, 30.6, 29.5]
        })
        st.dataframe(example, use_container_width=True)
        st.caption("4 colonnes: Sondage, Profondeur (m), pL (MPa), EM (MPa)")

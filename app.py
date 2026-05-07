import streamlit as st
import pandas as pd
import pdfplumber
import re
from io import BytesIO

# Configuration de la page
st.set_page_config(
    page_title="Extraction Géotechnique - Autoroute Marrakech",
    page_icon="🏗️",
    layout="wide"
)

# Titre principal
st.title("🏗️ Application d'Extraction Géotechnique")
st.markdown("### Extraction des valeurs pL (MPa) et EM (MPa) par sondage et par profondeur")
st.markdown("---")

# Fonction d'extraction depuis PDF
def extract_from_pdf(pdf_file):
    """Extrait les données Pl et EM par sondage à partir du PDF"""
    data = []
    
    try:
        with pdfplumber.open(pdf_file) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                # Extraire le texte de la page
                text = page.extract_text()
                
                # Chercher les références de sondage
                sondage_pattern = r'(SP[-_]?(?:Reta|Retra|RETA)[-_]?\d{3})'
                sondage_match = re.findall(sondage_pattern, text, re.IGNORECASE) if text else []
                
                # Extraire les tableaux
                tables = page.extract_tables()
                
                for table in tables:
                    if not table:
                        continue
                        
                    for row in table:
                        if not row or len(row) < 3:
                            continue
                        
                        # Parcourir les cellules pour trouver des valeurs
                        for i, cell in enumerate(row):
                            if cell and isinstance(cell, str):
                                # Chercher pattern profondeur (ex: 1.5, 3.0, 4.5)
                                prof_match = re.search(r'\b(\d+\.?\d*)\s*m?\s*$', cell.strip())
                                if prof_match:
                                    try:
                                        profondeur = float(prof_match.group(1))
                                        if 0 <= profondeur <= 50:
                                            # Chercher pl et em dans les cellules suivantes
                                            pl_val = None
                                            em_val = None
                                            
                                            for j in range(i+1, min(i+6, len(row))):
                                                if j < len(row) and row[j]:
                                                    val_match = re.search(r'\b(\d+\.?\d*)\b', str(row[j]))
                                                    if val_match:
                                                        val = float(val_match.group(1))
                                                        if 0.5 <= val <= 50 and pl_val is None:
                                                            pl_val = val
                                                        elif 10 <= val <= 3000 and em_val is None:
                                                            em_val = val
                                                    
                                                    if pl_val is not None and em_val is not None:
                                                        break
                                            
                                            if pl_val is not None and em_val is not None:
                                                sondage = sondage_match[0] if sondage_match else f"SP_{page_num:03d}"
                                                data.append({
                                                    'Sondage': sondage,
                                                    'Profondeur (m)': profondeur,
                                                    'pL (MPa)': pl_val,
                                                    'EM (MPa)': em_val
                                                })
                                    except (ValueError, IndexError):
                                        continue
    except Exception as e:
        st.error(f"Erreur lors de la lecture du PDF: {str(e)}")
    
    return pd.DataFrame(data)

# Fonction d'extraction depuis Excel
def extract_from_excel(excel_file):
    """Extrait les données à partir du fichier Excel"""
    try:
        df = pd.read_excel(excel_file)
        
        # Nettoyer les colonnes
        df.columns = df.columns.str.strip()
        
        # Chercher les colonnes nécessaires
        sondage_col = None
        profondeur_col = None
        pl_col = None
        em_col = None
        
        for col in df.columns:
            col_lower = col.lower()
            if 'sondage' in col_lower or 'forage' in col_lower:
                sondage_col = col
            elif 'profondeur' in col_lower or 'depth' in col_lower:
                profondeur_col = col
            elif 'pl' in col_lower or 'pL' in col:
                pl_col = col
            elif 'em' in col_lower or 'EM' in col:
                em_col = col
        
        if all([sondage_col, profondeur_col, pl_col, em_col]):
            result_df = pd.DataFrame({
                'Sondage': df[sondage_col],
                'Profondeur (m)': pd.to_numeric(df[profondeur_col], errors='coerce'),
                'pL (MPa)': pd.to_numeric(df[pl_col], errors='coerce'),
                'EM (MPa)': pd.to_numeric(df[em_col], errors='coerce')
            })
            result_df = result_df.dropna()
            return result_df
        else:
            st.warning(f"Colonnes non trouvées. Colonnes disponibles: {list(df.columns)}")
            return pd.DataFrame()
            
    except Exception as e:
        st.error(f"Erreur lors de la lecture de l'Excel: {str(e)}")
        return pd.DataFrame()

# Sidebar pour l'import
with st.sidebar:
    st.header("📁 Import des fichiers")
    
    uploaded_files = st.file_uploader(
        "Choisir des fichiers (PDF ou Excel)",
        type=['pdf', 'xlsx', 'xls'],
        accept_multiple_files=True
    )
    
    st.markdown("---")
    st.markdown("### 📋 Format attendu")
    st.info("""
    **Excel:** Fichier avec colonnes:
    - Sondage / forage
    - Profondeur (m)
    - pL (MPa)
    - EM (MPa)
    """)

# Stockage des données
if 'extracted_data' not in st.session_state:
    st.session_state.extracted_data = {}

# Traitement des fichiers
if uploaded_files:
    for file in uploaded_files:
        file_key = file.name
        
        if file_key not in st.session_state.extracted_data:
            with st.spinner(f"📊 Extraction de {file.name}..."):
                try:
                    if file.name.lower().endswith('.pdf'):
                        df = extract_from_pdf(file)
                    else:
                        df = extract_from_excel(file)
                    
                    if not df.empty:
                        st.session_state.extracted_data[file_key] = df
                        st.success(f"✅ {file.name}: {len(df)} lignes extraites")
                    else:
                        st.warning(f"⚠️ {file.name}: Aucune donnée trouvée")
                except Exception as e:
                    st.error(f"❌ Erreur avec {file.name}: {str(e)}")

# Affichage des données
if st.session_state.extracted_data:
    st.markdown("## 📊 Données extraites")
    
    # Sélection du fichier
    selected_file = st.selectbox(
        "📁 Sélectionner un fichier",
        list(st.session_state.extracted_data.keys())
    )
    
    if selected_file:
        df_selected = st.session_state.extracted_data[selected_file]
        
        if not df_selected.empty:
            sondages = sorted(df_selected['Sondage'].unique())
            
            # Filtre par sondage
            selected_sondage = st.selectbox(
                "Filtrer par sondage",
                ["Tous"] + list(sondages)
            )
            
            if selected_sondage != "Tous":
                display_df = df_selected[df_selected['Sondage'] == selected_sondage]
            else:
                display_df = df_selected
            
            # Afficher le tableau
            st.dataframe(
                display_df.sort_values(['Sondage', 'Profondeur (m)']),
                use_container_width=True,
                hide_index=True
            )
            
            # Statistiques
            st.markdown("### 📊 Statistiques")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Nombre total de mesures", len(df_selected))
            
            with col2:
                st.metric("Nombre de sondages", len(sondages))
            
            with col3:
                st.metric("Profondeur max", f"{df_selected['Profondeur (m)'].max():.1f} m")
            
            # Graphiques
            st.markdown("### 📈 Évolution avec la profondeur")
            
            for sondage in sondages[:5]:  # Limiter à 5 sondages pour la lisibilité
                with st.expander(f"Sondage {sondage}"):
                    sondage_df = df_selected[df_selected['Sondage'] == sondage].sort_values('Profondeur (m)')
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write("**pL (MPa)**")
                        st.line_chart(sondage_df.set_index('Profondeur (m)')['pL (MPa)'])
                    
                    with col2:
                        st.write("**EM (MPa)**")
                        st.line_chart(sondage_df.set_index('Profondeur (m)')['EM (MPa)'])
    
    # Export
    st.markdown("---")
    st.markdown("## 💾 Export des données")
    
    # Combiner toutes les données
    all_data = pd.concat(st.session_state.extracted_data.values(), ignore_index=True)
    
    csv = all_data.to_csv(index=False)
    st.download_button(
        label="📥 Télécharger CSV",
        data=csv,
        file_name="donnees_geotechniques.csv",
        mime="text/csv"
    )

else:
    st.info("👈 **Commencez par importer des fichiers PDF ou Excel dans la barre latérale**")
    
    with st.expander("📖 Exemple de format attendu"):
        example_data = {
            'Sondage': ['SP_Reta_043', 'SP_Reta_043', 'SP_Reta_043', 'SP_Reta_044', 'SP_Reta_044'],
            'Profondeur (m)': [1.5, 3.0, 4.5, 1.5, 3.0],
            'pL (MPa)': [1.17, 1.36, 2.56, 1.85, 3.46],
            'EM (MPa)': [25.1, 30.6, 65.1, 29.5, 65.3]
        }
        st.dataframe(pd.DataFrame(example_data), use_container_width=True)

st.markdown("---")
st.markdown("### ℹ️ À propos")
st.markdown("Application pour l'extraction des données géotechniques")

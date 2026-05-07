import streamlit as st
import pandas as pd
import pdfplumber
import re
from io import BytesIO
import numpy as np

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
    
    with pdfplumber.open(pdf_file) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            # Extraire le texte de la page
            text = page.extract_text()
            
            # Chercher les références de sondage
            sondage_pattern = r'(SP_(?:Reta|Retra|RETA)_\d{3})'
            sondage_match = re.findall(sondage_pattern, text, re.IGNORECASE)
            
            # Extraire les tableaux
            tables = page.extract_tables()
            
            for table in tables:
                if not table:
                    continue
                    
                for row in table:
                    if not row or len(row) < 3:
                        continue
                    
                    # Convertir la ligne en texte pour analyse
                    row_text = ' '.join([str(cell) if cell else '' for cell in row])
                    
                    # Chercher les valeurs numériques
                    numbers = re.findall(r'(\d+\.?\d*)', row_text)
                    
                    # Pattern pour identifier une ligne de données de sondage
                    if len(numbers) >= 3:
                        # Vérifier si la première valeur est une profondeur plausible (0-50m)
                        try:
                            profondeur = float(numbers[0])
                            if 0 <= profondeur <= 50:
                                # Chercher les valeurs pl et em
                                pl_values = []
                                em_values = []
                                
                                for i, num in enumerate(numbers[1:], 1):
                                    val = float(num)
                                    # pL typiquement entre 0.5 et 50 MPa
                                    if 0.5 <= val <= 50:
                                        pl_values.append(val)
                                    # EM typiquement entre 10 et 3000 MPa
                                    elif 10 <= val <= 3000:
                                        em_values.append(val)
                                
                                if pl_values and em_values:
                                    # Associer les sondages trouvés
                                    if sondage_match:
                                        current_sondage = sondage_match[0]
                                    else:
                                        current_sondage = f"SP_{page_num:03d}"
                                    
                                    # Prendre la première paire de valeurs
                                    data.append({
                                        'Sondage': current_sondage,
                                        'Profondeur (m)': profondeur,
                                        'pL (MPa)': pl_values[0],
                                        'EM (MPa)': em_values[0] if em_values else np.nan
                                    })
                        except (ValueError, IndexError):
                            continue
    
    # Nettoyer les données
    df = pd.DataFrame(data)
    if not df.empty:
        # Supprimer les doublons
        df = df.drop_duplicates(subset=['Sondage', 'Profondeur (m)'])
        # Trier par sondage et profondeur
        df = df.sort_values(['Sondage', 'Profondeur (m)'])
        # Réinitialiser l'index
        df = df.reset_index(drop=True)
    
    return df

# Fonction d'extraction depuis Excel
def extract_from_excel(excel_file):
    """Extrait les données à partir du fichier Excel"""
    try:
        # Lire le fichier Excel
        excel_data = pd.ExcelFile(excel_file)
        
        # Chercher la feuille avec les données
        target_sheets = ['Extraction pL EM', 'Feuil1', 'Sheet1', 'Données']
        df = None
        
        for sheet in target_sheets:
            if sheet in excel_data.sheet_names:
                df = pd.read_excel(excel_file, sheet_name=sheet)
                break
        
        if df is None:
            df = pd.read_excel(excel_file, sheet_name=excel_data.sheet_names[0])
        
        # Nettoyer les colonnes
        df.columns = df.columns.str.strip()
        
        # Renommer les colonnes si nécessaire
        column_mapping = {
            'pL (MPa)': 'pL (MPa)',
            'EM (MPa)': 'EM (MPa)',
            'Profondeur (m)': 'Profondeur (m)',
            'Sondage': 'Sondage',
            'Pl (MPa)': 'pL (MPa)',
            'Em (MPa)': 'EM (MPa)',
            'profondeur': 'Profondeur (m)',
            'profondeur (m)': 'Profondeur (m)',
            'sondage': 'Sondage'
        }
        
        for old, new in column_mapping.items():
            if old in df.columns:
                df.rename(columns={old: new}, inplace=True)
        
        # Vérifier les colonnes nécessaires
        required_cols = ['Sondage', 'Profondeur (m)', 'pL (MPa)', 'EM (MPa)']
        missing_cols = [col for col in required_cols if col not in df.columns]
        
        if missing_cols:
            st.warning(f"Colonnes manquantes: {missing_cols}")
            st.write("Colonnes disponibles:", list(df.columns))
            return pd.DataFrame()
        
        # Nettoyer les données
        df = df[required_cols].copy()
        df = df.dropna(subset=['Sondage', 'Profondeur (m)'])
        df['Profondeur (m)'] = pd.to_numeric(df['Profondeur (m)'], errors='coerce')
        df['pL (MPa)'] = pd.to_numeric(df['pL (MPa)'], errors='coerce')
        df['EM (MPa)'] = pd.to_numeric(df['EM (MPa)'], errors='coerce')
        df = df.dropna()
        
        return df
        
    except Exception as e:
        st.error(f"Erreur lors de la lecture de l'Excel: {str(e)}")
        return pd.DataFrame()

# Fonction pour générer l'Excel de sortie
def generate_output_excel(data_dict):
    """Génère un fichier Excel avec les données organisées"""
    output = BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Feuille récapitulative
        summary_data = []
        for source, df in data_dict.items():
            if not df.empty:
                for sondage in df['Sondage'].unique():
                    sondage_df = df[df['Sondage'] == sondage]
                    summary_data.append({
                        'Source': source,
                        'Sondage': sondage,
                        'Nombre de mesures': len(sondage_df),
                        'Profondeur min (m)': sondage_df['Profondeur (m)'].min(),
                        'Profondeur max (m)': sondage_df['Profondeur (m)'].max(),
                        'pL min (MPa)': sondage_df['pL (MPa)'].min(),
                        'pL max (MPa)': sondage_df['pL (MPa)'].max(),
                        'EM min (MPa)': sondage_df['EM (MPa)'].min(),
                        'EM max (MPa)': sondage_df['EM (MPa)'].max(),
                    })
        
        if summary_data:
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, sheet_name='Récapitulatif', index=False)
        
        # Données par source
        for source, df in data_dict.items():
            if not df.empty:
                sheet_name = source.replace('.', '_')[:31]
                df.to_excel(writer, sheet_name=sheet_name, index=False)
                
                # Créer une feuille par sondage
                for sondage in df['Sondage'].unique():
                    sondage_df = df[df['Sondage'] == sondage].sort_values('Profondeur (m)')
                    sondage_name = f"{sondage}"[:31]
                    if sondage_name not in writer.sheets:
                        sondage_df.to_excel(writer, sheet_name=sondage_name, index=False)
    
    output.seek(0)
    return output

# Sidebar pour l'import
with st.sidebar:
    st.header("📁 Import des fichiers")
    
    uploaded_files = st.file_uploader(
        "Choisir des fichiers (PDF ou Excel)",
        type=['pdf', 'xlsx', 'xls'],
        accept_multiple_files=True,
        help="Importez vos fichiers PDF contenant les résultats de sondage ou fichiers Excel"
    )
    
    st.markdown("---")
    st.markdown("### 📋 Format attendu")
    st.info("""
    **PDF:** Contenant des tableaux avec les valeurs pL et EM par profondeur
    
    **Excel:** Fichier avec colonnes:
    - Sondage
    - Profondeur (m)
    - pL (MPa)
    - EM (MPa)
    """)
    
    st.markdown("---")
    st.markdown("### 🎯 Instructions")
    st.markdown("""
    1. Importez vos fichiers PDF/Excel
    2. Visualisez les données extraites
    3. Exportez le rapport Excel complet
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
    col1, col2 = st.columns([2, 1])
    with col1:
        selected_file = st.selectbox(
            "📁 Sélectionner un fichier",
            list(st.session_state.extracted_data.keys()),
            key="file_selector"
        )
    
    if selected_file:
        df_selected = st.session_state.extracted_data[selected_file]
        sondages = sorted(df_selected['Sondage'].unique())
        
        # Onglets
        tabs = st.tabs(["📋 Tableau", "📈 Graphiques", "📊 Statistiques"])
        
        with tabs[0]:
            # Tableau des données
            st.subheader(f"Données - {selected_file}")
            
            # Filtre par sondage
            selected_sondage = st.selectbox(
                "Filtrer par sondage",
                ["Tous"] + list(sondages),
                key="sondage_filter"
            )
            
            if selected_sondage != "Tous":
                display_df = df_selected[df_selected['Sondage'] == selected_sondage]
            else:
                display_df = df_selected
            
            # Afficher le tableau
            st.dataframe(
                display_df.sort_values(['Sondage', 'Profondeur (m)']),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Profondeur (m)": st.column_config.NumberColumn(format="%.2f m"),
                    "pL (MPa)": st.column_config.NumberColumn(format="%.2f MPa"),
                    "EM (MPa)": st.column_config.NumberColumn(format="%.2f MPa")
                }
            )
        
        with tabs[1]:
            # Graphiques
            st.subheader("Évolution des paramètres avec la profondeur")
            
            for sondage in sondages:
                with st.expander(f"Sondage {sondage}"):
                    sondage_df = df_selected[df_selected['Sondage'] == sondage].sort_values('Profondeur (m)')
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.markdown("**pL (MPa)**")
                        st.line_chart(
                            sondage_df.set_index('Profondeur (m)')['pL (MPa)'],
                            height=300
                        )
                    
                    with col2:
                        st.markdown("**EM (MPa)**")
                        st.line_chart(
                            sondage_df.set_index('Profondeur (m)')['EM (MPa)'],
                            height=300
                        )
        
        with tabs[2]:
            # Statistiques
            st.subheader("Statistiques par sondage")
            
            stats_data = []
            for sondage in sondages:
                sondage_df = df_selected[df_selected['Sondage'] == sondage]
                stats_data.append({
                    'Sondage': sondage,
                    'Nb mesures': len(sondage_df),
                    'Prof min (m)': sondage_df['Profondeur (m)'].min(),
                    'Prof max (m)': sondage_df['Profondeur (m)'].max(),
                    'pL moyen (MPa)': sondage_df['pL (MPa)'].mean(),
                    'pL max (MPa)': sondage_df['pL (MPa)'].max(),
                    'EM moyen (MPa)': sondage_df['EM (MPa)'].mean(),
                    'EM max (MPa)': sondage_df['EM (MPa)'].max()
                })
            
            stats_df = pd.DataFrame(stats_data)
            st.dataframe(stats_df, use_container_width=True, hide_index=True)
    
    # Export
    st.markdown("---")
    st.markdown("## 💾 Export des données")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("📥 Exporter tout en CSV", use_container_width=True):
            # Combiner toutes les données
            all_data = pd.concat(st.session_state.extracted_data.values(), ignore_index=True)
            csv = all_data.to_csv(index=False)
            st.download_button(
                label="Télécharger CSV",
                data=csv,
                file_name="toutes_donnees_geotech.csv",
                mime="text/csv"
            )
    
    with col2:
        if st.button("📊 Générer rapport Excel", use_container_width=True):
            with st.spinner("Génération du rapport Excel..."):
                excel_report = generate_output_excel(st.session_state.extracted_data)
                st.download_button(
                    label="Télécharger Excel",
                    data=excel_report,
                    file_name="rapport_geotechnique_complet.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
    
    with col3:
        # Résumé
        total_sondages = sum(len(df['Sondage'].unique()) for df in st.session_state.extracted_data.values())
        total_mesures = sum(len(df) for df in st.session_state.extracted_data.values())
        st.metric("Total sondages", total_sondages)
        st.metric("Total mesures", total_mesures)

else:
    # Message d'accueil
    st.info("👈 **Commencez par importer des fichiers PDF ou Excel dans la barre latérale**")
    
    with st.expander("📖 Exemple de format attendu"):
        example_data = {
            'Sondage': ['SP_Reta_043', 'SP_Reta_043', 'SP_Reta_043', 'SP_Reta_044', 'SP_Reta_044'],
            'Profondeur (m)': [1.5, 3.0, 4.5, 1.5, 3.0],
            'pL (MPa)': [1.17, 1.36, 2.56, 1.85, 3.46],
            'EM (MPa)': [25.1, 30.6, 65.1, 29.5, 65.3]
        }
        st.dataframe(pd.DataFrame(example_data), use_container_width=True)
        
        st.markdown("""
        ### Structure attendue du fichier Excel:
        - **Sondage**: Identifiant du sondage (ex: SP_Reta_043)
        - **Profondeur (m)**: Profondeur en mètres
        - **pL (MPa)**: Valeur pL en MPa
        - **EM (MPa)**: Valeur EM en MPa
        """)

st.markdown("---")
st.markdown("### ℹ️ À propos")
st.markdown("Application développée pour l'extraction des données géotechniques - Autoroute Marrakech - Béni Mellal")

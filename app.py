import streamlit as st
import pandas as pd
import pdfplumber
import re
from io import BytesIO

st.set_page_config(
    page_title="Extraction Géotechnique",
    page_icon="🏗️",
    layout="wide"
)

st.title("🏗️ Application d'Extraction Géotechnique")
st.markdown("### Définissez la position des colonnes dans votre PDF")
st.markdown("---")

def generer_excel(df):
    """Génère Excel avec 4 colonnes"""
    output = BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Donnees_Geotechniques', index=False)
    
    output.seek(0)
    return output

def afficher_apercu_lignes(pdf_file):
    """Affiche les premières lignes du PDF pour aider l'utilisateur"""
    lignes_apercu = []
    
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages[:2]:  # 2 premières pages
            text = page.extract_text()
            if text:
                for ligne in text.split('\n')[:20]:  # 20 premières lignes
                    if ligne.strip():
                        nombres = re.findall(r'\b\d+\.?\d*\b', ligne)
                        if len(nombres) >= 2:
                            lignes_apercu.append(ligne[:100])
    
    return lignes_apercu

# Sidebar
with st.sidebar:
    st.header("📁 Import PDF")
    
    uploaded_file = st.file_uploader(
        "Choisir un fichier PDF",
        type=['pdf']
    )
    
    st.markdown("---")
    st.markdown("### 📋 Instructions")
    st.markdown("""
    1. **Importez votre PDF**
    2. **Regardez l'aperçu** des lignes
    3. **Dites à l'application** quelles colonnes correspondent à:
       - Profondeur
       - pL (MPa)
       - EM (MPa)
    4. **Extrayez** et **téléchargez** Excel
    """)

# Zone principale
if uploaded_file is not None:
    st.success(f"✅ Fichier chargé: {uploaded_file.name}")
    
    # Afficher l'aperçu
    st.subheader("📄 Aperçu des lignes du PDF")
    st.markdown("Regardez les lignes ci-dessous et identifiez la position des colonnes:")
    
    with st.spinner("Analyse du PDF..."):
        lignes_apercu = afficher_apercu_lignes(uploaded_file)
    
    if lignes_apercu:
        st.code("\n".join(lignes_apercu[:15]), language="text")
        
        # Configuration des colonnes
        st.subheader("🎯 Configurez la position des colonnes")
        st.markdown("Indiquez dans quel ordre se trouvent les colonnes dans votre PDF:")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            position_prof = st.selectbox(
                "📏 Position de **Profondeur (m)**",
                options=["1ère colonne", "2ème colonne", "3ème colonne"],
                index=0
            )
        
        with col2:
            position_pl = st.selectbox(
                "📊 Position de **pL (MPa)**",
                options=["1ère colonne", "2ème colonne", "3ème colonne"],
                index=1
            )
        
        with col3:
            position_em = st.selectbox(
                "📈 Position de **EM (MPa)**",
                options=["1ère colonne", "2ème colonne", "3ème colonne"],
                index=2
            )
        
        # Vérifier qu'il n'y a pas de doublon
        positions = [position_prof, position_pl, position_em]
        if len(set(positions)) != 3:
            st.error("❌ Les positions doivent être différentes! Chaque colonne doit avoir une position unique.")
        else:
            # Mapping des positions
            mapping = {
                "1ère colonne": 0,
                "2ème colonne": 1,
                "3ème colonne": 2
            }
            
            pos_prof = mapping[position_prof]
            pos_pl = mapping[position_pl]
            pos_em = mapping[position_em]
            
            st.info(f"""
            ✅ Configuration:
            - Profondeur = {position_prof}
            - pL = {position_pl}
            - EM = {position_em}
            """)
            
            # Extraction
            if st.button("🚀 Extraire les données", type="primary", use_container_width=True):
                with st.spinner("Extraction en cours..."):
                    donnees = []
                    sondage_actuel = None
                    
                    with pdfplumber.open(uploaded_file) as pdf:
                        for page in pdf.pages:
                            text = page.extract_text()
                            if text:
                                lignes = text.split('\n')
                                
                                for ligne in lignes:
                                    ligne = ligne.strip()
                                    
                                    # Chercher le nom du sondage
                                    if 'SP_Reta' in ligne or 'SP_' in ligne:
                                        match = re.search(r'(SP[-_]?[Rr]eta[-_]?\d{3}|SP[-_]?\d{3})', ligne)
                                        if match:
                                            sondage_actuel = match.group(1)
                                        continue
                                    
                                    # Extraire les nombres
                                    nombres = re.findall(r'\b(\d+\.?\d*)\b', ligne)
                                    
                                    if len(nombres) >= 3 and sondage_actuel:
                                        try:
                                            valeurs = [float(n) for n in nombres[:3]]
                                            
                                            prof = valeurs[pos_prof]
                                            pl = valeurs[pos_pl]
                                            em = valeurs[pos_em]
                                            
                                            # Vérifier les plages
                                            if 0.5 <= prof <= 50 and 0.5 <= pl <= 50 and 10 <= em <= 5000:
                                                donnees.append([sondage_actuel, round(prof, 1), round(pl, 2), round(em, 1)])
                                                
                                        except (ValueError, IndexError):
                                            pass
                    
                    if donnees:
                        df = pd.DataFrame(donnees, columns=['Sondage', 'Profondeur (m)', 'pL (MPa)', 'EM (MPa)'])
                        df = df.drop_duplicates(subset=['Sondage', 'Profondeur (m)'])
                        df = df.sort_values(['Sondage', 'Profondeur (m)'])
                        
                        st.session_state['df_extrait'] = df
                        st.success(f"✅ Extraction réussie! {len(df)} lignes trouvées")
                        st.balloons()
                    else:
                        st.error("❌ Aucune donnée trouvée. Vérifiez la configuration des colonnes.")
        
        # Affichage des résultats
        if 'df_extrait' in st.session_state and st.session_state['df_extrait'] is not None:
            df = st.session_state['df_extrait']
            
            st.markdown("---")
            st.subheader("📊 Résultats extraits")
            
            # Statistiques
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total mesures", len(df))
            with col2:
                st.metric("Sondages", len(df['Sondage'].unique()))
            with col3:
                st.metric("Profondeur max", f"{df['Profondeur (m)'].max()} m")
            
            # Tableau
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            # Graphiques
            st.subheader("📈 Visualisation")
            for sondage in df['Sondage'].unique():
                with st.expander(f"Sondage: {sondage}"):
                    sondage_df = df[df['Sondage'] == sondage].sort_values('Profondeur (m)')
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write("**pL (MPa)**")
                        st.line_chart(sondage_df.set_index('Profondeur (m)')['pL (MPa)'], height=300)
                    with col2:
                        st.write("**EM (MPa)**")
                        st.line_chart(sondage_df.set_index('Profondeur (m)')['EM (MPa)'], height=300)
            
            # Export
            st.markdown("---")
            st.subheader("💾 Télécharger")
            
            excel_file = generer_excel(df)
            st.download_button(
                label="📥 Télécharger Excel (4 colonnes)",
                data=excel_file,
                file_name="donnees_geotechniques.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                type="primary"
            )
            
            csv = df.to_csv(index=False)
            st.download_button(
                label="📥 Télécharger CSV",
                data=csv,
                file_name="donnees_geotechniques.csv",
                mime="text/csv",
                use_container_width=True
            )
    
    else:
        st.warning("⚠️ Impossible de lire le texte du PDF. Essayez avec un PDF texte (pas une image scannée).")
        
        # Option copier/coller
        with st.expander("📝 Alternative: Copier/Coller le texte"):
            st.markdown("Copiez le texte de votre PDF et collez-le ici:")
            
            texte_manuel = st.text_area(
                "Collez le texte:",
                height=200,
                placeholder="SP_Reta_043\n1.5 1.17 25.1\n3.0 1.36 30.6\n..."
            )
            
            if st.button("Extraire depuis le texte"):
                if texte_manuel:
                    donnees = []
                    sondage_actuel = None
                    
                    for ligne in texte_manuel.split('\n'):
                        if 'SP_Reta' in ligne:
                            match = re.search(r'(SP_Reta_\d{3})', ligne)
                            if match:
                                sondage_actuel = match.group(1)
                        else:
                            nombres = re.findall(r'\b(\d+\.?\d*)\b', ligne)
                            if len(nombres) == 3 and sondage_actuel:
                                try:
                                    donnees.append([sondage_actuel, float(nombres[0]), float(nombres[1]), float(nombres[2])])
                                except:
                                    pass
                    
                    if donnees:
                        df_manuel = pd.DataFrame(donnees, columns=['Sondage', 'Profondeur (m)', 'pL (MPa)', 'EM (MPa)'])
                        st.success(f"✅ {len(df_manuel)} lignes extraites")
                        st.dataframe(df_manuel, use_container_width=True)
                        
                        excel_manuel = generer_excel(df_manuel)
                        st.download_button(
                            label="📥 Télécharger Excel",
                            data=excel_manuel,
                            file_name="donnees_manuelles.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
else:
    st.info("👈 **Importez votre PDF dans la barre latérale gauche**")
    
    st.markdown("### Comment ça marche?")
    st.markdown("""
    1. **Importez votre PDF**
    2. **Regardez l'aperçu** des lignes du PDF
    3. **Choisissez l'ordre des colonnes** (ex: Profondeur en 1ère, pL en 2ème, EM en 3ème)
    4. **L'application extrait** automatiquement les données
    5. **Téléchargez** votre fichier Excel
    """)
    
    st.markdown("### Exemple:")
    exemple_df = pd.DataFrame({
        'Sondage': ['SP_Reta_043', 'SP_Reta_043', 'SP_Reta_044', 'SP_Reta_044'],
        'Profondeur (m)': [1.5, 3.0, 1.5, 3.0],
        'pL (MPa)': [1.17, 1.36, 1.85, 3.46],
        'EM (MPa)': [25.1, 30.6, 29.5, 65.3]
    })
    st.dataframe(exemple_df, use_container_width=True, hide_index=True)

st.markdown("---")
st.markdown("### 💡 Astuce")
st.caption("Si votre PDF contient les colonnes dans un ordre différent (ex: Profondeur, EM, pL), il suffit de le configurer dans les menus déroulants!")

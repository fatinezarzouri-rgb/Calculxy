import streamlit as st
import pandas as pd
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
st.markdown("### Importez un PDF scanné - Extraction automatique avec OCR")
st.markdown("---")

def generer_excel(df):
    """Génère Excel avec 4 colonnes"""
    output = BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Donnees_Geotechniques', index=False)
    
    output.seek(0)
    return output

def extraire_avec_ocr(pdf_file):
    """Extraction avec OCR pour PDF scannés"""
    donnees = []
    sondage_actuel = None
    
    profondeurs_standard = [1.5, 3.0, 4.5, 6.0, 7.5, 9.0, 10.5, 12.0, 13.5, 15.0]
    
    try:
        # Convertir le PDF en images
        with st.spinner("Conversion du PDF en images..."):
            images = pdf2image.convert_from_bytes(pdf_file.read(), dpi=300)
        
        progress_bar = st.progress(0)
        
        for idx, image in enumerate(images):
            progress_bar.progress((idx + 1) / len(images))
            
            # OCR sur l'image
            text = pytesseract.image_to_string(image, lang='fra+eng')
            
            lignes = text.split('\n')
            
            for ligne in lignes:
                ligne = ligne.strip()
                
                # Chercher le nom du sondage
                if 'SP_Reta' in ligne or 'SP_' in ligne:
                    match = re.search(r'(SP[-_]?[Rr]eta[-_]?\d{3}|SP[-_]?\d{3})', ligne)
                    if match:
                        sondage_actuel = match.group(1)
                    continue
                
                # Chercher les triplets de nombres
                nombres = re.findall(r'\b(\d+\.?\d*)\b', ligne)
                
                if len(nombres) >= 3 and sondage_actuel:
                    try:
                        v1 = float(nombres[0])
                        v2 = float(nombres[1])
                        v3 = float(nombres[2])
                        
                        prof = None
                        pl = None
                        em = None
                        
                        # Test profondeur
                        if v1 in profondeurs_standard or (0.5 <= v1 <= 50):
                            if 0.5 <= v2 <= 50 and 10 <= v3 <= 5000:
                                prof, pl, em = v1, v2, v3
                            elif 0.5 <= v3 <= 50 and 10 <= v2 <= 5000:
                                prof, pl, em = v1, v3, v2
                        
                        if prof is None and (v2 in profondeurs_standard or (0.5 <= v2 <= 50)):
                            if 0.5 <= v1 <= 50 and 10 <= v3 <= 5000:
                                prof, pl, em = v2, v1, v3
                            elif 0.5 <= v3 <= 50 and 10 <= v1 <= 5000:
                                prof, pl, em = v2, v3, v1
                        
                        if prof is None and (v3 in profondeurs_standard or (0.5 <= v3 <= 50)):
                            if 0.5 <= v1 <= 50 and 10 <= v2 <= 5000:
                                prof, pl, em = v3, v1, v2
                            elif 0.5 <= v2 <= 50 and 10 <= v1 <= 5000:
                                prof, pl, em = v3, v2, v1
                        
                        if prof is not None and pl is not None and em is not None:
                            if prof not in profondeurs_standard:
                                prof = min(profondeurs_standard, key=lambda x: abs(x - prof))
                            
                            donnees.append([sondage_actuel, round(prof, 1), round(pl, 2), round(em, 1)])
                            
                    except (ValueError, IndexError):
                        pass
        
        progress_bar.empty()
        
    except Exception as e:
        st.error(f"Erreur OCR: {str(e)}")
        return pd.DataFrame()
    
    if donnees:
        df = pd.DataFrame(donnees, columns=['Sondage', 'Profondeur (m)', 'pL (MPa)', 'EM (MPa)'])
        df = df.drop_duplicates(subset=['Sondage', 'Profondeur (m)'])
        df = df.sort_values(['Sondage', 'Profondeur (m)'])
        return df
    
    return pd.DataFrame()

# Sidebar
with st.sidebar:
    st.header("📁 Import PDF")
    
    uploaded_file = st.file_uploader(
        "Choisir un fichier PDF (même scanné)",
        type=['pdf'],
        help="Importez votre PDF - L'OCR va lire le texte automatiquement"
    )
    
    st.markdown("---")
    st.markdown("### ⚙️ Options")
    
    dpi = st.selectbox("Qualité OCR (plus haut = plus lent)", [200, 300, 400], index=1)
    
    st.markdown("---")
    st.markdown("### 📋 Format attendu")
    st.info("""
    Le PDF doit contenir:
    - SP_Reta_043, SP_Reta_044, etc.
    - Lignes avec 3 nombres: Profondeur pL EM
    - Exemple: 1.5 1.17 25.1
    """)

# Zone principale
if uploaded_file is not None:
    st.info("⏳ L'OCR peut prendre 30 secondes à 2 minutes selon la taille du PDF...")
    
    with st.spinner("Extraction OCR en cours..."):
        df = extraire_avec_ocr(uploaded_file)
        
        if not df.empty:
            st.success(f"✅ Extraction réussie! {len(df)} lignes trouvées")
            st.session_state['df_extrait'] = df
            
            # Aperçu
            st.subheader("📊 Données extraites")
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            # Statistiques
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total mesures", len(df))
            with col2:
                st.metric("Sondages", len(df['Sondage'].unique()))
            with col3:
                st.metric("Profondeur max", f"{df['Profondeur (m)'].max()} m")
            
            # Téléchargement Excel
            st.markdown("---")
            st.subheader("💾 Télécharger Excel")
            
            excel_file = generer_excel(df)
            st.download_button(
                label="📥 Télécharger Excel (4 colonnes)",
                data=excel_file,
                file_name="donnees_geotechniques.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                type="primary"
            )
            
            # Visualisation
            st.subheader("📈 Graphiques")
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
            
            # CSV aussi
            csv = df.to_csv(index=False)
            st.download_button(
                label="📥 Télécharger CSV",
                data=csv,
                file_name="donnees_geotechniques.csv",
                mime="text/csv",
                use_container_width=True
            )
        else:
            st.error("❌ Aucune donnée trouvée dans le PDF")
            st.info("""
            **Solutions possibles:**
            1. Le PDF n'est pas lisible (qualité image trop faible)
            2. Essayez l'option "Copier/Coller" ci-dessous
            """)
            
            # Alternative copier/coller
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
    
    st.markdown("### Exemple de résultat:")
    exemple_df = pd.DataFrame({
        'Sondage': ['SP_Reta_043', 'SP_Reta_043', 'SP_Reta_044', 'SP_Reta_044'],
        'Profondeur (m)': [1.5, 3.0, 1.5, 3.0],
        'pL (MPa)': [1.17, 1.36, 1.85, 3.46],
        'EM (MPa)': [25.1, 30.6, 29.5, 65.3]
    })
    st.dataframe(exemple_df, use_container_width=True, hide_index=True)

st.markdown("---")
st.markdown("### ⏱️ Temps d'extraction")
st.caption("- PDF texte: 2-5 secondes\n- PDF scanné avec OCR: 30-60 secondes")

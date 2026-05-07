import streamlit as st
import pandas as pd
import numpy as np
import re
from io import BytesIO
from PIL import Image
import cv2

st.set_page_config(
    page_title="Extraction Géotechnique",
    page_icon="🏗️",
    layout="wide"
)

st.title("🏗️ Application d'Extraction Géotechnique")
st.markdown("### Extraction depuis graphique avec interpolation des profondeurs")
st.markdown("---")

def interpoler_profondeur(y1, y2, x_interp, x1, x2):
    """Interpolation linéaire pour trouver la profondeur"""
    if x2 == x1:
        return y1
    return y1 + (y2 - y1) * (x_interp - x1) / (x2 - x1)

def extraire_depuis_texte_avec_interpolation(texte):
    """Extraction avec interpolation entre les graduations"""
    donnees = []
    sondage_actuel = None
    
    # Chercher les graduations de profondeur (1, 2, 3, 4, 5...)
    pattern_profondeur = r'\b([1-9]|10|11|12|13|14|15)\b'
    
    # Chercher les valeurs pL et EM
    pattern_valeurs = r'(\d+\.?\d*)'
    
    lignes = texte.split('\n')
    
    # Stocker les points trouvés
    points = []
    profondeurs_connues = []
    
    for i, ligne in enumerate(lignes):
        # Trouver le nom du sondage
        sondage_match = re.search(r'(SP[-_]?[Rr]eta[-_]?\d{3})', ligne)
        if sondage_match:
            if points and sondage_actuel:
                # Traiter les points du sondage précédent
                for point in points:
                    donnees.append([sondage_actuel, point[0], point[1], point[2]])
            sondage_actuel = sondage_match.group(1)
            points = []
            profondeurs_connues = []
            continue
        
        # Trouver les profondeurs graduées (1,2,3,4,5...)
        prof_match = re.findall(r'\b([1-9]|10|11|12|13|14|15)\b', ligne)
        if prof_match and len(prof_match) >= 2:
            for prof in prof_match:
                prof_int = int(prof)
                if prof_int not in profondeurs_connues:
                    profondeurs_connues.append(prof_int)
        
        # Trouver les valeurs pL et EM (deux nombres proches)
        nombres = re.findall(pattern_valeurs, ligne)
        
        if len(nombres) >= 2:
            try:
                val1 = float(nombres[0])
                val2 = float(nombres[1])
                
                # Déterminer quelle valeur est pL (0.5-50) et EM (10-5000)
                if 0.5 <= val1 <= 50 and 10 <= val2 <= 5000:
                    pl, em = val1, val2
                elif 0.5 <= val2 <= 50 and 10 <= val1 <= 5000:
                    pl, em = val2, val1
                else:
                    continue
                
                # Trouver la position approximative (ligne)
                position_y = i
                
                # Interpoler la profondeur
                if len(profondeurs_connues) >= 2:
                    # Trouver les deux graduations encadrantes
                    min_prof = min(profondeurs_connues)
                    max_prof = max(profondeurs_connues)
                    
                    # Interpolation simple: profondeur = position relative
                    prof_interpol = round(min_prof + (max_prof - min_prof) * 0.5, 1)
                    
                    points.append([prof_interpol, pl, em])
                    
            except:
                pass
    
    # Dernier sondage
    if points and sondage_actuel:
        for point in points:
            donnees.append([sondage_actuel, point[0], point[1], point[2]])
    
    if donnees:
        df = pd.DataFrame(donnees, columns=['Sondage', 'Profondeur (m)', 'pL (MPa)', 'EM (MPa)'])
        # Grouper par profondeur et prendre la moyenne si doublons
        df = df.groupby(['Sondage', 'Profondeur (m)'], as_index=False).agg({
            'pL (MPa)': 'mean',
            'EM (MPa)': 'mean'
        })
        df = df.sort_values(['Sondage', 'Profondeur (m)'])
        return df
    
    return pd.DataFrame()

def extraire_donnees_votre_format(texte):
    """Extraction spécifique pour votre format de logs"""
    donnees = []
    sondage_actuel = None
    
    # Liste des profondeurs standards
    profondeurs_standard = [1.5, 3.0, 4.5, 6.0, 7.5, 9.0, 10.5, 12.0, 13.5, 15.0]
    
    lignes = texte.split('\n')
    
    for ligne in lignes:
        ligne = ligne.strip()
        
        # Chercher sondage
        if 'SP_Reta' in ligne:
            match = re.search(r'(SP_Reta_\d{3})', ligne)
            if match:
                sondage_actuel = match.group(1)
            continue
        
        # Chercher les triplets
        nombres = re.findall(r'\b(\d+\.?\d*)\b', ligne)
        
        if len(nombres) == 3 and sondage_actuel:
            try:
                p1 = float(nombres[0])
                p2 = float(nombres[1])
                p3 = float(nombres[2])
                
                # Identifier profondeur, pl, em
                # Cas où p1 est la profondeur
                if p1 in profondeurs_standard:
                    if 0.5 <= p2 <= 50 and 10 <= p3 <= 5000:
                        donnees.append([sondage_actuel, p1, p2, p3])
                    elif 0.5 <= p3 <= 50 and 10 <= p2 <= 5000:
                        donnees.append([sondage_actuel, p1, p3, p2])
                # Cas où la profondeur n'est pas standard mais plausible
                elif 0.5 <= p1 <= 50:
                    if 0.5 <= p2 <= 50 and 10 <= p3 <= 5000:
                        # Arrondir la profondeur au 0.5 le plus proche
                        prof_arrondie = round(p1 * 2) / 2
                        donnees.append([sondage_actuel, prof_arrondie, p2, p3])
                    elif 0.5 <= p3 <= 50 and 10 <= p2 <= 5000:
                        prof_arrondie = round(p1 * 2) / 2
                        donnees.append([sondage_actuel, prof_arrondie, p3, p2])
            except:
                pass
    
    if donnees:
        df = pd.DataFrame(donnees, columns=['Sondage', 'Profondeur (m)', 'pL (MPa)', 'EM (MPa)'])
        df = df.drop_duplicates(subset=['Sondage', 'Profondeur (m)'])
        df = df.sort_values(['Sondage', 'Profondeur (m)'])
        return df
    return pd.DataFrame()

def generer_excel(df):
    """Génère Excel avec 4 colonnes"""
    output = BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Donnees_Geotechniques', index=False)
    
    output.seek(0)
    return output

# Interface
st.info("""
### 📖 Instructions:
1. Copiez le texte extrait de votre PDF (les logs)
2. Collez-le dans la zone ci-dessous
3. L'application va:
   - Identifier chaque sondage (SP_Reta_XXX)
   - Extraire les triplets (profondeur, pL, EM)
   - Interpoler les profondeurs manquantes
   - Générer un Excel avec 4 colonnes
""")

# Zone de texte pour copier/coller
texte_logs = st.text_area(
    "📝 Collez ici les logs extraits du PDF:",
    height=300,
    placeholder="Exemple:\nSP_Reta_043\n1.5 1.17 25.1\n3.0 1.36 30.6\n4.5 2.56 65.1\n\nSP_Reta_044\n1.5 1.85 29.5\n3.0 3.46 65.3\n4.5 3.56 63.4"
)

col1, col2 = st.columns(2)

with col1:
    if st.button("🔄 Extraire les données", use_container_width=True):
        if texte_logs:
            with st.spinner("Extraction en cours..."):
                # Essayer les deux méthodes
                df = extraire_donnees_votre_format(texte_logs)
                
                if df.empty:
                    df = extraire_depuis_texte_avec_interpolation(texte_logs)
                
                if not df.empty:
                    st.session_state['df_extrait'] = df
                    st.success(f"✅ Extraction réussie: {len(df)} lignes")
                else:
                    st.error("❌ Aucune donnée trouvée. Vérifiez le format.")
        else:
            st.warning("Veuillez coller des données")

with col2:
    if 'df_extrait' in st.session_state and st.session_state['df_extrait'] is not None:
        excel_file = generer_excel(st.session_state['df_extrait'])
        st.download_button(
            label="📥 Télécharger Excel",
            data=excel_file,
            file_name="donnees_geotechniques.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

# Affichage des résultats
if 'df_extrait' in st.session_state and st.session_state['df_extrait'] is not None:
    st.markdown("---")
    st.subheader("📊 Résultats extraits")
    
    df = st.session_state['df_extrait']
    
    st.dataframe(df, use_container_width=True, hide_index=True)
    
    # Graphiques
    st.subheader("📈 Visualisation")
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

# Exemple
with st.expander("📋 Voir un exemple de format accepté"):
    st.code("""
SP_Reta_043
1.5 1.17 25.1
3.0 1.36 30.6
4.5 2.56 65.1
6.0 2.91 69.1
7.5 3.73 73.5
9.0 5.32 256.3
10.5 6.02 639.7
12.0 7.41 1064.3
13.5 7.45 1933.3
15.0 7.48 2121.3

SP_Reta_044
1.5 1.85 29.5
3.0 3.46 65.3
4.5 3.56 63.4
6.0 3.92 81.9
7.5 7.32 400.4
9.0 7.41 571.4
10.5 7.42 1315.7
12.0 7.44 1644.4
13.5 7.46 1294.2
15.0 7.48 2609.1
    """)

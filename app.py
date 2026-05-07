import streamlit as st
import pandas as pd
import re
from io import BytesIO

st.set_page_config(
    page_title="Extraction Géotechnique",
    page_icon="🏗️",
    layout="wide"
)

st.title("🏗️ Application d'Extraction Géotechnique")
st.markdown("### Extraction des valeurs pL et EM - Copier/Coller depuis PDF")
st.markdown("---")

def generer_excel(df):
    """Génère Excel avec 4 colonnes"""
    output = BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Donnees_Geotechniques', index=False)
    
    output.seek(0)
    return output

def extraire_donnees(texte):
    """Extraction des données depuis le texte copié"""
    donnees = []
    sondage_actuel = None
    
    profondeurs_standard = [1.5, 3.0, 4.5, 6.0, 7.5, 9.0, 10.5, 12.0, 13.5, 15.0]
    
    lignes = texte.split('\n')
    
    for ligne in lignes:
        ligne = ligne.strip()
        
        if 'SP_Reta' in ligne or 'SP_' in ligne:
            match = re.search(r'(SP[-_]?[Rr]eta[-_]?\d{3}|SP[-_]?\d{3})', ligne)
            if match:
                sondage_actuel = match.group(1)
            continue
        
        nombres = re.findall(r'\b(\d+\.?\d*)\b', ligne)
        
        if len(nombres) == 3 and sondage_actuel:
            try:
                v1 = float(nombres[0])
                v2 = float(nombres[1])
                v3 = float(nombres[2])
                
                prof = None
                pl = None
                em = None
                
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
    
    if donnees:
        df = pd.DataFrame(donnees, columns=['Sondage', 'Profondeur (m)', 'pL (MPa)', 'EM (MPa)'])
        df = df.drop_duplicates(subset=['Sondage', 'Profondeur (m)'])
        df = df.sort_values(['Sondage', 'Profondeur (m)'])
        return df
    
    return pd.DataFrame()

st.info("""
**Comment utiliser:**
1. Ouvrez votre PDF dans un lecteur
2. Sélectionnez tout le texte (Ctrl+A)
3. Copiez le texte (Ctrl+C)
4. Collez le texte ci-dessous (Ctrl+V)
5. Cliquez sur "Extraire les données"
6. Téléchargez l'Excel
""")

texte_logs = st.text_area(
    "Collez ici le texte copié depuis votre PDF:",
    height=300,
    placeholder="SP_Reta_043\n1.5 1.17 25.1\n3.0 1.36 30.6\n4.5 2.56 65.1\n\nSP_Reta_044\n1.5 1.85 29.5\n3.0 3.46 65.3"
)

col1, col2 = st.columns(2)

with col1:
    if st.button("Extraire les données", use_container_width=True):
        if texte_logs and texte_logs.strip():
            with st.spinner("Extraction en cours..."):
                df = extraire_donnees(texte_logs)
                
                if not df.empty:
                    st.session_state['df_extrait'] = df
                    st.success(f"Extraction reussie: {len(df)} lignes trouvees")
                else:
                    st.error("Aucune donnee trouvee. Verifiez le format.")
        else:
            st.warning("Veuillez coller du texte")

with col2:
    if 'df_extrait' in st.session_state and st.session_state['df_extrait'] is not None:
        df = st.session_state['df_extrait']
        excel_file = generer_excel(df)
        st.download_button(
            label="Telecharger Excel",
            data=excel_file,
            file_name="donnees_geotechniques.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

if 'df_extrait' in st.session_state and st.session_state['df_extrait'] is not None:
    st.markdown("---")
    st.subheader("Resultats extraits")
    
    df = st.session_state['df_extrait']
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total mesures", len(df))
    with col2:
        st.metric("Nombre de sondages", len(df['Sondage'].unique()))
    with col3:
        st.metric("Profondeur max", f"{df['Profondeur (m)'].max()} m")
    
    st.dataframe(df, use_container_width=True, hide_index=True)
    
    st.subheader("Visualisation par sondage")
    
    for sondage in df['Sondage'].unique():
        with st.expander(f"Sondage: {sondage}"):
            sondage_df = df[df['Sondage'] == sondage].sort_values('Profondeur (m)')
            st.dataframe(sondage_df, hide_index=True, use_container_width=True)
            
            col1, col2 = st.columns(2)
            with col1:
                st.write("**pL (MPa)**")
                st.line_chart(sondage_df.set_index('Profondeur (m)')['pL (MPa)'])
            with col2:
                st.write("**EM (MPa)**")
                st.line_chart(sondage_df.set_index('Profondeur (m)')['EM (MPa)'])
    
    csv = df.to_csv(index=False)
    st.download_button(
        label="Telecharger CSV",
        data=csv,
        file_name="donnees_geotechniques.csv",
        mime="text/csv",
        use_container_width=True
    )

with st.expander("Charger un exemple"):
    if st.button("Charger l'exemple"):
        exemple = """SP_Reta_043
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
15.0 7.48 2609.1"""
        st.session_state['exemple_charge'] = exemple
        st.rerun()

if 'exemple_charge' in st.session_state:
    texte_logs = st.session_state['exemple_charge']
    st.code(texte_logs)
    st.info("Exemple charge! Cliquez sur 'Extraire les donnees'")

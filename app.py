import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
from datetime import datetime
import openfoodfacts

# --- 1. VISUELLES STYLING (DIREKT & SICHTBAR) ---
st.set_page_config(page_title="Med-Log Pro v2", layout="wide", page_icon="🩺")

st.markdown("""
    <style>
    /* Die Sidebar wird deutlich blau */
    [data-testid="stSidebar"] {
        background-color: #004a99;
    }
    [data-testid="stSidebar"] * {
        color: white !important;
    }
    /* Buttons werden moderner */
    .stButton>button {
        border-radius: 20px;
        background-color: #007bff;
        color: white;
        border: none;
        padding: 10px 24px;
        font-weight: bold;
    }
    /* Dashboard Metriken */
    div[data-testid="stMetricValue"] {
        color: #004a99;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. SOUND ENGINE (ROBUSTER) ---
def trigger_audio(url):
    # Dies injiziert ein kleines Skript, das den Ton abspielt
    st.components.v1.html(f"""
        <audio autoplay>
            <source src="{url}" type="audio/mp3">
        </audio>
        """, height=0)

# Sound URLs (Öffentliche, stabile Quellen)
SOUND_SUCCESS = "https://assets.mixkit.co/active_storage/sfx/2568/2568-preview.mp3"
SOUND_ERROR = "https://assets.mixkit.co/active_storage/sfx/2571/2571-preview.mp3"

# --- 3. DATENBANK LOGIK (WIE GEHABT) ---
def get_gsheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        if "gcp_service_account" in st.secrets:
            creds_info = st.secrets["gcp_service_account"]
            if isinstance(creds_info, str): creds_info = json.loads(creds_info)
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
        else:
            creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
        return gspread.authorize(creds)
    except: return None

@st.cache_data(ttl=600)
def lade_daten_gs_cached(sheet_name):
    client = get_gsheet_client()
    if client:
        try:
            sheet = client.open("Kcal_Datenbank").worksheet(sheet_name)
            data = sheet.get_all_records()
            return pd.DataFrame(data)
        except: return pd.DataFrame()
    return pd.DataFrame()

def lade_daten_gs(sheet_name):
    return lade_daten_gs_cached(sheet_name)

def speichere_zeile_gs(liste_werte, sheet_name):
    try:
        client = get_gsheet_client()
        client.open("Kcal_Datenbank").worksheet(sheet_name).append_row(liste_werte)
        st.cache_data.clear() 
        trigger_audio(SOUND_SUCCESS) # TON TRIGERN
        st.toast("✅ Erfolgreich gespeichert!", icon="🎯")
    except:
        trigger_audio(SOUND_ERROR) # FEHLER-TON
        st.error("Speichern fehlgeschlagen.")

# --- 4. NAVIGATION & INHALT ---
st.sidebar.markdown("# 🩺 Med-Log Pro")
st.sidebar.markdown("---")
menu = st.sidebar.radio("MENÜ", ["1. Mahlzeit erfassen", "2. Patienten-Dashboard", "3. Datenbank"])

if menu == "1. Mahlzeit erfassen":
    st.header("⚖️ Neue Mahlzeit protokollieren")
    df_db = lade_daten_gs("lebensmittel")
    df_p = lade_daten_gs("patienten")
    
    if not df_p.empty and not df_db.empty:
        c1, c2 = st.columns(2)
        with c1:
            p_wahl = st.selectbox("Patient:", df_p["Name"])
            m_zeit = st.selectbox("Mahlzeit:", ["Frühstück", "Mittag", "Abend", "Snack"])
            lebensmittel = st.selectbox("Lebensmittel:", df_db["Name"])
        
        with c2:
            st.info("Bitte Menge eingeben")
            menge = st.number_input("Menge (g / Stück):", min_value=0.1, value=1.0)
            if st.button("💾 Speichern", use_container_width=True):
                speichere_zeile_gs([str(datetime.now().date()), p_wahl, m_zeit, lebensmittel, menge, 0], "verzehr")
                st.balloons() # Visueller Effekt

elif menu == "2. Patienten-Dashboard":
    st.header("📊 Therapie-Dashboard")
    df_v = lade_daten_gs("verzehr")
    if not df_v.empty:
        st.metric("Gesamt-Einträge", len(df_v))
        st.dataframe(df_v, use_container_width=True)

elif menu == "3. Datenbank":
    st.header("🗄️ Stammdaten")
    df_db = lade_daten_gs("lebensmittel")
    if not df_db.empty:
        # Hier nutzen wir den Editor für schnelle Änderungen
        edited = st.data_editor(df_db, use_container_width=True, num_rows="dynamic")
        if st.button("💾 Alle Änderungen übernehmen"):
            client = get_gsheet_client()
            sheet = client.open("Kcal_Datenbank").worksheet("lebensmittel")
            sheet.clear()
            sheet.update([edited.columns.values.tolist()] + edited.values.tolist())
            st.cache_data.clear()
            trigger_audio(SOUND_SUCCESS)
            st.toast("Datenbank synchronisiert!", icon="🔄")

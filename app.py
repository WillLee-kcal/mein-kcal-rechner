import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
from datetime import datetime
import openfoodfacts
import base64

# --- KONSTANTEN ---
MAHLZEITEN_LISTE = ["Frühstück", "Zwischenmahlzeit 1", "Mittagessen", "Zwischenmahlzeit 2", "Abendessen", "Zwischenmahlzeit 3"]

# --- SOUND FUNKTIONEN ---
def play_sound(sound_type="success"):
    # Einfache Töne via Base64 (Success: kurzer hoher Ton, Error: tieferer Ton)
    sounds = {
        "success": "https://www.soundjay.com/buttons/sounds/button-37a.mp3",
        "save": "https://www.soundjay.com/buttons/sounds/button-09a.mp3",
        "error": "https://www.soundjay.com/buttons/sounds/button-10.mp3"
    }
    audio_html = f'<audio autoplay><source src="{sounds[sound_type]}" type="audio/mp3"></audio>'
    st.components.v1.html(audio_html, height=0)

# --- CSS FÜR KLINISCHEN LOOK ---
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stButton>button { border-radius: 8px; border: none; transition: 0.3s; }
    .stButton>button:hover { background-color: #007bff; color: white; transform: scale(1.02); }
    .stMetric { background-color: white; padding: 15px; border-radius: 12px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    div[data-testid="stExpander"] { border: none; box-shadow: 0 1px 3px rgba(0,0,0,0.1); border-radius: 8px; margin-bottom: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- 1. SETUP & VERBINDUNG ---
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
    except Exception as e:
        st.error(f"Verbindung fehlgeschlagen: {e}")
        return None

@st.cache_data(ttl=600)
def lade_daten_gs_cached(sheet_name):
    client = get_gsheet_client()
    if client:
        try:
            sheet = client.open("Kcal_Datenbank").worksheet(sheet_name)
            data = sheet.get_all_records()
            df = pd.DataFrame(data)
            df.columns = df.columns.str.strip()
            return df
        except: return pd.DataFrame()
    return pd.DataFrame()

def lade_daten_gs(sheet_name):
    return lade_daten_gs_cached(sheet_name)

def speichere_zeile_gs(liste_werte, sheet_name):
    try:
        client = get_gsheet_client()
        client.open("Kcal_Datenbank").worksheet(sheet_name).append_row(liste_werte)
        st.cache_data.clear() 
        play_sound("success")
    except: 
        play_sound("error")
        st.error("Fehler beim Speichern.")

def speichere_df_gs(df, sheet_name):
    try:
        client = get_gsheet_client()
        sheet = client.open("Kcal_Datenbank").worksheet(sheet_name)
        sheet.clear()
        df_clean = df.fillna("")
        sheet.update([df_clean.columns.values.tolist()] + df_clean.values.tolist())
        st.cache_data.clear() 
        play_sound("save")
    except Exception as e: 
        play_sound("error")
        st.error(f"Fehler beim Update: {e}")

# --- 2. LAYOUT & NAVIGATION ---
st.set_page_config(page_title="Kcal Tracker Pro", layout="wide", page_icon="🩹")
st.sidebar.markdown("<h2 style='color: #007bff;'>🩺 Med-Log Pro</h2>", unsafe_allow_html=True)
menu = st.sidebar.radio("Navigation:", ["1. Mahlzeit erfassen", "2. Patienten-Dashboard", "3. Patientenverwaltung", "4. Datenbank-Zentrale"])

# --- MODUL 1: MAHLZEIT ERFASSEN ---
if menu == "1. Mahlzeit erfassen":
    st.header("⚖️ Ernährungs-Protokoll")
    df_db = lade_daten_gs("lebensmittel")
    df_p = lade_daten_gs("patienten")
    
    if not df_p.empty and not df_db.empty:
        with st.container():
            c1, c2 = st.columns(2)
            with c1:
                p_wahl = st.selectbox("👤 Patient wählen:", df_p["Name"])
                m_zeit = st.selectbox("⏰ Mahlzeit:", MAHLZEITEN_LISTE)
                st.divider()
                auswahl_typ = st.radio("Kategorie filter:", ["Intern", "Extern", "Alle"], horizontal=True)
                df_gefiltert = df_db if auswahl_typ == "Alle" else df_db[df_db['Typ'] == auswahl_typ]
                lebensmittel_wahl = st.selectbox("🍎 Lebensmittel:", ["Bitte wählen..."] + list(df_gefiltert['Name'].unique()))

            if lebensmittel_wahl != "Bitte wählen...":
                item = df_db[df_db['Name'] == lebensmittel_wahl].iloc[0]
                k100 = pd.to_numeric(item.get('kcal_100g', 0), errors='coerce') or 0
                stk_w = pd.to_numeric(item.get('stueck_gewicht', 0), errors='coerce') or 0
                std_m = item.get('Standard_Menge', '1 Stück')

                with c2:
                    st.info(f"**Referenz:** {std_m} ≈ {item.get('kcal_pro_Einheit', 0)} kcal")
                    menge = st.number_input(f"Menge ({std_m}):", min_value=0.0, step=0.5, value=1.0)
                    basis = st.radio("Berechnungsgrundlage:", ["Stück / Einheit", "Gramm"], horizontal=True)
                    gewicht = menge * stk_w if basis == "Stück / Einheit" else menge
                    kcal_total = (k100 / 100) * gewicht
                    st.metric("Berechnete Energie", f"{kcal_total:.1f} kcal")
                    
                    if st.button("💾 Speichern & Quittieren", use_container_width=True):
                        heute = datetime.now().strftime("%Y-%m-%d")
                        speichere_zeile_gs([heute, p_wahl, m_zeit, lebensmittel_wahl, round(gewicht,1), round(kcal_total,1)], "verzehr")
                        st.balloons()
                        st.success(f"Eintrag für {p_wahl} erfolgreich!")

# --- MODUL 2: DASHBOARD ---
elif menu == "2. Patienten-Dashboard":
    st.header("📊 Therapie-Zentrale")
    df_v = lade_daten_gs("verzehr")
    df_p = lade_daten_gs("patienten")
    df_g = lade_daten_gs("gewichtsverlauf")
    
    if not df_p.empty:
        p_wahl = st.selectbox("Patientenakte wählen:", df_p["Name"])
        p_data = df_p[df_p["Name"] == p_wahl].iloc[0]
        
        t_kcal, t_trend = st.tabs(["⚡ Kalorien-Status", "📈 Gewichtsverlauf"])
        
        with t_kcal:
            heute = datetime.now().strftime("%Y-%m-%d")
            if not df_v.empty:
                df_v["Datum"] = df_v["Datum"].astype(str)
                df_heute = df_v[(df_v["Datum"] == heute) & (df_v["Patient"] == p_wahl)]
                gegessen = df_heute["Kcal_Gesamt"].sum() if not df_heute.empty else 0
                ziel = pd.to_numeric(p_data["Ziel_Kcal"], errors='coerce') or 2000
                
                c1, c2 = st.columns(2)
                # Farblogik für Metrik
                status_color = "normal" if gegessen < ziel else "inverse"
                c1.metric("Heute verzehrt", f"{gegessen:.0f} kcal", delta=f"{gegessen-ziel:.0f} Diff", delta_color=status_color)
                c2.metric("Tagesziel", f"{ziel:.0f} kcal")
                
                progress = min(gegessen/ziel, 1.0) if ziel > 0 else 0
                st.progress(progress)
                
                for m in MAHLZEITEN_LISTE:
                    m_data = df_heute[df_heute["Mahlzeit"] == m]
                    m_sum = m_data["Kcal_Gesamt"].sum()
                    with st.expander(f"{m} — {m_sum:.0f} kcal"):
                        if not m_data.empty:
                            for idx, row in m_data.iterrows():
                                cl, cr = st.columns([4, 1])
                                cl.write(f"**{row['Lebensmittel']}**: {row['Kcal_Gesamt']:.1f} kcal")
                                if cr.button("🗑️", key=f"del_{idx}"):
                                    full_v = lade_daten_gs("verzehr")
                                    full_v = full_v.drop(idx)
                                    speichere_df_gs(full_v, "verzehr")
                                    st.rerun()

        with t_trend:
            if not df_g.empty:
                df_hist = df_g[df_g["Patient"] == p_wahl].copy()
                if not df_hist.empty:
                    df_hist["Datum"] = pd.to_datetime(df_hist["Datum"])
                    df_hist = df_hist.sort_values("Datum")
                    st.line_chart(df_hist.set_index("Datum")["Gewicht"])

# --- MODUL 4: DATENBANK (EDITIERBAR & IMPORT) ---
elif menu == "4. Datenbank-Zentrale":
    st.header("🗄️ Stammdaten-Management")
    t_edit, t_imp, t_del_food = st.tabs(["✏️ Editor", "🌍 OFF-Import", "🗑️ Löschen"])
    
    df_db = lade_daten_gs("lebensmittel")
    
    with t_edit:
        if not df_db.empty:
            df_db["kcal_100g"] = pd.to_numeric(df_db["kcal_100g"], errors='coerce').fillna(0)
            df_db["stueck_gewicht"] = pd.to_numeric(df_db["stueck_gewicht"], errors='coerce').fillna(0)
            edited_df = st.data_editor(df_db, num_rows="dynamic", use_container_width=True, hide_index=True)
            if st.button("💾 Datenbank-Update"):
                speichere_df_gs(edited_df, "lebensmittel")
                st.success("Synchronisierung abgeschlossen!")

    with t_imp:
        suche = st.text_input("Markenprodukt via Open Food Facts suchen:")
        if suche:
            off_api = openfoodfacts.API(user_agent="KcalTracker/1.0")
            res = off_api.product.text_search(suche)
            if res and 'products' in res:
                for p in res['products'][:5]:
                    p_name = p.get('product_name', 'Unbekannt')
                    p_kcal = p.get('nutriments', {}).get('energy-kcal_100g')
                    if p_kcal:
                        ca, cb = st.columns([3, 1])
                        ca.write(f"**{p_name}** ({p_kcal} kcal/100g)")
                        if cb.button("📥 Import", key=f"imp_{p.get('_id')}"):
                            speichere_zeile_gs([p_name, p_kcal, 0, "1 Stück", 0, "Extern"], "lebensmittel")
                            st.rerun()
                            
    with t_del_food:
        if not df_db.empty:
            kill = st.selectbox("Eintrag entfernen:", ["Bitte wählen..."] + sorted(df_db["Name"].unique()))
            if kill != "Bitte wählen..." and st.button("🗑️ Endgültig löschen", type="primary"):
                speichere_df_gs(df_db[df_db["Name"] != kill], "lebensmittel")
                st.rerun()

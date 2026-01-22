import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
from datetime import datetime

# --- KONSTANTEN ---
MAHLZEITEN_LISTE = [
    "Frühstück", "Zwischenmahlzeit 1", "Mittagessen", 
    "Zwischenmahlzeit 2", "Abendessen", "Zwischenmahlzeit 3"
]

# --- 1. SETUP & VERBINDUNG ZU GOOGLE SHEETS ---
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

def lade_daten_gs(sheet_name):
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

def speichere_zeile_gs(liste_werte, sheet_name):
    try:
        client = get_gsheet_client()
        client.open("Kcal_Datenbank").worksheet(sheet_name).append_row(liste_werte)
    except: st.error("Fehler beim Speichern.")

def speichere_df_gs(df, sheet_name):
    try:
        client = get_gsheet_client()
        sheet = client.open("Kcal_Datenbank").worksheet(sheet_name)
        sheet.clear()
        df_clean = df.fillna("")
        sheet.update([df_clean.columns.values.tolist()] + df_clean.values.tolist())
    except: st.error("Fehler beim Update.")

# --- 2. LAYOUT & NAVIGATION ---
st.set_page_config(page_title="Kcal Tracker Pro", layout="wide", page_icon="🍎")
st.sidebar.title("🍎 Navigation")
menu = st.sidebar.radio("Menü wählen:", ["1. Mahlzeit erfassen", "2. Patienten-Dashboard", "3. Patientenverwaltung", "4. Datenbank-Info"])

# --- MODUL 1: MAHLZEIT ERFASSEN ---
if menu == "1. Mahlzeit erfassen":
    st.header("⚖️ Mahlzeit ins Logbuch eintragen")
    df_db = lade_daten_gs("lebensmittel")
    df_p = lade_daten_gs("patienten")
    
    if not df_p.empty:
        c1, c2 = st.columns(2)
        with c1:
            p_wahl = st.selectbox("Patient wählen:", df_p["Name"])
            m_zeit = st.selectbox("Mahlzeit wählen:", MAHLZEITEN_LISTE)
            suche = st.text_input("Lebensmittel suchen (z.B. Mischbrot):")
            
        if suche and not df_db.empty:
            treffer = df_db[df_db['Name'].str.contains(suche, case=False, na=False)]
            if not treffer.empty:
                wahl = st.selectbox("Gefunden:", treffer['Name'])
                item = treffer[treffer['Name'] == wahl].iloc[0]
                
                # Werte aus DB laden (inkl. neuer Spalte)
                k100 = pd.to_numeric(item.get('kcal_100g', 0), errors='coerce') or 0
                stk_w = pd.to_numeric(item.get('stueck_gewicht', 0), errors='coerce') or 0
                k_einheit = pd.to_numeric(item.get('kcal_pro_Einheit', 0), errors='coerce') or 0
                
                with c2:
                    st.info(f"💡 Referenzwert (DB): {k_einheit} kcal pro {item.get('Standard_Menge', 'Einheit')}")
                    menge = st.number_input("Anzahl / Menge:", min_value=0.0, step=0.5, value=1.0)
                    basis = st.radio("Berechnung:", ["Einheit / Stück", "Gramm"])
                
                # --- LIVE BERECHNUNG ---
                gewicht = menge * stk_w if basis == "Einheit / Stück" else menge
                kcal_total = (k100 / 100) * gewicht
                
                st.metric("Live-Berechnung", f"{kcal_total:.1f} kcal")
                
                if st.button("💾 Speichern"):
                    heute = datetime.now().strftime("%Y-%m-%d")
                    speichere_zeile_gs([heute, p_wahl, m_zeit, wahl, round(gewicht,1), round(kcal_total,1)], "verzehr")
                    st.success("Eintrag gespeichert!")
            else: st.error("Kein Eintrag gefunden.")

# --- MODUL 2: DASHBOARD ---
elif menu == "2. Patienten-Dashboard":
    st.header("📊 Therapie-Dashboard")
    df_v = lade_daten_gs("verzehr")
    df_p = lade_daten_gs("patienten")
    df_g = lade_daten_gs("gewichtsverlauf")
    
    if not df_p.empty:
        p_wahl = st.selectbox("Patient wählen:", df_p["Name"])
        p_data = df_p[df_p["Name"] == p_wahl].iloc[0]
        
        t_kcal, t_trend = st.tabs(["🍎 Kalorien heute", "📈 Gewichtsverlauf"])
        
        with t_kcal:
            heute = datetime.now().strftime("%Y-%m-%d")
            if not df_v.empty:
                df_v["Datum"] = df_v["Datum"].astype(str)
                df_heute = df_v[(df_v["Datum"] == heute) & (df_v["Patient"] == p_wahl)]
                gegessen = df_heute["Kcal_Gesamt"].sum() if not df_heute.empty else 0
                ziel = pd.to_numeric(p_data["Ziel_Kcal"], errors='coerce') or 2000
                
                col1, col2 = st.columns(2)
                col1.metric("Heute verzehrt", f"{gegessen:.0f} kcal")
                col2.metric("Tagesziel", f"{ziel:.0f} kcal")
                st.progress(min(gegessen/ziel, 1.0) if ziel > 0 else 0)
                
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
                    st.line_chart(df_hist.sort_values("Datum").set_index("Datum")["Gewicht"])
            
            with st.expander("➕ Neues Gewicht loggen"):
                neu_w = st.number_input("Gewicht (kg):", step=0.1)
                if st.button("Speichern"):
                    h_str = datetime.now().strftime("%Y-%m-%d")
                    speichere_zeile_gs([h_str, p_wahl, neu_w], "gewichtsverlauf")
                    st.rerun()

# --- MODUL 3: PATIENTEN ---
elif menu == "3. Patientenverwaltung":
    st.header("👥 Patientenverwaltung")
    df_p = lade_daten_gs("patienten")
    if not df_p.empty:
        st.dataframe(df_p, use_container_width=True, hide_index=True)
    with st.expander("Neuen Patienten anlegen"):
        with st.form("p_form"):
            n = st.text_input("Name")
            z = st.number_input("Ziel Kcal", value=2000)
            if st.form_submit_button("Speichern"):
                h = datetime.now().strftime("%Y-%m-%d")
                new_p = pd.DataFrame([[n, z, "", "", 165, "P25", 0, h]], 
                                     columns=["Name", "Ziel_Kcal", "Geschlecht", "Geburtsdatum", "Groesse_cm", "Ziel_Perzentile", "Gewicht_aktuell", "Wiegedatum"])
                df_p = pd.concat([df_p, new_p], ignore_index=True)
                speichere_df_gs(df_p, "patienten")
                st.rerun()

# --- MODUL 4: DATENBANK INFO ---
elif menu == "4. Datenbank-Info":
    st.header("📊 Lebensmittel-Übersicht")
    df_db = lade_daten_gs("lebensmittel")
    if not df_db.empty:
        st.write("Deine aktuelle Lebensmittel-Liste:")
        st.dataframe(df_db, use_container_width=True, hide_index=True)

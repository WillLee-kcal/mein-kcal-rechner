import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json

# --- 1. GOOGLE SHEETS VERBINDUNG (HYBRID-LOGIK) ---

def get_gsheet_client():
    # Definiert den Zugriffsbereich
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # VERSUCH A: Laden aus Streamlit Cloud Secrets (Online-Betrieb)
    if "gcp_service_account" in st.secrets:
        credentials_info = st.secrets["gcp_service_account"]
        # Falls die Secrets als Text (String) gespeichert sind, in ein Dictionary umwandeln
        if isinstance(credentials_info, str):
            credentials_info = json.loads(credentials_info)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials_info, scope)
    
    # VERSUCH B: Laden aus lokaler Datei (PC-Betrieb)
    else:
        try:
            creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
        except FileNotFoundError:
            st.error("Fehler: Keine Anmeldedaten gefunden! (Weder 'credentials.json' lokal noch 'Secrets' in der Cloud).")
            return None
            
    client = gspread.authorize(creds)
    return client

# --- 2. DATEN-FUNKTIONEN ---

def lade_daten_gs(sheet_name):
    try:
        client = get_gsheet_client()
        if client is None: return pd.DataFrame()
        sheet = client.open("Kcal_Datenbank").worksheet(sheet_name)
        data = sheet.get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"Fehler beim Laden von {sheet_name}: {e}")
        return pd.DataFrame()

def speichere_daten_gs(df, sheet_name):
    try:
        client = get_gsheet_client()
        if client is None: return False
        sheet = client.open("Kcal_Datenbank").worksheet(sheet_name)
        sheet.clear()
        # Header + Daten schreiben
        sheet.update([df.columns.values.tolist()] + df.values.tolist())
        return True
    except Exception as e:
        st.error(f"Fehler beim Speichern in {sheet_name}: {e}")
        return False

# --- 3. STREAMLIT OBERFLÄCHE ---

st.set_page_config(page_title="Kcal Management System", layout="wide")

st.sidebar.title("🍎 Navigation")
menu = st.sidebar.radio("Hauptmenü", [
    "1. Mahlzeit in Kcal berechnen", 
    "2. Patientenverwaltung", 
    "3. Datenbank bearbeiten"
])

# --- MODUL 1: MAHLZEIT BERECHNEN ---
if menu == "1. Mahlzeit in Kcal berechnen":
    st.header("⚖️ Mahlzeit berechnen")
    df_db = lade_daten_gs("lebensmittel")
    
    if df_db.empty:
        st.warning("Die Lebensmittel-Datenbank ist leer. Bitte in Punkt 3 Daten hinzufügen.")
    else:
        suche = st.text_input("Lebensmittel suchen:")
        treffer = df_db[df_db['Name'].str.contains(suche, case=False, na=False)]
        
        if not treffer.empty:
            auswahl = st.selectbox("Lebensmittel wählen:", treffer['Name'])
            item = df_db[df_db['Name'] == auswahl].iloc[0]
            
            col1, col2 = st.columns(2)
            with col1:
                einheit = st.radio("Einheit:", ["Gramm", "Stück"])
            with col2:
                menge = st.number_input("Menge:", min_value=0.0, step=1.0)
            
            if einheit == "Stück" and pd.notnull(item['stueck_gewicht']) and item['stueck_gewicht'] > 0:
                gewicht = menge * item['stueck_gewicht']
            else:
                gewicht = menge
            
            kcal = (item['kcal_100g'] / 100) * gewicht
            st.metric("Ergebnis", f"{kcal:.1f} kcal", delta=f"{gewicht:.1f} g Gesamtgewicht")
        else:
            st.info("Suchen Sie nach einem Lebensmittel in Ihrer Datenbank.")

# --- MODUL 2: PATIENTENVERWALTUNG ---
elif menu == "2. Patientenverwaltung":
    st.header("👥 Patientenverwaltung")
    df_p = lade_daten_gs("patienten")
    
    t1, t2, t3, t4 = st.tabs(["2.1 Anlegen", "2.2 Bearbeiten", "2.3 Löschen", "2.4 Übersicht"])

    with t1:
        with st.form("p_neu"):
            n_name = st.text_input("Name")
            n_ziel = st.number_input("Ziel (kcal)", min_value=0, value=2000)
            if st.form_submit_button("Speichern"):
                if n_name:
                    neu = pd.DataFrame([[n_name, n_ziel]], columns=["Name", "Ziel_Kcal"])
                    df_p = pd.concat([df_p, neu], ignore_index=True)
                    speichere_daten_gs(df_p, "patienten")
                    st.success("Patient angelegt!")
                    st.rerun()

    with t2:
        if not df_p.empty:
            idx = st.selectbox("Bearbeiten:", df_p.index, format_func=lambda x: df_p.iloc[idx]['Name'])
            en = st.text_input("Name korrigieren", value=df_p.iloc[idx]['Name'])
            ez = st.number_input("Ziel korrigieren", value=int(df_p.iloc[idx]['Ziel_Kcal']))
            if st.button("Speichern"):
                df_p.at[idx, 'Name'], df_p.at[idx, 'Ziel_Kcal'] = en, ez
                speichere_daten_gs(df_p, "patienten")
                st.success("Aktualisiert!")
                st.rerun()

    with t3:
        if not df_p.empty:
            d_idx = st.selectbox("Löschen:", df_p.index, format_func=lambda x: df_p.iloc[x]['Name'])
            if st.button("Löschen bestätigen", type="primary"):
                df_p = df_p.drop(d_idx)
                speichere_daten_gs(df_p, "patienten")
                st.rerun()

    with t4:
        st.dataframe(df_p, use_container_width=True)

# --- MODUL 3: DATENBANK ---
elif menu == "3. Datenbank bearbeiten":
    st.header("📊 Lebensmittel-Datenbank")
    df_db = lade_daten_gs("lebensmittel")
    st.dataframe(df_db, use_container_width=True)
    
    with st.expander("Neues Lebensmittel hinzufügen"):
        with st.form("f_neu"):
            fn = st.text_input("Bezeichnung")
            fk = st.number_input("Kcal/100g")
            fs = st.number_input("Stückgewicht (optional)")
            if st.form_submit_button("Hinzufügen"):
                neu_f = pd.DataFrame([[fn, fk, fs if fs > 0 else None]], 
                                     columns=["Name", "kcal_100g", "stueck_gewicht"])
                df_db = pd.concat([df_db, neu_f], ignore_index=True)
                speichere_daten_gs(df_db, "lebensmittel")
                st.rerun()
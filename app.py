import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- GOOGLE SHEETS SETUP ---

def get_gsheet_client():
    # Definiert den Zugriffsbereich (Scope)
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    # Nutzt deine heruntergeladene Schlüssel-Datei
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    client = gspread.authorize(creds)
    return client

def lade_daten_gs(sheet_name):
    try:
        client = get_gsheet_client()
        # Öffnet die Tabelle und das spezifische Tabellenblatt
        sheet = client.open("Kcal_Datenbank").worksheet(sheet_name)
        data = sheet.get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"Fehler beim Laden von {sheet_name}: {e}")
        return pd.DataFrame()

def speichere_daten_gs(df, sheet_name):
    try:
        client = get_gsheet_client()
        sheet = client.open("Kcal_Datenbank").worksheet(sheet_name)
        # Löscht das Blatt und schreibt die neuen Daten (inkl. Header) hinein
        sheet.clear()
        sheet.update([df.columns.values.tolist()] + df.values.tolist())
        return True
    except Exception as e:
        st.error(f"Fehler beim Speichern von {sheet_name}: {e}")
        return False

# --- STREAMLIT OBERFLÄCHE ---

st.set_page_config(page_title="Kcal Management System", layout="wide")

# Seitenleiste Navigation
st.sidebar.title("🍎 Navigation")
menu = st.sidebar.radio("Hauptmenü", [
    "1. Mahlzeit in Kcal berechnen", 
    "2. Patientenverwaltung", 
    "3. Datenbank bearbeiten"
])

# --- 1. MAHLZEIT BERECHNEN ---
if menu == "1. Mahlzeit in Kcal berechnen":
    st.header("⚖️ Mahlzeit berechnen")
    df_db = lade_daten_gs("lebensmittel")
    
    if df_db.empty:
        st.warning("Die Lebensmittel-Datenbank ist leer. Bitte in Punkt 3 Daten hinzufügen.")
    else:
        suche = st.text_input("Lebensmittel suchen (z.B. Apfel):")
        treffer = df_db[df_db['Name'].str.contains(suche, case=False, na=False)]
        
        if not treffer.empty:
            auswahl = st.selectbox("Gefundenes Lebensmittel wählen:", treffer['Name'])
            item = df_db[df_db['Name'] == auswahl].iloc[0]
            
            col1, col2 = st.columns(2)
            with col1:
                einheit = st.radio("Einheit:", ["Gramm", "Stück"])
            with col2:
                menge = st.number_input("Menge eingeben:", min_value=0.0, step=1.0)
            
            # Logik für Stück vs Gramm
            if einheit == "Stück" and pd.notnull(item['stueck_gewicht']) and item['stueck_gewicht'] > 0:
                gewicht = menge * item['stueck_gewicht']
                st.write(f"Berechnetes Gewicht: {gewicht}g (basiert auf {item['stueck_gewicht']}g pro Stück)")
            else:
                gewicht = menge
                if einheit == "Stück":
                    st.warning("Kein Stückgewicht hinterlegt. Es wird mit Gramm gerechnet.")
            
            ergebnis = (item['kcal_100g'] / 100) * gewicht
            st.metric("Gesamtkalorien", f"{ergebnis:.1f} kcal")
        else:
            st.info("Tippen Sie einen Namen ein, um die Datenbank zu durchsuchen.")

# --- 2. PATIENTENVERWALTUNG ---
elif menu == "2. Patientenverwaltung":
    st.header("👥 Patientenverwaltung")
    df_p = lade_daten_gs("patienten")
    
    tab1, tab2, tab3, tab4 = st.tabs(["2.1 Anlegen", "2.2 Bearbeiten", "2.3 Löschen", "2.4 Übersicht"])

    with tab1:
        with st.form("p_anlegen"):
            n_name = st.text_input("Name des Patienten")
            n_ziel = st.number_input("Tagesziel (kcal)", min_value=0, value=2000)
            if st.form_submit_button("Patient speichern"):
                if n_name:
                    # Neuen Patienten als DataFrame vorbereiten
                    neu = pd.DataFrame([[n_name, n_ziel]], columns=["Name", "Ziel_Kcal"])
                    df_p = pd.concat([df_p, neu], ignore_index=True)
                    if speichere_daten_gs(df_p, "patienten"):
                        st.success(f"Patient {n_name} wurde in Google Sheets gespeichert!")
                        st.rerun()
                else:
                    st.error("Name darf nicht leer sein.")

    with tab2:
        if not df_p.empty:
            p_index = st.selectbox("Welchen Patienten bearbeiten?", df_p.index, format_func=lambda x: df_p.iloc[x]['Name'])
            edit_name = st.text_input("Name ändern", value=df_p.iloc[p_index]['Name'])
            edit_ziel = st.number_input("Ziel kcal ändern", value=int(df_p.iloc[p_index]['Ziel_Kcal']))
            if st.button("Änderungen in Cloud speichern"):
                df_p.at[p_index, 'Name'] = edit_name
                df_p.at[p_index, 'Ziel_Kcal'] = edit_ziel
                speichere_daten_gs(df_p, "patienten")
                st.success("Daten aktualisiert!")
                st.rerun()

    with tab3:
        if not df_p.empty:
            del_index = st.selectbox("Welchen Patienten löschen?", df_p.index, format_func=lambda x: df_p.iloc[x]['Name'])
            if st.button("Endgültig aus Google Sheets löschen", type="primary"):
                df_p = df_p.drop(del_index)
                speichere_daten_gs(df_p, "patienten")
                st.warning("Patient gelöscht.")
                st.rerun()

    with tab4:
        st.subheader("Aktuelle Liste aus Google Sheets")
        st.dataframe(df_p, use_container_width=True)

# --- 3. DATENBANK BEARBEITEN ---
elif menu == "3. Datenbank bearbeiten":
    st.header("📊 Datenbank & Stückliste")
    df_db = lade_daten_gs("lebensmittel")
    
    st.dataframe(df_db, use_container_width=True)
    
    with st.expander("Neues Lebensmittel hinzufügen"):
        with st.form("food_form"):
            f_name = st.text_input("Bezeichnung")
            f_kcal = st.number_input("Kcal pro 100g", min_value=0.0)
            f_stk = st.number_input("Gewicht pro Stück in Gramm (optional)", min_value=0.0)
            if st.form_submit_button("In Google Sheets speichern"):
                if f_name:
                    neu_f = pd.DataFrame([[f_name, f_kcal, f_stk if f_stk > 0 else None]], 
                                         columns=["Name", "kcal_100g", "stueck_gewicht"])
                    df_db = pd.concat([df_db, neu_f], ignore_index=True)
                    speichere_daten_gs(df_db, "lebensmittel")
                    st.success(f"{f_name} hinzugefügt!")
                    st.rerun()
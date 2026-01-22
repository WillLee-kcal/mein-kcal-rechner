import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
from datetime import datetime

# --- GOOGLE SHEETS SETUP (HYBRID) ---
def get_gsheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        credentials_info = st.secrets["gcp_service_account"]
        if isinstance(credentials_info, str): credentials_info = json.loads(credentials_info)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials_info, scope)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    return gspread.authorize(creds)

def lade_daten_gs(sheet_name):
    try:
        client = get_gsheet_client()
        sheet = client.open("Kcal_Datenbank").worksheet(sheet_name)
        return pd.DataFrame(sheet.get_all_records())
    except: return pd.DataFrame()

def speichere_zeile_gs(liste_werte, sheet_name):
    client = get_gsheet_client()
    sheet = client.open("Kcal_Datenbank").worksheet(sheet_name)
    sheet.append_row(liste_werte)

def speichere_df_gs(df, sheet_name):
    client = get_gsheet_client()
    sheet = client.open("Kcal_Datenbank").worksheet(sheet_name)
    sheet.clear()
    sheet.update([df.columns.values.tolist()] + df.values.tolist())

# --- OBERFLÄCHE ---
st.set_page_config(page_title="Kcal Profi-Tracker", layout="wide")
st.sidebar.title("🍎 Navigation")
menu = st.sidebar.radio("Menü", ["1. Mahlzeit & Logbuch", "2. Dashboard (Grafik)", "3. Patienten", "4. Datenbank"])

# --- 1. MAHLZEIT BERECHNEN & SPEICHERN ---
if menu == "1. Mahlzeit & Logbuch":
    st.header("⚖️ Mahlzeit erfassen")
    df_db = lade_daten_gs("lebensmittel")
    df_p = lade_daten_gs("patienten")
    
    col_a, col_b = st.columns(2)
    with col_a:
        patient_wahl = st.selectbox("Für welchen Patienten?", df_p["Name"] if not df_p.empty else ["Keine Patienten"])
        suche = st.text_input("Lebensmittel suchen:")
    
    if not df_db.empty and suche:
        treffer = df_db[df_db['Name'].str.contains(suche, case=False, na=False)]
        if not treffer.empty:
            wahl = st.selectbox("Wählen:", treffer['Name'])
            item = df_db[df_db['Name'] == wahl].iloc[0]
            
            with col_b:
                menge = st.number_input("Menge (g oder Stück):", min_value=0.0)
                einheit = st.radio("Einheit:", ["Gramm", "Stück"])
            
            # Gewichtsberechnung
            gewicht = menge * item['stueck_gewicht'] if einheit == "Stück" and item['stueck_gewicht'] else menge
            kcal_total = (item['kcal_100g'] / 100) * gewicht
            
            st.metric("Berechnet:", f"{kcal_total:.1f} kcal")
            
            if st.button("Mahlzeit ins Logbuch eintragen"):
                heute = datetime.now().strftime("%Y-%m-%d")
                speichere_zeile_gs([heute, patient_wahl, wahl, gewicht, kcal_total], "verzehr")
                st.success("Gespeichert!")

# --- 2. DASHBOARD (GRAFIK) ---
elif menu == "2. Dashboard (Grafik)":
    st.header("📊 Tagesauswertung")
    df_v = lade_daten_gs("verzehr")
    df_p = lade_daten_gs("patienten")
    
    if not df_v.empty:
        heute = datetime.now().strftime("%Y-%m-%d")
        wahl_p = st.selectbox("Patient wählen:", df_p["Name"])
        
        # Daten filtern
        df_heute = df_v[(df_v["Datum"] == heute) & (df_v["Patient"] == wahl_p)]
        gegessen = df_heute["Kcal_Gesamt"].sum()
        ziel = df_p[df_p["Name"] == wahl_p]["Ziel_Kcal"].values[0]
        
        # Grafische Anzeige
        col1, col2 = st.columns(2)
        col1.metric("Heute gegessen", f"{gegessen:.0f} kcal")
        col2.metric("Tagesziel", f"{ziel:.0f} kcal", delta=int(ziel - gegessen))
        
        # Balkendiagramm
        st.subheader("Vergleich: Gegessen vs. Ziel")
        chart_data = pd.DataFrame({
            "Kategorie": ["Gegessen", "Ziel"],
            "Kalorien": [gegessen, ziel]
        })
        st.bar_chart(data=chart_data, x="Kategorie", y="Kalorien")
    else:
        st.info("Noch keine Mahlzeiten für heute eingetragen.")



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
import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
from datetime import datetime

# --- 1. GOOGLE SHEETS SETUP (HYBRID) ---
def get_gsheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        credentials_info = st.secrets["gcp_service_account"]
        if isinstance(credentials_info, str): 
            credentials_info = json.loads(credentials_info)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials_info, scope)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    return gspread.authorize(creds)

def lade_daten_gs(sheet_name):
    try:
        client = get_gsheet_client()
        sheet = client.open("Kcal_Datenbank").worksheet(sheet_name)
        return pd.DataFrame(sheet.get_all_records())
    except Exception as e:
        return pd.DataFrame()

def speichere_zeile_gs(liste_werte, sheet_name):
    client = get_gsheet_client()
    sheet = client.open("Kcal_Datenbank").worksheet(sheet_name)
    sheet.append_row(liste_werte)

def speichere_df_gs(df, sheet_name):
    client = get_gsheet_client()
    sheet = client.open("Kcal_Datenbank").worksheet(sheet_name)
    sheet.clear()
    sheet.update([df.columns.values.tolist()] + df.values.tolist())

# --- 2. OBERFLÄCHE ---
st.set_page_config(page_title="Kcal Profi-Tracker", layout="wide", page_icon="🍎")

st.sidebar.title("🍎 Navigation")
menu = st.sidebar.radio("Menü wählen:", [
    "1. Mahlzeit & Logbuch", 
    "2. Dashboard (Grafik)", 
    "3. Patientenverwaltung", 
    "4. Datenbank bearbeiten"
])

# --- MODUL 1: MAHLZEIT ERFASSEN ---
if menu == "1. Mahlzeit & Logbuch":
    st.header("⚖️ Mahlzeit berechnen & speichern")
    df_db = lade_daten_gs("lebensmittel")
    df_p = lade_daten_gs("patienten")
    
    if df_p.empty:
        st.warning("Bitte lege zuerst unter Punkt 3 einen Patienten an.")
    elif df_db.empty:
        st.warning("Bitte fülle zuerst deine Lebensmittel-Datenbank in Punkt 4.")
    else:
        col_a, col_b = st.columns(2)
        with col_a:
            p_wahl = st.selectbox("Für welchen Patienten?", df_p["Name"])
            suche = st.text_input("Lebensmittel suchen (Name eingeben):")
        
        if suche:
            treffer = df_db[df_db['Name'].str.contains(suche, case=False, na=False)]
            if not treffer.empty:
                wahl = st.selectbox("Gefunden:", treffer['Name'])
                item = df_db[df_db['Name'] == wahl].iloc[0]
                
                with col_b:
                    menge = st.number_input("Menge:", min_value=0.0, step=1.0)
                    einheit = st.radio("Einheit:", ["Gramm", "Stück"])
                
                gewicht = menge * item['stueck_gewicht'] if einheit == "Stück" and item['stueck_gewicht'] else menge
                kcal_total = (item['kcal_100g'] / 100) * gewicht
                
                st.metric("Berechnet", f"{kcal_total:.1f} kcal")
                
                if st.button("Direkt ins Logbuch eintragen"):
                    heute = datetime.now().strftime("%Y-%m-%d")
                    speichere_zeile_gs([heute, p_wahl, wahl, weight, kcal_total], "verzehr")
                    st.success(f"Eintrag für {p_wahl} gespeichert!")
            else:
                st.error("Kein passendes Lebensmittel gefunden.")

# --- MODUL 2: DASHBOARD ---
elif menu == "2. Dashboard (Grafik)":
    st.header("📊 Tagesauswertung")
    df_v = lade_daten_gs("verzehr")
    df_p = lade_daten_gs("patienten")
    
    if df_v.empty or "Datum" not in df_v.columns:
        st.info("Das Logbuch ist noch leer. Trage erst Mahlzeiten in Punkt 1 ein.")
    else:
        heute = datetime.now().strftime("%Y-%m-%d")
        p_wahl = st.selectbox("Fortschritt ansehen für:", df_p["Name"])
        
        df_v["Datum"] = df_v["Datum"].astype(str)
        df_heute = df_v[(df_v["Datum"] == heute) & (df_v["Patient"] == p_wahl)]
        
        gegessen = df_heute["Kcal_Gesamt"].sum()
        ziel = float(df_p[df_p["Name"] == p_wahl]["Ziel_Kcal"].values[0])
        rest = ziel - gegessen
        
        # Grafik-Sektion
        st.subheader(f"Status heute für {p_wahl}")
        c1, c2 = st.columns(2)
        c1.metric("Gegessen", f"{gegessen:.0f} kcal")
        c2.metric("Ziel", f"{ziel:.0f} kcal", delta=f"{int(rest)} kcal übrig")
        
        # Fortschrittsbalken
        prozent = min(gegessen / ziel, 1.0)
        st.progress(prozent)
        st.write(f"Du hast bereits **{prozent*100:.1f}%** deines Tagesziels erreicht.")

        if gegessen > ziel:
            st.error("⚠️ Tagesziel überschritten!")

        # Balken-Chart
        chart_data = pd.DataFrame({"Kategorie": ["Gegessen", "Ziel"], "Kcal": [gegessen, ziel]})
        st.bar_chart(chart_data, x="Kategorie", y="Kcal")

# --- MODUL 3: PATIENTENVERWALTUNG ---
elif menu == "3. Patientenverwaltung":
    st.header("👥 Patientenverwaltung")
    df_p = lade_daten_gs("patienten")
    t1, t2 = st.tabs(["Patient anlegen", "Übersicht"])
    with t1:
        with st.form("new_p"):
            n = st.text_input("Name")
            z = st.number_input("Ziel Kcal", value=2000)
            if st.form_submit_button("Speichern"):
                new_df = pd.concat([df_p, pd.DataFrame([[n, z]], columns=["Name", "Ziel_Kcal"])])
                speichere_df_gs(new_df, "patienten")
                st.rerun()
    with t2:
        st.dataframe(df_p, use_container_width=True)

# --- MODUL 4: DATENBANK ---
elif menu == "4. Datenbank bearbeiten":
    st.header("📊 Lebensmittel-Datenbank")
    df_db = lade_daten_gs("lebensmittel")
    st.dataframe(df_db, use_container_width=True)
    with st.expander("Neu hinzufügen"):
        with st.form("new_f"):
            fn = st.text_input("Name")
            fk = st.number_input("Kcal/100g")
            fs = st.number_input("Stückgewicht (optional)")
            if st.form_submit_button("Speichern"):
                new_db = pd.concat([df_db, pd.DataFrame([[fn, fk, fs]], columns=["Name", "kcal_100g", "stueck_gewicht"])])
                speichere_df_gs(new_db, "lebensmittel")
                st.rerun()

import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
from datetime import datetime

# --- 1. SETUP & VERBINDUNG ZU GOOGLE SHEETS ---
def get_gsheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    # Check ob Cloud-Secrets vorhanden sind, sonst lokale Datei
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
        data = sheet.get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"Fehler beim Laden von {sheet_name}: {e}")
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

# --- 2. LAYOUT & NAVIGATION ---
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
    st.header("⚖️ Mahlzeit erfassen")
    df_db = lade_daten_gs("lebensmittel")
    df_p = lade_daten_gs("patienten")
    
    if df_p.empty:
        st.warning("Bitte lege zuerst unter Punkt 3 einen Patienten an.")
    elif df_db.empty:
        st.warning("Lebensmittel-Datenbank ist leer.")
    else:
        typ_filter = st.radio("Kategorie:", ["Alle", "Intern", "Extern"], horizontal=True)
        col_a, col_b = st.columns(2)
        
        with col_a:
            p_wahl = st.selectbox("Für welchen Patienten?", df_p["Name"])
            df_gefiltert = df_db if typ_filter == "Alle" else df_db[df_db['Typ'] == typ_filter]
            suche = st.text_input("Lebensmittel suchen:")
        
        if suche:
            treffer = df_gefiltert[df_gefiltert['Name'].str.contains(suche, case=False, na=False)]
            if not treffer.empty:
                wahl = st.selectbox("Gefunden:", treffer['Name'])
                item = treffer[treffer['Name'] == wahl].iloc[0]
                
                std_info = item.get('Standard_Menge', 'Stück')
                st.info(f"💡 Info: 1 Einheit = {std_info}")
                
                with col_b:
                    menge = st.number_input("Anzahl / Menge:", min_value=0.0, step=0.5, value=1.0)
                    einheit = st.radio("Basis:", ["Stück / Einheit", "Gramm"])
                
                # Gewichtsberechnung
                stk_w = pd.to_numeric(item['stueck_gewicht'], errors='coerce') or 0
                kcal_100 = pd.to_numeric(item['kcal_100g'], errors='coerce') or 0
                
                gewicht = menge * stk_w if einheit == "Stück / Einheit" else menge
                kcal_total = (kcal_100 / 100) * gewicht
                
                st.metric("Berechnet", f"{kcal_total:.1f} kcal")
                
                if st.button("Speichern & Logbuch"):
                    heute = datetime.now().strftime("%Y-%m-%d")
                    speichere_zeile_gs([heute, p_wahl, wahl, gewicht, kcal_total], "verzehr")
                    st.success("Eintrag gespeichert!")
            else:
                st.error("Nichts gefunden.")

# --- MODUL 2: DASHBOARD (GRAFIK) ---
elif menu == "2. Dashboard (Grafik)":
    st.header("📊 Therapie-Dashboard")
    df_v = lade_daten_gs("verzehr")
    df_p = lade_daten_gs("patienten")
    
    if df_p.empty:
        st.info("Keine Patienten vorhanden.")
    else:
        p_wahl = st.selectbox("Patient wählen:", df_p["Name"])
        p_data = df_p[df_p["Name"] == p_wahl].iloc[0]
        
        # Biometrie-Berechnung
        w = pd.to_numeric(p_data.get("Gewicht_aktuell", 0), errors='coerce') or 0
        h = pd.to_numeric(p_data.get("Groesse_cm", 0), errors='coerce') or 0
        bmi = round(w / ((h/100)**2), 1) if h > 0 else 0
        
        st.subheader("🧬 Status")
        b1, b2, b3, b4 = st.columns(4)
        b1.metric("Gewicht", f"{w} kg")
        b2.metric("BMI", f"{bmi}")
        b3.metric("Ziel", p_data.get("Ziel_Perzentile", "N/A"))
        b4.metric("Letztes Wiegen", p_data.get("Wiegedatum", "N/A"))
        
        # BMI Ampel
        if bmi > 0:
            if bmi < 18.5: st.error("Status: Untergewicht")
            elif bmi < 25: st.success("Status: Normalgewicht")
            else: st.warning("Status: Übergewicht")

        st.divider()
        
        # Kalorien-Auswertung
        heute = datetime.now().strftime("%Y-%m-%d")
        if not df_v.empty and "Datum" in df_v.columns:
            df_v["Datum"] = df_v["Datum"].astype(str)
            df_heute = df_v[(df_v["Datum"] == heute) & (df_v["Patient"] == p_wahl)]
            gegessen = df_heute["Kcal_Gesamt"].sum()
            ziel = pd.to_numeric(p_data["Ziel_Kcal"], errors='coerce') or 2000
            
            m1, m2 = st.columns(2)
            m1.metric("Heute verzehrt", f"{gegessen:.0f} kcal")
            m2.metric("Ziel", f"{ziel:.0f} kcal", delta=f"{int(ziel-gegessen)} kcal rest")
            
            st.progress(min(gegessen/ziel, 1.0) if ziel > 0 else 0)
            
            chart_data = pd.DataFrame({"Typ": ["Gegessen", "Ziel"], "kcal": [gegessen, ziel]})
            st.bar_chart(chart_data, x="Typ", y="kcal")
            
            with st.expander("Heutige Mahlzeiten bearbeiten"):
                for i, row in df_heute.iterrows():
                    c1, c2 = st.columns([3, 1])
                    c1.write(f"{row['Lebensmittel']}: {row['Kcal_Gesamt']:.0f} kcal")
                    if c2.button("Löschen", key=f"del_{i}"):
                        full_v = lade_daten_gs("verzehr")
                        full_v = full_v.drop(i)
                        speichere_df_gs(full_v, "verzehr")
                        st.rerun()
        else:
            st.info("Noch kein Verzehr für heute geloggt.")

# --- MODUL 3: PATIENTENVERWALTUNG ---
elif menu == "3. Patientenverwaltung":
    st.header("👥 Patienten & Biometrie")
    df_p = lade_daten_gs("patienten")
    t1, t2, t3 = st.tabs(["📋 Liste", "➕ Neu", "✏️ Wiegen & Ziel"])
    
    with t1:
        if not df_p.empty:
            df_list = df_p.copy()
            # Robuste BMI Berechnung für die Liste
            w_col = pd.to_numeric(df_list.get("Gewicht_aktuell", 0), errors='coerce').fillna(0)
            h_col = pd.to_numeric(df_list.get("Groesse_cm", 0), errors='coerce').fillna(0)
            df_list["BMI"] = (w_col / ((h_col/100)**2)).round(1).replace([float('inf'), -float('inf')], 0).fillna(0)
            st.dataframe(df_list, use_container_width=True, hide_index=True)
            
    with t2:
        with st.form("p_neu"):
            c1, c2 = st.columns(2)
            with c1:
                n = st.text_input("Name")
                g = st.selectbox("Geschlecht", ["weiblich", "männlich"])
                geb = st.date_input("Geburtsdatum", value=datetime(2010, 1, 1))
            with c2:
                w = st.number_input("Gewicht (kg)", value=50.0)
                h = st.number_input("Größe (cm)", value=160)
                perz = st.text_input("Ziel-Perzentile", "P25")
            z = st.number_input("Kalorienziel", value=2000)
            if st.form_submit_button("Speichern"):
                heute = datetime.now().strftime("%Y-%m-%d")
                new_p = pd.DataFrame([[n, z, g, str(geb), h, perz, w, heute]], 
                                     columns=["Name", "Ziel_Kcal", "Geschlecht", "Geburtsdatum", "Groesse_cm", "Ziel_Perzentile", "Gewicht_aktuell", "Wiegedatum"])
                df_p = pd.concat([df_p, new_p], ignore_index=True)
                speichere_df_gs(df_p, "patienten")
                st.rerun()
                
    with t3:
        if not df_p.empty:
            p_edit = st.selectbox("Patient wählen:", df_p["Name"])
            idx = df_p[df_p["Name"] == p_edit].index[0]
            with st.form("p_edit_form"):
                new_w = st.number_input("Neues Gewicht", value=float(df_p.at[idx, "Gewicht_aktuell"]) if "Gewicht_aktuell" in df_p.columns else 50.0)
                new_z = st.number_input("Neues Kcal-Ziel", value=int(df_p.at[idx, "Ziel_Kcal"]))
                if st.form_submit_button("Aktualisieren"):
                    df_p.at[idx, "Gewicht_aktuell"] = new_w
                    df_p.at[idx, "Ziel_Kcal"] = new_z
                    df_p.at[idx, "Wiegedatum"] = datetime.now().strftime("%Y-%m-%d")
                    speichere_df_gs(df_p, "patienten")
                    st.success("Daten aktualisiert!")
                    st.rerun()

# --- MODUL 4: DATENBANK ---
elif menu == "4. Datenbank bearbeiten":
    st.header("📊 Lebensmittel-Datenbank")
    df_db = lade_daten_gs("lebensmittel")
    
    view = st.radio("Ansicht:", ["Alle", "Intern", "Extern"], horizontal=True)
    if view != "Alle":
        st.dataframe(df_db[df_db['Typ'] == view], use_container_width=True)
    else:
        st.dataframe(df_db, use_container_width=True)
    
    with st.expander("Neues Lebensmittel hinzufügen"):
        with st.form("f_add"):
            f_t = st.selectbox("Typ", ["Intern", "Extern"])
            f_n = st.text_input("Bezeichnung")
            f_k = st.number_input("Kcal / 100g")
            f_g = st.number_input("Stückgewicht (g)")
            f_s = st.text_input("Standardmenge (z.B. 1 Stück)")
            if st.form_submit_button("Hinzufügen"):
                new_f = pd.DataFrame([[f_n, f_k, f_g, f_s, f_t]], 
                                     columns=["Name", "kcal_100g", "stueck_gewicht", "Standard_Menge", "Typ"])
                df_db = pd.concat([df_db, new_f], ignore_index=True)
                speichere_df_gs(df_db, "lebensmittel")
                st.rerun()

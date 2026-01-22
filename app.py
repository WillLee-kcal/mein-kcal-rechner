import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
from datetime import datetime

# --- 1. SETUP & VERBINDUNG ---
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
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        # Sicherheits-Check: Leerzeichen aus Spaltennamen entfernen
        df.columns = df.columns.str.strip()
        return df
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

# --- 2. LAYOUT ---
st.set_page_config(page_title="Kcal Profi-Tracker", layout="wide", page_icon="🍎")
st.sidebar.title("🍎 Navigation")
menu = st.sidebar.radio("Menü wählen:", ["1. Mahlzeit & Logbuch", "2. Dashboard (Grafik)", "3. Patientenverwaltung", "4. Datenbank bearbeiten"])

# --- MODUL 1: MAHLZEIT ERFASSEN ---
if menu == "1. Mahlzeit & Logbuch":
    st.header("⚖️ Mahlzeit erfassen")
    df_db = lade_daten_gs("lebensmittel")
    df_p = lade_daten_gs("patienten")
    
    if df_p.empty:
        st.warning("Bitte erst Patienten anlegen (Punkt 3).")
    elif df_db.empty:
        st.warning("Datenbank leer.")
    else:
        typ_filter = st.radio("Kategorie:", ["Alle", "Intern", "Extern"], horizontal=True)
        c_a, c_b = st.columns(2)
        with c_a:
            p_wahl = st.selectbox("Patient:", df_p["Name"])
            df_gefiltert = df_db if typ_filter == "Alle" else df_db[df_db['Typ'] == typ_filter]
            suche = st.text_input("Suchen:")
        
        if suche:
            treffer = df_gefiltert[df_gefiltert['Name'].str.contains(suche, case=False, na=False)]
            if not treffer.empty:
                wahl = st.selectbox("Gefunden:", treffer['Name'])
                item = treffer[treffer['Name'] == wahl].iloc[0]
                st.info(f"Einheit: {item.get('Standard_Menge', '1 Stück')}")
                with c_b:
                    menge = st.number_input("Anzahl / Menge:", min_value=0.0, step=0.5, value=1.0)
                    einheit = st.radio("Basis:", ["Stück / Einheit", "Gramm"])
                
                s_w = pd.to_numeric(item['stueck_gewicht'], errors='coerce') or 0
                k_100 = pd.to_numeric(item['kcal_100g'], errors='coerce') or 0
                gewicht = menge * s_w if einheit == "Stück / Einheit" else menge
                kcal_t = (k_100 / 100) * gewicht
                st.metric("Ergebnis", f"{kcal_t:.1f} kcal")
                
                if st.button("Speichern"):
                    heute = datetime.now().strftime("%Y-%m-%d")
                    speichere_zeile_gs([heute, p_wahl, wahl, gewicht, kcal_t], "verzehr")
                    st.success("Eintrag gespeichert!")
            else: st.error("Nichts gefunden.")

# --- MODUL 2: DASHBOARD ---
elif menu == "2. Dashboard (Grafik)":
    st.header("📊 Therapie-Dashboard")
    df_v = lade_daten_gs("verzehr")
    df_p = lade_daten_gs("patienten")
    
    if df_p.empty:
        st.info("Keine Patienten vorhanden.")
    else:
        p_wahl = st.selectbox("Patient wählen:", df_p["Name"])
        p_data = df_p[df_p["Name"] == p_wahl].iloc[0]
        
        # Biometrie
        w = pd.to_numeric(p_data.get("Gewicht_aktuell", 0), errors='coerce') or 0
        h = pd.to_numeric(p_data.get("Groesse_cm", 0), errors='coerce') or 0
        bmi = round(w / ((h/100)**2), 1) if h > 0 else 0
        
        b1, b2, b3, b4 = st.columns(4)
        b1.metric("Gewicht", f"{w} kg")
        b2.metric("BMI", f"{bmi}")
        b3.metric("Ziel-Perz.", p_data.get("Ziel_Perzentile", "-"))
        b4.metric("Wiegedatum", p_data.get("Wiegedatum", "-"))
        
        st.divider()
        
        # Kalorien heute
        heute = datetime.now().strftime("%Y-%m-%d")
        if not df_v.empty and "Datum" in df_v.columns:
            df_v["Datum"] = df_v["Datum"].astype(str)
            df_heute = df_v[(df_v["Datum"] == heute) & (df_v["Patient"] == p_wahl)]
            
            gegessen = df_heute["Kcal_Gesamt"].sum() if not df_heute.empty else 0
            ziel = pd.to_numeric(p_data["Ziel_Kcal"], errors='coerce') or 2000
            
            m1, m2 = st.columns(2)
            m1.metric("Verzehrt", f"{gegessen:.0f} kcal")
            m2.metric("Rest", f"{int(ziel-gegessen)} kcal", delta=f"{int(ziel-gegessen)}")
            st.progress(min(gegessen/ziel, 1.0) if ziel > 0 else 0)
            
            if not df_heute.empty:
                with st.expander("Einträge von heute"):
                    # Sicherheitsprüfung für Spaltennamen
                    cols = df_heute.columns.tolist()
                    food_col = "Lebensmittel" if "Lebensmittel" in cols else cols[2]
                    kcal_col = "Kcal_Gesamt" if "Kcal_Gesamt" in cols else cols[4]
                    
                    for i, row in df_heute.iterrows():
                        c1, c2 = st.columns([3, 1])
                        c1.write(f"**{row[food_col]}**: {row[kcal_col]:.0f} kcal")
                        if c2.button("Löschen", key=f"del_{i}"):
                            full_v = lade_daten_gs("verzehr")
                            full_v = full_v.drop(i)
                            speichere_df_gs(full_v, "verzehr")
                            st.rerun()
            else: st.info("Noch kein Verzehr heute.")
        else: st.info("Logbuch leer.")

# --- MODUL 3: PATIENTEN ---
elif menu == "3. Patientenverwaltung":
    st.header("👥 Patientenverwaltung")
    df_p = lade_daten_gs("patienten")
    t1, t2, t3 = st.tabs(["📋 Liste", "➕ Neu", "✏️ Update"])
    
    with t1:
        if not df_p.empty: st.dataframe(df_p, use_container_width=True, hide_index=True)
    with t2:
        with st.form("p_neu"):
            n = st.text_input("Name")
            g = st.selectbox("Geschlecht", ["weiblich", "männlich"])
            geb = st.date_input("Geburtsdatum", value=datetime(2010, 1, 1))
            w = st.number_input("Gewicht (kg)", value=50.0)
            h = st.number_input("Größe (cm)", value=160)
            perz = st.text_input("Ziel-Perzentile", "P25")
            z = st.number_input("Ziel Kcal", value=2000)
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
            with st.form("p_edit"):
                new_w = st.number_input("Neues Gewicht", value=float(df_p.at[idx, "Gewicht_aktuell"]))
                new_z = st.number_input("Neues Kcal-Ziel", value=int(df_p.at[idx, "Ziel_Kcal"]))
                if st.form_submit_button("Aktualisieren"):
                    df_p.at[idx, "Gewicht_aktuell"] = new_w
                    df_p.at[idx, "Ziel_Kcal"] = new_z
                    df_p.at[idx, "Wiegedatum"] = datetime.now().strftime("%Y-%m-%d")
                    speichere_df_gs(df_p, "patienten")
                    st.rerun()

# --- MODUL 4: DATENBANK ---
elif menu == "4. Datenbank bearbeiten":
    st.header("📊 Lebensmittel")
    df_db = lade_daten_gs("lebensmittel")
    st.dataframe(df_db, use_container_width=True)
    with st.expander("Neu hinzufügen"):
        with st.form("f_add"):
            ft = st.selectbox("Typ", ["Intern", "Extern"])
            fn = st.text_input("Name")
            fk = st.number_input("Kcal/100g")
            fg = st.number_input("Stückgewicht")
            fs = st.text_input("Standardmenge")
            if st.form_submit_button("Hinzufügen"):
                new_f = pd.DataFrame([[fn, fk, fg, fs, ft]], columns=["Name", "kcal_100g", "stueck_gewicht", "Standard_Menge", "Typ"])
                df_db = pd.concat([df_db, new_f], ignore_index=True)
                speichere_df_gs(df_db, "lebensmittel")
                st.rerun()


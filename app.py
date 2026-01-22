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

# --- 1. SETUP & VERBINDUNG ---
def get_gsheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        if "gcp_service_account" in st.secrets:
            credentials_info = st.secrets["gcp_service_account"]
            if isinstance(credentials_info, str): 
                credentials_info = json.loads(credentials_info)
            creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials_info, scope)
        else:
            creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"🚨 Verbindung zu Google fehlgeschlagen: {e}")
        return None

def lade_daten_gs(sheet_name):
    client = get_gsheet_client()
    if client:
        try:
            # Versuche die Datei zu öffnen
            spreadsheet = client.open("Kcal_Datenbank")
            sheet = spreadsheet.worksheet(sheet_name)
            data = sheet.get_all_records()
            
            if not data: # Falls die Tabelle leer ist (nur Header)
                return pd.DataFrame()
                
            df = pd.DataFrame(data)
            df.columns = df.columns.str.strip()
            return df
        except gspread.exceptions.SpreadsheetNotFound:
            st.error(f"❌ Tabelle 'Kcal_Datenbank' wurde in Google Drive nicht gefunden!")
        except gspread.exceptions.WorksheetNotFound:
            st.error(f"❌ Tabellenblatt '{sheet_name}' fehlt in der Datei!")
        except Exception as e:
            st.error(f"❌ Fehler beim Laden von '{sheet_name}': {e}")
    return pd.DataFrame()

def speichere_zeile_gs(liste_werte, sheet_name):
    try:
        client = get_gsheet_client()
        sheet = client.open("Kcal_Datenbank").worksheet(sheet_name)
        sheet.append_row(liste_werte)
    except Exception as e:
        st.error(f"Fehler beim Speichern: {e}")

def speichere_df_gs(df, sheet_name):
    try:
        client = get_gsheet_client()
        sheet = client.open("Kcal_Datenbank").worksheet(sheet_name)
        sheet.clear()
        sheet.update([df.columns.values.tolist()] + df.values.tolist())
    except Exception as e:
        st.error(f"Fehler beim Aktualisieren der Tabelle: {e}")

# --- 2. LAYOUT ---
st.set_page_config(page_title="Kcal Profi-Tracker", layout="wide", page_icon="🍎")
st.sidebar.title("🍎 Navigation")
menu = st.sidebar.radio("Menü wählen:", ["1. Mahlzeit & Logbuch", "2. Dashboard (Grafik)", "3. Patientenverwaltung", "4. Datenbank"])

# --- MODUL 1: MAHLZEIT ERFASSEN ---
if menu == "1. Mahlzeit & Logbuch":
    st.header("⚖️ Mahlzeit erfassen")
    df_db = lade_daten_gs("lebensmittel")
    df_p = lade_daten_gs("patienten")
    
    if df_p.empty:
        st.warning("Keine Patientendaten gefunden. Bitte in Punkt 3 prüfen.")
    elif df_db.empty:
        st.warning("Lebensmittel-Datenbank konnte nicht geladen werden.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            p_wahl = st.selectbox("Für welchen Patienten?", df_p["Name"])
            m_zeit = st.selectbox("Mahlzeit auswählen:", MAHLZEITEN_LISTE)
            typ_f = st.radio("Kategorie:", ["Intern", "Extern", "Alle"], horizontal=True)
            
        with col2:
            suche = st.text_input("Lebensmittel suchen:")
            
        if suche:
            df_f = df_db if typ_f == "Alle" else df_db[df_db['Typ'] == typ_f]
            treffer = df_f[df_f['Name'].str.contains(suche, case=False, na=False)]
            
            if not treffer.empty:
                wahl = st.selectbox("Gefunden:", treffer['Name'])
                item = treffer[treffer['Name'] == wahl].iloc[0]
                st.info(f"💡 Einheit: {item.get('Standard_Menge', '1 Stück')}")
                
                c3, c4 = st.columns(2)
                with c3:
                    menge = st.number_input("Anzahl / Menge:", min_value=0.0, step=0.5, value=1.0)
                with c4:
                    basis = st.radio("Berechnung nach:", ["Stück / Einheit", "Gramm"])
                
                # Berechnung
                stk_w = pd.to_numeric(item['stueck_gewicht'], errors='coerce') or 0
                kcal_100 = pd.to_numeric(item['kcal_100g'], errors='coerce') or 0
                gewicht = menge * stk_w if basis == "Stück / Einheit" else menge
                kcal_total = (kcal_100 / 100) * gewicht
                
                st.metric("Berechnetes Ergebnis", f"{kcal_total:.1f} kcal")
                
                if st.button("💾 In Logbuch speichern"):
                    heute = datetime.now().strftime("%Y-%m-%d")
                    speichere_zeile_gs([heute, p_wahl, m_zeit, wahl, round(gewicht,1), round(kcal_total,1)], "verzehr")
                    st.success(f"Eintrag gespeichert!")
            else:
                st.error("Nichts gefunden.")

# --- MODUL 2: DASHBOARD ---
elif menu == "2. Dashboard (Grafik)":
    st.header("📊 Tageszusammenfassung")
    df_v = lade_daten_gs("verzehr")
    df_p = lade_daten_gs("patienten")
    
    if df_p.empty:
        st.info("Keine Patienten geladen.")
    else:
        p_wahl = st.selectbox("Patient wählen:", df_p["Name"])
        p_data = df_p[df_p["Name"] == p_wahl].iloc[0]
        heute = datetime.now().strftime("%Y-%m-%d")
        
        # Biometrie
        w = pd.to_numeric(p_data.get("Gewicht_aktuell", 0), errors='coerce') or 0
        h = pd.to_numeric(p_data.get("Groesse_cm", 0), errors='coerce') or 0
        bmi = round(w / ((h/100)**2), 1) if h > 0 else 0
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Gewicht", f"{w} kg")
        m2.metric("BMI", f"{bmi}")
        m3.metric("Ziel", p_data.get("Ziel_Perzentile", "-"))
        st.divider()
        
        if not df_v.empty:
            df_v["Datum"] = df_v.get("Datum", pd.Series()).astype(str)
            df_heute = df_v[(df_v["Datum"] == heute) & (df_v["Patient"] == p_wahl)]
            
            ges_kcal = df_heute["Kcal_Gesamt"].sum() if not df_heute.empty else 0
            ziel_kcal = pd.to_numeric(p_data["Ziel_Kcal"], errors='coerce') or 2000
            
            st.subheader(f"Tagesstand: {ges_kcal:.0f} / {ziel_kcal:.0f} kcal")
            st.progress(min(ges_kcal/ziel_kcal, 1.0) if ziel_kcal > 0 else 0)
            
            for m in MAHLZEITEN_LISTE:
                m_data = df_heute[df_heute["Mahlzeit"] == m]
                m_sum = m_data["Kcal_Gesamt"].sum()
                with st.expander(f"{m} ({m_sum:.0f} kcal)"):
                    if not m_data.empty:
                        for idx, row in m_data.iterrows():
                            c_l, c_r = st.columns([4, 1])
                            c_l.write(f"**{row['Lebensmittel']}**: {row['Kcal_Gesamt']:.1f} kcal")
                            if c_r.button("🗑️", key=f"del_{idx}"):
                                full_v = lade_daten_gs("verzehr")
                                full_v = full_v.drop(idx)
                                speichere_df_gs(full_v, "verzehr")
                                st.rerun()
                    else:
                        st.write("Keine Einträge.")
        else:
            st.info("Logbuch für heute leer.")

# --- MODUL 3: PATIENTEN ---
elif menu == "3. Patientenverwaltung":
    st.header("👥 Patientenverwaltung")
    df_p = lade_daten_gs("patienten")
    t1, t2, t3 = st.tabs(["📋 Liste", "➕ Neu", "✏️ Wiegen"])
    with t1:
        if not df_p.empty:
            st.dataframe(df_p, use_container_width=True, hide_index=True)
        else:
            st.write("Tabelle ist leer.")
    with t2:
        with st.form("p_new"):
            n = st.text_input("Name")
            g = st.selectbox("Geschlecht", ["weiblich", "männlich"])
            geb = st.date_input("Geburtsdatum", value=datetime(2010, 1, 1))
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
            with st.form("p_edit"):
                new_w = st.number_input("Gewicht", value=float(df_p.at[idx, "Gewicht_aktuell"]))
                new_z = st.number_input("Kcal-Ziel", value=int(df_p.at[idx, "Ziel_Kcal"]))
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
    if not df_db.empty:
        st.dataframe(df_db, use_container_width=True)
    with st.expander("Neu hinzufügen"):
        with st.form("f_add"):
            ft = st.selectbox("Typ", ["Intern", "Extern"])
            fn = st.text_input("Name")
            fk = st.number_input("Kcal/100g")
            fg = st.number_input("Stückgewicht (g)")
            fs = st.text_input("Standardmenge")
            if st.form_submit_button("Hinzufügen"):
                new_f = pd.DataFrame([[fn, fk, fg, fs, ft]], columns=["Name", "kcal_100g", "stueck_gewicht", "Standard_Menge", "Typ"])
                df_db = pd.concat([df_db, new_f], ignore_index=True)
                speichere_df_gs(df_db, "lebensmittel")
                st.rerun()

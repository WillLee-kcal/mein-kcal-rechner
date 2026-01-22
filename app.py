import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
from datetime import datetime

# --- KONSTANTEN ---
MAHLZEITEN_LISTE = [
    "Frühstück", 
    "Zwischenmahlzeit 1", 
    "Mittagessen", 
    "Zwischenmahlzeit 2", 
    "Abendessen", 
    "Zwischenmahlzeit 3"
]

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
        df = pd.DataFrame(sheet.get_all_records())
        df.columns = df.columns.str.strip() # Entfernt unsichtbare Leerzeichen
        return df
    except:
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
menu = st.sidebar.radio("Menü wählen:", ["1. Mahlzeit & Logbuch", "2. Dashboard (Grafik)", "3. Patientenverwaltung", "4. Datenbank"])

# --- MODUL 1: MAHLZEIT ERFASSEN ---
if menu == "1. Mahlzeit & Logbuch":
    st.header("⚖️ Mahlzeit erfassen")
    df_db = lade_daten_gs("lebensmittel")
    df_p = lade_daten_gs("patienten")
    
    if df_p.empty:
        st.warning("Bitte lege zuerst unter Punkt 3 einen Patienten an.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            p_wahl = st.selectbox("Für welchen Patienten?", df_p["Name"])
            m_zeit = st.selectbox("Mahlzeit auswählen:", MAHLZEITEN_LISTE)
            typ_f = st.radio("Kategorie:", ["Intern", "Extern", "Alle"], horizontal=True)
            
        with col2:
            suche = st.text_input("Lebensmittel suchen (z.B. Mischbrot):")
            
        if suche:
            # Suche in der Datenbank
            df_f = df_db if typ_f == "Alle" else df_db[df_db['Typ'] == typ_f]
            treffer = df_f[df_f['Name'].str.contains(suche, case=False, na=False)]
            
            if not treffer.empty:
                wahl = st.selectbox("Gefunden:", treffer['Name'])
                item = treffer[treffer['Name'] == wahl].iloc[0]
                
                # Info zur Standardmenge
                st.info(f"💡 Info aus Vorlage: 1 Einheit = {item.get('Standard_Menge', '1 Stück')}")
                
                c3, c4 = st.columns(2)
                with c3:
                    menge = st.number_input("Anzahl / Menge:", min_value=0.0, step=0.5, value=1.0)
                with c4:
                    basis = st.radio("Berechnung nach:", ["Stück / Einheit", "Gramm"])
                
                # --- KORREKTE BERECHNUNG ---
                # Wir holen die Zahlenwerte und sichern sie gegen Textfehler ab
                stk_gewicht = pd.to_numeric(item['stueck_gewicht'], errors='coerce') or 0
                kcal_100g = pd.to_numeric(item['kcal_100g'], errors='coerce') or 0
                
                # Gesamtgewicht bestimmen
                gewicht_final = menge * stk_gewicht if basis == "Stück / Einheit" else menge
                
                # Kcal berechnen: (kcal pro 100g / 100) * Gewicht
                kcal_total = (kcal_100g / 100) * gewicht_final
                
                st.metric("Berechnetes Ergebnis", f"{kcal_total:.1f} kcal", help=f"Rechnung: ({kcal_100g} / 100) * {gewicht_final}g")
                
                if st.button("💾 In Logbuch speichern"):
                    heute = datetime.now().strftime("%Y-%m-%d")
                    # Speichern: Datum, Patient, Mahlzeit, Lebensmittel, Menge, Kcal
                    speichere_zeile_gs([heute, p_wahl, m_zeit, wahl, gewicht_final, kcal_total], "verzehr")
                    st.success(f"Eintrag für {m_zeit} wurde gespeichert!")
            else:
                st.error("Kein Lebensmittel mit diesem Namen gefunden.")

# --- MODUL 2: DASHBOARD (GRAFIK & 6 MAHLZEITEN) ---
elif menu == "2. Dashboard (Grafik)":
    st.header("📊 Tageszusammenfassung & Status")
    df_v = lade_daten_gs("verzehr")
    df_p = lade_daten_gs("patienten")
    
    if df_p.empty:
        st.info("Noch keine Patienten vorhanden.")
    else:
        p_wahl = st.selectbox("Patient wählen:", df_p["Name"])
        p_data = df_p[df_p["Name"] == p_wahl].iloc[0]
        heute = datetime.now().strftime("%Y-%m-%d")
        
        # 🧬 Biometrie (BMI etc.)
        w = pd.to_numeric(p_data.get("Gewicht_aktuell", 0), errors='coerce') or 0
        h = pd.to_numeric(p_data.get("Groesse_cm", 0), errors='coerce') or 0
        bmi = round(w / ((h/100)**2), 1) if h > 0 else 0
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Gewicht", f"{w} kg")
        c2.metric("BMI", f"{bmi}")
        c3.metric("Ziel", p_data.get("Ziel_Perzentile", "-"))
        c4.metric("Wiegedatum", p_data.get("Wiegedatum", "-"))
        
        st.divider()
        
        # 🍴 Kalorien-Check (6 Mahlzeiten)
        if not df_v.empty:
            df_v["Datum"] = df_v["Datum"].astype(str)
            df_heute = df_v[(df_v["Datum"] == heute) & (df_v["Patient"] == p_wahl)]
            
            gesamt_kcal = df_heute["Kcal_Gesamt"].sum() if not df_heute.empty else 0
            ziel_kcal = pd.to_numeric(p_data["Ziel_Kcal"], errors='coerce') or 2000
            
            st.subheader(f"Kalorien: {gesamt_kcal:.0f} von {ziel_kcal:.0f} kcal")
            st.progress(min(gesamt_kcal/ziel_kcal, 1.0) if ziel_kcal > 0 else 0)
            
            # Mahlzeiten-Einteilung
            st.write("### Tagesplan (6 Mahlzeiten)")
            for m in MAHLZEITEN_LISTE:
                m_data = df_heute[df_heute["Mahlzeit"] == m]
                m_sum = m_data["Kcal_Gesamt"].sum()
                
                with st.expander(f"{m} — {m_sum:.0f} kcal"):
                    if not m_data.empty:
                        for idx, row in m_data.iterrows():
                            col_l, col_r = st.columns([4, 1])
                            col_l.write(f"**{row['Lebensmittel']}** ({row['Menge_g']:.0f}g) = {row['Kcal_Gesamt']:.1f} kcal")
                            if col_r.button("🗑️", key=f"del_{idx}"):
                                full_v = lade_daten_gs("verzehr")
                                full_v = full_v.drop(idx)
                                speichere_df_gs(full_v, "verzehr")
                                st.rerun()
                    else:
                        st.write("🚫 Keine Einträge für diese Mahlzeit.")
        else:
            st.info("Logbuch ist für heute noch leer.")


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




import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
from datetime import datetime

# --- 1. GOOGLE SHEETS SETUP ---
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

# --- MODUL 1: MAHLZEIT ERFASSEN (Mit Unterteilung Intern/Extern) ---
if menu == "1. Mahlzeit & Logbuch":
    st.header("⚖️ Mahlzeit erfassen")
    df_db = lade_daten_gs("lebensmittel")
    df_p = lade_daten_gs("patienten")
    
    if df_p.empty:
        st.warning("Bitte lege zuerst einen Patienten an.")
    elif df_db.empty:
        st.warning("Datenbank leer.")
    else:
        # Filter für die Datenbank-Unterteilung
        typ_filter = st.radio("Kategorie wählen:", ["Alle", "Intern", "Extern"], horizontal=True)
        
        col_a, col_b = st.columns(2)
        with col_a:
            p_wahl = st.selectbox("Patient:", df_p["Name"])
            
            # Datenbank filtern basierend auf Radio-Button
            if typ_filter != "Alle":
                df_gefiltert = df_db[df_db['Typ'] == typ_filter]
            else:
                df_gefiltert = df_db
                
            suche = st.text_input(f"Suche in {typ_filter}:")
        
        if suche:
            treffer = df_gefiltert[df_gefiltert['Name'].str.contains(suche, case=False, na=False)]
            if not treffer.empty:
                wahl = st.selectbox("Gefunden:", treffer['Name'])
                item = df_db[df_db['Name'] == wahl].iloc[0]
                
                # Info-Box aus den klinischen Daten
                std_info = item.get('Standard_Menge', 'Stück')
                st.info(f"Vorlage: 1 Einheit = {std_info}")
                
                with col_b:
                    menge = st.number_input("Anzahl / Menge:", min_value=0.0, step=0.5)
                    einheit = st.radio("Basis:", ["Stück / Einheit", "Gramm"])
                
                gewicht = menge * float(item['stueck_gewicht']) if einheit == "Stück / Einheit" else menge
                kcal_total = (float(item['kcal_100g']) / 100) * gewicht
                
                st.metric("Berechnet", f"{kcal_total:.1f} kcal")
                
                if st.button("Speichern"):
                    heute = datetime.now().strftime("%Y-%m-%d")
                    speichere_zeile_gs([heute, p_wahl, wahl, gewicht, kcal_total], "verzehr")
                    st.success("Im Logbuch vermerkt!")
            else:
                st.error("Nichts gefunden.")





# --- MODUL 1: MAHLZEIT ERFASSEN (Optimiert für Mengen) ---
if menu == "1. Mahlzeit & Logbuch":
    st.header("⚖️ Mahlzeit berechnen & speichern")
    df_db = lade_daten_gs("lebensmittel")
    df_p = lade_daten_gs("patienten")
    
    if not df_p.empty and not df_db.empty:
        col_a, col_b = st.columns(2)
        with col_a:
            p_wahl = st.selectbox("Für welchen Patienten?", df_p["Name"])
            suche = st.text_input("Lebensmittel suchen:")
        
        if suche:
            treffer = df_db[df_db['Name'].str.contains(suche, case=False, na=False)]
            if not treffer.empty:
                wahl = st.selectbox("Gefunden:", treffer['Name'])
                item = df_db[df_db['Name'] == wahl].iloc[0]
                
                # Anzeige der Standard-Menge aus deiner Vorlage
                std_menge = item.get('Standard_Menge', 'Stück')
                st.info(f"Info aus Vorlage: 1 Einheit entspricht ca. **{std_menge}**")
                
                with col_b:
                    menge = st.number_input(f"Wie viele {einheit if einheit=='Gramm' else 'Einheiten'}?", min_value=0.0, step=1.0)
                    einheit = st.radio("Berechnungsgrundlage:", ["Stück / Einheit", "Gramm"])
                
                # Logik: Entweder Gramm direkt oder (Einheit * Stückgewicht)
                if einheit == "Stück / Einheit":
                    gewicht = menge * float(item['stueck_gewicht'])
                    kcal_total = (float(item['kcal_100g']) / 100) * gewicht
                else:
                    gewicht = menge
                    kcal_total = (float(item['kcal_100g']) / 100) * gewicht
                
                st.metric("Ergebnis", f"{kcal_total:.1f} kcal", help=f"Gesamtgewicht: {gewicht}g")
                
                if st.button("Ins Logbuch eintragen"):
                    heute = datetime.now().strftime("%Y-%m-%d")
                    speichere_zeile_gs([heute, p_wahl, wahl, gewicht, kcal_total], "verzehr")
                    st.success("Eintrag gespeichert!")

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

# --- MODUL 3: PATIENTENVERWALTUNG (PROFI-VERSION) ---
elif menu == "3. Patientenverwaltung":
    st.header("👥 Patientenverwaltung & Biometrie")
    df_p = lade_daten_gs("patienten")
    
    t_liste, t_neu, t_edit, t_del = st.tabs([
        "📋 Patientenliste", "➕ Neu anlegen", "✏️ Daten anpassen", "🗑️ Löschen"
    ])

    # --- TAB 1: LISTE (Inkl. BMI-Berechnung) ---
    with t_liste:
        if not df_p.empty:
            # Falls Spalten fehlen, leere Werte ergänzen (Schutz vor Absturz)
            for col in ["Geschlecht", "Geburtsdatum", "Groesse_cm", "Ziel_Perzentile"]:
                if col not in df_p.columns: df_p[col] = ""

            st.dataframe(df_p, use_container_width=True, hide_index=True)
        else:
            st.info("Noch keine Patienten vorhanden.")

    # --- TAB 2: NEU ANLEGEN ---
    with t_neu:
        with st.form("p_neu_form"):
            col1, col2 = st.columns(2)
            with col1:
                new_n = st.text_input("Vollständiger Name")
                new_g = st.selectbox("Geschlecht", ["weiblich", "männlich", "divers"])
                new_birth = st.date_input("Geburtsdatum", value=datetime(2010, 1, 1))
            with col2:
                new_z = st.number_input("Tagesziel (kcal)", value=2000, step=50)
                new_h = st.number_input("Größe (in cm)", value=160)
                new_perz = st.text_input("Ziel-Perzentile (z.B. P25)", "P25")
            
            if st.form_submit_button("Patient speichern"):
                if new_n:
                    new_data = pd.DataFrame([[
                        new_n, new_z, new_g, str(new_birth), new_h, new_perz
                    ]], columns=["Name", "Ziel_Kcal", "Geschlecht", "Geburtsdatum", "Groesse_cm", "Ziel_Perzentile"])
                    
                    df_p = pd.concat([df_p, new_data], ignore_index=True)
                    speichere_df_gs(df_p, "patienten")
                    st.success(f"Patient {new_n} angelegt!")
                    st.rerun()

    # --- TAB 3: DATEN ANPASSEN ---
    with t_edit:
        if not df_p.empty:
            edit_n = st.selectbox("Patient wählen:", df_p["Name"])
            p_idx = df_p[df_p["Name"] == edit_n].index[0]
            
            # Bestehende Werte laden
            curr_z = df_p.at[p_idx, "Ziel_Kcal"]
            curr_h = df_p.at[p_idx, "Groesse_cm"] if "Groesse_cm" in df_p.columns else 160
            curr_perz = df_p.at[p_idx, "Ziel_Perzentile"] if "Ziel_Perzentile" in df_p.columns else "P25"
            
            col1, col2 = st.columns(2)
            with col1:
                up_z = st.number_input("Ziel (kcal) ändern:", value=int(curr_z))
                up_h = st.number_input("Größe (cm) ändern:", value=int(curr_h) if curr_h else 160)
            with col2:
                up_perz = st.text_input("Ziel-Perzentile ändern:", value=str(curr_perz))
                
            if st.button("Änderungen übernehmen"):
                df_p.at[p_idx, "Ziel_Kcal"] = up_z
                df_p.at[p_idx, "Groesse_cm"] = up_h
                df_p.at[p_idx, "Ziel_Perzentile"] = up_perz
                speichere_df_gs(df_p, "patienten")
                st.success("Daten aktualisiert!")
                st.rerun()

    # --- TAB 4: LÖSCHEN ---
    with t_del:
        if not df_p.empty:
            del_n = st.selectbox("Patient unwiderruflich löschen:", df_p["Name"])
            if st.button(f"Lösche {del_n}", type="primary"):
                df_p = df_p[df_p["Name"] != del_n]
                speichere_df_gs(df_p, "patienten")
                st.rerun()
                
# --- MODUL 4: DATENBANK BEARBEITEN (Mit Typ-Auswahl) ---
elif menu == "4. Datenbank bearbeiten":
    st.header("📊 Datenbank")
    df_db = lade_daten_gs("lebensmittel")
    
    # Filter-Anzeige der Tabelle
    ansicht = st.segmented_control("Tabellenansicht:", ["Intern", "Extern", "Alle"], default="Alle")
    if ansicht != "Alle":
        st.dataframe(df_db[df_db['Typ'] == ansicht], use_container_width=True)
    else:
        st.dataframe(df_db, use_container_width=True)
    
    with st.expander("Neues Produkt hinzufügen"):
        with st.form("add_food"):
            f_typ = st.selectbox("Typ:", ["Intern", "Extern"])
            f_name = st.text_input("Bezeichnung")
            f_kcal = st.number_input("Kcal/100g")
            f_stk = st.number_input("Stückgewicht (g)")
            f_std = st.text_input("Standard-Menge (z.B. 1 Eßl.)")
            if st.form_submit_button("Hinzufügen"):
                # Wir stellen sicher, dass die Spaltenreihenfolge stimmt
                new_row = pd.DataFrame([[f_name, f_kcal, f_stk, f_std, f_typ]], 
                                     columns=["Name", "kcal_100g", "stueck_gewicht", "Standard_Menge", "Typ"])
                df_db = pd.concat([df_db, new_row], ignore_index=True)
                speichere_df_gs(df_db, "lebensmittel")
                st.rerun()



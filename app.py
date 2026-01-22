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

# --- MODUL 2: DASHBOARD (VOLLSTÄNDIG: BIOMETRIE & KALORIEN) ---
elif menu == "2. Dashboard":
    st.header("📊 Therapie-Dashboard")
    
    # Daten laden
    df_v = lade_daten_gs("verzehr")
    df_p = lade_daten_gs("patienten")
    
    if df_p.empty:
        st.info("Noch keine Patienten im System. Bitte unter 'Patientenverwaltung' anlegen.")
    else:
        # Patientenauswahl
        p_wahl = st.selectbox("Patient wählen:", df_p["Name"])
        p_data = df_p[df_p["Name"] == p_wahl].iloc[0]
        
        # --- SEKTION 1: BIOMETRISCHER STATUS ---
        st.subheader("🧬 Biometrischer Status")
        b1, b2, b3, b4 = st.columns(4)
        
        # Biometrie-Berechnungen
        gewicht = p_data.get("Gewicht_aktuell", 0)
        groesse = p_data.get("Groesse_cm", 0)
        
        # BMI Formel: kg / (m^2)
        bmi = round(float(gewicht) / ((float(groesse)/100)**2), 1) if float(groesse) > 0 else 0
        
        b1.metric("Aktuelles Gewicht", f"{gewicht} kg")
        b2.metric("Aktueller BMI", f"{bmi}")
        b3.metric("Ziel-Perzentile", p_data.get("Ziel_Perzentile", "N/A"))
        b4.metric("Letztes Wiegen", p_data.get("Wiegedatum", "N/A"))
        
        st.divider()

        # --- SEKTION 2: KALORIEN-AUSWERTUNG (HEUTE) ---
        st.subheader(f"🍴 Kalorien-Bilanz für heute")
        
        if df_v.empty or "Datum" not in df_v.columns:
            st.info("Noch keine Mahlzeiten im Logbuch vermerkt.")
        else:
            heute = datetime.now().strftime("%Y-%m-%d")
            
            # Daten für heute filtern
            df_v["Datum"] = df_v["Datum"].astype(str)
            df_heute = df_v[(df_v["Datum"] == heute) & (df_v["Patient"] == p_wahl)]
            
            gegessen = df_heute["Kcal_Gesamt"].sum()
            ziel = float(p_data["Ziel_Kcal"])
            rest = ziel - gegessen
            
            # Metriken anzeigen
            m1, m2, m3 = st.columns(3)
            m1.metric("Heute verzehrt", f"{gegessen:.0f} kcal")
            m2.metric("Tagesziel", f"{ziel:.0f} kcal")
            m3.metric("Differenz / Rest", f"{int(rest)} kcal", delta=f"{int(rest)} übrig")
            
            # Fortschrittsbalken
            prozent = min(gegessen / ziel, 1.0) if ziel > 0 else 0
            st.progress(prozent)
            st.write(f"**{prozent*100:.1f}%** des Tagesziels erreicht.")
            
            if gegessen > ziel:
                st.warning("⚠️ Das Tagesziel wurde überschritten.")
            
            # Grafik: Balkendiagramm
            chart_data = pd.DataFrame({
                "Kategorie": ["Gegessen", "Ziel"],
                "Kalorien": [gegessen, ziel]
            })
            st.bar_chart(data=chart_data, x="Kategorie", y="Kalorien")

            # Tabelle der heutigen Mahlzeiten
            if not df_heute.empty:
                with st.expander("Detaillierte Mahlzeiten von heute"):
                    st.table(df_heute[["Lebensmittel", "Menge_g", "Kcal_Gesamt"]])
            else:
                st.write("Heute wurden noch keine Mahlzeiten eingetragen.")

# --- MODUL 3: PATIENTENVERWALTUNG (BIOMETRIE-UPDATE) ---
elif menu == "3. Patientenverwaltung":
    st.header("👥 Patientenverwaltung & Biometrie")
    df_p = lade_daten_gs("patienten")
    
    t_liste, t_neu, t_edit = st.tabs(["📋 Liste", "➕ Neu anlegen", "✏️ Wiegen & Anpassen"])

    # --- TAB: LISTE ---
    # --- TAB: LISTE ---
    with t_liste:
        if not df_p.empty:
            # Sicherheits-Kopie erstellen
            df_display = df_p.copy()
            
            # 1. Sicherstellen, dass alle benötigten Spalten da sind
            for col in ["Gewicht_aktuell", "Groesse_cm", "Ziel_Kcal"]:
                if col not in df_display.columns:
                    df_display[col] = 0
            
            # 2. Daten in Zahlen umwandeln (Fehler werden zu NaN/leer, dann zu 0)
            df_display["Gewicht_aktuell"] = pd.to_numeric(df_display["Gewicht_aktuell"], errors='coerce').fillna(0)
            df_display["Groesse_cm"] = pd.to_numeric(df_display["Groesse_cm"], errors='coerce').fillna(0)
            
            # 3. BMI berechnen (nur wenn Größe > 0)
            def berechne_bmi(row):
                w = row["Gewicht_aktuell"]
                h = row["Groesse_cm"]
                if h > 0 and w > 0:
                    return round(w / ((h / 100) ** 2), 1)
                return 0

            df_display["BMI"] = df_display.apply(berechne_bmi, axis=1)
            
            # Anzeige der Tabelle
            st.dataframe(df_display, use_container_width=True, hide_index=True)
        else:
            st.info("Noch keine Patienten vorhanden.")
    # --- TAB: NEU ANLEGEN ---
    with t_neu:
        with st.form("p_neu_full"):
            c1, c2 = st.columns(2)
            with c1:
                n = st.text_input("Name")
                g = st.selectbox("Geschlecht", ["weiblich", "männlich"])
                geb = st.date_input("Geburtsdatum", value=datetime(2010, 1, 1))
            with c2:
                w = st.number_input("Aktuelles Gewicht (kg)", value=50.0, step=0.1)
                h = st.number_input("Größe (cm)", value=160)
                perz = st.selectbox("Ziel-Perzentile", ["P3", "P10", "P25", "P50", "P75", "P90"])
            
            z = st.number_input("Kalorienziel (kcal)", value=2000)
            
            if st.form_submit_button("Patient inkl. Biometrie anlegen"):
                heute = datetime.now().strftime("%Y-%m-%d")
                new_data = pd.DataFrame([[n, z, g, str(geb), h, perz, w, heute]], 
                                        columns=["Name", "Ziel_Kcal", "Geschlecht", "Geburtsdatum", "Groesse_cm", "Ziel_Perzentile", "Gewicht_aktuell", "Wiegedatum"])
                df_p = pd.concat([df_p, new_data], ignore_index=True)
                speichere_df_gs(df_p, "patienten")
                st.success(f"{n} erfolgreich angelegt!")
                st.rerun()

    # --- TAB: WIEGEN & ANPASSEN ---
    with t_edit:
        if not df_p.empty:
            edit_n = st.selectbox("Patient wählen:", df_p["Name"])
            idx = df_p[df_p["Name"] == edit_n].index[0]
            
            st.subheader(f"Daten für {edit_n} aktualisieren")
            col1, col2 = st.columns(2)
            with col1:
                new_w = st.number_input("Neues Gewicht (kg)", value=float(df_p.at[idx, "Gewicht_aktuell"]) if "Gewicht_aktuell" in df_p.columns else 50.0)
                new_h = st.number_input("Größe (cm)", value=int(df_p.at[idx, "Groesse_cm"]))
            with col2:
                new_z = st.number_input("Kalorienziel (kcal)", value=int(df_p.at[idx, "Ziel_Kcal"]))
                new_perz = st.selectbox("Ziel-Perzentile", ["P3", "P10", "P25", "P50", "P75", "P90"], index=2)

            if st.button("Wiegedaten & Ziel speichern"):
                df_p.at[idx, "Gewicht_aktuell"] = new_w
                df_p.at[idx, "Groesse_cm"] = new_h
                df_p.at[idx, "Ziel_Kcal"] = new_z
                df_p.at[idx, "Ziel_Perzentile"] = new_perz
                df_p.at[idx, "Wiegedatum"] = datetime.now().strftime("%Y-%m-%d")
                speichere_df_gs(df_p, "patienten")
                st.success("Biometrie aktualisiert!")
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





import openfoodfacts
print("Installation erfolgreich!")
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
            creds_info = st.secrets["gcp_service_account"]
            if isinstance(creds_info, str): creds_info = json.loads(creds_info)
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
        else:
            creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Verbindung fehlgeschlagen: {e}")
        return None

@st.cache_data(ttl=600)
def lade_daten_gs_cached(sheet_name):
    client = get_gsheet_client()
    if client:
        try:
            sheet = client.open("Kcal_Datenbank").worksheet(sheet_name)
            data = sheet.get_all_records()
            df = pd.DataFrame(data)
            # Spaltennamen bereinigen (Leerzeichen weg)
            df.columns = df.columns.str.strip()
            return df
        except: return pd.DataFrame()
    return pd.DataFrame()

def lade_daten_gs(sheet_name):
    return lade_daten_gs_cached(sheet_name)

def speichere_zeile_gs(liste_werte, sheet_name):
    try:
        client = get_gsheet_client()
        client.open("Kcal_Datenbank").worksheet(sheet_name).append_row(liste_werte)
        st.cache_data.clear() 
    except: st.error("Fehler beim Speichern.")

def speichere_df_gs(df, sheet_name):
    try:
        client = get_gsheet_client()
        sheet = client.open("Kcal_Datenbank").worksheet(sheet_name)
        sheet.clear()
        df_clean = df.fillna("")
        sheet.update([df_clean.columns.values.tolist()] + df_clean.values.tolist())
        st.cache_data.clear() 
    except Exception as e: 
        st.error(f"Fehler beim Update: {e}")

# --- 2. LAYOUT & NAVIGATION ---
st.set_page_config(page_title="Kcal Tracker Pro", layout="wide", page_icon="📈")
st.sidebar.title("🍎 Navigation")
menu = st.sidebar.radio("Menü wählen:", ["1. Mahlzeit erfassen", "2. Patienten-Dashboard", "3. Patientenverwaltung", "4. Datenbank (Editierbar)"])

# --- MODUL 1: MAHLZEIT ERFASSEN ---
if menu == "1. Mahlzeit erfassen":
    st.header("⚖️ Mahlzeit ins Logbuch eintragen")
    df_db = lade_daten_gs("lebensmittel")
    df_p = lade_daten_gs("patienten")
    
    if not df_p.empty and not df_db.empty:
        c1, c2 = st.columns(2)
        with c1:
            p_wahl = st.selectbox("1. Patient wählen:", df_p["Name"])
            m_zeit = st.selectbox("2. Mahlzeit wählen:", MAHLZEITEN_LISTE)
            st.write("---")
            auswahl_typ = st.radio("3. Kategorie filter:", ["Intern", "Extern", "Alle"], horizontal=True)
            df_gefiltert = df_db if auswahl_typ == "Alle" else df_db[df_db['Typ'] == auswahl_typ]
            lebensmittel_wahl = st.selectbox("4. Lebensmittel wählen:", ["Bitte wählen..."] + list(df_gefiltert['Name'].unique()))

        if lebensmittel_wahl != "Bitte wählen...":
            item = df_db[df_db['Name'] == lebensmittel_wahl].iloc[0]
            k100 = pd.to_numeric(item.get('kcal_100g', 0), errors='coerce') or 0
            stk_w = pd.to_numeric(item.get('stueck_gewicht', 0), errors='coerce') or 0
            # Flexible Suche nach der Kcal-Spalte
            k_ref = 0
            for col in ["kcal_pro_Einheit", "Kcal_pro_Einheit", "kcal_pro_einheit"]:
                if col in item:
                    k_ref = pd.to_numeric(item[col], errors='coerce') or 0
                    break
            
            std_menge = item.get('Standard_Menge', '1 Stück')

            with c2:
                st.info(f"📋 **Referenz:** {std_menge} ≈ {k_ref} kcal")
                menge = st.number_input(f"Anzahl / Menge ({std_menge}):", min_value=0.0, step=0.5, value=1.0)
                basis = st.radio("Berechnungsgrundlage:", ["Stück / Einheit", "Gramm"])
                gewicht = menge * stk_w if basis == "Stück / Einheit" else menge
                kcal_total = (k100 / 100) * gewicht
                st.metric("Berechnetes Ergebnis", f"{kcal_total:.1f} kcal")
                
                if st.button("💾 In Logbuch speichern"):
                    heute = datetime.now().strftime("%Y-%m-%d")
                    speichere_zeile_gs([heute, p_wahl, m_zeit, lebensmittel_wahl, round(gewicht,1), round(kcal_total,1)], "verzehr")
                    st.success(f"Eintrag gespeichert!")

# --- MODUL 2: DASHBOARD ---
elif menu == "2. Patienten-Dashboard":
    st.header("📊 Therapie-Dashboard & Verlauf")
    df_v = lade_daten_gs("verzehr")
    df_p = lade_daten_gs("patienten")
    df_g = lade_daten_gs("gewichtsverlauf")
    
    if not df_p.empty:
        p_wahl = st.selectbox("Patient wählen:", df_p["Name"])
        p_data = df_p[df_p["Name"] == p_wahl].iloc[0]
        
        t_kcal, t_trend = st.tabs(["🍎 Kalorien heute", "📈 Gewichtsverlauf"])
        
        with t_kcal:
            heute = datetime.now().strftime("%Y-%m-%d")
            if not df_v.empty:
                df_v["Datum"] = df_v["Datum"].astype(str)
                df_heute = df_v[(df_v["Datum"] == heute) & (df_v["Patient"] == p_wahl)]
                gegessen = df_heute["Kcal_Gesamt"].sum() if not df_heute.empty else 0
                ziel = pd.to_numeric(p_data["Ziel_Kcal"], errors='coerce') or 2000
                
                c1, c2 = st.columns(2)
                c1.metric("Heute verzehrt", f"{gegessen:.0f} kcal")
                c2.metric("Tagesziel", f"{ziel:.0f} kcal")
                st.progress(min(gegessen/ziel, 1.0) if ziel > 0 else 0)
                
                for m in MAHLZEITEN_LISTE:
                    m_data = df_heute[df_heute["Mahlzeit"] == m]
                    m_sum = m_data["Kcal_Gesamt"].sum()
                    with st.expander(f"{m} — {m_sum:.0f} kcal"):
                        if not m_data.empty:
                            for idx, row in m_data.iterrows():
                                cl, cr = st.columns([4, 1])
                                cl.write(f"**{row['Lebensmittel']}**: {row['Kcal_Gesamt']:.1f} kcal")
                                if cr.button("🗑️", key=f"del_{idx}"):
                                    full_v = lade_daten_gs("verzehr")
                                    full_v = full_v.drop(idx)
                                    speichere_df_gs(full_v, "verzehr")
                                    st.rerun()

        with t_trend:
            if not df_g.empty:
                df_hist = df_g[df_g["Patient"] == p_wahl].copy()
                if not df_hist.empty:
                    df_hist["Datum"] = pd.to_datetime(df_hist["Datum"])
                    df_hist = df_hist.sort_values("Datum")
                    st.line_chart(df_hist.set_index("Datum")["Gewicht"])
            
            with st.expander("➕ Neues Gewicht loggen"):
                neu_date = st.date_input("Wiegedatum:", value=datetime.now())
                neu_w = st.number_input("Gewicht (kg):", step=0.1)
                if st.button("Gewicht speichern"):
                    speichere_zeile_gs([str(neu_date), p_wahl, neu_w], "gewichtsverlauf")
                    st.rerun()

# --- MODUL 3: PATIENTENVERWALTUNG ---
elif menu == "3. Patientenverwaltung":
    st.header("👥 Patientenverwaltung")
    df_p = lade_daten_gs("patienten")
    t_list, t_new, t_copy, t_del = st.tabs(["📋 Liste", "➕ Neu", "👯 Kopieren", "🗑️ Löschen"])
    
    with t_list:
        if not df_p.empty: st.dataframe(df_p, use_container_width=True, hide_index=True)
    
    with t_new:
        with st.form("p_new"):
            n = st.text_input("Name")
            z = st.number_input("Ziel Kcal", value=2000)
            if st.form_submit_button("Speichern"):
                heute = datetime.now().strftime("%Y-%m-%d")
                new_p = pd.DataFrame([[n, z, "", "", 165, "P25", 0, heute]], columns=df_p.columns)
                df_p = pd.concat([df_p, new_p], ignore_index=True)
                speichere_df_gs(df_p, "patienten")
                st.rerun()

    with t_del:
        if not df_p.empty:
            p_kill = st.selectbox("Patient löschen:", df_p["Name"])
            if st.button(f"Unwiderruflich löschen: {p_kill}", type="primary"):
                df_p = df_p[df_p["Name"] != p_kill]
                speichere_df_gs(df_p, "patienten")
                st.rerun()

# --- MODUL 4: DATENBANK (EDITIERBAR & IMPORT) ---
elif menu == "4. Datenbank (Editierbar)":
    st.header("📊 Lebensmittel-Datenbank & Import")
    
    tab_editor, tab_import = st.tabs(["✏️ Datenbank-Editor", "🌍 Externer Import (OFF)"])
    
    with tab_editor:
        df_db = lade_daten_gs("lebensmittel")
        if not df_db.empty:
            # Datentyp-Fix wie zuvor
            df_db["kcal_100g"] = pd.to_numeric(df_db["kcal_100g"], errors='coerce').fillna(0)
            df_db["stueck_gewicht"] = pd.to_numeric(df_db["stueck_gewicht"], errors='coerce').fillna(0)
            
            st.info("💡 Änderungen hier werden erst durch 'Speichern' permanent.")
            edited_df = st.data_editor(df_db, num_rows="dynamic", use_container_width=True, hide_index=True, key="db_edit_main")
            
            if st.button("💾 Alle Änderungen speichern"):
                speichere_df_gs(edited_df, "lebensmittel")
                st.success("Datenbank aktualisiert!")
                st.rerun()

    with tab_import:
        st.subheader("Produkte weltweit suchen")
        suche_begriff = st.text_input("Markenprodukt suchen (z.B. 'Snickers' oder 'Dr. Oetker'):")
        
        if suche_begriff:
            with st.spinner("Suche in Open Food Facts..."):
                off_api = openfoodfacts.API(user_agent="KcalTrackerKlinik/1.0")
                results = off_api.product.text_search(suche_begriff)
                
                if results and 'products' in results:
                    products = results['products'][:10] # Top 10 Ergebnisse
                    
                    for p in products:
                        p_name = p.get('product_name', 'Unbekannt')
                        p_brand = p.get('brands', 'Keine Marke')
                        nutriments = p.get('nutriments', {})
                        p_kcal = nutriments.get('energy-kcal_100g')
                        
                        if p_kcal is not None:
                            col_a, col_b = st.columns([3, 1])
                            col_a.write(f"**{p_name}** ({p_brand}) - {p_kcal} kcal/100g")
                            
                            # Import-Button für dieses spezifische Produkt
                            if col_b.button("📥 Importieren", key=f"import_{p.get('_id')}"):
                                # In eigene DB übernehmen
                                neue_zeile = [p_name, p_kcal, 0, 0, "1 Stück", "Extern"]
                                speichere_zeile_gs(neue_zeile, "lebensmittel")
                                st.success(f"'{p_name}' wurde deiner Liste hinzugefügt!")
                                st.rerun()
                        else:
                            st.write(f"⚪ {p_name} - (Keine Kcal-Daten verfügbar)")
                else:
                    st.error("Keine Produkte gefunden.")

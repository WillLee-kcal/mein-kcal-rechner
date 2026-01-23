import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
from datetime import datetime
import openfoodfacts

# --- 1. KONSTANTEN & SETUP ---
MAHLZEITEN_LISTE = ["Frühstück", "Zwischenmahlzeit 1", "Mittagessen", "Zwischenmahlzeit 2", "Abendessen", "Zwischenmahlzeit 3"]

# --- 2. VISUELLES STYLING (Medical Blue) ---
st.set_page_config(page_title="NutriCheck IA", layout="wide", page_icon="🩺")

st.markdown("""
    <style>
    [data-testid="stSidebar"] { background-color: #004a99; }
    [data-testid="stSidebar"] * { color: white !important; }
    .stButton>button { border-radius: 12px; background-color: #007bff; color: white; border: none; font-weight: bold; width: 100%; transition: 0.3s; }
    .stButton>button:hover { background-color: #0056b3; transform: scale(1.02); }
    .stMetric { background-color: white; padding: 15px; border-radius: 12px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
    div[data-testid="stExpander"] { border: 1px solid #e0e0e0; border-radius: 10px; margin-bottom: 5px; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SOUND ENGINE ---
def trigger_audio(sound_type="success"):
    urls = {
        "success": "https://assets.mixkit.co/active_storage/sfx/2568/2568-preview.mp3",
        "error": "https://assets.mixkit.co/active_storage/sfx/2571/2571-preview.mp3",
        "save": "https://assets.mixkit.co/active_storage/sfx/2567/2567-preview.mp3"
    }
    st.components.v1.html(f'<audio autoplay><source src="{urls[sound_type]}" type="audio/mp3"></audio>', height=0)

# --- 4. GOOGLE SHEETS VERBINDUNG & CACHING ---
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
    except: return None

@st.cache_data(ttl=600)
def lade_daten_gs_cached(sheet_name):
    client = get_gsheet_client()
    if client:
        try:
            sheet = client.open("Kcal_Datenbank").worksheet(sheet_name)
            data = sheet.get_all_records()
            df = pd.DataFrame(data)
            df.columns = df.columns.str.strip()
            return df
        except: return pd.DataFrame()
    return pd.DataFrame()

def lade_daten_gs(sheet_name): return lade_daten_gs_cached(sheet_name)

def speichere_zeile_gs(liste_werte, sheet_name):
    try:
        client = get_gsheet_client()
        client.open("Kcal_Datenbank").worksheet(sheet_name).append_row(liste_werte)
        st.cache_data.clear() 
        trigger_audio("success")
        st.toast("Eintrag erfolgreich gespeichert!", icon="✅")
    except: trigger_audio("error")

def speichere_df_gs(df, sheet_name):
    try:
        client = get_gsheet_client()
        sheet = client.open("Kcal_Datenbank").worksheet(sheet_name)
        sheet.clear()
        df_clean = df.fillna("")
        sheet.update([df_clean.columns.values.tolist()] + df_clean.values.tolist())
        st.cache_data.clear() 
        trigger_audio("save")
        st.toast("Datenbank synchronisiert!", icon="🔄")
    except: trigger_audio("error")

# --- 5. NAVIGATION ---
st.sidebar.markdown("# 🩺 NutriCheck IA")
st.sidebar.markdown("---")
menu = st.sidebar.radio("Navigation:", ["1. Mahlzeit erfassen", "2. Patienten-Dashboard", "3. Patientenverwaltung", "4. Datenbank-Zentrale"])

# --- MODUL 1: MAHLZEIT ERFASSEN ---
if menu == "1. Mahlzeit erfassen":
    st.header("⚖️ Ernährungs-Protokoll")
    df_db = lade_daten_gs("lebensmittel")
    df_p = lade_daten_gs("patienten")
    if not df_p.empty and not df_db.empty:
        c1, c2 = st.columns(2)
        with c1:
            p_wahl = st.selectbox("Patient wählen:", df_p["Name"])
            m_zeit = st.selectbox("Mahlzeit:", MAHLZEITEN_LISTE)
            st.divider()
            typ_filter = st.radio("Kategorie:", ["Alle", "Intern", "Extern"], horizontal=True)
            df_f = df_db if typ_filter == "Alle" else df_db[df_db['Typ'] == typ_filter]
            lebensmittel = st.selectbox("Lebensmittel:", ["Bitte wählen..."] + list(df_f['Name'].unique()))
        if lebensmittel != "Bitte wählen...":
            item = df_db[df_db['Name'] == lebensmittel].iloc[0]
            k100 = pd.to_numeric(item.get('kcal_100g', 0), errors='coerce') or 0
            stk_w = pd.to_numeric(item.get('stueck_gewicht', 0), errors='coerce') or 0
            with c2:
                st.info(f"Ref: {item.get('Standard_Menge','1 Stück')} ≈ {item.get('kcal_pro_Einheit', 0)} kcal")
                menge = st.number_input("Menge eingeben:", min_value=0.0, step=0.5, value=1.0)
                basis = st.radio("Basis:", ["Stück / Einheit", "Gramm"], horizontal=True)
                gew = menge * stk_w if basis == "Stück / Einheit" else menge
                kcal = (k100 / 100) * gew
                st.metric("Ergebnis", f"{kcal:.1f} kcal")
                if st.button("💾 In Logbuch speichern"):
                    speichere_zeile_gs([str(datetime.now().date()), p_wahl, m_zeit, lebensmittel, round(gew,1), round(kcal,1)], "verzehr")
                    st.balloons()

# --- MODUL 2: DASHBOARD ---
elif menu == "2. Patienten-Dashboard":
    st.header("📊 Therapie-Dashboard")
    df_v, df_p, df_g = lade_daten_gs("verzehr"), lade_daten_gs("patienten"), lade_daten_gs("gewichtsverlauf")
    if not df_p.empty:
        p_wahl = st.selectbox("Akte wählen:", df_p["Name"])
        p_data = df_p[df_p["Name"] == p_wahl].iloc[0]
        t1, t2 = st.tabs(["🍎 Heute", "📈 Verlauf"])
        with t1:
            heute = str(datetime.now().date())
            df_h = df_v[(df_v["Datum"].astype(str) == heute) & (df_v["Patient"] == p_wahl)] if not df_v.empty else pd.DataFrame()
            gegessen = df_h["Kcal_Gesamt"].sum() if not df_h.empty else 0
            ziel = pd.to_numeric(p_data["Ziel_Kcal"], errors='coerce') or 2000
            c1, c2 = st.columns(2)
            c1.metric("Heute", f"{gegessen:.0f} kcal")
            c2.metric("Ziel", f"{ziel:.0f} kcal")
            st.progress(min(gegessen/ziel, 1.0) if ziel > 0 else 0)
            for m in MAHLZEITEN_LISTE:
                m_data = df_h[df_h["Mahlzeit"] == m] if not df_h.empty else pd.DataFrame()
                with st.expander(f"{m} — {m_data['Kcal_Gesamt'].sum() if not m_data.empty else 0:.0f} kcal"):
                    if not m_data.empty:
                        for idx, row in m_data.iterrows():
                            cl, cr = st.columns([4, 1])
                            cl.write(f"{row['Lebensmittel']}: {row['Kcal_Gesamt']} kcal")
                            if cr.button("🗑️", key=f"del_{idx}"):
                                speichere_df_gs(df_v.drop(idx), "verzehr"); st.rerun()
        with t2:
            if not df_g.empty:
                df_hist = df_g[df_g["Patient"] == p_wahl].copy()
                if not df_hist.empty:
                    df_hist["Datum"] = pd.to_datetime(df_hist["Datum"])
                    st.line_chart(df_hist.sort_values("Datum").set_index("Datum")["Gewicht"])
            neu_w = st.number_input("Gewicht (kg):", step=0.1)
            if st.button("Gewicht speichern"):
                speichere_zeile_gs([str(datetime.now().date()), p_wahl, neu_w], "gewichtsverlauf"); st.rerun()

# --- MODUL 3: PATIENTENVERWALTUNG ---
elif menu == "3. Patientenverwaltung":
    st.header("👥 Patientenverwaltung")
    df_p = lade_daten_gs("patienten")
    t1, t2, t3, t4 = st.tabs(["📋 Liste", "➕ Neu", "👯 Kopieren", "🗑️ Löschen"])
    with t1: st.dataframe(df_p, use_container_width=True, hide_index=True)
    with t2:
        with st.form("new_p"):
            name = st.text_input("Name"); ziel = st.number_input("Ziel Kcal", value=2000)
            if st.form_submit_button("Speichern"):
                speichere_zeile_gs([name, ziel, "", "", 165, "P25", 0, str(datetime.now().date())], "patienten"); st.rerun()
    with t3:
        if not df_p.empty:
            vor = st.selectbox("Vorlage:", df_p["Name"]); new_n = st.text_input("Neuer Name")
            if st.button("Kopie erstellen"):
                v_d = df_p[df_p["Name"] == vor].iloc[0]
                speichere_zeile_gs([new_n, v_d['Ziel_Kcal'], v_d['Geschlecht'], v_d['Geburtsdatum'], v_d['Groesse_cm'], v_d['Ziel_Perzentile'], 0, str(datetime.now().date())], "patienten"); st.rerun()
    with t4:
        if not df_p.empty:
            kill = st.selectbox("Patient löschen:", df_p["Name"])
            if st.button("Unwiderruflich löschen", type="primary"):
                speichere_df_gs(df_p[df_p["Name"] != kill], "patienten"); st.rerun()

# --- MODUL 4: DATENBANK ---
elif menu == "4. Datenbank-Zentrale":
    st.header("🗄️ Stammdaten")
    t1, t2, t3 = st.tabs(["✏️ Editor", "🌍 Import", "🗑️ Löschen"])
    df_db = lade_daten_gs("lebensmittel")
    with t1:
        if not df_db.empty:
            for c in ["kcal_100g", "stueck_gewicht", "kcal_pro_Einheit"]:
                if c in df_db.columns: df_db[c] = pd.to_numeric(df_db[c], errors='coerce').fillna(0)
            ed = st.data_editor(df_db, num_rows="dynamic", use_container_width=True, hide_index=True)
            if st.button("💾 Update speichern"): speichere_df_gs(ed, "lebensmittel")
    with t2:
        suche = st.text_input("Produkt suchen (OFF):")
        if suche:
            res = openfoodfacts.API(user_agent="Kcal/1.0").product.text_search(suche)
            if res and 'products' in res:
                for p in res['products'][:5]:
                    p_n = p.get('product_name', 'Unbekannt'); p_k = p.get('nutriments', {}).get('energy-kcal_100g')
                    if p_k:
                        ca, cb = st.columns([3, 1])
                        ca.write(f"**{p_n}** ({p_k} kcal/100g)")
                        if cb.button("📥 Import", key=p.get('_id')):
                            speichere_zeile_gs([p_n, p_k, 0, "1 Stück", 0, "Extern"], "lebensmittel"); st.rerun()
    with t3:
        if not df_db.empty:
            kill = st.selectbox("Lebensmittel entfernen:", ["Wählen..."] + sorted(df_db["Name"].unique()))
            if kill != "Wählen..." and st.button("🗑️ Löschen"):
                speichere_df_gs(df_db[df_db["Name"] != kill], "lebensmittel"); st.rerun()


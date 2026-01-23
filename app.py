import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
from datetime import datetime
import openfoodfacts
import requests
from openai import OpenAI

# --- 1. BRANDING & GLOBALE KONFIGURATION ---
APP_NAME = "NutriCheck AI"
MAHLZEITEN_LISTE = ["Frühstück", "Zwischenmahlzeit 1", "Mittagessen", "Zwischenmahlzeit 2", "Abendessen", "Zwischenmahlzeit 3"]

st.set_page_config(page_title=APP_NAME, layout="wide", page_icon="🩺")

# Clinical Medical Blue Styling
st.markdown(f"""
    <style>
    [data-testid="stSidebar"] {{ background-color: #004a99; }}
    [data-testid="stSidebar"] * {{ color: white !important; }}
    .stButton>button {{ border-radius: 12px; background-color: #007bff; color: white; border: none; font-weight: bold; width: 100%; transition: 0.2s; }}
    .stButton>button:hover {{ background-color: #0056b3; transform: scale(1.01); }}
    .stMetric {{ background-color: white; padding: 15px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }}
    .ai-box {{ background-color: #f0f7ff; padding: 20px; border-radius: 15px; border: 1px solid #007bff; margin-bottom: 20px; }}
    </style>
    """, unsafe_allow_html=True)

# --- 2. HILFSFUNKTIONEN (SOUND & DB) ---
def trigger_feedback(type="success"):
    sounds = {"success": "https://assets.mixkit.co/active_storage/sfx/2568/2568-preview.mp3", 
              "error": "https://assets.mixkit.co/active_storage/sfx/2571/2571-preview.mp3"}
    st.components.v1.html(f'<audio autoplay><source src="{sounds[type]}" type="audio/mp3"></audio>', height=0)

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
    if not client: return pd.DataFrame()
    try:
        sheet = client.open("Kcal_Datenbank").worksheet(sheet_name)
        df = pd.DataFrame(sheet.get_all_records())
        df.columns = df.columns.str.strip()
        return df
    except: return pd.DataFrame()

def lade_daten_gs(sheet_name): return lade_daten_gs_cached(sheet_name)

def speichere_zeile_gs(liste_werte, sheet_name):
    try:
        client = get_gsheet_client()
        client.open("Kcal_Datenbank").worksheet(sheet_name).append_row(liste_werte)
        st.cache_data.clear()
        trigger_feedback("success")
        st.toast("Eintrag gespeichert!", icon="✅")
    except: trigger_feedback("error")

def speichere_df_gs(df, sheet_name):
    try:
        client = get_gsheet_client()
        sheet = client.open("Kcal_Datenbank").worksheet(sheet_name)
        sheet.clear()
        df_clean = df.fillna("")
        sheet.update([df_clean.columns.values.tolist()] + df_clean.values.tolist())
        st.cache_data.clear()
        trigger_feedback("success")
        st.toast("Datenbank synchronisiert!", icon="🔄")
    except: trigger_feedback("error")

# --- 3. AI LOGIK ---
def ai_analyse_ernaehrung(user_text, datenbank_liste):
    if not st.secrets.get("OPENAI_API_KEY"):
        st.error("OpenAI API Key fehlt in den Secrets!")
        return None
    
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    db_namen = ", ".join(datenbank_liste)
    
    prompt = f"""
    Analysiere den Satz und extrahiere Lebensmittel/Mengen. Gleiche sie mit dieser Liste ab: {db_namen}.
    Antworte NUR mit einem JSON-Objekt im Format: {{"items": [{{"item": "Name", "menge": 1.0, "basis": "Stück"}}]}}
    Satz: "{user_text}"
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={ "type": "json_object" }
        )
        return json.loads(response.choices[0].message.content).get("items", [])
    except Exception as e:
        st.error(f"AI-Fehler: {e}")
        return None

# --- 4. NAVIGATION ---
st.sidebar.markdown(f"# 🩺 {APP_NAME}")
menu = st.sidebar.radio("Navigation:", ["1. Mahlzeit erfassen", "2. Patienten-Dashboard", "3. Patientenverwaltung", "4. Datenbank-Zentrale"])

# --- MODUL 1: MAHLZEIT ERFASSEN ---
if menu == "1. Mahlzeit erfassen":
    st.header("⚖️ Ernährungs-Protokoll")
    df_db, df_p = lade_daten_gs("lebensmittel"), lade_daten_gs("patienten")
    
    t_man, t_ai = st.tabs(["📝 Manuell", "🤖 AI Smart-Input"])
    
    with t_man:
        if not df_p.empty and not df_db.empty:
            c1, c2 = st.columns(2)
            with c1:
                p_wahl = st.selectbox("Patient:", df_p["Name"], key="p_man")
                m_zeit = st.selectbox("Mahlzeit:", MAHLZEITEN_LISTE, key="m_man")
                lebensmittel = st.selectbox("Lebensmittel:", ["Bitte wählen..."] + sorted(df_db['Name'].unique()))
            if lebensmittel != "Bitte wählen...":
                item = df_db[df_db['Name'] == lebensmittel].iloc[0]
                with c2:
                    st.info(f"Ref: {item.get('Standard_Menge','1 Stk')} ≈ {item.get('kcal_pro_Einheit', 0)} kcal")
                    menge = st.number_input("Menge:", min_value=0.1, value=1.0)
                    basis = st.radio("Basis:", ["Stück / Einheit", "Gramm"], horizontal=True)
                    stk_w = pd.to_numeric(item.get('stueck_gewicht', 0)) or 1
                    gew = menge * stk_w if basis == "Stück / Einheit" else menge
                    kcal = (pd.to_numeric(item.get('kcal_100g', 0)) / 100) * gew
                    st.metric("Energie", f"{kcal:.1f} kcal")
                    if st.button("💾 Speichern"):
                        speichere_zeile_gs([str(datetime.now().date()), p_wahl, m_zeit, lebensmittel, round(gew,1), round(kcal,1)], "verzehr")

    with t_ai:
        st.markdown('<div class="ai-box">', unsafe_allow_html=True)
        st.subheader("🤖 AI Smart-Input")
        ai_input = st.text_area("Was wurde verzehrt?", placeholder="z.B. Zwei Snickers und 200ml Apfelsaft", key="ai_text_input")
        
        c1, c2 = st.columns(2)
        p_wahl_ai = c1.selectbox("Patient:", df_p["Name"], key="p_ai")
        m_zeit_ai = c2.selectbox("Mahlzeit:", MAHLZEITEN_LISTE, key="m_ai")
        
        # 1. ANALYSE-BUTTON
        if st.button("🚀 AI Analyse"):
            if ai_input:
                with st.spinner("AI gleicht Daten mit Datenbank ab..."):
                    # Wir speichern das Ergebnis im "Gedächtnis" (Session State)
                    st.session_state.ai_ergebnisse = ai_analyse_ernaehrung(ai_input, df_db["Name"].tolist())
            else:
                st.warning("Bitte gib erst einen Text ein.")

        # 2. ANZEIGE & SPEICHERN (Wird nur gezeigt, wenn Ergebnisse im Gedächtnis sind)
        if "ai_ergebnisse" in st.session_state and st.session_state.ai_ergebnisse:
            st.write("---")
            st.write("### Gefundene Lebensmittel:")
            
            for idx, res in enumerate(st.session_state.ai_ergebnisse):
                item_n = res.get("item")
                match = df_db[df_db["Name"] == item_n]
                
                if not match.empty:
                    row = match.iloc[0]
                    k100 = pd.to_numeric(row['kcal_100g'], errors='coerce') or 0
                    stk_w = pd.to_numeric(row['stueck_gewicht'], errors='coerce') or 1
                    
                    # Berechnung
                    m_wert = res.get("menge", 1)
                    basis_txt = res.get("basis", "Stück")
                    gew = m_wert * (stk_w if basis_txt == "Stück" else 1)
                    kcal = (k100 / 100) * gew
                    
                    col_a, col_b = st.columns([3, 1])
                    col_a.write(f"✅ **{item_n}**: {m_wert} {basis_txt} ({round(kcal)} kcal)")
                    
                    # Hier ist der wichtige Fix: Der Key muss absolut eindeutig sein (mit Index)
                    if col_b.button("Speichern", key=f"btn_save_{idx}_{item_n}"):
                        speichere_zeile_gs([str(datetime.now().date()), p_wahl_ai, m_zeit_ai, item_n, round(gew,1), round(kcal,1)], "verzehr")
                        # Optional: Ergebnis nach Speichern aus dem Gedächtnis löschen
                        # st.session_state.ai_ergebnisse.pop(idx)
                        # st.rerun()
                else:
                    st.warning(f"⚠️ '{item_n}' ist nicht in deiner Datenbank.")
        st.markdown('</div>', unsafe_allow_html=True)

# --- MODUL 2: DASHBOARD ---
elif menu == "2. Patienten-Dashboard":
    st.header("📊 Therapie-Dashboard")
    df_v, df_p, df_g = lade_daten_gs("verzehr"), lade_daten_gs("patienten"), lade_daten_gs("gewichtsverlauf")
    if not df_p.empty:
        p_wahl = st.selectbox("Akte:", df_p["Name"])
        p_data = df_p[df_p["Name"] == p_wahl].iloc[0]
        t1, t2 = st.tabs(["⚡ Kalorien", "📉 Verlauf"])
        with t1:
            heute = str(datetime.now().date())
            df_h = df_v[(df_v["Datum"].astype(str) == heute) & (df_v["Patient"] == p_wahl)] if not df_v.empty else pd.DataFrame()
            gegessen = df_h["Kcal_Gesamt"].sum() if not df_h.empty else 0
            ziel = pd.to_numeric(p_data["Ziel_Kcal"]) or 2000
            c1, c2 = st.columns(2)
            c1.metric("Heute", f"{gegessen:.0f} kcal")
            c2.metric("Ziel", f"{ziel:.0f} kcal")
            st.progress(min(gegessen/ziel, 1.0) if ziel > 0 else 0)
            for m in MAHLZEITEN_LISTE:
                m_data = df_h[df_h["Mahlzeit"] == m] if not df_h.empty else pd.DataFrame()
                with st.expander(f"{m} — {m_data['Kcal_Gesamt'].sum() if not m_data.empty else 0:.0f} kcal"):
                    if not m_data.empty:
                        for idx, row in m_data.iterrows():
                            cla, cra = st.columns([4, 1])
                            cla.write(f"{row['Lebensmittel']}: {row['Kcal_Gesamt']} kcal")
                            if cra.button("🗑️", key=f"del_{idx}"):
                                speichere_df_gs(df_v.drop(idx), "verzehr"); st.rerun()
        with t2:
            if not df_g.empty:
                df_hist = df_g[df_g["Patient"] == p_wahl].copy()
                if not df_hist.empty:
                    df_hist["Datum"] = pd.to_datetime(df_hist["Datum"])
                    st.line_chart(df_hist.sort_values("Datum").set_index("Datum")["Gewicht"])

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
            vor = st.selectbox("Vorlage:", df_p["Name"]); n_name = st.text_input("Neuer Name")
            if st.button("Kopie erstellen"):
                v_d = df_p[df_p["Name"] == vor].iloc[0]
                speichere_zeile_gs([n_name, v_d['Ziel_Kcal'], v_d['Geschlecht'], v_d['Geburtsdatum'], v_d['Groesse_cm'], v_d['Ziel_Perzentile'], 0, str(datetime.now().date())], "patienten"); st.rerun()
    with t4:
        if not df_p.empty:
            kill = st.selectbox("Patient löschen:", df_p["Name"])
            if st.button("Unwiderruflich löschen", type="primary"):
                speichere_df_gs(df_p[df_p["Name"] != kill], "patienten"); st.rerun()

# --- MODUL 4: DATENBANK ---
elif menu == "4. Datenbank-Zentrale":
    st.header("🗄️ Stammdaten")
    t1, t2, t3 = st.tabs(["✏️ Editor", "🌍 OFF-Import", "🗑️ Löschen"])
    df_db = lade_daten_gs("lebensmittel")
    with t1:
        if not df_db.empty:
            for c in ["kcal_100g", "stueck_gewicht", "kcal_pro_Einheit"]:
                if c in df_db.columns: df_db[c] = pd.to_numeric(df_db[c], errors='coerce').fillna(0)
            ed = st.data_editor(df_db, num_rows="dynamic", use_container_width=True, hide_index=True)
            if st.button("💾 Datenbank Update"): speichere_df_gs(ed, "lebensmittel")
    with t2:
        suche = st.text_input("Produkt suchen:")
        if suche:
            url = f"https://world.openfoodfacts.org/cgi/search.pl?search_terms={suche}&search_simple=1&action=process&json=1&page_size=5"
            try:
                res = requests.get(url, timeout=15).json()
                for p in res.get('products', []):
                    p_n = p.get('product_name', 'Unbekannt'); p_k = p.get('nutriments', {}).get('energy-kcal_100g')
                    if p_k:
                        ca, cb = st.columns([3, 1])
                        ca.write(f"**{p_n}** ({p_k} kcal/100g)")
                        if cb.button("📥 Import", key=p.get('_id')):
                            speichere_zeile_gs([p_n, p_k, 0, "1 Stück", 0, "Extern"], "lebensmittel"); st.rerun()
            except: st.error("Fehler beim Import-Server.")
    with t3:
        if not df_db.empty:
            kill = st.selectbox("Lebensmittel löschen:", ["Wählen..."] + sorted(df_db["Name"].unique()))
            if kill != "Wählen..." and st.button("🗑️ Löschen", type="primary"):
                speichere_df_gs(df_db[df_db["Name"] != kill], "lebensmittel"); st.rerun()



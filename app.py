import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime, timedelta, time
from sqlalchemy import create_engine, text

st.set_page_config(page_title="IdroSmart PRO 365", layout="wide", page_icon="💧")

GIORNI_IT = {
    "Monday": "Lunedì", "Tuesday": "Martedì", "Wednesday": "Mercoledì",
    "Thursday": "Giovedì", "Friday": "Venerdì", "Saturday": "Sabato", "Sunday": "Domenica"
}

GIORNI_SETTIMANA_LISTA = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]

MAP_GIORNI_ING = {
    0: "Lunedì", 1: "Martedì", 2: "Mercoledì", 3: "Giovedì", 4: "Venerdì", 5: "Sabato", 6: "Domenica"
}

ELENCO_CHIAVONI_REALI = ["Valvola Contrappesi", "Dogaro di Ravarino", "Piave 1", "Piave 2 (Targa)", "Fosso dei Monti", "Villa", "Vaccara", "Parmiggiani", "Rami (Kalos)", "Rangoni"]

# --- INIZIALIZZAZIONE SESSION STATE ---
if "manovre_temporanee_registrazione" not in st.session_state:
    st.session_state.manovre_temporanee_registrazione = []

# --- FUNZIONE DI CONNESSIONE SICURA CON POSTGRESQL (NEON) ---
def get_db_connection():
    db_url = st.secrets["connections"]["postgresql"]["url"]
    return psycopg2.connect(db_url)

def get_sqlalchemy_engine():
    db_url = st.secrets["connections"]["postgresql"]["url"]
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return create_engine(db_url)

# --- FUNZIONE DI CALCOLO GIRI CHIAVONE BASATA SULLA TABELLA UNIFICATA ---
def calcola_giri_chiavone(motori_totali, nome_chiavone):
    try:
        motori_totali = float(motori_totali)
        if pd.isna(motori_totali) or motori_totali <= 0:
            return 0.0, 0.0
    except Exception:
        return 0.0, 0.0
    
    tabella_reale = {
        "0.06": {"giri": 0.25, "portata": 1.0}, "0.12": {"giri": 0.50, "portata": 2.0},
        "0.18": {"giri": 0.75, "portata": 4.0}, "0.26": {"giri": 1.00, "portata": 5.0},
        "0.34": {"giri": 1.25, "portata": 7.0}, "0.42": {"giri": 1.50, "portata": 9.0},
        "0.52": {"giri": 1.75, "portata": 11.0}, "0.62": {"giri": 2.00, "portata": 13.0},
        "0.73": {"giri": 2.25, "portata": 15.0}, "0.85": {"giri": 2.50, "portata": 18.0},
        "1.00": {"giri": 2.75, "portata": 21.0}, "1.18": {"giri": 3.00, "portata": 25.0},
        "1.39": {"giri": 3.25, "portata": 29.0}, "1.65": {"giri": 3.50, "portata": 35.0},
        "2.00": {"giri": 3.75, "portata": 42.0}, "2.31": {"giri": 4.00, "portata": 49.0},
        "2.64": {"giri": 4.25, "portata": 55.0}, "3.00": {"giri": 4.50, "portata": 63.0},
        "3.34": {"giri": 4.75, "portata": 70.0}, "3.69": {"giri": 5.00, "portata": 77.0},
        "4.03": {"giri": 5.25, "row": 85.0, "portata": 85.0}, "4.38": {"giri": 5.50, "portata": 92.0},
        "4.73": {"giri": 5.75, "portata": 99.0}, "5.07": {"giri": 6.00, "portata": 107.0},
        "5.41": {"giri": 6.25, "portata": 114.0}, "5.75": {"giri": 6.50, "portata": 121.0},
        "6.08": {"giri": 6.75, "portata": 128.0}, "6.40": {"giri": 7.00, "portata": 134.0},
        "6.71": {"giri": 7.25, "portata": 141.0}, "7.01": {"giri": 7.50, "portata": 147.0},
        "7.29": {"giri": 7.75, "portata": 153.0}, "7.57": {"giri": 8.00, "portata": 159.0}
    }
    
    chiave_motori = f"{motori_totali:.2f}"
    if chiave_motori in tabella_reale:
        return tabella_reale[chiave_motori]["giri"], tabella_reale[chiave_motori]["portata"]
    
    array_motori = [float(k) for k in tabella_reale.keys()]
    idx_vicino = min(range(len(array_motori)), key=lambda i: abs(array_motori[i] - motori_totali))
    chiave_approssimata = f"{array_motori[idx_vicino]:.2f}"
    
    return tabella_reale[chiave_approssimata]["giri"], tabella_reale[chiave_approssimata]["portata"]

# --- FUNZIONE DI UTILITÀ PER CALCOLARE LE PERDITE DINAMICHE ---
def calcola_motori_con_perdite(motori_nominali):
    if motori_nominali == 0:
        return 0.0
    if motori_nominali + 0.5 <= 6.0:
        return motori_nominali + 0.5
    return motori_nominali + 1.0

# --- FUNZIONE CORRETTA PER TROVARE IL PICCO MASSIMO SOVRAPPOSTO MINUTO PER MINUTO ---
def calcola_picco_massimo_giorno(df_giorno, data_rif):
    if df_giorno.empty:
        return 0.0
    motori_minuto = [0.0] * 1440
    
    if isinstance(data_rif, datetime):
        data_rif = data_rif.date()
        
    for _, turno in df_giorno.iterrows():
        m_std = float(turno['motori_std'])
        dt_ini = pd.to_datetime(turno['data_inizio_dt'])
        dt_fin = pd.to_datetime(turno['data_fine_dt'])
        
        intervals = []
        if dt_ini.date() == dt_fin.date() and dt_fin.time() < dt_ini.time():
            intervals.append((datetime.combine(dt_ini.date(), dt_ini.time()), datetime.combine(dt_ini.date(), time(23, 59)) + timedelta(minutes=1)))
            intervals.append((datetime.combine(dt_ini.date() + timedelta(days=1), time(0, 0)), datetime.combine(dt_ini.date() + timedelta(days=1), dt_fin.time())))
        else:
            intervals.append((dt_ini, dt_fin))
            
        for s_dt, e_dt in intervals:
            if s_dt.date() < data_rif and e_dt.date() > data_rif:
                min_ini, min_fin = 0, 1440
            elif s_dt.date() == data_rif and e_dt.date() == data_rif:
                min_ini = s_dt.hour * 60 + s_dt.minute
                min_fin = e_dt.hour * 60 + e_dt.minute
            elif s_dt.date() == data_rif and e_dt.date() > data_rif:
                min_ini = s_dt.hour * 60 + s_dt.minute
                min_fin = 1440
            elif s_dt.date() < data_rif and e_dt.date() == data_rif:
                min_ini = 0
                min_fin = e_dt.hour * 60 + e_dt.minute
            else:
                continue
                
            for m in range(min_ini, min_fin):
                if 0 <= m < 1440:
                    motori_minuto[m] += m_std
                    
    return max(motori_minuto)

# --- FUNZIONE CORRETTA PER GENERARE LE FASCE ORARIE DEL TOTALE MOTORI AL MINUTO ---
def calcola_fasce_sovrapposte_giorno(df_giorno, data_rif):
    if df_giorno.empty:
        return []
    motori_minuto = [0.0] * 1440
    
    if isinstance(data_rif, datetime):
        data_rif = data_rif.date()
        
    for _, turno in df_giorno.iterrows():
        m_std = float(turno['motori_std'])
        dt_ini = pd.to_datetime(turno['data_inizio_dt'])
        dt_fin = pd.to_datetime(turno['data_fine_dt'])
        
        intervals = []
        if dt_ini.date() == dt_fin.date() and dt_fin.time() < dt_ini.time():
            intervals.append((datetime.combine(dt_ini.date(), dt_ini.time()), datetime.combine(dt_ini.date(), time(23, 59)) + timedelta(minutes=1)))
            intervals.append((datetime.combine(dt_ini.date() + timedelta(days=1), time(0, 0)), datetime.combine(dt_ini.date() + timedelta(days=1), dt_fin.time())))
        else:
            intervals.append((dt_ini, dt_fin))
            
        for s_dt, e_dt in intervals:
            if s_dt.date() < data_rif and e_dt.date() > data_rif:
                min_ini, min_fin = 0, 1440
            elif s_dt.date() == data_rif and e_dt.date() == data_rif:
                min_ini = s_dt.hour * 60 + s_dt.minute
                min_fin = e_dt.hour * 60 + e_dt.minute
            elif s_dt.date() == data_rif and e_dt.date() > data_rif:
                min_ini = s_dt.hour * 60 + s_dt.minute
                min_fin = 1440
            elif s_dt.date() < data_rif and e_dt.date() == data_rif:
                min_ini = 0
                min_fin = e_dt.hour * 60 + e_dt.minute
            else:
                continue
                
            for m in range(min_ini, min_fin):
                if 0 <= m < 1440:
                    motori_minuto[m] += m_std
                    
    fasce = []
    if sum(motori_minuto) == 0:
        return fasce
        
    inizio_m = 0
    valore_corrente = motori_minuto[0]
    
    for m in range(1, 1440):
        if abs(motori_minuto[m] - valore_corrente) > 0.01:
            if valore_corrente > 0:
                h_i, m_i = inizio_m // 60, inizio_m % 60
                h_f, m_f = m // 60, m % 60
                fasce.append({
                    "inizio": f"{h_i:02d}:{m_i:02d}",
                    "fine": f"{h_f:02d}:{m_f:02d}",
                    "motori": valore_corrente
                })
            inizio_m = m
            valore_corrente = motori_minuto[m]
            
    if valore_corrente > 0:
        h_i, m_i = inizio_m // 60, inizio_m % 60
        fasce.append({
            "inizio": f"{h_i:02d}:{m_i:02d}",
            "fine": "24:00",
            "motori": valore_corrente
        })
        
    return fasce

def inizializza_tabelle_personalizzate():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS irriganti (
            id SERIAL PRIMARY KEY, nome TEXT NOT NULL, zona TEXT, tipo_prelievo TEXT,
            motori_std REAL DEFAULT 1.0, minuti_distanza INTEGER DEFAULT 30,
            extra_fosso_sporco INTEGER DEFAULT 15, giorni_anticipo_manovra INTEGER DEFAULT 0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS prenotazioni (
            id SERIAL PRIMARY KEY, irrigante_id INTEGER,
            data_ora_inizio TEXT, data_ora_fine TEXT, config_scelta TEXT, stato TEXT DEFAULT 'PROGRAMMATO',
            FOREIGN KEY(irrigante_id) REFERENCES irriganti(id) ON DELETE CASCADE
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS manovre_personalizzate (
            id SERIAL PRIMARY KEY, irrigante_id INTEGER,
            descrizione TEXT NOT NULL, valore_anticipo REAL NOT NULL, unita_anticipo TEXT NOT NULL,
            FOREIGN KEY(irrigante_id) REFERENCES irriganti(id) ON DELETE CASCADE
        )
    ''')
    conn.commit()
    conn.close()

def inserisci_irrigante_completo(nome, zona, prelievo, motori, distanza, extra_fosso, giorni_ant):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO irriganti (nome, zona, tipo_prelievo, motori_std, minuti_distanza, extra_fosso_sporco, giorni_anticipo_manovra)
        VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
    ''', (nome, zona, prelievo, motori, distanza, extra_fosso, giorni_ant))
    id_generato = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    return id_generato

def aggiorna_irrigante_completo(id_irr, nome, zona, prelievo, motori, distanza, extra_fosso, giorni_ant):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE irriganti SET nome=%s, zona=%s, tipo_prelievo=%s, motori_std=%s, minuti_distanza=%s, extra_fosso_sporco=%s, giorni_anticipo_manovra=%s WHERE id=%s
    ''', (nome, zona, prelievo, motori, distanza, extra_fosso, giorni_ant, id_irr))
    conn.commit()
    conn.close()

def inserisci_manovra_personalizzata(irr_id, desc, val, unita):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO manovre_personalizzate (irrigante_id, descrizione, valore_anticipo, unita_anticipo) VALUES (%s, %s, %s, %s)', (irr_id, desc, val, unita))
    conn.commit()
    conn.close()

def cancella_manovra_personalizzata(manovra_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM manovre_personalizzate WHERE id = %s', (manovra_id,))
    conn.commit()
    conn.close()

def inserisci_prenotazione_avanzata(irrigante_id, inizio, fine, config):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO prenotazioni (irrigante_id, data_ora_inizio, data_ora_fine, config_scelta) VALUES (%s, %s, %s, %s)', (irrigante_id, inizio, fine, config))
    conn.commit()
    conn.close()

def cancella_prenotazione(id_prenotazione):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM prenotazioni WHERE id = %s", (id_prenotazione,))
    conn.commit()
    conn.close()

def cancella_turni_settimana(data_rif):
    inizio_sett = data_rif - timedelta(days=data_rif.weekday())
    fine_sett = inizio_sett + timedelta(days=6)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        DELETE FROM prenotazioni 
        WHERE date(substring(data_ora_inizio from 1 for 10)) >= date(%s) 
          AND date(substring(data_ora_inizio from 1 for 10)) <= date(%s)
    ''', (str(inizio_sett), str(fine_sett)))
    conn.commit()
    conn.close()

def cancella_turni_mese(data_rif):
    anno_mese = data_rif.strftime("%Y-%m")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM prenotazioni WHERE substring(data_ora_inizio from 1 for 7) = %s", (anno_mese,))
    conn.commit()
    conn.close()

def cancella_turni_generale():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM prenotazioni")
    conn.commit()
    conn.close()

def cancella_turni_specifico_irrigante(id_irr):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM prenotazioni WHERE irrigante_id = %s", (id_irr,))
    conn.commit()
    conn.close()

def selezionao_pompe_centrale(motori):
    if motori == 0: return "IMPIANTO FERMO", []
    elif motori <= 6.0: return "Solo POMPA P4 attiva", ["P4"]
    elif motori <= 8.0: return "Solo POMPA P3 (Inverter) attiva", ["P3"]
    elif motori <= 12.0: return "ENTRAMBE ATTIVE (P4 + P3) - Spinta Max 240 l/s", ["P4", "P3"]
    else: return "SOVRACCARICO (Oltre i 12 M)", ["P4", "P3"]

def ottieni_colore_stato_semplice(motori_totali, rangoni_attivo):
    if motori_totali == 0: return "#A0A0A0", "🟢 IMPIANTO FERMO"
    if motori_totali <= 6.0: colore_assegnato = "#28a745"
    elif motori_totali <= 10.0: colore_assegnato = "#007bff"
    elif motori_totali <= 11.0: colore_assegnato = "#e83e8c"
    elif motori_totali <= 12.0: colore_assegnato = "#ffc107"
    else: colore_assegnato = "#dc3545"

    if rangoni_attivo:
        if motori_totali > 12.0: return colore_assegnato, f"🔴 TEST FALLITO ({motori_totali:.1f} M)!"
        elif motori_totali >= 11.0: return colore_assegnato, "🟠 SOGLIA CRITICA TEST"
        else: return colore_assegnato, "🟢 REGIME DI PROVA"
    if motori_totali > 12.0: return colore_assegnato, "🔴 SOVRACCARICO STRUTTURALE"
    return colore_assegnato, "🟢 CARICO RETE REGOLARE"

def analizza_orario_lavoro(dt_obj):
    t = dt_obj.time()
    if (time(8, 0) <= t <= time(12, 0)) or (time(13, 30) <= t <= time(17, 30)): return "IN_ORARIO", ""
    elif t < time(8, 0): return "STRAORDINARIO_MATTINA", "#17a2b8"
    else: return "STRAORDINARIO_SERA", "#e83e8c"

def ottimizza_orario_manovra(dt_originale, ore_sovraccarico=0, motori_correnti=0):
    t_min = time(6, 15)
    t_max = time(20, 45)
    if dt_originale.weekday() in [5, 6]:
        if motori_correnti <= 12.5 and ore_sovraccarico <= 2:
            giorni_a_lunedi = 7 - dt_originale.weekday()
            return datetime.combine(dt_originale.date() + timedelta(days=giorni_a_lunedi), time(8, 0))
    if dt_originale.time() < t_min: return datetime.combine(dt_originale.date(), t_min)
    elif dt_originale.time() > t_max: return datetime.combine(dt_originale.date() + timedelta(days=1), t_min)
    return dt_originale

def determines_info_pompe_home(motori):
    if motori == 0: return "#ffffff", "Nessuna"
    elif motori <= 6.0: return "#d4edda", "P4"
    elif motori <= 8.0: return "#cce5ff", "P3"
    else: return "#f8d7da", "P3 + P4"

def ottieni_giorno_settimana(data_obj):
    return GIORNI_IT.get(data_obj.strftime("%A"), data_obj.strftime("%A"))

inizializza_tabelle_personalizzate()

try:
    conn_manutenzione = get_db_connection()
    cursor_m = conn_manutenzione.cursor()
    cursor_m.execute("DELETE FROM prenotazioni WHERE length(data_ora_inizio) < 16 OR length(data_ora_fine) < 16")
    conn_manutenzione.commit()
    conn_manutenzione.close()
except Exception:
    pass

engine = get_sqlalchemy_engine()
df_irriganti = pd.read_sql_query(text("SELECT * FROM irriganti ORDER BY nome"), engine)
df_tutti_attivi = pd.read_sql_query(text('''
    SELECT p.id, i.id AS irr_id, i.nome, i.motori_std, i.zona, i.minuti_distanza, i.extra_fosso_sporco, i.giorni_anticipo_manovra,
           p.data_ora_inizio, p.data_ora_fine, p.config_scelta
    FROM prenotazioni p 
    LEFT JOIN irriganti i ON p.irrigante_id = i.id
    WHERE p.stato = 'PROGRAMMATO' AND i.id IS NOT NULL
    ORDER BY p.data_ora_inizio ASC
'''), engine)

if not df_tutti_attivi.empty:
    df_tutti_attivi = df_tutti_attivi[df_tutti_attivi['data_ora_inizio'].str.len() >= 16].copy()
    if not df_tutti_attivi.empty:
        df_tutti_attivi['data_inizio_dt'] = pd.to_datetime(df_tutti_attivi['data_ora_inizio'])
        df_tutti_attivi['data_fine_dt'] = pd.to_datetime(df_tutti_attivi['data_ora_fine'])

if 'data_corrente' not in st.session_state:
    st.session_state.data_corrente = datetime.now().date()

if "data_settimana_macchine" not in st.session_state:
    st.session_state.data_settimana_macchine = st.session_state.data_corrente

def sync_da_dash(): 
    st.session_state.data_corrente = st.session_state.data_dash
    st.session_state.data_settimana_macchine = st.session_state.data_dash
def sync_da_agenda(): 
    st.session_state.data_corrente = st.session_state.data_agenda
    st.session_state.data_settimana_macchine = st.session_state.data_agenda
def sync_da_home(): 
    st.session_state.data_corrente = st.session_state.data_home
    st.session_state.data_settimana_macchine = st.session_state.data_home
def giorno_precedente(): 
    st.session_state.data_corrente -= timedelta(days=1)
    st.session_state.data_settimana_macchine = st.session_state.data_corrente
def giorno_successivo(): 
    st.session_state.data_corrente += timedelta(days=1)
    st.session_state.data_settimana_macchine = st.session_state.data_corrente

irriganti_giorno_corrente = []
rangoni_oggi_global = False
if not df_tutti_attivi.empty:
    df_giorno_attivi_global = df_tutti_attivi[(df_tutti_attivi['data_inizio_dt'].dt.date <= st.session_state.data_corrente) & (df_tutti_attivi['data_fine_dt'].dt.date >= st.session_state.data_corrente)].copy()
    rangoni_oggi_global = df_giorno_attivi_global['nome'].str.contains("Rangoni", case=False).any() if not df_giorno_attivi_global.empty else False
    for idx, r in df_giorno_attivi_global.iterrows():
        if r['data_inizio_dt'].date() < st.session_state.data_corrente:
            ora_inz_str = "00:00"
        else:
            ora_inz_str = r['data_inizio_dt'].strftime('%H:%M')
            
        if r['data_fine_dt'].date() > st.session_state.data_corrente:
            ora_fin_str = "24:00"
        else:
            ora_fin_str = r['data_fine_dt'].strftime('%H:%M')
            if ora_fin_str in ["23:59", "00:00"]: ora_fin_str = "24:00"
            
        irriganti_giorno_corrente.append({"id": r['id'], "nome": r['nome'], "fascia": f"{ora_inz_str} - {ora_fin_str}", "motori": r['motori_std']})

df_giorno_attuale_global = df_tutti_attivi[(df_tutti_attivi['data_inizio_dt'].dt.date <= st.session_state.data_corrente) & (df_tutti_attivi['data_fine_dt'].dt.date >= st.session_state.data_corrente)].copy() if not df_tutti_attivi.empty else pd.DataFrame()
motori_pre_perdite_global = calcola_picco_massimo_giorno(df_giorno_attuale_global, st.session_state.data_corrente)
motori_giorno_global = calcola_motori_con_perdite(motori_pre_perdite_global)
testo_pompe_g, _ = selezionao_pompe_centrale(motori_giorno_global)
esito_colore_g, _ = ottieni_colore_stato_semplice(motori_giorno_global, rangoni_oggi_global)
_, portata_globale_g_ls = calcola_giri_chiavone(motori_giorno_global, "Generico")

tab_home, tab_dashboard, tab_agenda, tab_sala_macchine, tab_anagrafica = st.tabs([
    "🏠 Home Page Settimanale", "📅 Gestione Turni & Rete", "📋 Agenda 365 Giorni", "📟 Sala Macchine (Timer)", "🚜 Anagrafica"
])

# =========================================================
# TAB 0: HOME PAGE
# =========================================================
with tab_home:
    st.title("💧 IdroSmart PRO 365 — Monitoraggio Centrale")
    
    valore_perdite_testo = "0.00" if motori_pre_perdite_global == 0 else ("0.50" if motori_giorno_global <= 6.0 else "1.00")
    st.markdown(f"""
    <div style="background-color:{esito_colore_g}; padding:18px; border-radius:10px; text-align:center; margin-bottom:20px;">
        <h3 style="color:white; margin:0; font-size:1.3rem;">📟 STATO IDRAULICO CORRENTE (PICCO DI MASSIMA SOVRAPPOSIZIONE): {st.session_state.data_corrente.strftime('%d/%m/%Y')}</h3>
        <h1 style="color:white; margin:5px 0; font-size:38px; font-weight:bold;">{motori_giorno_global:.2f} M massimi in contemporanea <span style='font-size:18px; font-weight:normal;'>(Incluso +{valore_perdite_testo} M perdite)</span></h1>
        <p style="color:white; margin:0; font-size:16px; font-weight:500;">ASSETTO MASSIMO PICCO: {testo_pompe_g} | PORTATA COMPLESSIVA RETE AL PICCO: {portata_globale_g_ls:.0f} l/s</p>
    </div>
    """, unsafe_allow_html=True)
    
    c_h1, c_h2, c_h3 = st.columns([1, 2, 1])
    with c_h1: st.button("⬅️ Giorno Precedente", on_click=giorno_precedente, use_container_width=True, key="home_prev")
    with c_h2: st.date_input("Data di Osservazione:", value=st.session_state.data_corrente, key="data_home", on_change=sync_da_home, label_visibility="collapsed")
    with c_h3: st.button("➡️ Giorno Successivo", on_click=giorno_successivo, use_container_width=True, key="home_next")
    
    st.markdown("### 🗓️ Quadro di Insieme Settimanale")
    inizio_settimana = st.session_state.data_corrente - timedelta(days=st.session_state.data_corrente.weekday())
    col_sett = st.columns(7)
    
    for i in range(7):
        giorno_loop = inizio_settimana + timedelta(days=i)
        nome_giorno_it = GIORNI_IT.get(giorno_loop.strftime("%A"), giorno_loop.strftime("%A"))
        df_loop_attivi = df_tutti_attivi[(df_tutti_attivi['data_inizio_dt'].dt.date <= giorno_loop) & (df_tutti_attivi['data_fine_dt'].dt.date >= giorno_loop)] if not df_tutti_attivi.empty else pd.DataFrame()
        
        motori_loop_pre = calcola_picco_massimo_giorno(df_loop_attivi, giorno_loop)
        motori_loop = calcola_motori_con_perdite(motori_loop_pre)
        rangoni_loop = df_loop_attivi['nome'].str.contains("Rangoni", case=False).any() if not df_loop_attivi.empty else False
        colore_loop, _ = ottieni_colore_stato_semplice(motori_loop, rangoni_loop)
        
        with col_sett[i]:
            if st.button(f"{nome_giorno_it} {giorno_loop.strftime('%d/%m')} ({motori_loop:.1f} M)", key=f"btn_giorno_{giorno_loop.strftime('%Y%m%d')}", use_container_width=True):
                st.session_state.data_corrente = giorno_loop
                st.session_state.data_settimana_macchine = giorno_loop
                st.rerun()
            
            bordo_giorno = "border: 3px solid #17a2b8;" if giorno_loop == st.session_state.data_corrente else "border: 1px solid rgba(0,0,0,0.1);"
            st.markdown(f'<div style="background-color:{colore_loop}; padding:6px; border-radius:5px; text-align:center; color:white; font-weight:bold; margin-bottom:8px; {bordo_giorno}"><div style="font-size:14px;">{motori_loop:.1f} M</div></div>', unsafe_allow_html=True)
            
            if df_loop_attivi.empty:
                st.markdown("<div style='text-align:center; color:#888; font-size:12px;'>Centrale Off</div>", unsafe_allow_html=True)
            else:
                for idx_ut, utenza in df_loop_attivi.iterrows():
                    h_inz = "00:00" if utenza['data_inizio_dt'].date() < giorno_loop else utenza['data_inizio_dt'].strftime('%H:%M')
                    h_fin = "24:00" if utenza['data_fine_dt'].date() > giorno_loop else utenza['data_fine_dt'].strftime('%H:%M')
                    if h_fin in ["23:59", "00:00"]: h_fin = "24:00"
                    
                    c_grid1, c_grid2 = st.columns([4, 1])
                    with c_grid1:
                        st.markdown(f'<div style="background-color:#f8f9fa; padding:5px; border-radius:4px; margin-bottom:5px; border-left:3px solid #007bff; text-align:left;"><div style="font-size:12px; font-weight:bold; color:#212529;">{utenza["nome"]}</div><div style="font-size:11px; color:#495057; font-family:monospace;">⏱️ {h_inz}-{h_fin}</div></div>', unsafe_allow_html=True)
                    with c_grid2:
                        if st.button("❌", key=f"del_home_grid_{utenza['id']}_{giorno_loop.strftime('%d%m')}", help="Rimuovi questo turno"):
                            cancella_prenotazione(int(utenza['id']))
                            st.rerun()
                            
    st.markdown("---")
    st.markdown(f"### 📊 Fasce di Carico Sovrapposte e Variazioni del Giorno ({st.session_state.data_corrente.strftime('%d/%m/%Y')})")
    df_giorno_corrente_sov = df_tutti_attivi[(df_tutti_attivi['data_inizio_dt'].dt.date <= st.session_state.data_corrente) & (df_tutti_attivi['data_fine_dt'].dt.date >= st.session_state.data_corrente)].copy() if not df_tutti_attivi.empty else pd.DataFrame()
    fasce_cronologiche = calcola_fasce_sovrapposte_giorno(df_giorno_corrente_sov, st.session_state.data_corrente)
    
    if not fasce_cronologiche:
        st.caption("Nessuna variazione o carico sovrapposto rilevato (Impianto Fermo).")
    else:
        c_fasce = st.columns(len(fasce_cronologiche) if len(fasce_cronologiche) <= 6 else 6)
        for idx_f, f_cron in enumerate(fasce_cronologiche):
            col_target = c_fasce[idx_f % len(c_fasce)]
            with col_target:
                motori_p_p = calcola_motori_con_perdite(f_cron['motori'])
                st.info(f"⏱️ **{f_cron['inizio']} — {f_cron['fine']}**\n\n🔹 Nominale: **{f_cron['motori']:.2f} M**\n\n⚡ Reale (+perdite): **{motori_p_p:.2f} M**")
                
    st.markdown("---")
    st.markdown(f"### 📋 Foglio Giornaliero Dettagliato del **{st.session_state.data_corrente.strftime('%d/%m/%Y')}**")
    if not irriganti_giorno_corrente:
        st.info("Nessun irrigante attivo programmato per questa giornata.")
    else:
        for irr in irriganti_giorno_corrente:
            col_info, col_totale, col_remove_h = st.columns([3, 1, 0.5])
            with col_info:
                st.markdown(f"**<span style='font-size:1.25rem;'>{irr['nome']}</span>**", unsafe_allow_html=True)
                st.caption(f"🕒 Fascia Oraria Attiva: {irr['fascia']}")
            with col_totale:
                colore_f, pompe_f = determines_info_pompe_home(irr['motori'])
                st.markdown(f'<div style="background-color:{colore_f}; padding:10px; border-radius:6px; text-align:center; border: 1px solid rgba(0,0,0,0.1); color: black; font-weight:bold;">{irr["motori"]:.2f} M <br><span style="font-size:0.85rem; font-weight:normal;">({pompe_f})</span></div>', unsafe_allow_html=True)
            with col_remove_h:
                st.write("")
                if st.button("🗑️ Rimuovi", key=f"del_home_det_{irr['id']}", use_container_width=True):
                    cancella_prenotazione(int(irr['id']))
                    st.rerun()

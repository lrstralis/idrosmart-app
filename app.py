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

# --- FUNZIONI DI LETTURA CON CACHE PER VELOCIZZARE L'APPLICAZIONE ---
@st.cache_data
def get_cached_irriganti():
    engine = get_sqlalchemy_engine()
    return pd.read_sql_query(text("SELECT * FROM irriganti ORDER BY nome"), engine)

@st.cache_data
def get_cached_tutti_attivi():
    engine = get_sqlalchemy_engine()
    return pd.read_sql_query(text('''
        SELECT p.id, i.id AS irr_id, i.nome, i.motori_std, i.zona, i.minuti_distanza, i.extra_fosso_sporco, i.giorni_anticipo_manovra,
               p.data_ora_inizio, p.data_ora_fine, p.config_scelta
        FROM prenotazioni p 
        LEFT JOIN irriganti i ON p.irrigante_id = i.id
        WHERE p.stato = 'PROGRAMMATO' AND i.id IS NOT NULL
        ORDER BY p.data_ora_inizio ASC
    '''), engine)

@st.cache_data
def get_cached_manovre_personalizzate():
    engine = get_sqlalchemy_engine()
    return pd.read_sql_query(text("SELECT * FROM manovre_personalizzate"), engine)

@st.cache_data
def get_cached_manovre_specifiche(id_selezionato):
    engine = get_sqlalchemy_engine()
    return pd.read_sql_query(text("SELECT * FROM manovre_personalizzate WHERE irrigante_id = :id"), engine, params={"id": int(id_selezionato)})


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
        "4.03": {"giri": 5.25, "portata": 85.0}, "4.38": {"giri": 5.50, "portata": 92.0},
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

# --- FUNZIONE NUOVA PER TROVARE IL PICCO MASSIMO SOVRAPPOSTO MINUTO PER MINUTO ---
def calcola_picco_massimo_giorno(df_giorno, data_rif):
    if df_giorno.empty:
        return 0.0
    motori_minuto = [0.0] * 1440
    for _, turno in df_giorno.iterrows():
        m_std = float(turno['motori_std'])
        dt_ini = turno['data_inizio_dt']
        dt_fin = turno['data_fine_dt']
        
        if dt_ini.date() < data_rif:
            min_ini = 0
        else:
            min_ini = dt_ini.hour * 60 + dt_ini.minute
            
        if dt_fin.date() > data_rif:
            min_fin = 1440
        else:
            min_fin = dt_fin.hour * 60 + dt_fin.minute
            if dt_fin.time() == time(23, 59):
                min_fin = 1440
                
        for m in range(min_ini, min_fin):
            if 0 <= m < 1440:
                motori_minuto[m] += m_std
                
    return max(motori_minuto)

# --- FUNZIONE PER GENERARE LE FASCE ORARIE DEL TOTALE MOTORI AL MINUTO ---
def calcola_fasce_sovrapposte_giorno(df_giorno, data_rif):
    motori_minuto = [0.0] * 1440
    if df_giorno.empty:
        return []
    
    for _, turno in df_giorno.iterrows():
        m_std = float(turno['motori_std'])
        dt_ini = turno['data_inizio_dt']
        dt_fin = turno['data_fine_dt']
        
        if dt_ini.date() < data_rif:
            min_ini = 0
        else:
            min_ini = dt_ini.hour * 60 + dt_ini.minute
            
        if dt_fin.date() > data_rif:
            min_fin = 1440
        else:
            min_fin = dt_fin.hour * 60 + dt_fin.minute
            if dt_fin.time() == time(23, 59):
                min_fin = 1440
                
        for m in range(min_ini, min_fin):
            if 0 <= m < 1440:
                motori_minuto[m] += m_std
                
    fasce = []
    if sum(motori_minuto) == 0:
        return fasce
        
    inizio_m = 0
    valore_corrente = motori_minuto[0]
    
    for m in range(1, 1440):
        if motori_minuto[m] != valore_corrente:
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
    st.cache_data.clear() # Svuota la cache ad ogni modifica
    return id_generato

def aggiorna_irrigante_completo(id_irr, nome, zona, prelievo, motori, distanza, extra_fosso, giorni_ant):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE irriganti SET nome=%s, zona=%s, tipo_prelievo=%s, motori_std=%s, minutes_distanza=%s, extra_fosso_sporco=%s, giorni_anticipo_manovra=%s WHERE id=%s
    ''', (nome, zona, prelievo, motori, distanza, extra_fosso, giorni_ant, id_irr))
    conn.commit()
    conn.close()
    st.cache_data.clear() # Svuota la cache ad ogni modifica

def inserisci_manovra_personalizzata(irr_id, desc, val, unita):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO manovre_personalizzate (irrigante_id, descrizione, valore_anticipo, unita_anticipo) VALUES (%s, %s, %s, %s)', (irr_id, desc, val, unita))
    conn.commit()
    conn.close()
    st.cache_data.clear() # Svuota la cache ad ogni modifica

def cancella_manovra_personalizzata(manovra_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM manovre_personalizzate WHERE id = %s', (manovra_id,))
    conn.commit()
    conn.close()
    st.cache_data.clear() # Svuota la cache ad ogni modifica

def inserisci_prenotazione_avanzata(irrigante_id, inizio, fine, config):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO prenotazioni (irrigante_id, data_ora_inizio, data_ora_fine, config_scelta) VALUES (%s, %s, %s, %s)', (irrigante_id, inizio, fine, config))
    conn.commit()
    conn.close()
    st.cache_data.clear() # Svuota la cache ad ogni modifica

def cancella_prenotazione(id_prenotazione):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM prenotazioni WHERE id = %s", (id_prenotazione,))
    conn.commit()
    conn.close()
    st.cache_data.clear() # Svuota la cache ad ogni modifica

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
    st.cache_data.clear() # Svuota la cache ad ogni modifica

def cancella_turni_mese(data_rif):
    anno_mese = data_rif.strftime("%Y-%m")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM prenotazioni WHERE substring(data_ora_inizio from 1 for 7) = %s", (anno_mese,))
    conn.commit()
    conn.close()
    st.cache_data.clear() # Svuota la cache ad ogni modifica

def cancella_turni_generale():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM prenotazioni")
    conn.commit()
    conn.close()
    st.cache_data.clear() # Svuota la cache ad ogni modifica

def cancella_turni_specifico_irrigante(id_irr):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM prenotazioni WHERE irrigante_id = %s", (id_irr,))
    conn.commit()
    conn.close()
    st.cache_data.clear() # Svuota la cache ad ogni modifica

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

# Richiamo delle funzioni caricate in cache
df_irriganti = get_cached_irriganti()
df_tutti_attivi = get_cached_tutti_attivi()

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

# =========================================================
# TAB 1: GESTIONE TURNI & RETE
# =========================================================
with tab_dashboard:
    st.title("💧 IdroSmart PRO — Controllo Distribuzione Idrica")
    
    st.sidebar.header("➕ Inserisci Nuovo Turno")
    tipo_elemento_scelto = st.sidebar.radio("Tipo Elemento da inserire:", ["Agricoltori", "Chiavoni"], horizontal=True)
    
    if tipo_elemento_scelto == "Agricoltori":
        opzioni_sb = df_irriganti['nome'].tolist() if not df_irriganti.empty else []
        if not opzioni_sb: opzioni_sb = ["Nessun agricoltore registrato"]
        tipo_pesca_scelta = st.sidebar.radio("Modalità Prelievo", ["Fosso", "Diretta"], index=1)
    else:
        opzioni_sb = ELENCO_CHIAVONI_REALI
        tipo_pesca_scelta = "Fosso"
        st.sidebar.info("🌊 Modalità bloccata per i Chiavoni Reali: **Fosso**")
        
    irrigante_scelto = st.sidebar.selectbox("Seleziona Contadino / Chiavone", opzioni_sb)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, zona, tipo_prelievo, motori_std FROM irriganti WHERE nome = %s", (irrigante_scelto,))
    riga_esistente = cursor.fetchone()
    conn.close()

    if riga_esistente:
        id_irrigante_db = int(riga_esistente[0])
        zona_default = riga_esistente[1]
        tipo_prelievo_default = riga_esistente[2]
        motori_default = float(riga_esistente[3])
    else:
        id_irrigante_db = None
        tipo_prelievo_default = "Fosso" if tipo_elemento_scelto == "Chiavoni" else "Diretta"
        motori_default = 1.0
        zona_default = irrigante_scelto if irrigante_scelto in ELENCO_CHIAVONI_REALI else "Valvola Contrappesi"
        
    if tipo_pesca_scelta == "Fosso" or tipo_elemento_scelto == "Chiavoni":
        motori_scelti_sb = st.sidebar.number_input("Motori totali da far uscire (M):", min_value=0.0, max_value=12.0, value=motori_default, step=0.01, key=f"motori_input_{irrigante_scelto}")
        giri_calc_sb, _ = calcola_giri_chiavone(motori_scelti_sb, zona_default)
        st.sidebar.info(f"⚙️ Giri Chiavone calcolati a fianco: **{giri_calc_sb:.2f} Giri**")
    else:
        motori_scelti_sb = motori_default
        
    st.sidebar.markdown("---")
    st.sidebar.subheader("📅 Frequenza e Giorni di Ripetizione")
    giorni_ripetizione = st.sidebar.multiselect("Seleziona i giorni della settimana per ripetere il turno:", GIORNI_SETTIMANA_LISTA)
    
    disabilita_date = len(giorni_ripetizione) > 0
    data_inizio = st.sidebar.date_input("Dal giorno:", datetime.now(), disabled=disabilita_date)
    
    lista_ore = [f"{h:02d}:{m:02d}" for h in range(24) for m in [0, 15, 30, 45]] + ["24:00"]
    ora_inizio_str = st.sidebar.selectbox("Ora Inizio:", lista_ore, index=32) 
    data_fine = st.sidebar.date_input("Al giorno:", datetime.now(), disabled=disabilita_date)
    ora_fine_str = st.sidebar.selectbox("Ora Fine:", lista_ore, index=48) 
    
    st.sidebar.markdown("---")
    fosso_sporco_attivo = st.sidebar.checkbox("⚠️ Segnala Fosso Sporco")

    if st.sidebar.button("Salva Turno in Agenda"):
        if not irrigante_scelto or irrigante_scelto == "Nessun agricoltore registrato":
            st.sidebar.error("Seleziona un elemento valido!")
        else:
            if id_irrigante_db is not None:
                aggiorna_irrigante_completo(id_irrigante_db, irrigante_scelto, zona_default, tipo_prelievo_default, motori_scelti_sb, 30, 15, 0)
            else:
                zona_ins = zona_default
                prelievo_ins = "Fosso" if irrigante_scelto in ELENCO_CHIAVONI_REALI else tipo_pesca_scelta
                id_irrigante_db = inserisci_irrigante_completo(irrigante_scelto, zona_ins, prelievo_ins, motori_scelti_sb, 30, 15, 0)
                
            lista_coppie_date = []
            if disabilita_date:
                passo = datetime.now().date()
                fine_stagione = datetime(datetime.now().year, 9, 30).date()
                while passo <= fine_stagione:
                    if MAP_GIORNI_ING[passo.weekday()] in giorni_ripetizione:
                        lista_coppie_date.append((passo, passo))
                    passo += timedelta(days=1)
            else:
                lista_coppie_date.append((data_inizio, data_fine))
                
            salva_ora_fine = "23:59" if ora_fine_str == "24:00" else ora_fine_str
            config_salv = "Fosso" if irrigante_scelto in ELENCO_CHIAVONI_REALI else tipo_pesca_scelta
                
            for d_ini, d_fin in lista_coppie_date:
                inizio_completo = f"{d_ini.strftime('%Y-%m-%d')} {ora_inizio_str}"
                
                if ora_fine_str != "24:00" and ora_fine_str <= ora_inizio_str:
                    d_fin_effettivo = d_ini + timedelta(days=1)
                else:
                    d_fin_effettivo = d_fin
                    
                fine_completo = f"{d_fin_effettivo.strftime('%Y-%m-%d')} {salva_ora_fine}"
                inserisci_prenotazione_avanzata(id_irrigante_db, inizio_completo, fine_completo, config_salv)
                
            st.sidebar.success("Turni registrati correttamente!")
            st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.subheader("⚠️ Danger Zone — Rimozione Massiva")
    opzione_canc_massa = st.sidebar.selectbox("Scegli blocco da svuotare:", ["Nessuna azione", "Turni della Settimana", "Turni del Mese", "Turni di uno specifico Agricoltore/Chiavone", "Tutti i turni in generale"])
    
    id_irr_canc_selettiva = None
    if opzione_canc_massa == "Turni di uno specifico Agricoltore/Chiavone":
        opzioni_canc_selezione = df_irriganti['nome'].tolist() if not df_irriganti.empty else []
        irrigante_da_svuotare = st.sidebar.selectbox("Seleziona profilo da ripulire del tutto:", opzioni_canc_selezione)
        if irrigante_da_svuotare and not df_irriganti.empty:
            id_irr_canc_selettiva = int(df_irriganti[df_irriganti['nome'] == irrigante_da_svuotare]['id'].values[0])

    if opzione_canc_massa != "Nessuna azione":
        testo_conferma = "CONFERMA ELIMINAZIONE"
        codice_verifica = st.sidebar.text_input(f"Digita '{testo_conferma}' per procedere:")
        if st.sidebar.button("🚨 Esegui Svuotamento Massivo"):
            if codice_verifica == testo_conferma:
                if opzione_canc_massa == "Turni della Settimana":
                    cancella_turni_settimana(st.session_state.data_corrente)
                elif opzione_canc_massa == "Turni del Mese":
                    cancella_turni_mese(st.session_state.data_corrente)
                elif opzione_canc_massa == "Turni di uno specifico Agricoltore/Chiavone" and id_irr_canc_selettiva is not None:
                    cancella_turni_specifico_irrigante(id_irr_canc_selettiva)
                elif opzione_canc_massa == "Tutti i turni in generale":
                    cancella_turni_generale()
                st.rerun()

    c_nav1, c_nav2, c_nav3 = st.columns([1, 2, 1])
    with c_nav1: st.button("⬅️ Giorno Precedente", on_click=giorno_precedente, use_container_width=True, key="dash_prev")
    with c_nav2: st.date_input("Seleziona Giorno:", value=st.session_state.data_corrente, key="data_dash", on_change=sync_da_dash, label_visibility="collapsed")
    with c_nav3: st.button("➡️ Giorno Successivo", on_click=giorno_successivo, use_container_width=True, key="dash_next")
            
    df_giorno_attivi = df_tutti_attivi[(df_tutti_attivi['data_inizio_dt'].dt.date <= st.session_state.data_corrente) & (df_tutti_attivi['data_fine_dt'].dt.date >= st.session_state.data_corrente)].copy() if not df_tutti_attivi.empty else pd.DataFrame()
    rangoni_oggi = df_giorno_attivi['nome'].str.contains("Rangoni", case=False).any() if not df_giorno_attivi.empty else False

    motori_pre_perdite = calcola_picco_massimo_giorno(df_giorno_attivi, st.session_state.data_corrente)
    motori_giorno = calcola_motori_con_perdite(motori_pre_perdite)
    testo_pompe, _ = selezionao_pompe_centrale(motori_giorno)
    esito_colore, _ = ottieni_colore_stato_semplice(motori_giorno, rangoni_oggi)
    _, portata_globale_ls = calcola_giri_chiavone(motori_giorno, "Generico")

    valore_perdite_testo_dash = "0.00" if motori_pre_perdite == 0 else ("0.50" if motori_giorno <= 6.0 else "1.00")
    st.markdown(f"""
    <div style="background-color:{esito_colore}; padding:20px; border-radius:10px; text-align:center; margin-bottom:25px;">
        <h2 style="color:white; margin:0;">📟 STATO IDRAULICO RETE DEL GIORNO (PICCO MASSIMO): {st.session_state.data_corrente.strftime('%d/%m/%Y')}</h2>
        <h1 style="color:white; margin:10px 0 0 0; font-size:45px; font-weight:bold;">{motori_giorno:.2f} M massimi in contemporanea <span style='font-size:20px; font-weight:normal;'>(Incluso +{valore_perdite_testo_dash} M perdite)</span></h1>
        <p style="color:white; margin:5px 0 0 0; font-size:18px; font-weight:500;">ASSETTO MASSIMO PICCO: {testo_pompe} | PORTATA RETE AL PICCO: {portata_globale_ls:.0f} l/s</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f"#### 📊 Cronoprogramma di Carico e Fasce Sovrapposte ({st.session_state.data_corrente.strftime('%d/%m/%Y')})")
    fasce_cronologiche_dash = calcola_fasce_sovrapposte_giorno(df_giorno_attivi, st.session_state.data_corrente)
    if fasce_cronologiche_dash:
        righe_c_d = []
        for f_cd in fasce_cronologiche_dash:
            m_reali_fd = calcola_motori_con_perdite(f_cd['motori'])
            righe_c_d.append({
                "Fascia Oraria": f"⏱️ {f_cd['inizio']} — {f_cd['fine']}",
                "Carico Richiesto (Nominale)": f"{f_cd['motori']:.2f} M",
                "Assetto Reale (+Perdite)": f"{m_reali_fd:.2f} M",
                "Configurazione Pompe": selezionao_pompe_centrale(m_reali_fd)[0]
            })
        st.table(pd.DataFrame(righe_c_d))
    else:
        st.caption("Nessun carico sovrapposto.")

    st.subheader(f"📋 Dettaglio Utenze Attive Giornaliere ({st.session_state.data_corrente.strftime('%d/%m/%Y')})")
    if df_giorno_attivi.empty:
        st.info("Nessun prelievo programmato per questo giorno.")
    else:
        righe_tabella = []
        for idx, r in df_giorno_attivi.iterrows():
            _, portata_s = calcola_giri_chiavone(r['motori_std'], r['zona'])
            
            h_inz_tab = "00:00" if r['data_inizio_dt'].date() < st.session_state.data_corrente else r['data_inizio_dt'].strftime('%H:%M')
            h_fin_tab = "24:00" if r['data_fine_dt'].date() > st.session_state.data_corrente else r['data_fine_dt'].strftime('%H:%M')
            if h_fin_tab in ["23:59", "00:00"]: h_fin_tab = "24:00"
            
            righe_tabella.append({
                "Azienda Agricola / Contadino": r['nome'], "Zona Idraulica": r['zona'],
                "Fascia Oraria": f"{h_inz_tab} - {h_fin_tab}",
                "Modalità": r['config_scelta'], "Carico Richiesto (Motori M)": f"{r['motori_std']:.2f} M", "Portata (l/s)": f"{portata_s:.0f} l/s"
            })
        st.table(pd.DataFrame(righe_tabella))
        
        st.markdown("##### 🗑️ Rimozione Manuale Veloce Turni del Giorno:")
        for idx, r in df_giorno_attivi.iterrows():
            c_del1, c_del2 = st.columns([5, 1])
            with c_del1: 
                h_inz_tab = "00:00" if r['data_inizio_dt'].date() < st.session_state.data_corrente else r['data_inizio_dt'].strftime('%H:%M')
                h_fin_tab = "24:00" if r['data_fine_dt'].date() > st.session_state.data_corrente else r['data_fine_dt'].strftime('%H:%M')
                if h_fin_tab in ["23:59", "00:00"]: h_fin_tab = "24:00"
                st.write(f"🚜 Turno: **{r['nome']}** | Orario: {h_inz_tab} - {h_fin_tab} ({r['zona']}) | Modalità: *{r['config_scelta']}*")
            with c_del2:
                if st.button("🗑️ Rimuovi", key=f"del_dash_{r['id']}", use_container_width=True):
                    cancella_prenotazione(int(r['id']))
                    st.rerun()

# =========================================================
# TAB 2: AGENDA GIORNALIERA DELLE MANOVRE
# =========================================================
with tab_agenda:
    st.title("📋 Agenda Giornaliera delle Manovre")
    
    c_nav_a1, c_nav_a2, c_nav_a3 = st.columns([1, 2, 1])
    with c_nav_a1: st.button("⬅️ Ieri", on_click=giorno_precedente, use_container_width=True, key="agenda_prev")
    with c_nav_a2: st.date_input("Calendario:", value=st.session_state.data_corrente, key="data_agenda", on_change=sync_da_agenda, label_visibility="collapsed")
    with c_nav_a3: st.button("➡️ Domani", on_click=giorno_successivo, use_container_width=True, key="agenda_next")
    
    st.markdown(f"### 🗓️ Registro Ordini di Servizio del: **{st.session_state.data_corrente.strftime('%d/%m/%Y')}**")

    if df_tutti_attivi.empty:
        st.info("Nessuna manovra presente nel sistema.")
    else:
        manovre_totali = []
        df_manovre_p = get_cached_manovre_personalizzate() # Utilizzo della cache

        for idx, row in df_tutti_attivi.iterrows():
            in_dt = row['data_inizio_dt']
            fi_dt = row['data_fine_dt']

            if fi_dt.weekday() in [5, 6] and row['config_scelta'] == "Fosso":
                lun_mattina = datetime.combine(fi_dt.date() + timedelta(days=(7 - fi_dt.weekday())), time(8, 0))
                manovre_totali.append({
                    "Data/Ora": fi_dt,
                    "Tipo": "🌊 Invaso Rangona",
                    "ForzaOraria": "INFO",
                    "Descrizione": f"Fine turno weekend di {row['nome']}. Lasciare correre l'acqua fino a Lunedì {lun_mattina.strftime('%d/%m')} ore 08:00 per rimpinguare l'invaso Rangona."
                })

            sub_m = df_manovre_p[df_manovre_p['irrigante_id'] == int(row['irr_id'])]
            for _, m_row in sub_m.iterrows():
                try:
                    val = float(m_row['valore_anticipo'])
                    unita = m_row['unita_anticipo']
                    
                    if unita == "Ore": td = timedelta(hours=val)
                    elif unita == "Mezze Giornate": td = timedelta(hours=val * 12)
                    else: td = timedelta(days=val)

                    ora_manovra_dinamica = in_dt - td
                    if ora_manovra_dinamica.year >= datetime.now().year - 1:
                        ora_manovra_ott = ottimizza_orario_manovra(ora_manovra_dinamica, motori_correnti=motori_giorno_global)
                        manovre_totali.append({
                            "Data/Ora": ora_manovra_ott,
                            "Tipo": "🔧 Manovra Configurata",
                            "ForzaOraria": "CONTROLLA",
                            "Descrizione": f"[{row['nome']}] {m_row['descrizione']} (Anticipo impostato: {val} {unita})."
                        })
                except OverflowError:
                    pass

        if len(manovre_totali) > 0:
            df_manovre = pd.DataFrame(manovre_totali).sort_values(by="Data/Ora").drop_duplicates(subset=["Data/Ora", "Descrizione"])
            df_giorno = df_manovre[df_manovre['Data/Ora'].dt.date == st.session_state.data_corrente]
            
            if df_giorno.empty:
                st.info("Nessuna manovra fisica pianificata o configurata in anagrafica per oggi.")
            else:
                for _, m in df_giorno.iterrows():
                    ora_f = "24:00" if m['Data/Ora'].strftime('%H:%M') in ["23:59", "00:00"] and m['ForzaOraria'] == "INFO" else m['Data/Ora'].strftime("%H:%M")
                    
                    if m['ForzaOraria'] == "INFO":
                        st.success(f"🌊 **ORE {ora_f}** — [{m['Tipo']}] {m['Descrizione']}")
                    else:
                        stato_lavoro, colore_allarme = analizza_orario_lavoro(m['Data/Ora'])
                        if stato_lavoro == "IN_ORARIO":
                            st.warning(f"⏰ **ORE {ora_f}** — [{m['Tipo']}] {m['Descrizione']}")
                        else:
                            st.markdown(f'<div style="background-color:{colore_allarme}; padding:10px; border-radius:5px; color:white; font-weight:bold; margin-bottom:8px;">⚠️ STRAORDINARIO — ORE {ora_f} — [{m['Tipo']}] {m['Descrizione']}</div>', unsafe_allow_html=True)
        else:
            st.info("Nessuna manovra fisica pianificata o configurata in anagrafica per oggi.")

# =========================================================
# TAB 3: VIDEATA SALA MACCHINE
# =========================================================
with tab_sala_macchine:
    st.title("📟 Quadro Controllo Automatizzato Orologi di Centrale")
    st.write("La sezione mostra esclusivamente gli intervalli di accensione e spegnimento operativi delle pompe P3 e P4 calcolati in base al carico totale di motori richiesto in ogni istante del giorno con logica dei ritardi integrata.")
    
    c_sm1, c_sm2, c_sm3 = st.columns([1, 2, 1])
    with c_sm1:
        if st.button("⬅️ Settimana Precedente", key="sm_sett_prev", use_container_width=True):
            st.session_state.data_settimana_macchine -= timedelta(days=7)
            st.rerun()
    with c_sm2:
        inizio_sett_sm = st.session_state.data_settimana_macchine - timedelta(days=st.session_state.data_settimana_macchine.weekday())
        fine_sett_sm = inizio_sett_sm + timedelta(days=6)
        st.markdown(f"<h4 style='text-align:center; color:#17a2b8;'>📅 Settimana da {inizio_sett_sm.strftime('%d/%m')} a {fine_sett_sm.strftime('%d/%m/%Y')}</h4>", unsafe_allow_html=True)
    with c_sm3:
        if st.button("Settimana Successiva ➡️", key="sm_sett_next", use_container_width=True):
            st.session_state.data_settimana_macchine += timedelta(days=7)
            st.rerun()

    for giorno_idx in range(7):
        giorno_esaminato = inizio_sett_sm + timedelta(days=giorno_idx)
        nome_giorno_it = GIORNI_IT.get(giorno_esaminato.strftime('%A'), giorno_esaminato.strftime('%A'))
        
        st.markdown(f"<h5 style='background-color:#f0f2f6; padding:6px; border-radius:5px; margin-top:15px;'>📆 {nome_giorno_it} {giorno_esaminato.strftime('%d/%m/%Y')}</h5>", unsafe_allow_html=True)
        
        if not df_tutti_attivi.empty:
            df_giorno_sm = df_tutti_attivi[
                (df_tutti_attivi['data_inizio_dt'].dt.date <= giorno_esaminato) & 
                (df_tutti_attivi['data_fine_dt'].dt.date >= giorno_esaminato)
            ].copy()
        else:
            df_giorno_sm = pd.DataFrame()
            
        p4_nominale = [False] * 1440
        p3_nominale = [False] * 1440
        motori_minuto_arr = [0.0] * 1440
        
        for minuto_del_giorno in range(1440):
            ora = minuto_del_giorno // 60
            minuto = minuto_del_giorno % 60
            tempo_minuto_inizio = datetime.combine(giorno_esaminato, time(ora, minuto))
            tempo_minuto_fine = tempo_minuto_inizio + timedelta(minutes=1)
            
            motori_min = 0.0
            if not df_giorno_sm.empty:
                for _, turno in df_giorno_sm.iterrows():
                    limite_fine = turno['data_fine_dt']
                    if limite_fine.time() == time(23, 59):
                        limite_fine = datetime.combine(limite_fine.date(), time(23, 59, 59))
                        
                    if turno['data_inizio_dt'] < tempo_minuto_fine and limite_fine > tempo_minuto_inizio:
                        motori_min += float(turno['motori_std'])
            
            motori_minuto_arr[minuto_del_giorno] = motori_min
            
            p4_nominale[minuto_del_giorno] = False
            p3_nominale[minuto_del_giorno] = False
            
            if motori_min > 0:
                totale_con_perdite = calcola_motori_con_perdite(motori_min)
                if totale_con_perdite <= 6.0:
                    p4_nominale[minuto_del_giorno] = True
                elif totale_con_perdite <= 8.0:
                    p3_nominale[minuto_del_giorno] = True
                else:
                    p4_nominale[minuto_del_giorno] = True
                    p3_nominale[minuto_del_giorno] = True

        p4_attiva = [False] * 1440
        p3_attiva = [False] * 1440
        
        p4_reale_prec = False
        p3_reale_prec = False
        
        idx_m = 0
        while idx_m < 1440:
            p4_wants = p4_nominale[idx_m]
            p3_wants = p3_nominale[idx_m]
            
            if p4_wants and p3_wants and not p4_reale_prec and not p3_reale_prec:
                p3_attiva[idx_m] = True
                p4_attiva[idx_m] = False
                p3_reale_prec = True
                p4_reale_prec = False
                idx_m += 1
                for _ in range(2): 
                    if idx_m < 1440:
                        p3_attiva[idx_m] = p3_nominale[idx_m]
                        p4_attiva[idx_m] = False
                        p4_reale_prec = False
                        p3_reale_prec = p3_attiva[idx_m]
                        idx_m += 1
                continue
            
            if p3_wants and not p4_wants and p4_reale_prec and not p3_reale_prec:
                motori_attuali = motori_minuto_arr[idx_m]
                motori_con_perdite_ist = calcola_motori_con_perdite(motori_attuali)
                ritardo_minuti = 4 if (6.0 <= motori_con_perdite_ist <= 7.0) else 2
                for _ in range(ritardo_minuti):
                    if idx_m < 1440:
                        p4_attiva[idx_m] = p4_nominale[idx_m]
                        p3_attiva[idx_m] = False
                        p3_reale_prec = False
                        p4_reale_prec = p4_attiva[idx_m]
                        idx_m += 1
                continue
                
            p4_attiva[idx_m] = p4_wants
            p3_attiva[idx_m] = p3_wants
            p4_reale_prec = p4_attiva[idx_m]
            p3_reale_prec = p3_attiva[idx_m]
            idx_m += 1

        def unisci_fasce_orarie(array_presenza):
            fasce = []
            in_blocco = False
            inizio_blocco = None
            for m_giorno in range(1440):
                if array_presenza[m_giorno] and not in_blocco:
                    in_blocco = True
                    h_ini = m_giorno // 60
                    m_ini = m_giorno % 60
                    inizio_blocco = f"{h_ini:02d}:{m_ini:02d}"
                elif not array_presenza[m_giorno] and in_blocco:
                    in_blocco = False
                    h_fin = m_giorno // 60
                    m_fin = m_giorno % 60
                    fasce.append(f"⏱️ {inizio_blocco} — {h_fin:02d}:{m_fin:02d}")
            if in_blocco:
                fasce.append(f"⏱️ {inizio_blocco} — 24:00")
            return fasce

        fasce_p4 = unisci_fasce_orarie(p4_attiva)
        fasce_p3 = unisci_fasce_orarie(p3_attiva)

        col_p4_sm, col_p3_sm = st.columns(2)
        with col_p4_sm:
            st.markdown("<b style='color:#dc3545;'>📟 ORARI ACCENSIONE POMPA P4 (Bassa Pressione)</b>", unsafe_allow_html=True)
            if fasce_p4:
                for fascia_oraria_testo in fasce_p4: st.code(fascia_oraria_testo, language=None)
            else: st.caption("Pompa P4 Spenta per l'intera giornata")
                
        with col_p3_sm:
            st.markdown("<b style='color:#17a2b8;'>📟 ORARI ACCENSIONE POMPA P3 (Alta Pressione / Inverter)</b>", unsafe_allow_html=True)
            if fasce_p3:
                for fascia_oraria_testo in fasce_p3: st.code(fascia_oraria_testo, language=None)
            else: st.caption("Pompa P3 Spenta per l'intera giornata")

# =========================================================
# TAB 4: GESTIONE ANAGRAFICA
# =========================================================
with tab_anagrafica:
    st.title("🚜 Parametri e Anagrafica Utenze")
    sub_ins, sub_mod, sub_vis = st.tabs(["➕ Registra Profilo", "📝 Modifica Scheda", "📊 Tabella Riassuntiva"])
    
    with sub_ins:
        st.subheader("📋 Dati Anagrafici Utenza")
        n_nome = st.text_input("Nome / Identificativo Utenza o Chiavone", key="ins_nome")
        n_prelievo = st.selectbox("Prelievo Standard", ["Fosso", "Diretta"], key="ins_prelievo")
        is_diretta_ins = (n_prelievo == "Diretta")
        n_zona = st.selectbox("Nodo Idraulico Associato", ELENCO_CHIAVONI_REALI, index=0, disabled=is_diretta_ins, key="ins_zona")
        n_motori = st.number_input("Motori assorbiti (M)", min_value=0.0, max_value=12.0, value=1.0, step=0.1, key="ins_motori")
        n_distanza = st.number_input("Minuti di distanza per apertura:", min_value=0, max_value=180, value=30, key="ins_distanza")
        n_extra_fosso = st.number_input("Minuti Extra Fosso Sporco:", min_value=0, max_value=120, value=15, key="ins_extra")
        n_giorni_ant = st.selectbox("Giorni pre-anticipo manovre:", [0, 1, 2], key="ins_giorni_ant")
        
        st.markdown("---")
        st.subheader("⚙️ Aggiungi Manovre Personalizzate all'elenco temporaneo")
        c_ins_m1, c_ins_m2, c_ins_m3 = st.columns([3, 1, 1])
        with c_ins_m1: desc_manovra_ins = st.text_input("Cosa fare? (Descrizione)", placeholder="Es. Pulizia filtri secondari", key="tmp_desc")
        with c_ins_m2: val_manovra_ins = st.number_input("Tempo prima", min_value=0.5, max_value=60.0, value=2.0, step=0.5, key="tmp_val")
        with c_ins_m3: unita_manovra_ins = st.selectbox("Unità", ["Ore", "Mezze Giornate", "Giorni"], key="tmp_unit")
        
        if st.button("➕ Inserisci Manovra nella Lista"):
            if desc_manovra_ins:
                st.session_state.manovre_temporanee_registrazione.append({"descrizione": desc_manovra_ins, "valore": val_manovra_ins, "unita": unita_manovra_ins})
                st.rerun()

        if st.session_state.manovre_temporanee_registrazione:
            st.markdown("##### 📝 Lista delle Manovre pronte al salvataggio:")
            for idx_tmp, m_tmp in enumerate(st.session_state.manovre_temporanee_registrazione):
                col_m_v, col_m_d = st.columns([5, 1])
                with col_m_v: st.write(f"🔧 **{m_tmp['descrizione']}** da farsi **{m_tmp['valore']} {m_tmp['unita']}** prima del turno.")
                with col_m_d:
                    if st.button("🗑️ Rimuovi", key=f"del_tmp_m_{idx_tmp}", use_container_width=True):
                        st.session_state.manovre_temporanee_registrazione.pop(idx_tmp)
                        st.rerun()

        st.markdown("---")
        if st.button("💾 Salva Profilo Completo (Utenza + Tutte le Manovre)", type="primary"):
            if n_nome:
                zona_da_salvare = "Valvola Contrappesi" if is_diretta_ins else n_zona
                nuovo_id = inserisci_irrigante_completo(n_nome, zona_da_salvare, n_prelievo, n_motori, n_distanza, n_extra_fosso, n_giorni_ant)
                for m_salvare in st.session_state.manovre_temporanee_registrazione:
                    inserisci_manovra_personalizzata(nuovo_id, m_salvare['descrizione'], m_salvare['valore'], m_salvare['unita'])
                st.session_state.manovre_temporanee_registrazione = []
                st.success("Profilo salvato correttamente!")
                st.rerun()

    with sub_mod:
        if df_irriganti.empty: st.info("Database vuoto.")
        else:
            selezionato_mod = st.selectbox("Seleziona la scheda da modificare:", df_irriganti['nome'].tolist())
            dati_c = df_irriganti[df_irriganti['nome'] == selezionato_mod].iloc[0]
            id_selezionato = int(dati_c['id'])

            with st.form("form_mod_irr"):
                m_nome = st.text_input("Identificativo", value=str(dati_c['nome']))
                m_prelievo = st.selectbox("Prelievo", ["Fosso", "Diretta"], index=0 if dati_c['tipo_prelievo'] == "Fosso" else 1)
                is_diretta_mod = (m_prelievo == "Diretta")
                zona_corrente_db = str(dati_c['zona'])
                zona_preimpostata_selectbox = zona_corrente_db if zona_corrente_db in ELENCO_CHIAVONI_REALI else ELENCO_CHIAVONI_REALI[0]
                m_zona = st.selectbox("Chiavone Reale Associato", ELENCO_CHIAVONI_REALI, index=ELENCO_CHIAVONI_REALI.index(zona_preimpostata_selectbox), disabled=is_diretta_mod)
                m_motori = st.number_input("Motori (M)", min_value=0.0, max_value=12.0, value=float(dati_c['motori_std']))
                m_distanza = st.number_input("Minuti di distanza:", min_value=0, max_value=180, value=int(dati_c['minuti_distanza']))
                m_extra_fosso = st.number_input("Minuti Extra Fosso:", min_value=0, max_value=180, value=int(dati_c['extra_fosso_sporco']))
                m_giorni_ant = st.selectbox("Giorni anticipo:", [0, 1, 2], index=int(dati_c['giorni_anticipo_manovra']) if dati_c['giorni_anticipo_manovra'] in [0,1,2] else 0)
                if st.form_submit_button("Aggiorna Scheda"):
                    zona_da_salvare_mod = "Valvola Contrappesi" if is_diretta_mod else m_zona
                    aggiorna_irrigante_completo(id_selezionato, m_nome, zona_da_salvare_mod, m_prelievo, m_motori, m_distanza, m_extra_fosso, m_giorni_ant)
                    st.success("Scheda aggiornata!")
                    st.rerun()

            st.markdown("---")
            st.subheader(f"⚙️ Configurazione Manovre Personalizzate per {dati_c['nome']}")
            with st.form("form_aggiungi_manovra_personalizzata"):
                c_m1, c_m2, c_m3 = st.columns([3, 1, 1])
                with c_m1: desc_manovra = st.text_input("Cosa fare? (Descrizione Manovra)", placeholder="Es. Pulizia filtri secondari")
                with c_m2: val_manovra = st.number_input("Tempo prima", min_value=0.5, max_value=60.0, value=2.0, step=0.5)
                with c_m3: unita_manovra = st.selectbox("Unità", ["Ore", "Mezze Giornate", "Giorni"])
                if st.form_submit_button("➕ Aggiungi Manovra a questo Profilo"):
                    if desc_manovra:
                        inserisci_manovra_personalizzata(id_selezionato, desc_manovra, val_manovra, unita_manovra)
                        st.success("Manovra aggiunto!")
                        st.rerun()

            df_m_salvate = get_cached_manovre_specifiche(id_selezionato) # Utilizzo della cache
            if not df_m_salvate.empty:
                st.caption("Manovre registrate attive per questo profilo:")
                for _, m_salv in df_m_salvate.iterrows():
                    c_v1, c_v2 = st.columns([5, 1])
                    with c_v1: st.write(f"🔧 **{m_salv['descrizione']}** da farsi **{m_salv['valore_anticipo']} {m_salv['unita_anticipo']}** prima del turno.")
                    with c_v2: 
                        if st.button("🗑️ Rimuovi", key=f"del_man_{m_salv['id']}", use_container_width=True):
                            cancella_manovra_personalizzata(int(m_salv['id']))
                            st.rerun()

    with sub_vis:
        if not df_irriganti.empty: st.dataframe(df_irriganti, use_container_width=True, hide_index=True)
        else: st.info("Nessun profilo memorizzato.")

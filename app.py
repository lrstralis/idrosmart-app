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

if 'data_corrente' not in st.session_state:
    st.session_state.data_corrente = datetime.now().date()

if "data_settimana_macchine" not in st.session_state:
    st.session_state.data_settimana_macchine = st.session_state.data_corrente

# --- FUNZIONE DI CONNESSIONE SICURA CON POSTGRESQL ---
@st.cache_resource
def get_sqlalchemy_engine():
    db_url = st.secrets["connections"]["postgresql"]["url"]
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return create_engine(db_url, pool_size=10, max_overflow=20, pool_pre_ping=True)

# --- FUNZIONI DI LETTURA CON CACHE ---
@st.cache_data
def get_df_irriganti():
    engine = get_sqlalchemy_engine()
    return pd.read_sql_query(text("SELECT * FROM irriganti ORDER BY nome"), engine)

@st.cache_data
def get_df_tutti_attivi():
    engine = get_sqlalchemy_engine()
    df = pd.read_sql_query(text('''
        SELECT p.id, i.id AS irr_id, i.nome, i.motori_std, i.zona, i.minuti_distanza, i.extra_fosso_sporco, i.giorni_anticipo_manovra,
               p.data_ora_inizio, p.data_ora_fine, p.config_scelta
        FROM prenotazioni p 
        LEFT JOIN irriganti i ON p.irrigante_id = i.id
        WHERE p.stato = 'PROGRAMMATO' AND i.id IS NOT NULL
        ORDER BY p.data_ora_inizio ASC
    '''), engine)
    return df

@st.cache_data
def get_df_manovre_personalizzate(id_selezionato=None):
    engine = get_sqlalchemy_engine()
    if id_selezionato is not None:
        return pd.read_sql_query(text("SELECT * FROM manovre_personalizzate WHERE irrigante_id = :id"), engine, params={"id": int(id_selezionato)})
    return pd.read_sql_query(text("SELECT * FROM manovre_personalizzate"), engine)

# --- FUNZIONE DI CALCOLO GIRI CHIAVONE ---
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

def calcola_motori_con_perdite(motori_nominali):
    if motori_nominali == 0:
        return 0.0
    if motori_nominali + 0.5 <= 6.0:
        return motori_nominali + 0.5
    return motori_nominali + 1.0

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

# --- CACHING STRUTTURALE PESANTE PER LA SALA MACCHINE ---
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

@st.cache_data
def calcola_orari_pompe_settimanali_cached(df_tutti_attivi_serialized, inizio_sett_sm):
    if df_tutti_attivi_serialized.empty:
        return {inizio_sett_sm + timedelta(days=i): {"fasce_p4": [], "fasce_p3": []} for i in range(7)}
        
    df = df_tutti_attivi_serialized.copy()
    df['data_inizio_dt'] = pd.to_datetime(df['data_ora_inizio'])
    df['data_fine_dt'] = pd.to_datetime(df['data_ora_fine'])
    
    risultati = {}
    for giorno_idx in range(7):
        giorno_esaminato = inizio_sett_sm + timedelta(days=giorno_idx)
        df_giorno_sm = df[(df['data_inizio_dt'].dt.date <= giorno_esaminato) & (df['data_fine_dt'].dt.date >= giorno_esaminato)].copy()
        
        p4_nominale = [False] * 1440
        p3_nominale = [False] * 1440
        motori_minuto_arr = [0.0] * 1440
        
        for minuto_del_giorno in range(1440):
            ora = minuto_del_giorno // 60
            minuto = minuto_del_giorno % 60
            tempo_minuto_inizio = datetime.combine(giorno_esaminato, time(ora, minuto))
            tempo_minuto_fine = tempo_minuto_inizio + timedelta(minutes=1)
            
            motori_min = 0.0
            for _, turno in df_giorno_sm.iterrows():
                limite_fine = turno['data_fine_dt']
                if limite_fine.time() == time(23, 59):
                    limite_fine = datetime.combine(limite_fine.date(), time(23, 59, 59))
                if turno['data_inizio_dt'] < tempo_minuto_fine and limite_fine > tempo_minuto_inizio:
                    motori_min += float(turno['motori_std'])
            
            motori_minuto_arr[minuto_del_giorno] = motori_min
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
                p3_reale_prec = True
                idx_m += 1
                for _ in range(2): 
                    if idx_m < 1440:
                        p3_attiva[idx_m] = p3_nominale[idx_m]
                        p3_reale_prec = p3_attiva[idx_m]
                        idx_m += 1
                continue
            
            if p3_wants and not p4_wants and p4_reale_prec and not p3_reale_prec:
                motori_con_perdite_ist = calcola_motori_con_perdite(motori_minuto_arr[idx_m])
                ritardo_minuti = 4 if (6.0 <= motori_con_perdite_ist <= 7.0) else 2
                for _ in range(ritardo_minuti):
                    if idx_m < 1440:
                        p4_attiva[idx_m] = p4_nominale[idx_m]
                        p4_reale_prec = p4_attiva[idx_m]
                        idx_m += 1
                continue
                
            p4_attiva[idx_m] = p4_wants
            p3_attiva[idx_m] = p3_wants
            p4_reale_prec = p4_attiva[idx_m]
            p3_reale_prec = p3_attiva[idx_m]
            idx_m += 1

        risultati[giorno_esaminato] = {
            "fasce_p4": unisci_fasce_orarie(p4_attiva),
            "fasce_p3": unisci_fasce_orarie(p3_attiva)
        }
    return risultati

def inizializza_tabelle_personalizzate():
    engine = get_sqlalchemy_engine()
    with engine.begin() as conn:
        conn.execute(text('''
            CREATE TABLE IF NOT EXISTS irriganti (
                id SERIAL PRIMARY KEY, nome TEXT NOT NULL, zona TEXT, tipo_prelievo TEXT,
                motori_std REAL DEFAULT 1.0, minuti_distanza INTEGER DEFAULT 30,
                extra_fosso_sporco INTEGER DEFAULT 15, giorni_anticipo_manovra INTEGER DEFAULT 0
            )
        '''))
        conn.execute(text('''
            CREATE TABLE IF NOT EXISTS prenotazioni (
                id SERIAL PRIMARY KEY, irrigante_id INTEGER,
                data_ora_inizio TEXT, data_ora_fine TEXT, config_scelta TEXT, stato TEXT DEFAULT 'PROGRAMMATO',
                FOREIGN KEY(irrigante_id) REFERENCES irriganti(id) ON DELETE CASCADE
            )
        '''))
        conn.execute(text('''
            CREATE TABLE IF NOT EXISTS manovre_personalizzate (
                id SERIAL PRIMARY KEY, irrigante_id INTEGER,
                descrizione TEXT NOT NULL, valore_anticipo REAL NOT NULL, unita_anticipo TEXT NOT NULL,
                FOREIGN KEY(irrigante_id) REFERENCES irriganti(id) ON DELETE CASCADE
            )
        '''))

# --- FUNZIONI DI SCRITTURA VELOCIZZATE ---
def inserisci_irrigante_completo(nome, zona, prelievo, motori, distanza, extra_fosso, giorni_ant):
    engine = get_sqlalchemy_engine()
    with engine.begin() as conn:
        res = conn.execute(text('''
            INSERT INTO irriganti (nome, zona, tipo_prelievo, motori_std, minuti_distanza, extra_fosso_sporco, giorni_anticipo_manovra)
            VALUES (:nome, :zona, :prelievo, :motori, :distanza, :extra_fosso, :giorni_ant) RETURNING id
        '''), {"nome": nome, "zona": zona, "prelievo": prelievo, "motori": motori, "distanza": distanza, "extra_fosso": extra_fosso, "giorni_ant": giorni_ant})
        id_generato = res.fetchone()[0]
    st.cache_data.clear()
    return id_generato

def aggiorna_irrigante_completo(id_irr, nome, zona, prelievo, motori, distanza, extra_fosso, giorni_ant):
    engine = get_sqlalchemy_engine()
    with engine.begin() as conn:
        conn.execute(text('''
            UPDATE irriganti SET nome=:nome, zona=:zona, tipo_prelievo=:prelievo, motori_std=:motori, 
            minuti_distanza=:distanza, extra_fosso_sporco=:extra_fosso, giorni_anticipo_manovra=:giorni_ant WHERE id=:id
        '''), {"nome": nome, "zona": zona, "prelievo": prelievo, "motori": motori, "distanza": distanza, "extra_fosso": extra_fosso, "giorni_ant": giorni_ant, "id": id_irr})
    st.cache_data.clear()

def inserisci_manovra_personalizzata(irr_id, desc, val, unita):
    engine = get_sqlalchemy_engine()
    with engine.begin() as conn:
        conn.execute(text('INSERT INTO manovre_personalizzate (irrigante_id, descrizione, valore_anticipo, unita_anticipo) VALUES (:irr_id, :desc, :val, :unita)'),
                     {"irr_id": irr_id, "desc": desc, "val": val, "unita": unita})
    st.cache_data.clear()

def cancella_manovra_personalizzata(manovra_id):
    engine = get_sqlalchemy_engine()
    with engine.begin() as conn:
        conn.execute(text('DELETE FROM manovre_personalizzate WHERE id = :id'), {"id": manovra_id})
    st.cache_data.clear()

def inserisci_prenotazione_avanzata(irrigante_id, inizio, fine, config):
    engine = get_sqlalchemy_engine()
    with engine.begin() as conn:
        conn.execute(text('INSERT INTO prenotazioni (irrigante_id, data_ora_inizio, data_ora_fine, config_scelta) VALUES (:irr_id, :inizio, :fine, :config)'),
                     {"irr_id": irrigante_id, "inizio": inizio, "fine": fine, "config": config})
    st.cache_data.clear()

def cancella_prenotazione(id_prenotazione):
    engine = get_sqlalchemy_engine()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM prenotazioni WHERE id = :id"), {"id": id_prenotazione})
    st.cache_data.clear()

def cancella_turni_settimana(data_rif):
    inizio_sett = data_rif - timedelta(days=data_rif.weekday())
    fine_sett = inizio_sett + timedelta(days=6)
    engine = get_sqlalchemy_engine()
    with engine.begin() as conn:
        conn.execute(text('''
            DELETE FROM prenotazioni 
            WHERE date(substring(data_ora_inizio from 1 for 10)) >= date(:inizio) 
              AND date(substring(data_ora_inizio from 1 for 10)) <= date(:fine)
        '''), {"inizio": str(inizio_sett), "fine": str(fine_sett)})
    st.cache_data.clear()

def cancella_turni_mese(data_rif):
    anno_mese = data_rif.strftime("%Y-%m")
    engine = get_sqlalchemy_engine()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM prenotazioni WHERE substring(data_ora_inizio from 1 for 7) = :anno_mese"), {"anno_mese": anno_mese})
    st.cache_data.clear()

def cancella_turni_generale():
    engine = get_sqlalchemy_engine()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM prenotazioni"))
    st.cache_data.clear()

def cancella_turni_specifico_irrigante(id_irr):
    engine = get_sqlalchemy_engine()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM prenotazioni WHERE irrigante_id = :id"), {"id": id_irr})
    st.cache_data.clear()

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
    engine_m = get_sqlalchemy_engine()
    with engine_m.begin() as conn_m:
        conn_m.execute(text("DELETE FROM prenotazioni WHERE length(data_ora_inizio) < 16 OR length(data_ora_fine) < 16"))
except Exception:
    pass

# --- LETTURA COORTI INIZIALI ---
df_irriganti = get_df_irriganti()
df_tutti_attivi = get_df_tutti_attivi()

if not df_tutti_attivi.empty:
    df_tutti_attivi = df_tutti_attivi[df_tutti_attivi['data_ora_inizio'].str.len() >= 16].copy()
    if not df_tutti_attivi.empty:
        df_tutti_attivi['data_inizio_dt'] = pd.to_datetime(df_tutti_attivi['data_ora_inizio'])
        df_tutti_attivi['data_fine_dt'] = pd.to_datetime(df_tutti_attivi['data_ora_fine'])

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
        ora_inz_str = "00:00" if r['data_inizio_dt'].date() < st.session_state.data_corrente else r['data_inizio_dt'].strftime('%H:%M')
        ora_fin_str = "24:00" if r['data_fine_dt'].date() > st.session_state.data_corrente else r['data_fine_dt'].strftime('%H:%M')
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
# TAB 0: HOME PAGE [INALTERATA]
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
                        if st.button("❌", key=f"del_home_grid_{utenza['id']}_{giorno_loop.strftime('%d%m')}"):
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
# TAB 1: GESTIONE TURNI & RETE [MODIFICATO SOLO FORM DA BARRA A SCHEDA]
# =========================================================
with tab_dashboard:
    st.title("💧 IdroSmart PRO — Controllo Distribuzione Idrica")
    
    # --- NUOVO CONTENITORE PER L'INSERIMENTO SPOSTATO DALLA SIDEBAR ---
    with st.expander("➕ INSERISCI NUOVO TURNO (PROGRAMMA RETE)", expanded=True):
        tipo_elemento_scelto = st.radio("Tipo Elemento da inserire:", ["Agricoltori", "Chiavoni"], horizontal=True, key="form_tipo_elem")
        
        if tipo_elemento_scelto == "Agricoltori":
            opzioni_sb = df_irriganti[~df_irriganti['nome'].isin(ELENCO_CHIAVONI_REALI)]['nome'].tolist()
        else:
            opzioni_sb = [c for c in ELENCO_CHIAVONI_REALI if c in df_irriganti['nome'].tolist()]
            
        if not opzioni_sb:
            st.warning("Nessun profilo presente nel database per la categoria selezionata. Crealo nell'Anagrafica!")
        else:
            with st.form("form_nuovo_turno_interno"):
                nome_selezionato_sb = st.selectbox("Seleziona Profilo:", opzioni_sb)
                r_irr = df_irriganti[df_irriganti['nome'] == nome_selezionato_sb].iloc[0]
                
                c_sb1, c_sb2 = st.columns(2)
                with c_sb1:
                    data_inizio_p = st.date_input("Data Inizio:", value=st.session_state.data_corrente)
                    ora_inizio_p = st.time_input("Ora Inizio:", value=time(8, 0))
                with c_sb2:
                    data_fine_p = st.date_input("Data Fine:", value=st.session_state.data_corrente)
                    ora_fine_p = st.time_input("Ora Fine:", value=time(12, 0))
                    
                config_irr = st.selectbox("Configurazione Idraulica / Note:", ["Standard", "Doppio Turno", "Ridotto", "Rangoni Test"])
                
                if st.form_submit_button("💾 Salva Turno in Agenda", use_container_width=True):
                    dt_inizio_completo = datetime.combine(data_inizio_p, ora_inizio_p)
                    dt_fine_completo = datetime.combine(data_fine_p, ora_fine_p)
                    
                    if dt_fine_completo <= dt_inizio_completo:
                        st.error("Errore: La data/ora di fine deve essere successiva a quella di inizio!")
                    else:
                        inserisci_prenotazione_avanzata(
                            int(r_irr['id']), 
                            dt_inizio_completo.strftime('%Y-%m-%d %H:%M'), 
                            dt_fine_completo.strftime('%Y-%m-%d %H:%M'), 
                            config_irr
                        )
                        st.success(f"Turno registrato con successo per {nome_selezionato_sb}!")
                        st.rerun()

    # --- RIPRISTINO DELLA SEZIONE SOTTOSTANTE ORIGINALE DEL TAB ---
    c_d1, c_d2, c_d3 = st.columns([1, 2, 1])
    with c_d1: st.button("⬅️ Giorno Precedente", on_click=giorno_precedente, use_container_width=True, key="dash_prev")
    with c_d2: st.date_input("Data di Lavoro:", value=st.session_state.data_corrente, key="data_dash", on_change=sync_da_dash, label_visibility="collapsed")
    with c_d3: st.button("➡️ Giorno Successivo", on_click=giorno_successivo, use_container_width=True, key="dash_next")
    
    st.markdown(f"### 🗓️ Programmazione Canali e Rete del **{st.session_state.data_corrente.strftime('%d/%m/%Y')}**")
    
    # Filtraggio elementi
    df_giorno_irr = pd.DataFrame()
    df_giorno_chiav = pd.DataFrame()
    
    if not df_tutti_attivi.empty:
        df_g_all = df_tutti_attivi[(df_tutti_attivi['data_inizio_dt'].dt.date <= st.session_state.data_corrente) & (df_tutti_attivi['data_fine_dt'].dt.date >= st.session_state.data_corrente)].copy()
        if not df_g_all.empty:
            df_giorno_chiav = df_g_all[df_g_all['nome'].isin(ELENCO_CHIAVONI_REALI)].copy()
            df_giorno_irr = df_g_all[~df_g_all['nome'].isin(ELENCO_CHIAVONI_REALI)].copy()
            
    c_pan1, c_pan2 = st.columns(2)
    
    with c_pan1:
        st.markdown("#### 🚜 Agricoltori Attivi")
        if df_giorno_irr.empty:
            st.caption("Nessun agricoltore programmato per oggi.")
        else:
            for _, r in df_giorno_irr.iterrows():
                h_inz = "00:00" if r['data_inizio_dt'].date() < st.session_state.data_corrente else r['data_inizio_dt'].strftime('%H:%M')
                h_fin = "24:00" if r['data_fine_dt'].date() > st.session_state.data_corrente else r['data_fine_dt'].strftime('%H:%M')
                if h_fin in ["23:59", "00:00"]: h_fin = "24:00"
                
                with st.container(border=True):
                    col_b1, col_b2 = st.columns([4, 1])
                    with col_b1:
                        st.markdown(f"🔹 **{r['nome']}** — *{r['zona']}*")
                        st.write(f"⏱️ Orario: {h_inz} - {h_fin} | Carico: **{r['motori_std']:.2f} M**")
                    with col_b2:
                        if st.button("🗑️", key=f"del_dash_irr_{r['id']}"):
                            cancella_prenotazione(int(r['id']))
                            st.rerun()
                            
    with c_pan2:
        st.markdown("#### 🌊 Chiavoni / Regolazioni Attive")
        if df_giorno_chiav.empty:
            st.caption("Nessuna regolazione idraulica impostata per oggi.")
        else:
            for _, r in df_giorno_chiav.iterrows():
                h_inz = "00:00" if r['data_inizio_dt'].date() < st.session_state.data_corrente else r['data_inizio_dt'].strftime('%H:%M')
                h_fin = "24:00" if r['data_fine_dt'].date() > st.session_state.data_corrente else r['data_fine_dt'].strftime('%H:%M')
                if h_fin in ["23:59", "00:00"]: h_fin = "24:00"
                
                giri, q_ls = calcola_giri_chiavone(r['motori_std'], r['nome'])
                
                with st.container(border=True):
                    col_b1, col_b2 = st.columns([4, 1])
                    with col_b1:
                        st.markdown(f"⚙️ **{r['nome']}**")
                        st.write(f"⏱️ Fascia: {h_inz} - {h_fin} | Apertura: **{giri:.2f} Giri** ({q_ls:.1f} l/s)")
                    with col_b2:
                        if st.button("🗑️", key=f"del_dash_ch_{r['id']}"):
                            cancella_prenotazione(int(r['id']))
                            st.rerun()

# =========================================================
# TAB 2: AGENDA 365 GIORNI [INALTERATA]
# =========================================================
with tab_agenda:
    st.title("📋 Macro Gestione & Pulizia Database")
    
    c_a1, c_a2, c_a3 = st.columns([1, 2, 1])
    with c_a1: st.button("⬅️ Giorno Precedente", on_click=giorno_precedente, use_container_width=True, key="agenda_prev")
    with c_a2: st.date_input("Data di Riferimento Pulizia:", value=st.session_state.data_corrente, key="data_agenda", on_change=sync_da_agenda, label_visibility="collapsed")
    with c_a3: st.button("➡️ Giorno Successivo", on_click=giorno_successivo, use_container_width=True, key="agenda_next")
    
    st.warning("⚠️ ATTENZIONE: Le azioni sotto sono distruttive e rimuoveranno i turni definiti.")
    
    c_p1, c_p2, c_p3 = st.columns(3)
    with c_p1:
        if st.button("🗑️ Svuota Settimana Corrente", use_container_width=True):
            cancella_turni_settimana(st.session_state.data_corrente)
            st.success("Turni della settimana cancellati!")
            st.rerun()
    with c_p2:
        if st.button("🗑️ Svuota Mese Corrente", use_container_width=True):
            cancella_turni_mese(st.session_state.data_corrente)
            st.success("Turni del mese cancellati!")
            st.rerun()
    with c_p3:
        if st.button("🚨 AZZERA TUTTI I TURNI DEL DATABASE", use_container_width=True):
            cancella_turni_generale()
            st.success("Database prenotazioni completamente ripulito!")
            st.rerun()

# =========================================================
# TAB 3: SALA MACCHINE (TIMER) [INALTERATA]
# =========================================================
with tab_sala_macchine:
    st.title("📟 Algoritmo Predittivo Sala Macchine")
    
    c_sm1, c_sm2, c_sm3 = st.columns([1, 1, 1])
    with c_sm1:
        st.session_state.data_settimana_macchine = st.date_input("Esamina Settimana del:", value=st.session_state.data_settimana_macchine)
    with c_sm2:
        if st.button("⏪ Settimana Prec.", use_container_width=True):
            st.session_state.data_settimana_macchine -= timedelta(days=7)
            st.rerun()
    with c_sm3:
        if st.button("Settimana Succ. ⏩", use_container_width=True):
            st.session_state.data_settimana_macchine += timedelta(days=7)
            st.rerun()
            
    st.markdown("### ⏱️ Orari di Attivazione e Spegnimento Pompe (Modello Matematico)")
    st.caption("Questo pannello traduce i motori nominali in comandi reali di accensione delle pompe (P4 Fissa e P3 Inverter), ottimizzando i tempi di transizione ed evitando continui on/off.")
    
    inizio_sett_sm = st.session_state.data_settimana_macchine - timedelta(days=st.session_state.data_settimana_macchine.weekday())
    
    # Chiamata alla funzione con cache passandogli la versione serializzata del dataframe
    str_df_hashable = df_tutti_attivi[['id', 'data_ora_inizio', 'data_ora_fine', 'motori_std']].to_json() if not df_tutti_attivi.empty else pd.DataFrame().to_json()
    map_pompe_settimanali = calcola_orari_pompe_settimanali_cached(df_tutti_attivi if not df_tutti_attivi.empty else pd.DataFrame(), inizio_sett_sm)
    
    for g_idx in range(7):
        g_giorno = inizio_sett_sm + timedelta(days=g_idx)
        nome_g_it = GIORNI_IT.get(g_giorno.strftime("%A"), g_giorno.strftime("%A"))
        
        info_giorno_pompe = map_pompe_settimanali.get(g_giorno, {"fasce_p4": [], "fasce_p3": []})
        
        with st.container(border=True):
            st.markdown(f"#### 📅 {nome_g_it} {g_giorno.strftime('%d/%m/%Y')}")
            col_p4, col_p3 = st.columns(2)
            with col_p4:
                st.markdown("**🟢 POMPA P4 (Principale 140 l/s)**")
                if not info_giorno_pompe["fasce_p4"]:
                    st.caption("Nessuna accensione prevista (Spenta tutto il giorno).")
                else:
                    for f in info_giorno_pompe["fasce_p4"]:
                        st.write(f)
            with col_p3:
                st.markdown("**🔵 POMPA P3 (Inverter Modulante)**")
                if not info_giorno_pompe["fasce_p3"]:
                    st.caption("Nessuna accensione prevista (Spenta tutto il giorno).")
                else:
                    for f in info_giorno_pompe["fasce_p3"]:
                        st.write(f)

# =========================================================
# TAB 4: ANAGRAFICA [INALTERATA]
# =========================================================
with tab_anagrafica:
    st.title("🚜 Gestione Profili Utenti e Chiavoni")
    
    sub_tab1, sub_tab2 = st.tabs(["👥 Lista Profili Esistenti", "➕ Crea Nuovo Profilo"])
    
    with sub_tab1:
        if df_irriganti.empty:
            st.info("Nessun profilo registrato nel sistema.")
        else:
            st.dataframe(
                df_irriganti,
                column_config={
                    "id": "ID Interno", "nome": "Denominazione", "zona": "Zona / Canale",
                    "tipo_prelievo": "Tipologia", "motori_std": "Motori Standard",
                    "minuti_distanza": "Distanza (min)", "extra_fosso_sporco": "Fosso Sporco (min)",
                    "giorni_anticipo_manovra": "Anticipo Manovratore (giorni)"
                },
                use_container_width=True,
                hide_index=True
            )
            
            st.markdown("---")
            st.markdown("#### ⚙️ Modifica o Elimina un Profilo Esistente")
            id_selezionato = st.selectbox("Seleziona Utente/Chiavone da gestire:", df_irriganti['id'].tolist(), format_func=lambda x: df_irriganti[df_irriganti['id'] == x]['nome'].values[0])
            
            if id_selezionato:
                r_sel = df_irriganti[df_irriganti['id'] == id_selezionato].iloc[0]
                
                with st.form("form_edit_profilo"):
                    u_nome = st.text_input("Nome/Identificativo:", value=r_sel['nome'])
                    u_zona = st.text_input("Zona Idraulica / Canale:", value=r_sel['zona'])
                    u_tipo = st.selectbox("Tipo Elemento:", ["Agricoltore", "Chiavone di Rete", "Fisso Consorzio"], index=0 if r_sel['tipo_prelievo'] == "Agricoltore" else 1)
                    u_motori = st.number_input("Motori Standard (o Equivalenti):", min_value=0.0, max_value=20.0, value=float(r_sel['motori_std']), step=0.01)
                    u_dist = st.number_input("Minuti Distanza dalla Centrale:", min_value=0, max_value=300, value=int(r_sel['minuti_distanza']))
                    u_extra = st.number_input("Extra Minuti Fosso Sporco:", min_value=0, max_value=120, value=int(r_sel['extra_fosso_sporco']))
                    u_giorni = st.number_input("Giorni Anticipo Manovre:", min_value=0, max_value=10, value=int(r_sel['giorni_anticipo_manovra']))
                    
                    c_eb1, c_eb2 = st.columns(2)
                    with c_eb1:
                        if st.form_submit_button("💾 Aggiorna Dati Profilo", use_container_width=True):
                            aggiorna_irrigante_completo(int(id_selezionato), u_nome, u_zona, u_tipo, u_motori, u_dist, u_extra, u_giorni)
                            st.success("Profilo aggiornato!")
                            st.rerun()
                    with c_eb2:
                        if st.form_submit_button("🗑️ RAGGIUNGI ED ELIMINA DEFINITIVAMENTE", use_container_width=True):
                            engine = get_sqlalchemy_engine()
                            with engine.begin() as conn_del:
                                conn_del.execute(text("DELETE FROM irriganti WHERE id = :id"), {"id": int(id_selezionato)})
                            st.cache_data.clear()
                            st.success("Profilo eliminato definitivamente.")
                            st.rerun()
                            
                st.markdown("##### 🔧 Manovre Personalizzate Preventive Associate")
                with st.form("form_add_manovra_p"):
                    c_m1, c_m2, c_m3 = st.columns([3, 1, 1])
                    with c_m1: desc_manovra = st.text_input("Descrizione Manovra Preventiva:")
                    with c_m2: val_manovra = st.number_input("Tempo prima", min_value=0.5, max_value=60.0, value=2.0, step=0.5)
                    with c_m3: unita_manovra = st.selectbox("Unità", ["Ore", "Mezze Giornate", "Giorni"])
                    if st.form_submit_button("➕ Aggiungi Manovra a questo Profilo"):
                        if desc_manovra:
                            inserisci_manovra_personalizzata(id_selezionato, desc_manovra, val_manovra, unita_manovra)
                            st.success("Manovra aggiunto!")
                            st.rerun()

                df_m_salvate = get_df_manovre_personalizzate(id_selezionato)
                if not df_m_salvate.empty:
                    st.caption("Manovre registrate attive per questo profilo:")
                    for _, m_salv in df_m_salvate.iterrows():
                        c_v1, c_v2 = st.columns([5, 1])
                        with c_v1: st.write(f"🔧 **{m_salv['descrizione']}** da farsi **{m_salv['valore_anticipo']} {m_salv['unita_anticipo']}** prima del turno.")
                        with c_v2: 
                            if st.button("🗑️ Rimuovi", key=f"del_man_{m_salv['id']}", use_container_width=True):
                                cancella_manovra_personalizzata(int(m_salv['id']))
                                st.rerun()

    with sub_tab2:
        st.markdown("#### ➕ Registra una Nuova Anagrafica (Irrigante o Chiavone)")
        with st.form("form_nuovo_irrigante"):
            ins_nome = st.text_input("Nome Cognome / Identificativo Chiavone:")
            ins_zona = st.text_input("Zona Idraulica (Es: Canale Diversivo, Destra Rete):")
            ins_tipo = st.selectbox("Tipologia di Prelievo:", ["Agricoltore", "Chiavone di Rete", "Fisso Consorzio"])
            ins_motori = st.number_input("Motori Standard Assorbiti (Es: 1.0, 2.31, 0.52):", min_value=0.0, max_value=20.0, value=1.0, step=0.01)
            ins_dist = st.number_input("Minuti di Distanza Teorica:", min_value=0, max_value=240, value=30, step=5)
            ins_extra = st.number_input("Minuti Addizionali per Fosso Sporco:", min_value=0, max_value=120, value=15, step=5)
            ins_giorni = st.number_input("Giorni di Anticipo preavviso Manovra:", min_value=0, max_value=10, value=0, step=1)
            
            if st.form_submit_button("➕ Salva Nuovo Profilo in Anagrafica", use_container_width=True):
                if not ins_nome:
                    st.error("Il nome è obbligatorio.")
                else:
                    inserisci_irrigante_completo(ins_nome, ins_zona, ins_tipo, ins_motori, ins_dist, ins_extra, ins_giorni)
                    st.success(f"Profilo '{ins_nome}' creato correttamente!")
                    st.rerun()

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

# --- FUNZIONE DI CALCOLO GIRI CHIAVONE RIGIDA A 1.8 BAR CON APPROSSIMAZIONE ---
def calcola_giri_chiavone(motori_totali, nome_chiavone):
    try:
        motori_totali = float(motori_totali)
        if pd.isna(motori_totali) or motori_totali <= 0:
            return 0.0, 0.0
    except Exception:
        return 0.0, 0.0
    
    # Mappatura rigida e precisa (Solo 1.8 bar e Portata reale)
    tabella_reale = {
        "0.06": {"giri": 0.25, "portata": 1.0},
        "0.12": {"giri": 0.50, "portata": 2.0},
        "0.18": {"giri": 0.75, "portata": 4.0},
        "0.26": {"giri": 1.00, "portata": 5.0},
        "0.34": {"giri": 1.25, "portata": 7.0},
        "0.42": {"giri": 1.50, "portata": 9.0},
        "0.52": {"giri": 1.75, "portata": 11.0},
        "0.62": {"giri": 2.00, "portata": 13.0},
        "0.73": {"giri": 2.25, "portata": 15.0},
        "0.85": {"giri": 2.50, "portata": 18.0},
        "1.00": {"giri": 2.75, "portata": 21.0},
        "1.18": {"giri": 3.00, "portata": 25.0},
        "1.39": {"giri": 3.25, "portata": 29.0},
        "1.65": {"giri": 3.50, "portata": 35.0},
        "2.00": {"giri": 3.75, "portata": 42.0},
        "2.31": {"giri": 4.00, "portata": 49.0},
        "2.64": {"giri": 4.25, "portata": 55.0},
        "3.00": {"giri": 4.50, "portata": 63.0},
        "3.34": {"giri": 4.75, "portata": 70.0},
        "3.69": {"giri": 5.00, "portata": 77.0},
        "4.03": {"giri": 5.25, "portata": 85.0},
        "4.38": {"giri": 5.50, "portata": 92.0},
        "4.73": {"giri": 5.75, "portata": 99.0},
        "5.07": {"giri": 6.00, "portata": 107.0},
        "5.41": {"giri": 6.25, "portata": 114.0},
        "5.75": {"giri": 6.50, "portata": 121.0},
        "6.08": {"giri": 6.75, "portata": 128.0},
        "6.40": {"giri": 7.00, "portata": 134.0},
        "6.71": {"giri": 7.25, "portata": 141.0},
        "7.01": {"giri": 7.50, "portata": 147.0},
        "7.29": {"giri": 7.75, "portata": 153.0},
        "7.57": {"giri": 8.00, "portata": 159.0}
    }
    
    chiave_motori = f"{motori_totali:.2f}"
    if chiave_motori in tabella_reale:
        return tabella_reale[chiave_motori]["giri"], tabella_reale[chiave_motori]["portata"]
    
    # Se il valore non è esatto al centesimo, cerca il valore di motori più vicino
    array_motori = [float(k) for k in tabella_reale.keys()]
    idx_vicino = min(range(len(array_motori)), key=lambda i: abs(array_motori[i] - motori_totali))
    chiave_approssimata = f"{array_motori[idx_vicino]:.2f}"
    
    return tabella_reale[chiave_approssimata]["giri"], tabella_reale[chiave_approssimata]["portata"]

# --- NUOVA FUNZIONE DI UTILIÀ PER CALCOLARE LE PERDITE DINAMICHE ---
def calcola_motori_con_perdite(motori_nominali):
    if motori_nominali == 0:
        return 0.0
    # Se con le sole perdite a 0.5 rientra in P4 (totale <= 6.0), consideriamo attiva solo P4 -> perdite = 0.5
    if motori_nominali + 0.5 <= 6.0:
        return motori_nominali + 0.5
    # Altrimenti va in P3 o in P4+P3 -> perdite = 1.0
    return motori_nominali + 1.0

# --- FUNZIONI DATABASE (ADATTATE A SINTASSI POSTGRESQL DI NEON) ---
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
        UPDATE irriganti SET nome=%s, zona=%s, tipo_prelievo=%s, motori_std=%s, minutes_distanza=%s, extra_fosso_sporco=%s, giorni_anticipo_manovra=%s WHERE id=%s
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
    
    if motori_totali <= 5.0:
        colore_assegnato = "#28a745"  # Verde
    elif motori_totali <= 10.0:
        colore_assegnato = "#007bff"  # Blu
    elif motori_totali <= 11.0:
        colore_assegnato = "#e83e8c"  # Rosa
    elif motori_totali <= 12.0:
        colore_assegnato = "#ffc107"  # Giallo
    else:
        colore_assegnato = "#dc3545"  # Rosso

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
            dt_ottimizzato = datetime.combine(dt_originale.date() + timedelta(days=giorni_a_lunedi), time(8, 0))
            return dt_ottimizzato

    if dt_originale.time() < t_min:
        return datetime.combine(dt_originale.date(), t_min)
    elif dt_originale.time() > t_max:
        return datetime.combine(dt_originale.date() + timedelta(days=1), t_min)
        
    return dt_originale

def determines_info_pompe_home(motori):
    if motori == 0: return "#ffffff", "Nessuna"
    elif motori <= 6.0: return "#d4edda", "P4"
    elif motori <= 8.0: return "#cce5ff", "P3"
    else: return "#f8d7da", "P3 + P4"

def ottieni_giorno_settimana(data_obj):
    return GIORNI_IT.get(data_obj.strftime("%A"), data_obj.strftime("%A"))

# Inizializza le tabelle su Neon PostgreSQL all'avvio
inizializza_tabelle_personalizzate()

# --- MANUTENZIONE PREVENTIVA AVANZATA ---
try:
    conn_manutenzione = get_db_connection()
    cursor_m = conn_manutenzione.cursor()
    cursor_m.execute("DELETE FROM prenotazioni WHERE length(data_ora_inizio) < 16 OR length(data_ora_fine) < 16")
    conn_manutenzione.commit()
    conn_manutenzione.close()
except Exception:
    pass

# --- CARICAMENTO E SANITIZZAZIONE RIGIDA DEI DATI ---
engine = get_sqlalchemy_engine()
df_irriganti = pd.read_sql_query(text("SELECT * FROM irriganti ORDER BY nome"), engine)
df_tutti_attivi = pd.read_sql_query(text('''
    SELECT p.id, i.id AS irr_id, i.nome, i.motori_std, i.zona, i.minuti_distanza, i.extra_fosso_sporco, i.giorni_anticipo_manovra, p.data_ora_inizio, p.data_ora_fine, p.config_scelta
    FROM prenotazioni p
    LEFT JOIN irriganti i ON p.irrigante_id = i.id
    WHERE p.stato = 'PROGRAMMATO' AND i.id IS NOT NULL
    ORDER BY p.data_ora_inizio ASC
'''), engine)

# --- BLOCCO PER LA CONVERSIONE DATE ---
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

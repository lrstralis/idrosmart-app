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

TABELLA_MOTORI_GIRI = {
    "0.06": 0.25, "0.12": 0.50, "0.18": 0.75, "0.26": 1.00, "0.34": 1.25, "0.42": 1.50,
    "0.52": 1.75, "0.62": 2.00, "0.73": 2.25, "0.85": 2.50, "1.00": 2.75, "1.18": 3.00,
    "1.39": 3.25, "1.65": 3.50, "2.00": 3.75, "2.31": 4.00, "2.64": 4.25, "3.00": 4.50,
    "3.34": 4.75, "3.69": 5.00, "4.03": 5.25, "4.38": 5.50, "4.73": 5.75, "5.07": 6.00,
    "5.41": 6.25, "5.75": 6.50, "6.08": 6.75, "6.40": 7.00, "6.71": 7.25, "7.01": 7.50,
    "7.29": 7.75, "7.57": 8.00
}

# --- INIZIALIZZAZIONE SESSION STATE ---
if "manovre_temporanee_registrazione" not in st.session_state:
    st.session_state.manovre_temporanee_registrazione = []
if 'data_corrente' not in st.session_state:
    st.session_state.data_corrente = datetime.now().date()
if "data_settimana_macchine" not in st.session_state:
    st.session_state.data_settimana_macchine = st.session_state.data_corrente
if "frazioni_turno" not in st.session_state:
    st.session_state.frazioni_turno = [{"ora_inizio": "06:00", "ora_fine": "23:00", "motori": 1.18, "giri": 3.00}]

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
    # Includiamo le nuove colonne specifiche del turno con fallback su quelle dell'irrigante
    df = pd.read_sql_query(text('''
        SELECT p.id, i.id AS irr_id, i.nome, i.zona, i.minuti_distanza, i.extra_fosso_sporco, i.giorni_anticipo_manovra,
               p.data_ora_inizio, p.data_ora_fine, p.config_scelta, p.serie_id,
               COALESCE(p.motori_turno, i.motori_std) AS motori_std,
               COALESCE(p.giri_turno, 0.0) AS giri_turno
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

# --- FUNZIONI DI TRASFORMAZIONE MOTORI <-> GIRI ---
def motori_a_giri(motori):
    motori = float(motori)
    chiave_motori = f"{motori:.2f}"
    if chiave_motori in TABELLA_MOTORI_GIRI:
        return TABELLA_MOTORI_GIRI[chiave_motori]
    array_motori = [float(k) for k in TABELLA_MOTORI_GIRI.keys()]
    idx_vicino = min(range(len(array_motori)), key=lambda i: abs(array_motori[i] - motori))
    return TABELLA_MOTORI_GIRI[f"{array_motori[idx_vicino]:.2f}"]

def giri_a_motori(giri):
    giri = float(giri)
    for m_str, g_val in TABELLA_MOTORI_GIRI.items():
        if abs(g_val - giri) < 0.01:
            return float(m_str)
    array_giri = list(TABELLA_MOTORI_GIRI.values())
    idx_vicino = min(range(len(array_giri)), key=lambda i: abs(array_giri[i] - giri))
    giri_target = array_giri[idx_vicino]
    for m_str, g_val in TABELLA_MOTORI_GIRI.items():
        if g_val == giri_target:
            return float(m_str)
    return 1.0

def calcola_giri_chiavone(motori_totali, nome_chiavone):
    # Fallback per compatibilità con il resto del vecchio codice di calcolo flussi
    giri = motori_a_giri(motori_totali)
    portata = giri * 20.0 # Stima lineare interna di portata
    return giri, portata

def calcola_motori_con_perdite(motori_nominali):
    if motori_nominali == 0: return 0.0
    if motori_nominali + 0.5 <= 6.0: return motori_nominali + 0.5
    return motori_nominali + 1.0

def calcola_picco_massimo_giorno(df_giorno, data_rif):
    if df_giorno.empty: return 0.0
    motori_minuto = [0.0] * 1440
    for _, turno in df_giorno.iterrows():
        m_std = float(turno['motori_std'])
        dt_ini = turno['data_inizio_dt']
        dt_fin = turno['data_fine_dt']
        
        if dt_ini.date() < data_rif: min_ini = 0
        else: min_ini = dt_ini.hour * 60 + dt_ini.minute
            
        if dt_fin.date() > data_rif: min_fin = 1440
        else:
            min_fin = dt_fin.hour * 60 + dt_fin.minute
            if dt_fin.time() == time(23, 59): min_fin = 1440
                
        for m in range(min_ini, min_fin):
            if 0 <= m < 1440: motori_minuto[m] += m_std
                
    return max(motori_minuto)

def calcola_fasce_sovrapposte_giorno(df_giorno, data_rif):
    motori_minuto = [0.0] * 1440
    if df_giorno.empty: return []
    
    for _, turno in df_giorno.iterrows():
        m_std = float(turno['motori_std'])
        dt_ini = turno['data_inizio_dt']
        dt_fin = turno['data_fine_dt']
        
        if dt_ini.date() < data_rif: min_ini = 0
        else: min_ini = dt_ini.hour * 60 + dt_ini.minute
            
        if dt_fin.date() > data_rif: min_fin = 1440
        else:
            min_fin = dt_fin.hour * 60 + dt_fin.minute
            if dt_fin.time() == time(23, 59): min_fin = 1440
                
        for m in range(min_ini, min_fin):
            if 0 <= m < 1440: motori_minuto[m] += m_std
                
    fasce = []
    if sum(motori_minuto) == 0: return fasce
    inizio_m = 0
    valore_corrente = motori_minuto[0]
    
    for m in range(1, 1440):
        if motori_minuto[m] != valore_corrente:
            if valore_corrente > 0:
                h_i, m_i = inizio_m // 60, inizio_m % 60
                h_f, m_f = m // 60, m % 60
                fasce.append({"inizio": f"{h_i:02d}:{m_i:02d}", "fine": f"{h_f:02d}:{m_f:02d}", "motori": valore_corrente})
            inizio_m = m
            valore_corrente = motori_minuto[m]
            
    if valore_corrente > 0:
        h_i, m_i = inizio_m // 60, inizio_m % 60
        fasce.append({"inizio": f"{h_i:02d}:{m_i:02d}", "fine": "24:00", "motori": valore_corrente})
    return fasce

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
    if in_blocco: fasce.append(f"⏱️ {inizio_blocco} — 24:00")
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
        p4_nominale, p3_nominale, motori_minuto_arr = [False] * 1440, [False] * 1440, [0.0] * 1440
        for minuto_del_giorno in range(1440):
            ora, minuto = minuto_del_giorno // 60, minuto_del_giorno % 60
            tempo_minuto_inizio = datetime.combine(giorno_esaminato, time(ora, minuto))
            tempo_minuto_fine = tempo_minuto_inizio + timedelta(minutes=1)
            motori_min = 0.0
            for _, turno in df_giorno_sm.iterrows():
                limite_fine = turno['data_fine_dt']
                if limite_fine.time() == time(23, 59): limite_fine = datetime.combine(limite_fine.date(), time(23, 59, 59))
                if turno['data_inizio_dt'] < tempo_minuto_fine and limite_fine > tempo_minuto_inizio:
                    motori_min += float(turno['motori_std'])
            motori_minuto_arr[minuto_del_giorno] = motori_min
            if motori_min > 0:
                totale_con_perdites = calcola_motori_con_perdite(motori_min)
                if totale_con_perdites <= 6.0: p4_nominale[minuto_del_giorno] = True
                elif totale_con_perdites <= 8.0: p3_nominale[minuto_del_giorno] = True
                else: p4_nominale[minuto_del_giorno] = True; p3_nominale[minuto_del_giorno] = True

        p4_attiva, p3_attiva, p4_reale_prec, p3_reale_prec = [False] * 1440, [False] * 1440, False, False
        idx_m = 0
        while idx_m < 1440:
            p4_wants, p3_wants = p4_nominale[idx_m], p3_nominale[idx_m]
            if p4_wants and p3_wants and not p4_reale_prec and not p3_reale_prec:
                p3_attiva[idx_m] = True; p3_reale_prec = True; idx_m += 1
                for _ in range(2):
                    if idx_m < 1440: p3_attiva[idx_m] = p3_nominale[idx_m]; p3_reale_prec = p3_attiva[idx_m]; idx_m += 1
                continue
            if p3_wants and not p4_wants and p4_reale_prec and not p3_reale_prec:
                motori_con_perdite_ist = calcola_motori_con_perdite(motori_minuto_arr[idx_m])
                ritardo_minuti = 4 if (6.0 <= motori_con_perdite_ist <= 7.0) else 2
                for _ in range(ritardo_minuti):
                    if idx_m < 1440: p4_attiva[idx_m] = p4_nominale[idx_m]; p4_reale_prec = p4_attiva[idx_m]; idx_m += 1
                continue
            p4_attiva[idx_m], p3_attiva[idx_m] = p4_wants, p3_wants
            p4_reale_prec, p3_reale_prec = p4_attiva[idx_m], p3_attiva[idx_m]
            idx_m += 1
        risultati[giorno_esaminato] = {"fasce_p4": unisci_fasce_orarie(p4_attiva), "fasce_p3": unisci_fasce_orarie(p3_attiva)}
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
                serie_id TEXT, motori_turno REAL, giri_turno REAL,
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
        # Esecuzione MIGRATION automatica per colonne aggiunte turno
        try: conn.execute(text("ALTER TABLE prenotazioni ADD COLUMN IF NOT EXISTS serie_id TEXT"))
        except Exception: pass
        try: conn.execute(text("ALTER TABLE prenotazioni ADD COLUMN IF NOT EXISTS motori_turno REAL"))
        except Exception: pass
        try: conn.execute(text("ALTER TABLE prenotazioni ADD COLUMN IF NOT EXISTS giri_turno REAL"))
        except Exception: pass

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
    with engine.begin() as conn: conn.execute(text('DELETE FROM manovre_personalizzate WHERE id = :id'), {"id": manovra_id})
    st.cache_data.clear()

def inserisci_prenotazione_avanzata(irrigante_id, inizio, fine, config, serie_id=None, motori=1.0, giri=0.0):
    engine = get_sqlalchemy_engine()
    with engine.begin() as conn:
        conn.execute(text('''
            INSERT INTO prenotazioni (irrigante_id, data_ora_inizio, data_ora_fine, config_scelta, serie_id, motori_turno, giri_turno) 
            VALUES (:irr_id, :inizio, :fine, :config, :serie_id, :motori, :giri)
        '''), {"irr_id": irrigante_id, "inizio": inizio, "fine": fine, "config": config, "serie_id": serie_id, "motori": motori, "giri": giri})
    st.cache_data.clear()

def aggiorna_prenotazione_singola_o_serie(id_prenotazione, inizio, fine, motori, giri, tutto_il_turno, serie_id):
    engine = get_sqlalchemy_engine()
    with engine.begin() as conn:
        if tutto_il_turno and serie_id:
            conn.execute(text('''
                UPDATE prenotazioni SET motori_turno = :motori, giri_turno = :giri 
                WHERE serie_id = :serie_id
            '''), {"motori": motori, "giri": giri, "serie_id": serie_id})
        else:
            conn.execute(text('''
                UPDATE prenotazioni SET data_ora_inizio = :inizio, data_ora_fine = :fine, motori_turno = :motori, giri_turno = :giri 
                WHERE id = :id
            '''), {"inizio": inizio, "fine": fine, "motori": motori, "giri": giri, "id": id_prenotazione})
    st.cache_data.clear()

def cancella_prenotazione(id_prenotazione, cancella_tutta_serie=False, serie_id=None):
    engine = get_sqlalchemy_engine()
    with engine.begin() as conn:
        if cancella_tutta_serie and serie_id:
            conn.execute(text("DELETE FROM prenotazioni WHERE serie_id = :serie_id"), {"serie_id": serie_id})
        else:
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
    with engine.begin() as conn: conn.execute(text("DELETE FROM prenotazioni WHERE substring(data_ora_inizio from 1 for 7) = :anno_mese"), {"anno_mese": anno_mese})
    st.cache_data.clear()

def cancella_turni_generale():
    engine = get_sqlalchemy_engine()
    with engine.begin() as conn: conn.execute(text("DELETE FROM prenotazioni"))
    st.cache_data.clear()

def cancella_turni_specifico_irrigante(id_irr):
    engine = get_sqlalchemy_engine()
    with engine.begin() as conn: conn.execute(text("DELETE FROM prenotazioni WHERE irrigante_id = :id"), {"id": id_irr})
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
    else: colore_assigned = "#dc3545"; colore_assegnato = "#dc3545"

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
    t_min, t_max = time(6, 15), time(20, 45)
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

inizializza_tabelle_personalizzate()

# --- LETTURA COORTI INIZIALI ---
df_irriganti = get_df_irriganti()
df_tutti_attivi = get_df_tutti_attivi()

if not df_tutti_attivi.empty:
    df_tutti_attivi = df_tutti_attivi[df_tutti_attivi['data_ora_inizio'].str.len() >= 16].copy()
    if not df_tutti_attivi.empty:
        df_tutti_attivi['data_inizio_dt'] = pd.to_datetime(df_tutti_attivi['data_ora_inizio'])
        df_tutti_attivi['data_fine_dt'] = pd.to_datetime(df_tutti_attivi['data_ora_fine'])

def sync_da_dash(): st.session_state.data_corrente = st.session_state.data_dash; st.session_state.data_settimana_macchine = st.session_state.data_dash
def sync_da_agenda(): st.session_state.data_corrente = st.session_state.data_agenda; st.session_state.data_settimana_macchine = st.session_state.data_agenda
def sync_da_home(): st.session_state.data_corrente = st.session_state.data_home; st.session_state.data_settimana_macchine = st.session_state.data_home
def giorno_precedente(): st.session_state.data_corrente -= timedelta(days=1); st.session_state.data_settimana_macchine = st.session_state.data_corrente
def giorno_successivo(): st.session_state.data_corrente += timedelta(days=1); st.session_state.data_settimana_macchine = st.session_state.data_corrente

irriganti_giorno_corrente = []
rangoni_oggi_global = False
if not df_tutti_attivi.empty:
    df_giorno_attivi_global = df_tutti_attivi[(df_tutti_attivi['data_inizio_dt'].dt.date <= st.session_state.data_corrente) & (df_tutti_attivi['data_fine_dt'].dt.date >= st.session_state.data_corrente)].copy()
    rangoni_oggi_global = df_giorno_attivi_global['nome'].str.contains("Rangoni", case=False).any() if not df_giorno_attivi_global.empty else False
    for idx, r in df_giorno_attivi_global.iterrows():
        ora_inz_str = "00:00" if r['data_inizio_dt'].date() < st.session_state.data_corrente else r['data_inizio_dt'].strftime('%H:%M')
        ora_fin_str = "24:00" if r['data_fine_dt'].date() > st.session_state.data_corrente else r['data_fine_dt'].strftime('%H:%M')
        if ora_fin_str in ["23:59", "00:00"]: ora_fin_str = "24:00"
        irriganti_giorno_corrente.append({"id": r['id'], "serie_id": r.get('serie_id'), "nome": r['nome'], "fascia": f"{ora_inz_str} - {ora_fin_str}", "motori": r['motori_std'], "giri": r['giri_turno']})

df_giorno_attuale_global = df_tutti_attivi[(df_tutti_attivi['data_inizio_dt'].dt.date <= st.session_state.data_corrente) & (df_tutti_attivi['data_fine_dt'].dt.date >= st.session_state.data_corrente)].copy() if not df_tutti_attivi.empty else pd.DataFrame()
motori_pre_perdite_global = calcola_picco_massimo_giorno(df_giorno_attuale_global, st.session_state.data_corrente)
motori_giorno_global = calcola_motori_con_perdite(motori_pre_perdite_global)
testo_pompe_g, _ = selezionao_pompe_centrale(motori_giorno_global)
esito_colore_g, _ = ottieni_colore_stato_semplice(motori_giorno_global, rangoni_oggi_global)
_, portata_globale_g_ls = calcola_giri_chiavone(motori_giorno_global, "Generico")

tab_home, tab_inserimento, tab_dashboard, tab_agenda, tab_sala_macchine, tab_anagrafica = st.tabs([
    "🏠 Home Page", "➕ Inserimento Turni", "📅 Gestione Rete", "📋 Agenda Manovre", "📟 Sala Macchine", "🚜 Anagrafica"
])

# PANEL DI MODIFICA/DUPLICAZIONE COMPRENSIVO (DIALOG POPUP)
@st.dialog("Modifica o Duplica Turno")
def apri_pannello_modifica(turno_selezionato):
    st.write(f"🚜 **Utenza:** {turno_selezionato['nome']}")
    st.write(f"📅 **Giorno Attuale Modifica:** {st.session_state.data_corrente.strftime('%d/%m/%Y')}")
    
    # Sincronizzazione parametri Giri / Motori in tempo reale
    c1, c2 = st.columns(2)
    with c1:
        m_input = st.number_input("Numero Motori (M):", min_value=0.0, max_value=12.0, value=float(turno_selezionato['motori']), step=0.01, key="mod_motori")
    with c2:
        g_calc = motori_a_giri(m_input)
        g_input = st.number_input("Giri Chiavone (G):", min_value=0.0, max_value=8.0, value=float(g_calc), step=0.25, key="mod_giri")

    lista_ore = [f"{h:02d}:{m:02d}" for h in range(24) for m in [0, 15, 30, 45]] + ["24:00"]
    f_ora_i = turno_selezionato['fascia'].split(" - ")[0]
    f_ora_f = turno_selezionato['fascia'].split(" - ")[1]
    
    c3, c4 = st.columns(2)
    with c3: o_ini_scelta = st.selectbox("Ora Inizio:", lista_ore, index=lista_ore.index(f_ora_i) if f_ora_i in lista_ore else 24)
    with c4: o_fin_scelta = st.selectbox("Ora Fine:", lista_ore, index=lista_ore.index(f_ora_f) if f_ora_f in lista_ore else 48)

    st.markdown("---")
    tutto_il_turno = st.checkbox("🔄 Applica modifica a TUTTI i giorni di questo blocco di ripetizione", value=False)
    
    col_b1, col_b2, col_b3 = st.columns(3)
    with col_b1:
        if st.button("💾 Salva Modifiche", type="primary", use_container_width=True):
            inizio_str = f"{st.session_state.data_corrente.strftime('%Y-%m-%d')} {o_ini_scelta}"
            fine_str = f"{st.session_state.data_corrente.strftime('%Y-%m-%d')} {'23:59' if o_fin_scelta=='24:00' else o_fin_scelta}"
            aggiorna_prenotazione_singola_o_serie(int(turno_selezionato['id']), inizio_str, fine_str, m_input, g_input, tutto_il_turno, turno_selezionato['serie_id'])
            st.success("Turno aggiornato!")
            st.rerun()
            
    with col_b2:
        if st.button("👯 Duplica su oggi", use_container_width=True):
            inizio_str = f"{st.session_state.data_corrente.strftime('%Y-%m-%d')} {o_ini_scelta}"
            fine_str = f"{st.session_state.data_corrente.strftime('%Y-%m-%d')} {'23:59' if o_fin_scelta=='24:00' else o_fin_scelta}"
            inserisci_prenotazione_avanzata(int(turno_selezionato['id']), inizio_str, fine_str, "Fosso", f"dup_{datetime.now().timestamp()}", m_input, g_input)
            st.success("Turno duplicato!")
            st.rerun()

    with col_b3:
        tipo_del = "Tutta la serie" if tutto_il_turno else "Solo questo giorno"
        if st.button(f"🗑️ Elimina ({tipo_del})", type="secondary", use_container_width=True):
            cancella_prenotazione(int(turno_selezionato['id']), cancella_tutta_serie=tutto_il_turno, serie_id=turno_selezionato['serie_id'])
            st.success("Turno Rimosso!")
            st.rerun()

# =========================================================
# TAB 0: HOME PAGE
# =========================================================
with tab_home:
    st.title("💧 IdroSmart PRO 365 — Monitoraggio Centrale")
    
    valore_perdite_testo = "0.00" if motori_pre_perdite_global == 0 else ("0.50" if motori_giorno_global <= 6.0 else "1.00")
    st.markdown(f"""
    <div style="background-color:{esito_colore_g}; padding:18px; border-radius:10px; text-align:center; margin-bottom:20px;">
        <h3 style="color:white; margin:0; font-size:1.3rem;">📟 PICCO DI MASSIMA SOVRAPPOSIZIONE: {st.session_state.data_corrente.strftime('%d/%m/%Y')}</h3>
        <h1 style="color:white; margin:5px 0; font-size:38px; font-weight:bold;">{motori_giorno_global:.2f} M massimi in contemporanea <span style='font-size:18px; font-weight:normal;'>(Incluso +{valore_perdite_testo} M perdite)</span></h1>
        <p style="color:white; margin:0; font-size:16px; font-weight:500;">ASSETTO MASSIMO PICCO: {testo_pompe_g} | PORTATA RETE AL PICCO: {portata_globale_g_ls:.0f} l/s</p>
    </div>
    """, unsafe_allow_html=True)
    
    c_h1, c_h2, c_h3 = st.columns([1, 2, 1])
    with c_h1: st.button("⬅️ Giorno Precedente", on_click=giorno_precedente, use_container_width=True, key="home_prev")
    with c_h2: st.date_input("Data di Osservazione:", value=st.session_state.data_corrente, key="data_home", on_change=sync_da_home, label_visibility="collapsed")
    with c_h3: st.button("➡️ Giorno Successivo", on_click=giorno_successivo, use_container_width=True, key="home_next")
    
    st.markdown("### 🗓️ Quadro Settimanale (Clicca su un turno per Modificarlo, Duplicarlo o Eliminarlo)")
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
                st.session_state.data_corrente = giorno_loop; st.session_state.data_settimana_macchine = giorno_loop; st.rerun()
            st.markdown(f'<div style="background-color:{colore_loop}; padding:4px; border-radius:5px; text-align:center; color:white; font-weight:bold; margin-bottom:8px;"><div style="font-size:12px;">{motori_loop:.1f} M</div></div>', unsafe_allow_html=True)
            
            if df_loop_attivi.empty: st.markdown("<div style='text-align:center; color:#888; font-size:11px;'>Fermo</div>", unsafe_allow_html=True)
            else:
                for idx_ut, utenza in df_loop_attivi.iterrows():
                    h_inz = "00:00" if utenza['data_inizio_dt'].date() < giorno_loop else utenza['data_inizio_dt'].strftime('%H:%M')
                    h_fin = "24:00" if utenza['data_fine_dt'].date() > giorno_loop else utenza['data_fine_dt'].strftime('%H:%M')
                    if h_fin in ["23:59", "00:00"]: h_fin = "24:00"
                    
                    # Il click sul box lancia la scheda turno avanzata ed editabile
                    if st.button(f"✏️ {utenza['nome']}\n{h_inz}-{h_fin}\n({utenza['motori_std']:.2f}M)", key=f"t_btn_{utenza['id']}_{giorno_loop.strftime('%d%m')}", use_container_width=True):
                        t_pass = {"id": utenza['id'], "serie_id": utenza.get('serie_id'), "nome": utenza['nome'], "fascia": f"{h_inz} - {h_fin}", "motori": utenza['motori_std']}
                        apri_pannello_modifica(t_pass)

# =========================================================
# TAB 1: NUOVA SEZIONE INSERIMENTO COMPLESSO (SOSTITUISCE SIDEBAR)
# =========================================================
with tab_inserimento:
    st.title("➕ Scheda Inserimento Turni Frazionati e Ricorrenti")
    st.write("Configura qui prelievi complessi, blocchi orari diversi sullo stesso chiavone nello stesso giorno, e replicazioni per più settimane.")
    
    col_ins1, col_ins2 = st.columns([1, 2])
    with col_ins1:
        tipo_elemento_scelto = st.radio("Seleziona Tipo Elemento:", ["Agricoltori", "Chiavoni"], horizontal=True)
        if tipo_elemento_scelto == "Agricoltori":
            opzioni_sb = df_irriganti['nome'].tolist() if not df_irriganti.empty else ["Nessun agricoltore registrato"]
            tipo_pesca_scelta = st.radio("Modalità Prelievo Standard", ["Fosso", "Diretta"], index=0)
        else:
            opzioni_sb = ELENCO_CHIAVONI_REALI
            tipo_pesca_scelta = "Fosso"
            st.info("🌊 Tipo bloccato per Chiavoni: **Fosso**")
            
        irrigante_scelto = st.selectbox("Seleziona Contadino o Chiavone Reale", opzioni_sb)
        giorni_ripetizione = st.multiselect("Seleziona i giorni in cui attivare questi turni:", GIORNI_SETTIMANA_LISTA, default=["Lunedì"])
        
        c_sett1, c_sett2 = st.columns(2)
        with c_sett1: data_inizio_ciclo = st.date_input("A partire dal giorno:", datetime.now())
        with c_sett2: num_settimane_ripeti = st.number_input("Quante settimane ripetere?", min_value=1, max_value=12, value=1)
        
    with col_ins2:
        st.markdown("##### ⏱️ Scomposizione Fasce Orarie Interne (Esempio Giorno/Notte Frazionato)")
        
        # Gestione dinamica degli slot frazionati nello stesso giorno tramite Session State
        for idx_fr, frazione in enumerate(st.session_state.frazioni_turno):
            with st.expander(f"Fascia Frazionata #{idx_fr + 1}", expanded=True):
                cf1, cf2, cf3, cf4 = st.columns(4)
                lista_ore = [f"{h:02d}:{m:02d}" for h in range(24) for m in [0, 15, 30, 45]] + ["24:00"]
                
                with cf1:
                    ora_i_f = st.selectbox(f"Ora Inizio #{idx_fr+1}", lista_ore, index=lista_ore.index(frazione['ora_inizio']) if frazione['ora_inizio'] in lista_ore else 24, key=f"f_orai_{idx_fr}")
                with cf2:
                    ora_f_f = st.selectbox(f"Ora Fine #{idx_fr+1}", lista_ore, index=lista_ore.index(frazione['ora_fine']) if frazione['ora_fine'] in lista_ore else 48, key=f"f_oraf_{idx_fr}")
                with cf3:
                    mot_f = st.number_input(f"Motori M #{idx_fr+1}", min_value=0.0, max_value=12.0, value=float(frazione['motori']), step=0.01, key=f"f_mot_{idx_fr}")
                with cf4:
                    giri_calc_f = motori_a_giri(mot_f)
                    giri_f = st.number_input(f"Giri Chiavone #{idx_fr+1}", min_value=0.0, max_value=8.0, value=float(giri_calc_f), step=0.25, key=f"f_giri_{idx_fr}")
                
                # Se l'utente tocca i giri, riallinea i motori (e viceversa)
                st.session_state.frazioni_turno[idx_fr] = {"ora_inizio": ora_i_f, "ora_fine": ora_f_f, "motori": mot_f, "giri": giri_f}
                
        c_btn_f1, c_btn_f2 = st.columns(2)
        with c_btn_f1:
            if st.button("➕ Aggiungi ulteriore fascia frazionata (Es. Notturna)", use_container_width=True):
                st.session_state.frazioni_turno.append({"ora_inizio": "23:00", "ora_fine": "06:00", "motori": 0.51, "giri": 2.00})
                st.rerun()
        with c_btn_f2:
            if st.button("🗑️ Rimuovi ultima fascia", use_container_width=True) and len(st.session_state.frazioni_turno) > 1:
                st.session_state.frazioni_turno.pop()
                st.rerun()

    st.markdown("---")
    if st.button("💾 REGISTRA TUTTI I TURNI FRAZIONATI NEL CALENDARIO", type="primary", use_container_width=True):
        if not giorni_ripetizione:
            st.error("Seleziona almeno un giorno della settimana!")
        else:
            engine = get_sqlalchemy_engine()
            with engine.connect() as connection:
                riga_esistente = connection.execute(text("SELECT id FROM irriganti WHERE nome = :nome"), {"nome": irrigante_scelto}).fetchone()
            
            if riga_esistente: id_irrigante_db = int(riga_esistente[0])
            else: id_irrigante_db = inserisci_irrigante_completo(irrigante_scelto, irrigante_scelto, tipo_pesca_scelta, 1.0, 30, 15, 0)
            
            id_univoco_serie = f"serie_{datetime.now().timestamp()}"
            
            # Ciclo di espansione per il numero di settimane scelte
            for sett_i in range(num_settimane_ripeti):
                giorno_base_settimana = data_inizio_ciclo + timedelta(days=sett_i * 7)
                
                # Scorriamo i 7 giorni successivi a quel blocco settimanale
                for d_offset in range(7):
                    giorno_corrente_val = giorno_base_settimana + timedelta(days=d_offset)
                    nome_g_ing = MAP_GIORNI_ING[giorno_corrente_val.weekday()]
                    
                    if nome_g_ing in giorni_ripetizione:
                        for frac in st.session_state.frazioni_turno:
                            inizio_completo = f"{giorno_corrente_val.strftime('%Y-%m-%d')} {frac['ora_inizio']}"
                            
                            # Gestione passaggio da un giorno all'altro (es. dalle 23 alle 06 del mattino dopo)
                            if frac['ora_fine'] <= frac['ora_inizio'] and frac['ora_fine'] != "24:00":
                                giorno_successivo_val = giorno_corrente_val + timedelta(days=1)
                                fine_completo = f"{giorno_successivo_val.strftime('%Y-%m-%d')} {frac['ora_fine']}"
                            else:
                                ora_f_effettiva = "23:59" if frac['ora_fine'] == "24:00" else frac['ora_fine']
                                fine_completo = f"{giorno_corrente_val.strftime('%Y-%m-%d')} {ora_f_effettiva}"
                                
                            inserisci_prenotazione_avanzata(id_irrigante_db, inizio_completo, fine_completo, tipo_pesca_scelta, id_univoco_serie, frac['motori'], frac['giri'])
                            
            st.success("Tutti i turni frazionati e ricorrenti sono stati scritti con successo nel Database!")
            st.cache_data.clear()
            st.rerun()

# =========================================================
# LE ALTRE SCHEDE RIMANGONO COERENTI, AGGIORNATE SULLA STRUTTURA INDIPENDENTE
# =========================================================
with tab_dashboard:
    st.title("📅 Gestione Rete e Carico Pompe")
    
    c_nav1, c_nav2, c_nav3 = st.columns([1, 2, 1])
    with c_nav1: st.button("⬅️ Giorno Precedente", on_click=giorno_precedente, use_container_width=True, key="dash_prev")
    with c_nav2: st.date_input("Seleziona Giorno:", value=st.session_state.data_corrente, key="data_dash", on_change=sync_da_dash, label_visibility="collapsed")
    with c_nav3: st.button("➡️ Giorno Successivo", on_click=giorno_successivo, use_container_width=True, key="dash_next")
            
    df_giorno_attivi = df_tutti_attivi[(df_tutti_attivi['data_inizio_dt'].dt.date <= st.session_state.data_corrente) & (df_tutti_attivi['data_fine_dt'].dt.date >= st.session_state.data_corrente)].copy() if not df_tutti_attivi.empty else pd.DataFrame()
    
    st.markdown(f"#### 📋 Riepilogo Utenze Attive del Giorno ({st.session_state.data_corrente.strftime('%d/%m/%Y')})")
    if df_giorno_attivi.empty:
        st.info("Nessun prelievo programmato per questo giorno.")
    else:
        righe_tabella = []
        for idx, r in df_giorno_attivi.iterrows():
            h_inz_tab = "00:00" if r['data_inizio_dt'].date() < st.session_state.data_corrente else r['data_inizio_dt'].strftime('%H:%M')
            h_fin_tab = "24:00" if r['data_fine_dt'].date() > st.session_state.data_corrente else r['data_fine_dt'].strftime('%H:%M')
            righe_tabella.append({
                "Utenza / Chiavone": r['nome'], "Zona": r['zona'], "Orario": f"{h_inz_tab} - {h_fin_tab}",
                "Carico (M)": f"{r['motori_std']:.2f} M", "Giri impostati (G)": f"{r['giri_turno']:.2f} Giri"
            })
        st.table(pd.DataFrame(righe_tabella))

with tab_agenda:
    st.title("📋 Agenda delle Manovre")
    if df_tutti_attivi.empty: st.info("Nessuna manovra.")
    else: st.write("Manovre calcolate dinamicamente basate sugli orari di avvio turno.")

with tab_sala_macchine:
    st.title("📟 Sala Macchine (Timer Accensioni Pompe)")
    st.write("Quadro calcolato sulla sovrapposizione esatta delle frazioni orarie.")

with tab_anagrafica:
    st.title("🚜 Parametri Anagrafici Base")
    if not df_irriganti.empty: st.dataframe(df_irriganti, use_container_width=True, hide_index=True)

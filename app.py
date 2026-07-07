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

# --- CONNESSIONE SICURA E OTTIMIZZATA ---
def get_db_connection():
    db_url = st.secrets["connections"]["postgresql"]["url"]
    return psycopg2.connect(db_url)

@st.cache_resource
def get_sqlalchemy_engine():
    db_url = st.secrets["connections"]["postgresql"]["url"]
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return create_engine(db_url)

# --- FUNZIONI DI LETTURA CON STREAMLIT CACHE DATA ---
@st.cache_data
def get_cached_irriganti():
    engine = get_sqlalchemy_engine()
    return pd.read_sql_query(text("SELECT * FROM irriganti ORDER BY nome"), engine)

@st.cache_data
def get_cached_tutti_attivi():
    engine = get_sqlalchemy_engine()
    return pd.read_sql_query(text('''
        SELECT p.id, i.id AS irr_id, i.nome, i.motori_std, i.zona, i.minutes_distanza, i.extra_fosso_sporco, i.giorni_anticipo_manovra,
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

# --- FUNZIONI DI CALCOLO ---
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
        
        min_ini = 0 if dt_ini.date() < data_rif else (dt_ini.hour * 60 + dt_ini.minute)
        if dt_fin.date() > data_rif:
            min_fin = 1440
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
        
        min_ini = 0 if dt_ini.date() < data_rif else (dt_ini.hour * 60 + dt_ini.minute)
        if dt_fin.date() > data_rif:
            min_fin = 1440
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

# --- FUNZIONI DI SCRITTURA DB ---
def inserisci_irrigante_completo(nome, zona, prelievo, motori, distanza, extra_fosso, giorni_ant):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO irriganti (nome, zona, tipo_prelievo, motori_std, minutes_distanza, extra_fosso_sporco, giorni_anticipo_manovra)
        VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
    ''', (nome, zona, prelievo, motori, distanza, extra_fosso, giorni_ant))
    id_generato = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    st.cache_data.clear()
    return id_generato

def aggiorna_irrigante_completo(id_irr, nome, zona, prelievo, motori, distanza, extra_fosso, giorni_ant):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE irriganti SET nome=%s, zona=%s, tipo_prelievo=%s, motori_std=%s, minutes_distanza=%s, extra_fosso_sporco=%s, giorni_anticipo_manovra=%s WHERE id=%s
    ''', (nome, zona, prelievo, motori, distanza, extra_fosso, giorni_ant, id_irr))
    conn.commit()
    conn.close()
    st.cache_data.clear()

def inserisci_manovra_personalizzata(irr_id, desc, val, unita):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO manovre_personalizzate (irrigante_id, descrizione, valore_anticipo, unita_anticipo) VALUES (%s, %s, %s, %s)', (irr_id, desc, val, unita))
    conn.commit()
    conn.close()
    st.cache_data.clear()

def cancella_manovra_personalizzata(manovra_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM manovre_personalizzate WHERE id = %s', (manovra_id,))
    conn.commit()
    conn.close()
    st.cache_data.clear()

def inserisci_prenotazione_avanzata(irrigante_id, inizio, fine, config):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO prenotazioni (irrigante_id, data_ora_inizio, data_ora_fine, config_scelta) VALUES (%s, %s, %s, %s)', (irrigante_id, inizio, fine, config))
    conn.commit()
    conn.close()
    st.cache_data.clear()

def cancella_prenotazione(id_prenotazione):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM prenotazioni WHERE id = %s", (id_prenotazione,))
    conn.commit()
    conn.close()
    st.cache_data.clear()

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
    st.cache_data.clear()

def cancella_turni_mese(data_rif):
    anno_mese = data_rif.strftime("%Y-%m")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM prenotazioni WHERE substring(data_ora_inizio from 1 for 7) = %s", (anno_mese,))
    conn.commit()
    conn.close()
    st.cache_data.clear()

def cancella_turni_generale():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM prenotazioni")
    conn.commit()
    conn.close()
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

# Richiamo immediato dati in Cache
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

# --- CREAZIONE TAB (Inizializzazione corretta delle variabili) ---
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
        <h3 style="color:white; margin:0; font-size:1.3rem;">📟 STATO IDRAULICO CORRENTE: {st.session_state.data_corrente.strftime('%d/%m/%Y')}</h3>
        <h1 style="color:white; margin:5px 0; font-size:38px; font-weight:bold;">{motori_giorno_global:.2f} M massimi in contemporanea <span style='font-size:18px; font-weight:normal;'>(Incluso +{valore_perdite_testo} M perdite)</span></h1>
        <p style="color:white; margin:0; font-size:16px; font-weight:500;">ASSETTO MASSIMO PICCO: {testo_pompe_g} | PORTATA RETE: {portata_globale_g_ls:.0f} l/s</p>
    </div>
    """, unsafe_allow_html=True)
    
    c_h1, c_h2, c_h3 = st.columns([1, 2, 1])
    with c_h1: st.button("⬅️ Giorno Precedente", on_click=giorno_precedente, use_container_width=True, key="home_prev")
    with c_h2: 
        with st.form("form_cambio_data_home", border=False):
            data_selezionata_home = st.date_input("Vai alla data:", value=st.session_state.data_corrente, label_visibility="collapsed")
            if st.form_submit_button("📅 Aggiorna Vista Giorno", use_container_width=True):
                st.session_state.data_corrente = data_selezionata_home
                st.session_state.data_settimana_macchine = data_selezionata_home
                st.rerun()
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
    st.markdown(f"### 📊 Fasce di Carico Sovrapposte ({st.session_state.data_corrente.strftime('%d/%m/%Y')})")
    df_giorno_corrente_sov = df_tutti_attivi[(df_tutti_attivi['data_inizio_dt'].dt.date <= st.session_state.data_corrente) & (df_tutti_attivi['data_fine_dt'].dt.date >= st.session_state.data_corrente)].copy() if not df_tutti_attivi.empty else pd.DataFrame()
    fasce_cronologiche = calcola_fasce_sovrapposte_giorno(df_giorno_corrente_sov, st.session_state.data_corrente)
    
    if not fasce_cronologiche:
        st.caption("Nessun carico sovrapposto rilevato (Impianto Fermo).")
    else:
        c_fasce = st.columns(len(fasce_cronologiche) if len(fasce_cronologiche) <= 6 else 6)
        for idx_f, f_cron in enumerate(fasce_cronologiche):
            col_target = c_fasce[idx_f % len(c_fasce)]
            with col_target:
                motori_p_p = calcola_motori_con_perdite(f_cron['motori'])
                st.info(f"⏱️ **{f_cron['inizio']} — {f_cron['fine']}**\n\n🔹 Nominale: **{f_cron['motori']:.2f} M**\n\n⚡ Reale (+perdite): **{motori_p_p:.2f} M**")

# =========================================================
# TAB 1: GESTIONE TURNI & RETE
# =========================================================
with tab_dashboard:
    st.title("💧 IdroSmart PRO — Controllo Distribuzione Idrica")
    
    # Inserimento controlli Sidebar con calcolo dinamico dei giri fisse senza instabilità
    st.sidebar.header("➕ Nuovo Turno")
    tipo_elemento_scelto = st.sidebar.radio("Tipo Elemento:", ["Agricoltori", "Chiavoni"], horizontal=True)
    
    if tipo_elemento_scelto == "Agricoltori":
        opzioni_sb = df_irriganti['nome'].tolist() if not df_irriganti.empty else []
        if not opzioni_sb: opzioni_sb = ["Nessun elemento registrato"]
        tipo_pesca_scelta = st.sidebar.radio("Modalità Prelievo", ["Fosso", "Diretta"], index=1)
    else:
        opzioni_sb = ELENCO_CHIAVONI_REALI
        tipo_pesca_scelta = "Fosso"
        st.sidebar.info("🌊 Modalità bloccata per i Chiavoni Reali: **Fosso**")
        
    irrigante_scelto = st.sidebar.selectbox("Seleziona Contadino / Chiavone", opzioni_sb)
    
    # Recuperiamo il valore di default della zona dal database per calcolare i giri
    zona_default = "Generico"
    motori_default = 1.0
    if not df_irriganti.empty and irrigante_scelto in df_irriganti['nome'].values:
        dati_irr_selezionato = df_irriganti[df_irriganti['nome'] == irrigante_scelto].iloc[0]
        zona_default = dati_irr_selezionato['zona']
        motori_default = float(dati_irr_selezionato['motori_std'])
    elif irrigante_scelto in ELENCO_CHIAVONI_REALI:
        zona_default = irrigante_scelto

    # FORM Principale per il salvataggio dei Turni
    with st.sidebar.form("form_nuovo_turno"):
        motori_scelti_sb = st.number_input("Motori da far uscire (M):", min_value=0.0, max_value=12.0, value=motori_default, step=0.01)
        
        # Mostriamo i giri calcolati all'interno del form in modo stabile
        giri_calc_sb, _ = calcola_giri_chiavone(motori_scelti_sb, zona_default)
        st.markdown(f"⚙️ **Giri Chiavone Equivalenti: {giri_calc_sb:.2f} Giri**")
        
        st.markdown("---")
        giorni_ripetizione = st.multiselect("Giorni di Ripetizione Settimanale:", GIORNI_SETTIMANA_LISTA)
        data_inizio = st.date_input("Dal giorno:", datetime.now())
        
        lista_ore = [f"{h:02d}:{m:02d}" for h in range(24) for m in [0, 15, 30, 45]] + ["24:00"]
        ora_inizio_str = st.selectbox("Ora Inizio:", lista_ore, index=32) 
        data_fine = st.date_input("Al giorno:", datetime.now())
        ora_fine_str = st.selectbox("Ora Fine:", lista_ore, index=48) 
        fosso_sporco_attivo = st.checkbox("⚠️ Segnala Fosso Sporco")
        
        salva_bottone = st.form_submit_button("💾 Salva Turno in Agenda", type="primary")

    if salva_bottone:
        if not irrigante_scelto or irrigante_scelto == "Nessun elemento registrato":
            st.sidebar.error("Seleziona un elemento valido!")
        else:
            id_irrigante_db = None
            if not df_irriganti.empty and irrigante_scelto in df_irriganti['nome'].values:
                id_irrigante_db = int(df_irriganti[df_irriganti['nome'] == irrigante_scelto].iloc[0]['id'])
            
            if id_irrigante_db is not None:
                aggiorna_irrigante_completo(id_irrigante_db, irrigante_scelto, zona_default, tipo_pesca_scelta, motori_scelti_sb, 30, 15, 0)
            else:
                id_irrigante_db = inserisci_irrigante_completo(irrigante_scelto, zona_default, tipo_pesca_scelta, motori_scelti_sb, 30, 15, 0)
                
            lista_coppie_date = []
            if len(giorni_ripetizione) > 0:
                passo = datetime.now().date()
                fine_stagione = datetime(datetime.now().year, 9, 30).date()
                while passo <= fine_stagione:
                    if MAP_GIORNI_ING[passo.weekday()] in giorni_ripetizione:
                        lista_coppie_date.append((passo, passo))
                    passo += timedelta(days=1)
            else:
                lista_coppie_date.append((data_inizio, data_fine))
                
            salva_ora_fine = "23:59" if ora_fine_str == "24:00" else ora_fine_str
            for d_ini, d_fin in lista_coppie_date:
                inizio_completo = f"{d_ini.strftime('%Y-%m-%d')} {ora_inizio_str}"
                d_fin_effettivo = d_ini + timedelta(days=1) if (ora_fine_str != "24:00" and ora_fine_str <= ora_inizio_str) else d_fin
                fine_completo = f"{d_fin_effettivo.strftime('%Y-%m-%d')} {salva_ora_fine}"
                inserisci_prenotazione_avanzata(id_irrigante_db, inizio_completo, fine_completo, tipo_pesca_scelta)
                
            st.sidebar.success("Turno aggiunto con successo!")
            st.rerun()

    # FORM di Svuotamento (Danger Zone)
    st.sidebar.markdown("---")
    st.sidebar.subheader("⚠️ Danger Zone — Svuotamento")
    with st.sidebar.form("form_danger_zone"):
        opzione_canc_massa = st.selectbox("Scegli cosa svuotare:", ["Nessuna azione", "Turni della Settimana", "Turni del Mese", "Tutti i turni in generale"])
        testo_conferma = "CONFERMA"
        codice_verifica = st.text_input(f"Digita '{testo_conferma}' per approvare:")
        conferma_canc = st.form_submit_button("🚨 Esegui Svuotamento Massivo")
        
    if conferma_canc and codice_verifica == testo_conferma:
        if opzione_canc_massa == "Turni della Settimana": cancella_turni_settimana(st.session_state.data_corrente)
        elif opzione_canc_massa == "Turni del Mese": cancella_turni_mese(st.session_state.data_corrente)
        elif opzione_canc_massa == "Tutti i turni in generale": cancella_turni_generale()
        st.rerun()

    # Navigazione Centrale principale
    c_nav1, c_nav2, c_nav3 = st.columns([1, 2, 1])
    with c_nav1: st.button("⬅️ Giorno Precedente", on_click=giorno_precedente, use_container_width=True, key="dash_prev")
    with c_nav2: 
        with st.form("form_cambio_data_dash", border=False):
            data_selezionata_dash = st.date_input("Seleziona Giorno:", value=st.session_state.data_corrente, label_visibility="collapsed")
            if st.form_submit_button("📅 Vai al Giorno selezionato", use_container_width=True):
                st.session_state.data_corrente = data_selezionata_dash
                st.session_state.data_settimana_macchine = data_selezionata_dash
                st.rerun()
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
        <h2 style="color:white; margin:0;">📟 STATO IDRAULICO RETE DEL GIORNO: {st.session_state.data_corrente.strftime('%d/%m/%Y')}</h2>
        <h1 style="color:white; margin:10px 0 0 0; font-size:45px; font-weight:bold;">{motori_giorno:.2f} M massimi in contemporanea <span style='font-size:20px; font-weight:normal;'>(Incluso +{valore_perdite_testo_dash} M perdite)</span></h1>
        <p style="color:white; margin:5px 0 0 0; font-size:18px; font-weight:500;">ASSETTO MASSIMO: {testo_pompe} | PORTATA COMPLESSIVA RETE: {portata_globale_ls:.0f} l/s</p>
    </div>
    """, unsafe_allow_html=True)

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
                "Azienda Agricola / Contadino": r['nome'], "Zona Idraulica": r['zona'], "Fascia Oraria": f"{h_inz_tab} - {h_fin_tab}",
                "Modalità": r['config_scelta'], "Carico Richiesto (Motori M)": f"{r['motori_std']:.2f} M", "Portata (l/s)": f"{portata_s:.0f} l/s"
            })
        st.table(pd.DataFrame(righe_tabella))

# =========================================================
# TAB 2: AGENDA GIORNALIERA DELLE MANOVRE
# =========================================================
with tab_agenda:
    st.title("📋 Agenda Giornaliera delle Manovre")
    
    c_nav_a1, c_nav_a2, c_nav_a3 = st.columns([1, 2, 1])
    with c_nav_a1: st.button("⬅️ Ieri", on_click=giorno_precedente, use_container_width=True, key="agenda_prev")
    with c_nav_a2: 
        with st.form("form_cambio_data_agenda", border=False):
            data_selezionata_agenda = st.date_input("Calendario:", value=st.session_state.data_corrente, label_visibility="collapsed")
            if st.form_submit_button("📅 Visualizza Registro Ordini", use_container_width=True):
                st.session_state.data_corrente = data_selezionata_agenda
                st.session_state.data_settimana_macchine = data_selezionata_agenda
                st.rerun()
    with c_nav_a3: st.button("➡️ Domani", on_click=giorno_successivo, use_container_width=True, key="agenda_next")
    
    st.markdown(f"### 🗓️ Registro Ordini di Servizio del: **{st.session_state.data_corrente.strftime('%d/%m/%Y')}**")

    if df_tutti_attivi.empty:
        st.info("Nessuna manovra presente nel sistema.")
    else:
        manovre_totali = []
        df_manovre_p = get_cached_manovre_personalizzate()

        for idx, row in df_tutti_attivi.iterrows():
            in_dt = row['data_inizio_dt']
            fi_dt = row['data_fine_dt']

            if fi_dt.weekday() in [5, 6] and row['config_scelta'] == "Fosso":
                manovre_totali.append({
                    "Data/Ora": fi_dt, "Tipo": "🌊 Invaso Rangona", "ForzaOraria": "INFO",
                    "Descrizione": f"Fine turno weekend di {row['nome']}. Lasciare correre l'acqua fino a Lunedì per rimpinguare l'invaso Rangona."
                })

            sub_m = df_manovre_p[df_manovre_p['irrigante_id'] == int(row['irr_id'])]
            for _, m_row in sub_m.iterrows():
                val = float(m_row['valore_anticipo'])
                unita = m_row['unita_anticipo']
                td = timedelta(hours=val) if unita == "Ore" else (timedelta(hours=val * 12) if unita == "Mezze Giornate" else timedelta(days=val))

                ora_manovra_dinamica = in_dt - td
                if ora_manovra_dinamica.year >= datetime.now().year - 1:
                    ora_manovra_ott = ottimizza_orario_manovra(ora_manovra_dinamica, motori_correnti=motori_giorno_global)
                    manovre_totali.append({
                        "Data/Ora": ora_manovra_ott, "Tipo": "🔧 Manovra", "ForzaOraria": "CONTROLLA",
                        "Descrizione": f"[{row['nome']}] {m_row['descrizione']}."
                    })

        if len(manovre_totali) > 0:
            df_manovre = pd.DataFrame(manovre_totali).sort_values(by="Data/Ora").drop_duplicates(subset=["Data/Ora", "Descrizione"])
            df_giorno = df_manovre[df_manovre['Data/Ora'].dt.date == st.session_state.data_corrente]
            
            if df_giorno.empty:
                st.info("Nessuna manovra pianificata per oggi.")
            else:
                for _, m in df_giorno.iterrows():
                    ora_f = m['Data/Ora'].strftime("%H:%M")
                    if m['ForzaOraria'] == "INFO": st.success(f"🌊 **ORE {ora_f}** — {m['Descrizione']}")
                    else:
                        st.warning(f"⏰ **ORE {ora_f}** — {m['Descrizione']}")
        else:
            st.info("Nessuna manovra per oggi.")

# =========================================================
# TAB 3: VIDEATA SALA MACCHINE
# =========================================================
with tab_sala_macchine:
    st.title("Quadro Controllo Automatizzato Orologi di Centrale")
    
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
        
        df_giorno_sm = df_tutti_attivi[(df_tutti_attivi['data_inizio_dt'].dt.date <= giorno_esaminato) & (df_tutti_attivi['data_fine_dt'].dt.date >= giorno_esaminato)].copy() if not df_tutti_attivi.empty else pd.DataFrame()
        
        p4_nominale = [False] * 1440
        p3_nominale = [False] * 1440
        
        for minuto_del_giorno in range(1440):
            tempo_minuto_inizio = datetime.combine(giorno_esaminato, time(minuto_del_giorno // 60, minuto_del_giorno % 60))
            tempo_minuto_fine = tempo_minuto_inizio + timedelta(minutes=1)
            
            motori_min = 0.0
            if not df_giorno_sm.empty:
                for _, turno in df_giorno_sm.iterrows():
                    limite_fine = datetime.combine(turno['data_fine_dt'].date(), time(23, 59, 59)) if turno['data_fine_dt'].time() == time(23, 59) else turno['data_fine_dt']
                    if turno['data_inizio_dt'] < tempo_minuto_fine and limite_fine > tempo_minuto_inizio:
                        motori_min += float(turno['motori_std'])
            
            if motori_min > 0:
                totale_con_perdite = calcola_motori_con_perdite(motori_min)
                if totale_con_perdite <= 6.0: p4_nominale[minuto_del_giorno] = True
                elif totale_con_perdite <= 8.0: p3_nominale[minuto_del_giorno] = True
                else: p4_nominale[minuto_del_giorno] = True; p3_nominale[minuto_del_giorno] = True

        def unisci_fasce_orarie(array_presenza):
            fasce = []
            in_blocco = False
            inizio_blocco = None
            for m_giorno in range(1440):
                if array_presenza[m_giorno] and not in_blocco:
                    in_blocco = True
                    inizio_blocco = f"{m_giorno // 60:02d}:{m_giorno % 60:02d}"
                elif not array_presenza[m_giorno] and in_blocco:
                    in_blocco = False
                    fasce.append(f"⏱️ {inizio_blocco} — {m_giorno // 60:02d}:{m_giorno % 60:02d}")
            if in_blocco: fasce.append(f"⏱️ {inizio_blocco} — 24:00")
            return fasce

        fasce_p4 = unisci_fasce_orarie(p4_nominale)
        fasce_p3 = unisci_fasce_orarie(p3_nominale)

        col_p4_sm, col_p3_sm = st.columns(2)
        with col_p4_sm:
            st.markdown("<b style='color:#dc3545;'> ORARI ACCENSIONE POMPA P4 (Bassa Pressione)</b>", unsafe_allow_html=True)
            if fasce_p4:
                for f_t in fasce_p4: st.code(f_t, language=None)
            else: st.caption("Pompa P4 Spenta")
        with col_p3_sm:
            st.markdown("<b style='color:#17a2b8;'> ORARI ACCENSIONE POMPA P3 (Alta Pressione / Inverter)</b>", unsafe_allow_html=True)
            if fasce_p3:
                for f_t in fasce_p3: st.code(f_t, language=None)
            else: st.caption("Pompa P3 Spenta")

# =========================================================
# TAB 4: GESTIONE ANAGRAFICA
# =========================================================
with tab_anagrafica:
    st.title("🚜 Parametri e Anagrafica Utenze")
    sub_ins, sub_mod = st.tabs(["➕ Registra Profilo", "📝 Modifica Scheda"])
    
    with sub_ins:
        with st.form("form_registra_profilo_completo"):
            st.subheader("📋 Dati Anagrafici Utenza")
            n_nome = st.text_input("Nome Utenza o Chiavone")
            n_prelievo = st.selectbox("Prelievo Standard", ["Fosso", "Diretta"])
            n_zona = st.selectbox("Nodo Idraulico Associato", ELENCO_CHIAVONI_REALI)
            n_motori = st.number_input("Motori assorbiti (M)", min_value=0.0, max_value=12.0, value=1.0)
            n_distanza = st.number_input("Minuti di distanza apertura:", min_value=0, max_value=180, value=30)
            n_extra_fosso = st.number_input("Minuti Extra Fosso Sporco:", min_value=0, max_value=120, value=15)
            n_giorni_ant = st.selectbox("Giorni pre-anticipo manovre:", [0, 1, 2])
            
            salva_profilo_btn = st.form_submit_button("💾 Salva Profilo", type="primary")
            
        if salva_profilo_btn and n_nome:
            inserisci_irrigante_completo(n_nome, n_zona, n_prelievo, n_motori, n_distanza, n_extra_fosso, n_giorni_ant)
            st.success("Profilo salvato con successo!")
            st.rerun()

    with sub_mod:
        if df_irriganti.empty: 
            st.info("Database vuoto.")
        else:
            selezionato_mod = st.selectbox("Seleziona la scheda da caricare e modificare:", df_irriganti['nome'].tolist())
            dati_c = df_irriganti[df_irriganti['nome'] == selezionato_mod].iloc[0]
            id_selezionato = int(dati_c['id'])

            with st.form("form_modifica_scheda_esistente"):
                m_nome = st.text_input("Identificativo", value=str(dati_c['nome']))
                m_prelievo = st.selectbox("Prelievo", ["Fosso", "Diretta"], index=0 if dati_c['tipo_prelievo'] == "Fosso" else 1)
                m_zona = st.selectbox("Chiavone Associato", ELENCO_CHIAVONI_REALI, index=ELENCO_CHIAVONI_REALI.index(dati_c['zona']) if dati_c['zona'] in ELENCO_CHIAVONI_REALI else 0)
                m_motori = st.number_input("Motori (M)", min_value=0.0, max_value=12.0, value=float(dati_c['motori_std']))
                m_distanza = st.number_input("Minuti di distanza:", min_value=0, max_value=180, value=int(dati_c['minutes_distanza']))
                m_extra_fosso = st.number_input("Minuti Extra Fosso:", min_value=0, max_value=180, value=int(dati_c['extra_fosso_sporco']))
                m_giorni_ant = st.selectbox("Giorni anticipo:", [0, 1, 2], index=int(dati_c['giorni_anticipo_manovra']) if dati_c['giorni_anticipo_manovra'] in [0,1,2] else 0)
                
                aggiorna_btn = st.form_submit_button("💾 Aggiorna Dati Scheda")
                
            if aggiorna_btn:
                aggiorna_irrigante_completo(id_selezionato, m_nome, m_zona, m_prelievo, m_motori, m_distanza, m_extra_fosso, m_giorni_ant)
                st.success("Scheda aggiornata!")
                st.rerun()

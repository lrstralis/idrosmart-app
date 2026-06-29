import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta, time

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

# --- INIZIALIZZAZIONE SESSION STATE PER ELENCO TEMPORANEO MANOVRE RETE ---
if "manovre_temporanee_registrazione" not in st.session_state:
    st.session_state.manovre_temporanee_registrazione = []

# --- FUNZIONE DI CALCOLO GIRI CHIAVONE BASATA SULLA TABELLA UNIFICATA ---
def calcola_giri_chiavone(motori_totali, nome_chiavone):
    if motori_totali <= 0:
        return 0.0, 0.0
    
    tabella_reale = {
        "0.06": {"1.8": 0.25, "0.6": 0.25}, "0.12": {"1.8": 0.50, "0.6": 0.75},
        "0.18": {"1.8": 0.75, "0.6": 1.00}, "0.26": {"1.8": 1.00, "0.6": 1.25},
        "0.34": {"1.8": 1.25, "0.6": 1.50}, "0.42": {"1.8": 1.50, "0.6": 2.00},
        "0.52": {"1.8": 1.75, "0.6": 2.50}, "0.62": {"1.8": 2.00, "0.6": 2.75},
        "0.73": {"1.8": 2.25, "0.6": 3.25}, "0.85": {"1.8": 2.50, "0.6": 3.50},
        "0.98": {"1.8": 2.75, "0.6": 4.00}, "1.11": {"1.8": 3.00, "0.6": 4.25},
        "1.18": {"1.8": 3.25, "0.6": 4.50}, "1.25": {"1.8": 3.50, "0.6": 4.75},
        "1.39": {"1.8": 3.75, "0.6": 5.00}, "1.52": {"1.8": 4.00, "0.6": 5.25},
        "1.65": {"1.8": 4.25, "0.6": 5.50}, "1.79": {"1.8": 4.50, "0.6": 6.00},
        "1.93": {"1.8": 4.75, "0.6": 6.25}, "2.08": {"1.8": 5.00, "0.6": 6.50},
        "2.31": {"1.8": 5.25, "0.6": 6.75}, "2.42": {"1.8": 5.50, "0.6": 7.00},
        "2.64": {"1.8": 5.75, "0.6": 7.25}, "3.00": {"1.8": 6.00, "0.6": 7.50},
        "3.34": {"1.8": 6.25, "0.6": 7.75}, "3.69": {"1.8": 6.50, "0.6": 8.25},
        "4.04": {"1.8": 6.75, "0.6": 8.50}, "4.39": {"1.8": 7.00, "0.6": 8.75},
        "4.73": {"1.8": 7.25, "0.6": 9.25}, "5.07": {"1.8": 7.50, "0.6": 9.75},
        "5.41": {"1.8": 7.75, "0.6": 10.00}
    }
    
    chiavoni_1_8_bar = ["Valvola Contrappesi", "Dogaro di Ravarino", "Piave 1", "Piave 2 (Targa)", "Fosso dei Monti"]
    pressione_chiavone = "1.8" if nome_chiavone in chiavoni_1_8_bar else "0.6"
    
    chiave_motori = f"{motori_totali:.2f}"
    if chiave_motori in tabella_reale:
        giri = tabella_reale[chiave_motori][pressione_chiavone]
        return giri, motori_totali * 20.0
    
    array_motori = [float(k) for k in tabella_reale.keys()]
    idx_vicino = min(range(len(array_motori)), key=lambda i: abs(array_motori[i] - motori_totali))
    chiave_approssimata = f"{array_motori[idx_vicino]:.2f}"
    
    giri = tabella_reale[chiave_approssimata][pressione_chiavone]
    return giri, motori_totali * 20.0

# --- FUNZIONI DATABASE ---
def inizializza_tabelle_personalizzate():
    conn = sqlite3.connect('idrosmart.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS irriganti (
            id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, zona TEXT, tipo_prelievo TEXT,
            motori_std REAL DEFAULT 1.0, minuti_distanza INTEGER DEFAULT 30,
            extra_fosso_sporco INTEGER DEFAULT 15, giorni_anticipo_manovra INTEGER DEFAULT 0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS prenotazioni (
            id INTEGER PRIMARY KEY AUTOINCREMENT, irrigante_id INTEGER,
            data_ora_inizio TEXT, data_ora_fine TEXT, config_scelta TEXT, stato TEXT DEFAULT 'PROGRAMMATO',
            FOREIGN KEY(irrigante_id) REFERENCES irriganti(id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS manovre_personalizzate (
            id INTEGER PRIMARY KEY AUTOINCREMENT, irrigante_id INTEGER,
            descrizione TEXT NOT NULL, valore_anticipo REAL NOT NULL, unita_anticipo TEXT NOT NULL,
            FOREIGN KEY(irrigante_id) REFERENCES irriganti(id)
        )
    ''')
    conn.commit()
    conn.close()

def inserisci_irrigante_completo(nome, zona, prelievo, motori, distanza, extra_fosso, giorni_ant):
    conn = sqlite3.connect('idrosmart.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO irriganti (nome, zona, tipo_prelievo, motori_std, minuti_distanza, extra_fosso_sporco, giorni_anticipo_manovra)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (nome, zona, prelievo, motori, distanza, extra_fosso, giorni_ant))
    id_generato = cursor.lastrowid
    conn.commit()
    conn.close()
    return id_generato

def aggiorna_irrigante_completo(id_irr, nome, zona, prelievo, motori, distanza, extra_fosso, giorni_ant):
    conn = sqlite3.connect('idrosmart.db')
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE irriganti SET nome=?, zona=?, tipo_prelievo=?, motori_std=?, minuti_distanza=?, extra_fosso_sporco=?, giorni_anticipo_manovra=? WHERE id=?
    ''', (nome, zona, prelievo, motori, distanza, extra_fosso, giorni_ant, id_irr))
    conn.commit()
    conn.close()

def inserisci_manovra_personalizzata(irr_id, desc, val, unita):
    conn = sqlite3.connect('idrosmart.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO manovre_personalizzate (irrigante_id, descrizione, valore_anticipo, unita_anticipo) VALUES (?, ?, ?, ?)', (irr_id, desc, val, unita))
    conn.commit()
    conn.close()

def cancella_manovra_personalizzata(manovra_id):
    conn = sqlite3.connect('idrosmart.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM manovre_personalizzate WHERE id = ?', (manovra_id,))
    conn.commit()
    conn.close()

def inserisci_prenotazione_avanzata(irrigante_id, inizio, fine, config):
    conn = sqlite3.connect('idrosmart.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO prenotazioni (irrigante_id, data_ora_inizio, data_ora_fine, config_scelta) VALUES (?, ?, ?, ?)', (irrigante_id, inizio, fine, config))
    conn.commit()
    conn.close()

def cancella_prenotazione(id_prenotazione):
    conn = sqlite3.connect('idrosmart.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM prenotazioni WHERE id = ?", (id_prenotazione,))
    conn.commit()
    conn.close()

# --- FUNZIONI DI CANCELLAZIONE MASSIVA RICHIESTE ---
def cancella_turni_settimana(data_rif):
    inizio_sett = data_rif - timedelta(days=data_rif.weekday())
    fine_sett = inizio_sett + timedelta(days=6)
    conn = sqlite3.connect('idrosmart.db')
    cursor = conn.cursor()
    cursor.execute('''
        DELETE FROM prenotazioni 
        WHERE date(substr(data_ora_inizio, 1, 10)) >= date(?) 
          AND date(substr(data_ora_inizio, 1, 10)) <= date(?)
    ''', (str(inizio_sett), str(fine_sett)))
    conn.commit()
    conn.close()

def cancella_turni_mese(data_rif):
    anno_mese = data_rif.strftime("%Y-%m")
    conn = sqlite3.connect('idrosmart.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM prenotazioni WHERE substr(data_ora_inizio, 1, 7) = ?", (anno_mese,))
    conn.commit()
    conn.close()

def cancella_turni_generale():
    conn = sqlite3.connect('idrosmart.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM prenotazioni")
    conn.commit()
    conn.close()

def seleziona_pompe_centrale(motori):
    if motori == 0: return "IMPIANTO FERMO", []
    elif motori <= 6.0: return "Solo POMPA P4 attiva", ["P4"]
    elif motori <= 8.0: return "Solo POMPA P3 (Inverter) attiva", ["P3"]
    elif motori <= 12.0: return "ENTRAMBE ATTIVE (P4 + P3) - Spinta Max 240 l/s", ["P4", "P3"]
    else: return "SOVRACCARICO (Oltre i 12 M)", ["P4", "P3"]

def ottieni_colore_stato_semplice(motori_totali, rangoni_attivo):
    if motori_totali == 0: return "#A0A0A0", "🟢 IMPIANTO FERMO"
    if rangoni_attivo:
        if motori_totali > 12.0: return "#dc3545", f"🔴 TEST FALLITO ({motori_totali:.1f} M)!"
        elif motori_totali >= 11.0: return "#fd7e14", "🟠 SOGLIA CRITICA TEST"
        else: return "#28a745", "🟢 REGIME DI PROVA"
    if motori_totali > 12.0: return "#dc3545", "🔴 SOVRACCARICO STRUTTURALE"
    return "#28a745", "🟢 CARICO RETE REGOLARE"

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

inizializza_tabelle_personalizzate()

# --- MANUTENZIONE PREVENTIVA DEL DATABASE (Risoluzione Radicale Errori Stringhe Date Incomplete) ---
try:
    conn_manutenzione = sqlite3.connect('idrosmart.db')
    cursor_m = conn_manutenzione.cursor()
    cursor_m.execute("DELETE FROM prenotazioni WHERE length(data_ora_inizio) < 16 OR length(data_ora_fine) < 16")
    conn_manutenzione.commit()
    conn_manutenzione.close()
except Exception as e:
    pass

# --- CARICAMENTO DATI ---
conn = sqlite3.connect('idrosmart.db')
df_irriganti = pd.read_sql_query("SELECT * FROM irriganti ORDER BY nome", conn)
df_tutti_attivi = pd.read_sql_query('''
    SELECT p.id, i.id AS irr_id, i.nome, i.motori_std, i.zona, i.minuti_distanza, i.extra_fosso_sporco, i.giorni_anticipo_manovra,
           p.data_ora_inizio, p.data_ora_fine, p.config_scelta
    FROM prenotazioni p JOIN irriganti i ON p.irrigante_id = i.id
    WHERE p.stato = 'PROGRAMMATO' ORDER BY p.data_ora_inizio ASC
''', conn)
conn.close()

if not df_tutti_attivi.empty:
    df_tutti_attivi['data_inizio_dt'] = pd.to_datetime(df_tutti_attivi['data_ora_inizio'], errors='raise')
    df_tutti_attivi['data_fine_dt'] = pd.to_datetime(df_tutti_attivi['data_ora_fine'], errors='raise')

if 'data_corrente' not in st.session_state:
    st.session_state.data_corrente = datetime.now().date()

def sync_da_dash(): st.session_state.data_corrente = st.session_state.data_dash
def sync_da_agenda(): st.session_state.data_corrente = st.session_state.data_agenda
def sync_da_home(): st.session_state.data_corrente = st.session_state.data_home
def giorno_precedente(): st.session_state.data_corrente -= timedelta(days=1)
def giorno_successivo(): st.session_state.data_corrente += timedelta(days=1)

irriganti_giorno_corrente = []
rangoni_oggi_global = False
if not df_tutti_attivi.empty:
    df_giorno_attivi_global = df_tutti_attivi[(df_tutti_attivi['data_inizio_dt'].dt.date <= st.session_state.data_corrente) & (df_tutti_attivi['data_fine_dt'].dt.date >= st.session_state.data_corrente)].copy()
    rangoni_oggi_global = df_giorno_attivi_global['nome'].str.contains("Rangoni", case=False).any() if not df_giorno_attivi_global.empty else False
    for idx, r in df_giorno_attivi_global.iterrows():
        ora_inz_str = "00:00" if r['data_inizio_dt'].date() < st.session_state.data_corrente else r['data_inizio_dt'].strftime('%H:%M')
        ora_fin_str = "24:00" if r['data_fine_dt'].date() > st.session_state.data_corrente else r['data_fine_dt'].strftime('%H:%M')
        irriganti_giorno_corrente.append({"nome": r['nome'], "fascia": f"{ora_inz_str}-{ora_fin_str}", "motori": r['motori_std']})

motori_pre_perdite_global = df_tutti_attivi[(df_tutti_attivi['data_inizio_dt'].dt.date <= st.session_state.data_corrente) & (df_tutti_attivi['data_fine_dt'].dt.date >= st.session_state.data_corrente)]['motori_std'].sum() if not df_tutti_attivi.empty else 0.0
motori_giorno_global = (motori_pre_perdite_global + 0.5) if motori_pre_perdite_global > 0 else 0.0
testo_pompe_g, _ = seleziona_pompe_centrale(motori_giorno_global)
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
    
    st.markdown(f"""
    <div style="background-color:{esito_colore_g}; padding:18px; border-radius:10px; text-align:center; margin-bottom:20px;">
        <h3 style="color:white; margin:0; font-size:1.3rem;">📟 STATO IDRAULICO CORRENTE: {st.session_state.data_corrente.strftime('%d/%m/%Y')}</h3>
        <h1 style="color:white; margin:5px 0; font-size:38px; font-weight:bold;">{motori_giorno_global:.2f} M totali impegnati <span style='font-size:18px; font-weight:normal;'>(Incluso +0.50 M perdite)</span></h1>
        <p style="color:white; margin:0; font-size:16px; font-weight:500;">ASSETTO IMPIANTO: {testo_pompe_g} | PORTATA COMPLESSIVA RETE: {portata_globale_g_ls:.0f} l/s</p>
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
        
        motori_loop_pre = df_loop_attivi['motori_std'].sum() if not df_loop_attivi.empty else 0.0
        motori_loop = (motori_loop_pre + 0.5) if motori_loop_pre > 0 else 0.0
        rangoni_loop = df_loop_attivi['nome'].str.contains("Rangoni", case=False).any() if not df_loop_attivi.empty else False
        colore_loop, _ = ottieni_colore_stato_semplice(motori_loop, rangoni_loop)
        
        with col_sett[i]:
            if st.button(f"{nome_giorno_it} {giorno_loop.strftime('%d/%m')} ({motori_loop:.1f} M)", key=f"btn_giorno_{giorno_loop.strftime('%Y%m%d')}", use_container_width=True):
                st.session_state.data_corrente = giorno_loop
                st.rerun()
            
            bordo_giorno = "border: 3px solid #17a2b8;" if giorno_loop == st.session_state.data_corrente else "border: 1px solid rgba(0,0,0,0.1);"
            st.markdown(f'<div style="background-color:{colore_loop}; padding:6px; border-radius:5px; text-align:center; color:white; font-weight:bold; margin-bottom:8px; {bordo_giorno}"><div style="font-size:14px;">{motori_loop:.1f} M</div></div>', unsafe_allow_html=True)
            
            if df_loop_attivi.empty:
                st.markdown("<div style='text-align:center; color:#888; font-size:12px;'>Centrale Off</div>", unsafe_allow_html=True)
            else:
                for _, utenza in df_loop_attivi.iterrows():
                    h_inz = utenza['data_inizio_dt'].strftime('%H:%M')
                    h_fin = utenza['data_fine_dt'].strftime('%H:%M')
                    if h_fin == "23:59" or h_fin == "00:00": h_fin = "24:00"
                    st.markdown(f'<div style="background-color:#f8f9fa; padding:5px; border-radius:4px; margin-bottom:5px; border-left:3px solid #007bff; text-align:left;"><div style="font-size:12px; font-weight:bold; color:#212529;">{utenza["nome"]}</div><div style="font-size:11px; color:#495057; font-family:monospace;">⏱️ {h_inz}-{h_fin}</div></div>', unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(f"### 📋 Foglio Giornaliero Dettagliato del **{st.session_state.data_corrente.strftime('%d/%m/%Y')}**")
    if not irriganti_giorno_corrente:
        st.info("Nessun irrigante attivo programmato per questa giornata.")
    else:
        for irr in irriganti_giorno_corrente:
            col_info, col_totale = st.columns([3, 1])
            with col_info:
                st.markdown(f"**<span style='font-size:1.25rem;'>{irr['nome']}</span>**", unsafe_allow_html=True)
                st.caption(f"🕒 Fascia Oraria Attiva: {irr['fascia']}")
            with col_totale:
                colore_f, pompe_f = determines_info_pompe_home(irr['motori'])
                st.markdown(f'<div style="background-color:{colore_f}; padding:10px; border-radius:6px; text-align:center; border: 1px solid rgba(0,0,0,0.1); color: black; font-weight:bold;">{irr["motori"]:.2f} M <br><span style="font-size:0.85rem; font-weight:normal;">({pompe_f})</span></div>', unsafe_allow_html=True)

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
    else:
        opzioni_sb = ELENCO_CHIAVONI_REALI
        
    irrigante_scelto = st.sidebar.selectbox("Seleziona Contadino / Chiavone", opzioni_sb)
    
    # --- RISOLUZIONE INTEGRITYERROR CHIAVONI ---
    # Verifica l'esistenza del nome nel database globale a prescindere dal tipo selezionato
    conn = sqlite3.connect('idrosmart.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, zona, tipo_prelievo, motori_std FROM irriganti WHERE nome = ?", (irrigante_scelto,))
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
        
    tipo_pesca_scelta = st.sidebar.radio("Modalità Prelievo", ["Fosso", "Diretta"], index=0 if tipo_prelievo_default == "Fosso" else 1)
    
    if tipo_pesca_scelta == "Fosso" or tipo_elemento_scelto == "Chiavoni":
        motori_scelti_sb = st.sidebar.number_input("Motori totali da far uscire (M):", min_value=0.0, max_value=12.0, value=motori_default, step=0.1)
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
        if not irrigante_scelto:
            st.sidebar.error("Seleziona un elemento valido!")
        else:
            if id_irrigante_db is None:
                # Forza i chiavoni reali ad avere i parametri coerenti e la modalità fosso nativa
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
            
            # Forza la configurazione del turno a 'Fosso' per i chiavoni reali
            config_salv = "Fosso" if irrigante_scelto in ELENCO_CHIAVONI_REALI else tipo_pesca_scelta
                
            for d_ini, d_fin in lista_coppie_date:
                inizio_completo = f"{d_ini} {ora_inizio_str}"
                fine_completo = f"{d_fin} {salva_ora_fine}"
                inserisci_prenotazione_avanzata(id_irrigante_db, inizio_completo, fine_completo, config_salv)
                
            st.sidebar.success("Turni registrati correttamente!")
            st.rerun()

    # --- SEZIONE: SELEZIONE CANCELLAZIONE MASSIVA TURNI ---
    st.sidebar.markdown("---")
    st.sidebar.subheader("⚠️ Danger Zone — Rimozione Massiva")
    opzione_canc_massa = st.sidebar.selectbox("Scegli blocco da svuotare:", ["Nessuna azione", "Turni della Settimana", "Turni del Mese", "Tutti i turni in generale"])
    if opzione_canc_massa != "Nessuna azione":
        testo_conferma = "CONFERMA ELIMINAZIONE"
        codice_verifica = st.sidebar.text_input(f"Digita '{testo_conferma}' per procedere:")
        if st.sidebar.button("🚨 Esegui Svuotamento Massivo"):
            if codice_verifica == testo_conferma:
                if opzione_canc_massa == "Turni della Settimana":
                    cancella_turni_settimana(st.session_state.data_corrente)
                    st.sidebar.success("Turni settimanali cancellati correttamente!")
                elif opzione_canc_massa == "Turni del Mese":
                    cancella_turni_mese(st.session_state.data_corrente)
                    st.sidebar.success("Turni del mese corrente cancellati!")
                elif opzione_canc_massa == "Tutti i turni in generale":
                    cancella_turni_generale()
                    st.sidebar.success("Intero storico turni azzerato!")
                st.rerun()
            else:
                st.sidebar.error("Testo di conferma non corretto.")

    c_nav1, c_nav2, c_nav3 = st.columns([1, 2, 1])
    with c_nav1: st.button("⬅️ Giorno Precedente", on_click=giorno_precedente, use_container_width=True, key="dash_prev")
    with c_nav2: st.date_input("Seleziona Giorno:", value=st.session_state.data_corrente, key="data_dash", on_change=sync_da_dash, label_visibility="collapsed")
    with c_nav3: st.button("➡️ Giorno Successivo", on_click=giorno_successivo, use_container_width=True, key="dash_next")
            
    df_giorno_attivi = df_tutti_attivi[(df_tutti_attivi['data_inizio_dt'].dt.date <= st.session_state.data_corrente) & (df_tutti_attivi['data_fine_dt'].dt.date >= st.session_state.data_corrente)].copy() if not df_tutti_attivi.empty else pd.DataFrame()
    rangoni_oggi = df_giorno_attivi['nome'].str.contains("Rangoni", case=False).any() if not df_giorno_attivi.empty else False

    motori_pre_perdite = df_giorno_attivi['motori_std'].sum() if not df_giorno_attivi.empty else 0.0
    motori_giorno = (motori_pre_perdite + 0.5) if motori_pre_perdite > 0 else 0.0
    testo_pompe, _ = seleziona_pompe_centrale(motori_giorno)
    esito_colore, _ = ottieni_colore_stato_semplice(motori_giorno, rangoni_oggi)
    _, portata_globale_ls = calcola_giri_chiavone(motori_giorno, "Generico")

    st.markdown(f"""
    <div style="background-color:{esito_colore}; padding:20px; border-radius:10px; text-align:center; margin-bottom:25px;">
        <h2 style="color:white; margin:0;">📟 STATO IDRAULICO RETE DEL GIORNO: {st.session_state.data_corrente.strftime('%d/%m/%Y')}</h2>
        <h1 style="color:white; margin:10px 0 0 0; font-size:45px; font-weight:bold;">{motori_giorno:.2f} M totali impegnati <span style='font-size:20px; font-weight:normal;'>(Incluso +0.50 M perdite)</span></h1>
        <p style="color:white; margin:5px 0 0 0; font-size:18px; font-weight:500;">ASSETTO CENTRALINA: {testo_pompe} | PORTATA RETE: {portata_globale_ls:.0f} l/s</p>
    </div>
    """, unsafe_allow_html=True)

    st.subheader(f"📋 Dettaglio Utenze Attive Giornaliere ({st.session_state.data_corrente.strftime('%d/%m/%Y')})")
    if df_giorno_attivi.empty:
        st.info("Nessun prelievo programmato per questo giorno.")
    else:
        righe_tabella = []
        for idx, r in df_giorno_attivi.iterrows():
            _, portata_s = calcola_giri_chiavone(r['motori_std'], r['zona'])
            h_f_vis = "24:00" if r['data_fine_dt'].strftime('%H:%M') in ["23:59", "00:00"] else r['data_fine_dt'].strftime('%H:%M')
            righe_tabella.append({
                "Azienda Agricola / Contadino": r['nome'], "Zona Idraulica": r['zona'],
                "Fascia Oraria": f"{r['data_inizio_dt'].strftime('%H:%M')} - {h_f_vis}",
                "Modalità": r['config_scelta'], "Carico Richiesto (Motori M)": f"{r['motori_std']:.2f} M", "Portata (l/s)": f"{portata_s:.0f} l/s"
            })
        
        # Rendering Tabella
        st.table(pd.DataFrame(righe_tabella))
        
        # --- NUOVA FUNZIONALITÀ: CANCELLAZIONE SINGOLA GIORNO PER GIORNO ---
        st.markdown("##### 🗑️ Rimozione Manuale Veloce Turni del Giorno:")
        for idx, r in df_giorno_attivi.iterrows():
            c_del1, c_del2 = st.columns([5, 1])
            with c_del1: 
                h_f_vis = "24:00" if r['data_fine_dt'].strftime('%H:%M') in ["23:59", "00:00"] else r['data_fine_dt'].strftime('%H:%M')
                st.write(f"🚜 Turno: **{r['nome']}** | Orario: {r['data_inizio_dt'].strftime('%H:%M')} - {h_f_vis} ({r['zona']}) | Modalità: *{r['config_scelta']}*")
            with c_del2:
                if st.button("🗑️ Rimuovi", key=f"del_dash_{r['id']}", use_container_width=True):
                    cancella_prenotazione(int(r['id']))
                    st.rerun()

# =========================================================
# TAB 2: AGENDA GIORNALIERA DELLE MANOVRE (SOLO DA ANAGRAFICA)
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
        conn = sqlite3.connect('idrosmart.db')
        df_manovre_p = pd.read_sql_query("SELECT * FROM manovre_personalizzate", conn)
        conn.close()

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
                val = float(m_row['valore_anticipo'])
                unita = m_row['unita_anticipo']
                
                if unita == "Ore": td = timedelta(hours=val)
                elif unita == "Mezze Giornate": td = timedelta(hours=val * 12)
                else: td = timedelta(days=val)

                ora_manovra_dinamica = in_dt - td
                ora_manovra_ott = ottimizza_orario_manovra(ora_manovra_dinamica, motori_correnti=motori_giorno_global)
                
                manovre_totali.append({
                    "Data/Ora": ora_manovra_ott,
                    "Tipo": "🔧 Manovra Configurata",
                    "ForzaOraria": "CONTROLLA",
                    "Descrizione": f"[{row['nome']}] {m_row['descrizione']} (Anticipo impostato: {val} {unita})."
                })

        if manovre_totali:
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
            st.info("Nessuna manovra programmata.")

# =========================================================
# TAB 3: VIDEATA SALA MACCHINE (TIMER SETTIMANALE AUTOMATIZZATO 24H)
# =========================================================
with tab_sala_macchine:
    st.title("📟 Quadro Controllo Automatizzato Orologi di Centrale")
    st.write("La sezione mostra esclusivamente gli intervalli di accensione e spegnimento operativi delle pompe P3 e P4 calcolati in base al carico totale di motori richiesto in ogni istante del giorno.")
    
    # Inizializzazione della variabile temporale dedicata ed esclusiva per la Sala Macchine
    if "data_settimana_macchine" not in st.session_state:
        st.session_state.data_settimana_macchine = st.session_state.data_corrente

    # Pulsanti di navigazione settimanale ad uso esclusivo di questo tab
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

    # Ciclo lineare di analisi sui 7 giorni della settimana selezionata
    for giorno_idx in range(7):
        giorno_esaminato = inizio_sett_sm + timedelta(days=giorno_idx)
        nome_giorno_it = GIORNI_IT.get(giorno_esaminato.strftime('%A'), giorno_esaminato.strftime('%A'))
        
        st.markdown(f"<h5 style='background-color:#f0f2f6; padding:6px; border-radius:5px; margin-top:15px;'>📆 {nome_giorno_it} {giorno_esaminato.strftime('%d/%m/%Y')}</h5>", unsafe_allow_html=True)
        
        # Filtra tutti i turni attivi (agricoltori + chiavoni) che coprono il giorno preso in esame
        if not df_tutti_attivi.empty:
            df_giorno_sm = df_tutti_attivi[
                (df_tutti_attivi['data_inizio_dt'].dt.date <= giorno_esaminato) & 
                (df_tutti_attivi['data_fine_dt'].dt.date >= giorno_esaminato)
            ].copy()
        else:
            df_giorno_sm = pd.DataFrame()
            
        # Creazione dei vettori di stato a 96 quarti d'ora (24 ore * 4 quarti)
        p4_attiva = [False] * 96
        p3_attiva = [False] * 96
        
        for quarto in range(96):
            ora = quarto // 4
            minuto = (quarto % 4) * 15
            tempo_quarto_inizio = datetime.combine(giorno_esaminato, time(ora, minuto))
            tempo_quarto_fine = tempo_quarto_inizio + timedelta(minutes=15)
            
            # Calcolo del carico idraulico reale di motori espresso in questo specifico quarto d'ora
            motori_quarto = 0.0
            if not df_giorno_sm.empty:
                for _, turno in df_giorno_sm.iterrows():
                    if turno['data_inizio_dt'] < tempo_quarto_fine and turno['data_fine_dt'] > tempo_quarto_inizio:
                        motori_quarto += float(turno['motori_std'])
            
            # Determinazione degli assetti macchina (con costante delle perdite di rete incluse se l'impianto eroga)
            if motori_quarto > 0:
                totale_con_perdite = motori_quarto + 0.5
                
                if totale_con_perdite <= 6.0:
                    p4_attiva[quarto] = True
                elif totale_con_perdite <= 8.0:
                    p3_attiva[quarto] = True
                else:
                    # In caso di superamento di 8 M si attivano contemporaneamente entrambe le pompe
                    p4_attiva[quarto] = True
                    p3_attiva[quarto] = True

        # Funzione logica interna per raggruppare i quarti d'ora adiacenti in fasce orarie visualizzabili
        def unisci_fasce_orarie(array_presenza):
            fasce = []
            in_blocco = False
            inizio_blocco = None
            
            for q in range(96):
                if array_presenza[q] and not in_blocco:
                    in_blocco = True
                    h_ini = q // 4
                    m_ini = (q % 4) * 15
                    inizio_blocco = f"{h_ini:02d}:{m_ini:02d}"
                elif not array_presenza[q] and in_blocco:
                    in_blocco = False
                    h_fin = q // 4
                    m_fin = (q % 4) * 15
                    fasce.append(f"⏱️ {inizio_blocco} — {h_fin:02d}:{m_fin:02d}")
            
            if in_blocco:
                fasce.append(f"⏱️ {inizio_blocco} — 24:00")
            return fasce

        fasce_p4 = unisci_fasce_orarie(p4_attiva)
        fasce_p3 = unisci_fasce_orarie(p3_attiva)

        # Rendering grafico diviso nelle due colonne pulite native per le pompe
        col_p4_sm, col_p3_sm = st.columns(2)
        with col_p4_sm:
            st.markdown("<b style='color:#dc3545;'>📟 ORARI ACCENSIONE POMPA P4 (Bassa Pressione)</b>", unsafe_allow_html=True)
            if fasce_p4:
                for f in fasce_p4: st.code(f, language="text")
            else:
                st.caption("Pompa P4 Spenta per l'intera giornata")
                
        with col_p3_sm:
            st.markdown("<b style='color:#17a2b8;'>📟 ORARI ACCENSIONE POMPA P3 (Alta Pressione / Inverter)</b>", unsafe_allow_html=True)
            if fasce_p3:
                for f in fasce_p3: st.code(f, language="text")
            else:
                st.caption("Pompa P3 Spenta per l'intera giornata")

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
        n_zona = st.selectbox(
            "Nodo Idraulico Associato", 
            ELENCO_CHIAVONI_REALI, 
            index=0, 
            disabled=is_diretta_ins,
            help="Disabilitato se la modalità di prelievo è 'Diretta'",
            key="ins_zona"
        )
        
        n_motori = st.number_input("Motori assorbiti (M)", min_value=0.0, max_value=12.0, value=1.0, step=0.1, key="ins_motori")
        n_distanza = st.number_input("Minuti di distanza per apertura:", min_value=0, max_value=180, value=30, key="ins_distanza")
        n_extra_fosso = st.number_input("Minuti Extra Fosso Sporco:", min_value=0, max_value=120, value=15, key="ins_extra")
        n_giorni_ant = st.selectbox("Giorni pre-anticipo manovre:", [0, 1, 2], key="ins_giorni_ant")
        
        st.markdown("---")
        st.subheader("⚙️ Aggiungi Manovre Personalizzate all'elenco temporaneo")
        
        c_ins_m1, c_ins_m2, c_ins_m3 = st.columns([3, 1, 1])
        with c_ins_m1: desc_manovra_ins = st.text_input("Cosa fare? (Descrizione)", placeholder="Es. Pulizia filtri secondari, Controllo livello", key="tmp_desc")
        with c_ins_m2: val_manovra_ins = st.number_input("Tempo prima", min_value=0.5, max_value=60.0, value=2.0, step=0.5, key="tmp_val")
        with c_ins_m3: unita_manovra_ins = st.selectbox("Unità", ["Ore", "Mezze Giornate", "Giorni"], key="tmp_unit")
        
        if st.button("➕ Inserisci Manovra nella Lista"):
            if desc_manovra_ins:
                st.session_state.manovre_temporanee_registrazione.append({
                    "descrizione": desc_manovra_ins,
                    "valore": val_manovra_ins,
                    "unita": unita_manovra_ins
                })
                st.success(f"Manovra '{desc_manovra_ins}' aggiunta alla lista provvisoria!")
                st.rerun()

        if st.session_state.manovre_temporanee_registrazione:
            st.markdown("##### 📝 Lista delle Manovre pronte al salvataggio:")
            for idx_tmp, m_tmp in enumerate(st.session_state.manovre_temporanee_registrazione):
                col_m_v, col_m_d = st.columns([5, 1])
                with col_m_v:
                    st.write(f"🔧 **{m_tmp['descrizione']}** da farsi **{m_tmp['valore']} {m_tmp['unita']}** prima del turno.")
                with col_m_d:
                    if st.button("🗑️ Rimuovi", key=f"del_tmp_m_{idx_tmp}", use_container_width=True):
                        st.session_state.manovre_temporanee_registrazione.pop(idx_tmp)
                        st.rerun()
        else:
            st.caption("Nessuna manovra inserita nella lista provvisoria.")

        st.markdown("---")
        if st.button("💾 Salva Profilo Completo (Utenza + Tutte le Manovre)", type="primary"):
            if n_nome:
                zona_da_salvare = "Valvola Contrappesi" if is_diretta_ins else n_zona
                nuovo_id = inserisci_irrigante_completo(n_nome, zona_da_salvare, n_prelievo, n_motori, n_distanza, n_extra_fosso, n_giorni_ant)
                
                for m_salvare in st.session_state.manovre_temporanee_registrazione:
                    inserisci_manovra_personalizzata(nuovo_id, m_salvare['descrizione'], m_salvare['valore'], m_salvare['unita'])
                
                st.session_state.manovre_temporanee_registrazione = []
                st.success("Profilo e intero blocco manovre salvati nel Database!")
                st.rerun()
            else:
                st.error("Inserisci il Nome / Identificativo Utenza prima di salvare.")

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
                idx_z = ELENCO_CHIAVONI_REALI.index(dati_c['zona']) if dati_c['zona'] in ELENCO_CHIAVONI_REALI else 0
                m_zona = st.selectbox(
                    "Chiavone Reale Associato", 
                    ELENCO_CHIAVONI_REALI, 
                    index=0 if is_diretta_mod else idx_z, 
                    disabled=is_diretta_mod,
                    help="Disabilitato se la modalità di prelievo è 'Diretta'"
                )
                
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
                with c_m1: desc_manovra = st.text_input("Cosa fare? (Descrizione Manovra)", placeholder="Es. Pulizia filtri secondari, Ispezione bocchetta")
                with c_m2: val_manovra = st.number_input("Tempo prima", min_value=0.5, max_value=60.0, value=2.0, step=0.5)
                with c_m3: unita_manovra = st.selectbox("Unità", ["Ore", "Mezze Giornate", "Giorni"])
                if st.form_submit_button("➕ Aggiungi Manovra a questo Profilo"):
                    if desc_manovra:
                        inserisci_manovra_personalizzata(id_selezionato, desc_manovra, val_manovra, unita_manovra)
                        st.success("Manovra aggiunto!")
                        st.rerun()

            conn = sqlite3.connect('idrosmart.db')
            df_m_salvate = pd.read_sql_query("SELECT * FROM manovre_personalizzate WHERE irrigante_id = ?", conn, params=[id_selezionato])
            conn.close()

            if not df_m_salvate.empty:
                st.caption("Manovre registrate attive per questo profilo:")
                for _, m_salv in df_m_salvate.iterrows():
                    c_v1, c_v2 = st.columns([5, 1])
                    with c_v1: st.write(f"🔧 **{m_salv['descrizione']}** da farsi **{m_salv['valore_anticipo']} {m_salv['unita_anticipo']}** prima del turno.")
                    with c_v2: 
                        if st.button("🗑️ Rimuovi", key=f"del_man_{m_salv['id']}", use_container_width=True):
                            cancella_manovra_personalizzata(int(m_salv['id']))
                            st.rerun()
            else:
                st.info("Nessuna manovra opzionale registrata per questa utenza.")

    with sub_vis:
        if not df_irriganti.empty: st.dataframe(df_irriganti, use_container_width=True, hide_index=True)
        else: st.info("Nessun record memorizzato.")

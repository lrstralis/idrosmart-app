# =========================================================
# TAB 1: GESTIONE TURNI & RETE
# =========================================================
with tab_dashboard:
    st.title("💧 IdroSmart PRO — Controllo Distribuzione Idrica")
    st.sidebar.header("➕ Inserisci Nuovo Turno")
    
    tipo_elemento_scelto = st.sidebar.radio("Tipo Elemento da inserire:", ["Agricoltori", "Chiavoni"], horizontal=True)
    
    if tipo_elemento_scelto == "Agricoltori":
        opzioni_sb = df_irriganti['nome'].tolist() if not df_irriganti.empty else []
        if not opzioni_sb:
            opzioni_sb = ["Nessun agricoltore registrato"]
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
        tipo_prelievo_default = "Fosso" if tipo_elemento_scelto == "Chiavoni" else tipo_pesca_scelta
        motori_default = 1.0
        zona_default = irrigante_scelto if irrigante_scelto in ELENCO_CHIAVONI_REALI else "Generico"
        
    if tipo_pesca_scelta == "Fosso" or tipo_elemento_scelto == "Chiavoni":
        # Usiamo una chiave fissa "motori_input_fissa" per evitare che Streamlit perda lo stato al cambio selezione
        motori_scelti_sb = st.sidebar.number_input("Motori totali da far uscire (M):", min_value=0.0, max_value=12.0, value=motori_default, step=0.01, key="motori_input_fissa")
        giri_calc_sb, _ = calcola_giri_chiavone(motori_scelti_sb, zona_default)
        st.sidebar.success(f"⚙️ Giri Chiavone calcolati: **{giri_calc_sb:.2f} Giri**")
    else:
        motori_scelti_sb = motori_default

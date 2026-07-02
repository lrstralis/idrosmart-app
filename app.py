# === CORREZIONE BLOCCO 1 (Pompa P4) ===
        fasce_p4 = unisci_fasce_orarie(p4_attiva)
        fasce_p3 = unisci_fasce_orarie(p3_attiva)

        col_p4_sm, col_p3_sm = st.columns(2)
        with col_p4_sm:
            st.markdown("<b style='color:#dc3545;'>📟 ORARI ACCENSIONE POMPA P4 (Bassa Pressione)</b>", unsafe_allow_html=True)
            if fasce_p4:
                for idx_f, fascia_oraria_testo in enumerate(fasce_p4): 
                    st.code(fascia_oraria_testo, language="text", key=f"code_p4_{giorno_idx}_{idx_f}")
            else:
                st.caption("Pompa P4 Spenta per l'intera giornata")
                
        # === CORREZIONE BLOCCO 2 (Pompa P3) ===
        with col_p3_sm:
            st.markdown("<b style='color:#17a2b8;'>📟 ORARI ACCENSIONE POMPA P3 (Alta Pressione / Inverter)</b>", unsafe_allow_html=True)
            if fasce_p3:
                for idx_f, fascia_oraria_testo in enumerate(fasce_p3): 
                    st.code(fascia_oraria_testo, language="text", key=f"code_p3_{giorno_idx}_{idx_f}")
            else:
                st.caption("Pompa P3 Spenta per l'intera giornata")

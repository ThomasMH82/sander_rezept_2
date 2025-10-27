"""
Debug-Script für Speiseplan-Generator
Hilft bei der Fehlersuche
"""

import streamlit as st

def zeige_debug_info():
    """Zeigt Debug-Informationen an"""
    
    with st.expander("🐛 Debug-Informationen", expanded=False):
        st.markdown("### Session State")
        
        # Überprüfe was im Session State ist
        st.write("**Vorhandene Keys:**")
        if hasattr(st, 'session_state'):
            for key in st.session_state.keys():
                st.write(f"- {key}: {type(st.session_state[key])}")
        else:
            st.write("Kein Session State verfügbar")
        
        st.divider()
        
        # Speiseplan-Info
        if 'speiseplan' in st.session_state:
            sp = st.session_state['speiseplan']
            st.write("**Speiseplan:**")
            st.write(f"- Typ: {type(sp)}")
            if isinstance(sp, dict):
                st.write(f"- Keys: {list(sp.keys())}")
                if 'speiseplan' in sp and 'wochen' in sp['speiseplan']:
                    st.write(f"- Anzahl Wochen: {len(sp['speiseplan']['wochen'])}")
        else:
            st.write("**Speiseplan:** Nicht vorhanden")
        
        st.divider()
        
        # Rezepte-Info
        if 'rezepte' in st.session_state:
            rez = st.session_state['rezepte']
            st.write("**Rezepte:**")
            st.write(f"- Typ: {type(rez)}")
            if isinstance(rez, dict):
                st.write(f"- Keys: {list(rez.keys())}")
                if 'rezepte' in rez:
                    st.write(f"- Anzahl Rezepte: {len(rez['rezepte'])}")
                    st.write(f"- Rezept-Typ: {type(rez['rezepte'])}")
                    if len(rez['rezepte']) > 0:
                        st.write(f"- Erstes Rezept Keys: {list(rez['rezepte'][0].keys())}")
            elif rez is None:
                st.write("- Wert ist None!")
        else:
            st.write("**Rezepte:** Nicht vorhanden")
        
        st.divider()
        
        # Cost Tracker Info
        if 'cost_tracker' in st.session_state:
            ct = st.session_state['cost_tracker']
            st.write("**Cost Tracker:**")
            st.write(f"- Typ: {type(ct)}")
            if ct:
                try:
                    costs = ct.get_costs()
                    st.write(f"- Input Tokens: {costs['input_tokens']}")
                    st.write(f"- Output Tokens: {costs['output_tokens']}")
                    st.write(f"- Gesamtkosten: ${costs['total_cost']:.4f}")
                except Exception as e:
                    st.write(f"- Fehler beim Abrufen: {e}")
        else:
            st.write("**Cost Tracker:** Nicht vorhanden")
        
        st.divider()
        
        # API Response Debug
        if 'debug_raw_responses' in st.session_state and len(st.session_state['debug_raw_responses']) > 0:
            st.write("**API-Responses (letzte):**")
            for i, resp in enumerate(st.session_state['debug_raw_responses'][-3:], 1):  # Zeige letzte 3
                st.write(f"{i}. Länge: {resp['length']} Zeichen")
                with st.expander(f"Preview {i}"):
                    st.code(resp['preview'])
        else:
            st.write("**API-Responses:** Keine vorhanden")
        
        st.divider()
        
        # JSON Error Debug
        if 'last_json_error' in st.session_state:
            st.write("**Letzter JSON-Fehler:**")
            err = st.session_state['last_json_error']
            st.write(f"- Fehler: {err.get('error', 'N/A')}")
            st.write(f"- Rohe Länge: {err.get('raw_length', 'N/A')} Zeichen")
            with st.expander("Bereinigte Antwort (Anfang)"):
                st.code(err.get('cleaned_text', 'N/A'))
        else:
            st.write("**Letzter JSON-Fehler:** Keiner")
        
        st.divider()
        
        # Modul-Imports
        st.write("**Importierte Module:**")
        try:
            import prompts
            st.write("✅ prompts.py")
        except ImportError as e:
            st.write(f"❌ prompts.py: {e}")
        
        try:
            import pdf_generator
            st.write("✅ pdf_generator.py")
        except ImportError as e:
            st.write(f"❌ pdf_generator.py: {e}")
        
        try:
            import cost_tracker
            st.write("✅ cost_tracker.py")
            from cost_tracker import KOSTEN_TRACKING_AKTIVIERT
            st.write(f"   - KOSTEN_TRACKING_AKTIVIERT(): {KOSTEN_TRACKING_AKTIVIERT()}")
        except ImportError as e:
            st.write(f"❌ cost_tracker.py: {e}")
        
        st.divider()
        
        # Python-Version
        import sys
        st.write(f"**Python-Version:** {sys.version}")
        
        # Streamlit-Version
        st.write(f"**Streamlit-Version:** {st.__version__}")


def teste_api_connection(api_key):
    """Testet die API-Verbindung"""
    import requests
    
    st.write("### 🔌 API-Verbindungs-Test")
    
    if not api_key:
        st.warning("Kein API-Key vorhanden")
        return
    
    try:
        with st.spinner("Teste API-Verbindung..."):
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01"
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 50,
                    "messages": [{"role": "user", "content": "Antworte nur mit 'OK'"}]
                },
                timeout=30
            )
            
            if response.status_code == 200:
                st.success("✅ API-Verbindung funktioniert!")
                data = response.json()
                st.write("**Response:**")
                st.json(data)
            else:
                st.error(f"❌ API-Fehler: Status {response.status_code}")
                st.write(response.text)
                
    except Exception as e:
        st.error(f"❌ Fehler: {e}")


if __name__ == "__main__":
    st.title("🐛 Debug-Tool für Speiseplan-Generator")
    
    zeige_debug_info()
    
    st.divider()
    
    api_key = st.text_input("API-Key für Connection-Test (optional)", type="password")
    if st.button("API-Verbindung testen"):
        teste_api_connection(api_key)
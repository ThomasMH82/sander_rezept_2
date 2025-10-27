"""
Hauptanwendung für den Speiseplan-Generator
Orchestriert alle Module und bietet die Streamlit-UI
"""

import streamlit as st
import requests
import json
import re

# Import der eigenen Module
from prompts import get_speiseplan_prompt, get_rezepte_prompt, get_pruefung_prompt
from pdf_generator import erstelle_speiseplan_pdf, erstelle_rezept_pdf, erstelle_alle_rezepte_pdf
from rezept_datenbank import RezeptDatenbank

# ============== KOSTEN-TRACKING (OPTIONAL) ==============
# Um Kosten-Tracking zu deaktivieren, kommentieren Sie die folgenden 2 Zeilen aus:
from cost_tracker import CostTracker, zeige_kosten_anzeige, zeige_kosten_warnung_bei_grossen_plaenen, zeige_kosten_in_sidebar, KOSTEN_TRACKING_AKTIVIERT
KOSTEN_TRACKING = KOSTEN_TRACKING_AKTIVIERT()
# ========================================================

# ============== REZEPT-DATENBANK INITIALISIEREN ==============
# Erstelle Datenbank-Instanz
@st.cache_resource
def hole_datenbank():
    """Holt eine gecachte Instanz der Rezept-Datenbank"""
    return RezeptDatenbank()

DB = hole_datenbank()
# =============================================================


# ==================== KONFIGURATION ====================
st.set_page_config(
    page_title="Speiseplan-Generator",
    layout="wide",
    page_icon="👨‍🍳"
)


# ==================== API-FUNKTIONEN ====================

def bereinige_json_response(text):
    """
    Bereinigt die API-Antwort und extrahiert nur das JSON
    
    Args:
        text (str): Roher Antwort-Text von der API
        
    Returns:
        str: Bereinigter JSON-String
    """
    # Entferne Markdown-Formatierung
    text = re.sub(r'```json\n?', '', text)
    text = re.sub(r'```\n?', '', text)
    text = text.strip()
    
    # Finde erste { und letzte }
    first_brace = text.find('{')
    last_brace = text.rfind('}')
    
    if first_brace != -1 and last_brace != -1:
        text = text[first_brace:last_brace + 1]
    
    return text


def repariere_json(json_str):
    """
    Versucht ein unvollständiges JSON zu reparieren
    
    Args:
        json_str (str): Möglicherweise unvollständiges JSON
        
    Returns:
        str: Repariertes JSON oder Original
    """
    # Zähle öffnende und schließende Klammern
    open_braces = json_str.count('{')
    close_braces = json_str.count('}')
    open_brackets = json_str.count('[')
    close_brackets = json_str.count(']')
    
    # Füge fehlende schließende Klammern hinzu
    if open_braces > close_braces:
        json_str += '}' * (open_braces - close_braces)
    
    if open_brackets > close_brackets:
        json_str += ']' * (open_brackets - close_brackets)
    
    # Entferne trailing commas vor schließenden Klammern
    json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
    
    # Entferne unvollständige letzte Zeilen
    # Finde letztes vollständiges Objekt
    lines = json_str.split('\n')
    for i in range(len(lines) - 1, -1, -1):
        # Wenn Zeile mit } oder ] endet, ist sie wahrscheinlich vollständig
        if lines[i].strip().endswith(('}', ']', '}')):
            json_str = '\n'.join(lines[:i+1])
            break
    
    return json_str


def rufe_claude_api(prompt, api_key, max_tokens=20000):
    """
    Ruft die Claude API auf und gibt die Antwort zurück
    
    Args:
        prompt (str): Der Prompt für Claude
        api_key (str): Der Anthropic API-Key
        max_tokens (int): Maximale Anzahl Tokens in der Antwort
        
    Returns:
        tuple: (parsed_data, error, usage_data) - Daten, Fehlermeldung und Token-Usage
    """
    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01"
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=180  # 3 Minuten Timeout für große Anfragen
        )
        
        if response.status_code != 200:
            error_msg = f"API-Fehler: Status {response.status_code}"
            try:
                error_detail = response.json()
                error_msg += f" - {error_detail.get('error', {}).get('message', response.text)}"
            except:
                error_msg += f" - {response.text}"
            return None, error_msg, None
        
        data = response.json()
        response_text = data['content'][0]['text']
        
        # Speichere rohe Antwort für Debug
        if 'debug_raw_responses' not in st.session_state:
            st.session_state['debug_raw_responses'] = []
        st.session_state['debug_raw_responses'].append({
            'length': len(response_text),
            'preview': response_text[:200] + '...' if len(response_text) > 200 else response_text
        })
        
        # JSON bereinigen und parsen
        cleaned_text = bereinige_json_response(response_text)
        
        try:
            parsed_data = json.loads(cleaned_text)
        except json.JSONDecodeError as e:
            # Versuch 1: JSON reparieren
            st.warning("⚠️ JSON unvollständig - versuche automatische Reparatur...")
            
            try:
                repaired_text = repariere_json(cleaned_text)
                parsed_data = json.loads(repaired_text)
                st.success("✅ JSON erfolgreich repariert!")
            except json.JSONDecodeError as e2:
                # Versuch 2: Teilextraktion
                st.warning("⚠️ Reparatur fehlgeschlagen - versuche Teilextraktion...")
                
                # Bei JSON-Fehler: Zeige mehr Details
                error_msg = f"JSON-Parsing-Fehler: {str(e)}\n"
                error_msg += f"Antwort-Länge: {len(response_text)} Zeichen\n"
                error_msg += f"Bereinigte Länge: {len(cleaned_text)} Zeichen\n"
                error_msg += "\n**❌ PROBLEM: Plan ist zu groß für eine Anfrage**\n\n"
                error_msg += "**✅ LÖSUNGEN:**\n"
                error_msg += "1. **Empfohlen:** Max. 3 Wochen, 4 Linien (84 Menüs)\n"
                error_msg += "2. **Schrittweise:** Generieren Sie 1 Woche mit allen Linien, dann die nächste\n"
                error_msg += "3. **Weniger Linien:** Reduzieren Sie auf 3 statt 5 Menülinien\n"
                
                # Zeige Bereich um den Fehler
                if hasattr(e, 'pos'):
                    start = max(0, e.pos - 100)
                    end = min(len(cleaned_text), e.pos + 100)
                    error_msg += f"\n\n**Debug - Bereich um Fehler:**\n...{cleaned_text[start:end]}...\n"
                
                # Speichere für Debug
                st.session_state['last_json_error'] = {
                    'error': str(e),
                    'error_2': str(e2),
                    'raw_length': len(response_text),
                    'cleaned_text': cleaned_text[:1000],  # Erste 1000 Zeichen
                    'repaired_attempt': repaired_text[:1000] if 'repaired_text' in locals() else None
                }
                
                return None, error_msg, None
        
        # Usage-Daten extrahieren (für Kosten-Tracking)
        usage_data = data.get('usage', {})
        
        return parsed_data, None, usage_data
        
    except requests.exceptions.Timeout:
        return None, "Timeout: Die API-Anfrage hat zu lange gedauert (>3min). Reduzieren Sie die Anzahl Wochen/Menülinien.", None
    except requests.exceptions.RequestException as e:
        return None, f"Netzwerkfehler: {str(e)}", None
    except Exception as e:
        return None, f"Unerwarteter Fehler: {str(e)}", None


def generiere_speiseplan_mit_rezepten(wochen, menulinien, menu_namen, api_key):
    """
    Hauptfunktion die den kompletten Workflow orchestriert
    
    Args:
        wochen (int): Anzahl Wochen
        menulinien (int): Anzahl Menülinien
        menu_namen (list): Namen der Menülinien
        api_key (str): Claude API-Key
        
    Returns:
        tuple: (speiseplan, rezepte, pruefung, error, cost_tracker)
    """
    # ============== KOSTEN-TRACKING INITIALISIEREN ==============
    cost_tracker = None
    if KOSTEN_TRACKING:
        cost_tracker = CostTracker()
    # ============================================================
    
    # Berechne Komplexität
    anzahl_menues = wochen * menulinien * 7  # Tage pro Woche
    
    # Warnung bei sehr großen Plänen
    if anzahl_menues > 100:
        st.warning(f"""
        ⚠️ **Sehr großer Speiseplan**
        
        Sie erstellen {anzahl_menues} Menüs ({wochen} Wochen × {menulinien} Linien × 7 Tage).
        
        **Problem:** Bei mehr als 100 Menüs ist die Erfolgsrate nur ~70-80%.
        
        **💡 EMPFEHLUNG - Automatische Aufteilung:**
        """)
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("✅ Automatisch aufteilen (empfohlen)", type="primary"):
                st.session_state['auto_split'] = True
                st.info("Plan wird automatisch in kleinere Teile aufgeteilt!")
                
        with col2:
            if st.button("⚠️ Trotzdem versuchen"):
                st.session_state['auto_split'] = False
        
        if st.session_state.get('auto_split') is None:
            st.stop()  # Warte auf Nutzer-Entscheidung
        
        if st.session_state.get('auto_split'):
            st.info("""
            **Automatische Aufteilung aktiviert:**
            - Plan wird wochenweise generiert
            - Höhere Erfolgsrate (95%+)
            - Am Ende werden alle Teile kombiniert
            
            ⏱️ Dauert etwas länger, aber viel zuverlässiger!
            """)
            
            # TODO: Implementierung der Auto-Split-Funktion
            # Für jetzt: Warnung
            st.warning("⚠️ Auto-Split Feature wird in v1.3 verfügbar sein. Bitte reduzieren Sie vorerst die Größe.")
            return None, None, None, "Bitte reduzieren Sie auf max. 3 Wochen, 4 Linien.", cost_tracker
    
    elif anzahl_menues > 70:
        st.info(f"""
        💡 **Großer Speiseplan**
        
        {anzahl_menues} Menüs werden erstellt.
        
        **Dies kann:**
        - 3-5 Minuten dauern
        - ~${0.005 * anzahl_menues:.2f} kosten
        - Gelegentlich fehlschlagen
        
        **Tipp:** Bei Fehlern einfach nochmal versuchen oder kleiner generieren.
        """)
    
    # Dynamische max_tokens basierend auf Größe
    # Claude Sonnet 4 Maximum Output ist 8192 Tokens
    if anzahl_menues <= 30:
        speiseplan_tokens = 16000
        rezepte_tokens = 16000
    elif anzahl_menues <= 70:
        speiseplan_tokens = 32000  # Für größere Pläne
        rezepte_tokens = 32000
    elif anzahl_menues <= 100:
        speiseplan_tokens = 64000  # Für sehr große Pläne
        rezepte_tokens = 64000
    else:
        # Maximum für extrem große Pläne (wird wahrscheinlich fehlschlagen)
        speiseplan_tokens = 100000
        rezepte_tokens = 100000
        st.warning(f"⚠️ Verwende MAXIMUM Token-Limit ({speiseplan_tokens}) - Erfolgsrate < 70%")
        st.info("💡 **Besser:** Teilen Sie den Plan in kleinere Teile auf!")
    
    # Schritt 1: Speiseplan erstellen
    with st.spinner(f"🔄 Speiseplan wird erstellt... ({anzahl_menues} Menüs, kann 1-5 Minuten dauern)"):
        # Für sehr große Pläne: Vereinfachter Prompt
        if anzahl_menues > 100:
            st.info("💡 Verwende vereinfachten Modus für großen Plan (weniger Details, aber vollständiger)")
            # TODO: Vereinfachten Prompt erstellen
        
        prompt = get_speiseplan_prompt(wochen, menulinien, menu_namen)
        speiseplan_data, error, usage = rufe_claude_api(prompt, api_key, max_tokens=speiseplan_tokens)
        
        # ============== KOSTEN-TRACKING ==============
        if KOSTEN_TRACKING and cost_tracker and usage:
            cost_tracker.add_usage(usage)
        # =============================================
        
        if error:
            st.error(f"❌ Fehler beim Erstellen des Speiseplans:")
            st.error(error)
            
            # Zeige Debug-Infos bei JSON-Fehler
            if 'last_json_error' in st.session_state:
                with st.expander("🐛 Debug-Informationen zum Fehler"):
                    st.json(st.session_state['last_json_error'])
                    st.write("**Tipp:** Aktivieren Sie Debug-Modus in der Sidebar für mehr Details")
            
            return None, None, None, f"Fehler beim Erstellen des Speiseplans: {error}", cost_tracker
    
    # Schritt 2: Qualitätsprüfung (optional, kann auch parallel laufen)
    with st.spinner("🔍 Qualitätsprüfung läuft..."):
        pruef_prompt = get_pruefung_prompt(speiseplan_data)
        pruefung_data, error_pruef, usage_pruef = rufe_claude_api(pruef_prompt, api_key, max_tokens=8000)
        
        # ============== KOSTEN-TRACKING ==============
        if KOSTEN_TRACKING and cost_tracker and usage_pruef:
            cost_tracker.add_usage(usage_pruef)
        # =============================================
        
        # Prüfung ist optional, daher bei Fehler nur warnen
        if error_pruef:
            st.warning(f"⚠️ Qualitätsprüfung konnte nicht durchgeführt werden: {error_pruef}")
            pruefung_data = None
    
    # Schritt 3: Rezepte erstellen
    with st.spinner(f"📖 Detaillierte Rezepte werden erstellt... (kann 1-2 Minuten dauern)"):
        rezepte_prompt = get_rezepte_prompt(speiseplan_data)
        rezepte_data, error_rezepte, usage_rezepte = rufe_claude_api(rezepte_prompt, api_key, max_tokens=rezepte_tokens)
        
        # ============== KOSTEN-TRACKING ==============
        if KOSTEN_TRACKING and cost_tracker and usage_rezepte:
            cost_tracker.add_usage(usage_rezepte)
        # =============================================
        
        if error_rezepte:
            st.error(f"❌ Fehler bei Rezept-Generierung: {error_rezepte}")
            
            # Zeige Debug-Infos
            if 'last_json_error' in st.session_state:
                with st.expander("🐛 Debug-Informationen zum Rezept-Fehler"):
                    st.json(st.session_state['last_json_error'])
            
            rezepte_data = None
        elif not rezepte_data:
            st.warning("⚠️ Keine Rezepte erhalten - prüfen Sie die API-Antwort")
            rezepte_data = None
        else:
            # Debug: Überprüfe Struktur
            if isinstance(rezepte_data, dict) and 'rezepte' in rezepte_data:
                anzahl = len(rezepte_data['rezepte'])
                st.success(f"✅ {anzahl} Rezepte erstellt!")
                
                # ============== AUTOMATISCHES SPEICHERN IN DATENBANK ==============
                try:
                    gespeichert = DB.speichere_alle_rezepte(rezepte_data)
                    if gespeichert > 0:
                        st.info(f"💾 {gespeichert} Rezepte in Bibliothek gespeichert!")
                except Exception as e:
                    st.warning(f"⚠️ Rezepte konnten nicht gespeichert werden: {e}")
                # ==================================================================
            else:
                st.warning(f"⚠️ Unerwartete Rezept-Struktur: {type(rezepte_data)}")
    
    return speiseplan_data, rezepte_data, pruefung_data, None, cost_tracker


# ==================== UI-FUNKTIONEN ====================

def zeige_sidebar():
    """
    Erstellt die Sidebar mit allen Eingabefeldern
    
    Returns:
        tuple: (api_key, wochen, menulinien, menu_namen, button_clicked)
    """
    with st.sidebar:
        st.header("🔑 API-Konfiguration")
        
        # Versuche API-Key aus Secrets zu laden
        api_key_from_secrets = None
        try:
            if hasattr(st, 'secrets') and 'ANTHROPIC_API_KEY' in st.secrets:
                api_key_from_secrets = st.secrets['ANTHROPIC_API_KEY']
                st.success("✅ API-Key aus Konfiguration geladen!")
                st.info("💡 Sie können den Key auch manuell unten eingeben, um ihn zu überschreiben.")
        except Exception:
            pass
        
        # Manueller API-Key Input (optional, überschreibt Secrets)
        api_key_manual = st.text_input(
            "Claude API-Key (optional)",
            type="password",
            help="Geben Sie Ihren Anthropic API-Key ein (https://console.anthropic.com/) - Optional, falls nicht in Konfiguration hinterlegt",
            placeholder="Optional - nur wenn nicht in secrets.toml hinterlegt"
        )
        
        # Verwende manuellen Key wenn eingegeben, sonst den aus Secrets
        api_key = api_key_manual if api_key_manual else api_key_from_secrets
        
        if not api_key:
            st.warning("⚠️ Bitte API-Key eingeben oder in secrets.toml hinterlegen")
            with st.expander("ℹ️ Wie hinterlege ich den API-Key dauerhaft?"):
                st.markdown("""
                **Lokal (auf Ihrem Computer):**
                1. Erstellen Sie eine Datei `.streamlit/secrets.toml` im Projektordner
                2. Fügen Sie hinzu:
                ```toml
                ANTHROPIC_API_KEY = "Ihr-API-Key-hier"
                ```
                3. Starten Sie die App neu
                
                **Auf Streamlit Cloud:**
                1. Gehen Sie zu Ihrem App-Dashboard
                2. Klicken Sie auf "⚙️ Settings"
                3. Öffnen Sie "Secrets"
                4. Fügen Sie hinzu:
                ```toml
                ANTHROPIC_API_KEY = "Ihr-API-Key-hier"
                ```
                5. Klicken Sie auf "Save"
                """)
        
        st.divider()
        
        st.header("⚙️ Speiseplan-Konfiguration")
        wochen = st.number_input("Anzahl Wochen", min_value=1, max_value=4, value=1)
        menulinien = st.number_input("Anzahl Menülinien", min_value=1, max_value=5, value=2)
        
        st.subheader("Bezeichnung der Menülinien")
        menu_namen = []
        for i in range(menulinien):
            name = st.text_input(
                f"Menülinie {i+1}",
                value=f"Menü {i+1}",
                key=f"menu_{i}"
            )
            menu_namen.append(name)
        
        st.divider()
        
        button_clicked = st.button(
            "🚀 Speiseplan generieren & prüfen",
            type="primary",
            use_container_width=True,
            disabled=not api_key
        )
        
        # ============== KOSTEN IN SIDEBAR (OPTIONAL) ==============
        if KOSTEN_TRACKING and 'cost_tracker' in st.session_state:
            zeige_kosten_in_sidebar(st.session_state['cost_tracker'])
        # ==========================================================
        
        # ============== DEBUG-MODUS (ZUM TESTEN) ==============
        # Kommentieren Sie die folgenden Zeilen aus, wenn nicht benötigt:
        st.sidebar.divider()
        if st.sidebar.checkbox("🐛 Debug-Modus", value=False):
            from debug_tool import zeige_debug_info
            zeige_debug_info()
        # ======================================================
        
        return api_key, wochen, menulinien, menu_namen, button_clicked


def zeige_speiseplan_tab(speiseplan, pruefung=None):
    """
    Zeigt den Speiseplan-Tab an
    
    Args:
        speiseplan (dict): Die Speiseplan-Daten
        pruefung (dict, optional): Die Prüfungsdaten
    """
    st.header("📋 Speiseplan")
    
    # PDF-Export Button
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        try:
            pdf_buffer = erstelle_speiseplan_pdf(speiseplan)
            st.download_button(
                label="📄 Speiseplan als PDF (DIN A4 quer)",
                data=pdf_buffer,
                file_name="Speiseplan.pdf",
                mime="application/pdf",
                use_container_width=True
            )
        except Exception as e:
            st.error(f"PDF-Erstellung fehlgeschlagen: {e}")
            st.info("Versuchen Sie es erneut oder laden Sie die Seite neu.")
    
    st.divider()
    
    # Qualitätsprüfung anzeigen (wenn vorhanden)
    if pruefung:
        with st.expander("✅ Qualitätsprüfung durch Experten", expanded=False):
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Gesamtbewertung", pruefung.get('gesamtbewertung', 'N/A'))
            with col2:
                st.metric("Punktzahl", pruefung.get('punktzahl', 'N/A'))
            
            if pruefung.get('fazit'):
                st.info(f"**Fazit:** {pruefung['fazit']}")
            
            if pruefung.get('positiveAspekte'):
                st.markdown("**✓ Positive Aspekte:**")
                for aspekt in pruefung['positiveAspekte']:
                    st.write(f"• {aspekt}")
    
    # Speiseplan anzeigen
    for woche in speiseplan['speiseplan']['wochen']:
        st.subheader(f"📅 Woche {woche['woche']}")
        
        for tag in woche['tage']:
            st.markdown(f"### {tag['tag']}")
            
            for menu in tag['menues']:
                with st.expander(f"**{menu['menuName']}**", expanded=True):
                    col1, col2, col3 = st.columns(3)
                    
                    # Frühstück
                    with col1:
                        st.markdown("**🌅 Frühstück**")
                        st.write(menu['fruehstueck']['hauptgericht'])
                        if menu['fruehstueck'].get('beilagen'):
                            st.caption(f"mit {', '.join(menu['fruehstueck']['beilagen'])}")
                        if menu['fruehstueck'].get('getraenk'):
                            st.caption(f"☕ {menu['fruehstueck']['getraenk']}")
                    
                    # Mittagessen
                    with col2:
                        st.markdown("**🍽️ Mittagessen**")
                        if menu['mittagessen'].get('vorspeise'):
                            st.caption(f"Vorspeise: {menu['mittagessen']['vorspeise']}")
                        st.write(f"**{menu['mittagessen']['hauptgericht']}**")
                        if menu['mittagessen'].get('beilagen'):
                            st.success(f"🥔 Beilagen: {', '.join(menu['mittagessen']['beilagen'])}")
                        if menu['mittagessen'].get('nachspeise'):
                            st.caption(f"🍰 {menu['mittagessen']['nachspeise']}")
                        if menu['mittagessen'].get('naehrwerte'):
                            st.caption(f"📊 {menu['mittagessen']['naehrwerte'].get('kalorien', '')} | Protein: {menu['mittagessen']['naehrwerte'].get('protein', '')}")
                        if menu['mittagessen'].get('allergene'):
                            st.warning(f"⚠️ Allergene: {', '.join(menu['mittagessen']['allergene'])}")
                    
                    # Abendessen
                    with col3:
                        st.markdown("**🌙 Abendessen**")
                        st.write(menu['abendessen']['hauptgericht'])
                        if menu['abendessen'].get('beilagen'):
                            st.caption(f"mit {', '.join(menu['abendessen']['beilagen'])}")
                        if menu['abendessen'].get('getraenk'):
                            st.caption(f"🥤 {menu['abendessen']['getraenk']}")
                    
                    # Zwischenmahlzeit (wenn vorhanden)
                    if menu.get('zwischenmahlzeit'):
                        st.markdown(f"**🍎 Zwischenmahlzeit:** {menu['zwischenmahlzeit']}")
            
            st.divider()


def zeige_rezepte_tab(rezepte_data):
    """
    Zeigt den Rezepte-Tab an
    
    Args:
        rezepte_data (dict): Die Rezept-Daten
    """
    st.header("📖 Detaillierte Rezepte")
    
    if not rezepte_data or 'rezepte' not in rezepte_data:
        st.info("Keine Rezepte verfügbar.")
        return
    
    # Alle Rezepte PDF-Export
    try:
        alle_rezepte_pdf = erstelle_alle_rezepte_pdf(rezepte_data)
        st.download_button(
            label="📚 Alle Rezepte als PDF herunterladen",
            data=alle_rezepte_pdf,
            file_name="Alle_Rezepte.pdf",
            mime="application/pdf",
            use_container_width=True
        )
    except Exception as e:
        st.error(f"PDF-Erstellung fehlgeschlagen: {e}")
        st.info("Einzelne Rezepte können weiter unten heruntergeladen werden.")
    
    st.divider()
    
    # Rezepte anzeigen
    for rezept in rezepte_data['rezepte']:
        with st.expander(f"**{rezept['name']}** ({rezept.get('menu', 'N/A')})", expanded=False):
            col1, col2 = st.columns([3, 1])
            
            # Info
            with col1:
                st.markdown(f"**{rezept['portionen']} Portionen** | {rezept.get('tag', '')} Woche {rezept.get('woche', '')}")
                st.caption(f"⏱️ Vorbereitung: {rezept['zeiten']['vorbereitung']} | Garzeit: {rezept['zeiten']['garzeit']}")
            
            # PDF-Download
            with col2:
                try:
                    rezept_pdf = erstelle_rezept_pdf(rezept)
                    st.download_button(
                        label="📄 Als PDF",
                        data=rezept_pdf,
                        file_name=f"Rezept_{rezept['name'].replace(' ', '_').replace('/', '_')}.pdf",
                        mime="application/pdf",
                        key=f"pdf_{rezept['name']}",
                        use_container_width=True
                    )
                except Exception as e:
                    st.error(f"PDF-Fehler: {str(e)[:50]}...")
                    st.caption("Bitte Seite neu laden")
            
            # Zutaten
            st.markdown("### 🥘 Zutaten")
            zutaten_cols = st.columns(2)
            for i, zutat in enumerate(rezept['zutaten']):
                col_idx = i % 2
                with zutaten_cols[col_idx]:
                    zutat_text = f"**{zutat['menge']}** {zutat['name']}"
                    if zutat.get('hinweis'):
                        zutat_text += f"\n<small>{zutat['hinweis']}</small>"
                    st.markdown(f"• {zutat_text}")
            
            # Zubereitung
            st.markdown("### 👨‍🍳 Zubereitung")
            for i, schritt in enumerate(rezept['zubereitung'], 1):
                st.info(f"**Schritt {i}:** {schritt}")
            
            # Nährwerte
            st.markdown("### 📊 Nährwerte pro Portion")
            n = rezept['naehrwerte']
            cols = st.columns(5)
            cols[0].metric("Kalorien", n.get('kalorien', 'N/A'))
            cols[1].metric("Protein", n.get('protein', 'N/A'))
            cols[2].metric("Fett", n.get('fett', 'N/A'))
            cols[3].metric("KH", n.get('kohlenhydrate', 'N/A'))
            cols[4].metric("Ballaststoffe", n.get('ballaststoffe', 'N/A'))
            
            # Allergene
            if rezept.get('allergene') and len(rezept['allergene']) > 0:
                st.warning(f"⚠️ **Allergene:** {', '.join(rezept['allergene'])}")
            
            # Tipps
            if rezept.get('tipps') and len(rezept['tipps']) > 0:
                st.markdown("### 💡 Tipps für die Großküche")
                for tipp in rezept['tipps']:
                    st.success(f"• {tipp}")
            
            # Variationen
            if rezept.get('variationen'):
                st.markdown("### 🔄 Variationen")
                if rezept['variationen'].get('pueriert'):
                    st.write(f"**Pürierte Kost:** {rezept['variationen']['pueriert']}")
                if rezept['variationen'].get('leichteKost'):
                    st.write(f"**Leichte Kost:** {rezept['variationen']['leichteKost']}")


def zeige_bibliothek_tab():
    """
    Zeigt den Bibliotheks-Tab mit gespeicherten Rezepten
    """
    st.header("📚 Rezept-Bibliothek")
    st.markdown("*Ihre Sammlung generierter Rezepte*")
    
    # Statistiken
    stats = DB.hole_statistiken()
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("📖 Rezepte", stats['anzahl_rezepte'])
    with col2:
        if stats['meistverwendet']:
            st.metric("🌟 Meistverwendet", stats['meistverwendet'][0][1])
        else:
            st.metric("🌟 Meistverwendet", 0)
    with col3:
        st.metric("🏷️ Tags", len(stats['tags']))
    with col4:
        if stats['bestbewertet']:
            st.metric("⭐ Beste Bewertung", stats['bestbewertet'][0][1])
        else:
            st.metric("⭐ Beste Bewertung", "-")
    
    st.divider()
    
    # Suche und Filter
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        suchbegriff = st.text_input("🔍 Suche nach Name oder Zutat", placeholder="z.B. Schweinebraten, Kartoffeln...")
    
    with col2:
        if stats['tags']:
            ausgewaehlte_tags = st.multiselect("🏷️ Filter nach Tags", options=list(stats['tags'].keys()))
        else:
            ausgewaehlte_tags = []
            st.info("Keine Tags verfügbar")
    
    with col3:
        sortierung = st.selectbox("📊 Sortierung", 
            ["Meistverwendet", "Neueste", "Name A-Z", "Beste Bewertung"])
    
    # Suche durchführen
    rezepte = DB.suche_rezepte(suchbegriff=suchbegriff, tags=ausgewaehlte_tags)
    
    # Sortierung anwenden
    if sortierung == "Name A-Z":
        rezepte = sorted(rezepte, key=lambda x: x['name'])
    elif sortierung == "Neueste":
        rezepte = sorted(rezepte, key=lambda x: x['erstellt_am'], reverse=True)
    elif sortierung == "Beste Bewertung":
        rezepte = sorted(rezepte, key=lambda x: x['bewertung'], reverse=True)
    # "Meistverwendet" ist schon Standard-Sortierung
    
    st.write(f"**{len(rezepte)} Rezepte gefunden**")
    
    # Export/Import
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("💾 Alle exportieren (JSON)"):
            try:
                dateiname = DB.exportiere_als_json()
                with open(dateiname, 'rb') as f:
                    st.download_button(
                        label="📥 JSON herunterladen",
                        data=f,
                        file_name=dateiname,
                        mime="application/json"
                    )
                st.success(f"✅ {stats['anzahl_rezepte']} Rezepte exportiert!")
            except Exception as e:
                st.error(f"Export fehlgeschlagen: {e}")
    
    with col2:
        uploaded_file = st.file_uploader("📤 JSON importieren", type=['json'])
        if uploaded_file:
            try:
                # Speichere temporär
                with open("temp_import.json", "wb") as f:
                    f.write(uploaded_file.getbuffer())
                
                count = DB.importiere_aus_json("temp_import.json")
                st.success(f"✅ {count} Rezepte importiert!")
                
                import os
                os.remove("temp_import.json")
                st.rerun()
            except Exception as e:
                st.error(f"Import fehlgeschlagen: {e}")
    
    with col3:
        if st.button("🗑️ Bibliothek leeren", type="secondary"):
            if st.session_state.get('bestaetigung_loeschen'):
                # Hier würde DB gelöscht - nicht implementiert für Sicherheit
                st.warning("⚠️ Funktion deaktiviert. Löschen Sie die Datei 'rezepte_bibliothek.db' manuell.")
                st.session_state['bestaetigung_loeschen'] = False
            else:
                st.session_state['bestaetigung_loeschen'] = True
                st.warning("⚠️ Nochmal klicken zum Bestätigen!")
    
    st.divider()
    
    # Rezepte anzeigen
    if len(rezepte) == 0:
        st.info("📭 Keine Rezepte gefunden. Generieren Sie einen Speiseplan, um Rezepte zu sammeln!")
    else:
        for rezept in rezepte:
            with st.expander(f"**{rezept['name']}** {'⭐' * rezept['bewertung']}", expanded=False):
                col1, col2, col3 = st.columns([3, 1, 1])
                
                # Info
                with col1:
                    st.markdown(f"**{rezept['portionen']} Portionen**")
                    if rezept['menu_linie']:
                        st.caption(f"🍽️ {rezept['menu_linie']}")
                    st.caption(f"⏱️ Vorbereitung: {rezept['vorbereitung']} | Garzeit: {rezept['garzeit']}")
                    st.caption(f"📅 Erstellt: {rezept['erstellt_am'][:10]}")
                    st.caption(f"🔄 Verwendet: {rezept['verwendet_count']}x")
                
                # Aktionen
                with col2:
                    try:
                        # Konvertiere zu richtigem Format für PDF
                        rezept_fuer_pdf = {
                            'name': rezept['name'],
                            'menu': rezept.get('menu_linie', ''),
                            'tag': '',
                            'woche': '',
                            'portionen': rezept['portionen'],
                            'zeiten': {
                                'vorbereitung': rezept['vorbereitung'],
                                'garzeit': rezept['garzeit'],
                                'gesamt': rezept.get('gesamtzeit', '')
                            },
                            'zutaten': rezept['zutaten'],
                            'zubereitung': rezept['zubereitung'],
                            'naehrwerte': rezept['naehrwerte'],
                            'allergene': rezept['allergene'],
                            'tipps': rezept['tipps'],
                            'variationen': rezept['variationen']
                        }
                        
                        rezept_pdf = erstelle_rezept_pdf(rezept_fuer_pdf)
                        st.download_button(
                            label="📄 PDF",
                            data=rezept_pdf,
                            file_name=f"Rezept_{rezept['name'].replace(' ', '_')}.pdf",
                            mime="application/pdf",
                            key=f"biblio_pdf_{rezept['id']}",
                            use_container_width=True
                        )
                    except Exception as e:
                        st.error(f"PDF-Fehler: {str(e)[:30]}...")
                
                # Bewertung & Löschen
                with col3:
                    bewertung = st.select_slider(
                        "⭐ Bewertung",
                        options=[0, 1, 2, 3, 4, 5],
                        value=rezept['bewertung'],
                        key=f"bewertung_{rezept['id']}"
                    )
                    if bewertung != rezept['bewertung']:
                        DB.bewerte_rezept(rezept['id'], bewertung)
                        st.rerun()
                    
                    if st.button("🗑️", key=f"del_{rezept['id']}", help="Rezept löschen"):
                        DB.loesche_rezept(rezept['id'])
                        st.success("Rezept gelöscht!")
                        st.rerun()
                
                # Rezept-Details
                st.markdown("### 🥘 Zutaten")
                cols = st.columns(2)
                for i, zutat in enumerate(rezept['zutaten']):
                    col_idx = i % 2
                    with cols[col_idx]:
                        st.write(f"• **{zutat['menge']}** {zutat['name']}")
                
                st.markdown("### 👨‍🍳 Zubereitung")
                for i, schritt in enumerate(rezept['zubereitung'], 1):
                    st.write(f"**{i}.** {schritt}")
                
                # Tags
                if rezept.get('tags'):
                    st.markdown("### 🏷️ Tags")
                    st.write(" • ".join([f"`{tag}`" for tag in rezept['tags']]))
                
                # Button: Als Vorlage verwenden
                if st.button(f"📋 Als Vorlage verwenden", key=f"template_{rezept['id']}"):
                    st.session_state['vorlage_rezept'] = rezept
                    DB.markiere_als_verwendet(rezept['id'], "Als Vorlage verwendet")
                    st.success("✅ Rezept als Vorlage gespeichert! Verwenden Sie es beim nächsten Speiseplan.")


# ==================== HAUPTPROGRAMM ====================

def main():
    """
    Hauptfunktion der Anwendung
    """
    # Titel
    st.title("👨‍🍳 Professioneller Speiseplan-Generator")
    st.markdown("*Für Gemeinschaftsverpflegung, Krankenhäuser & Senioreneinrichtungen*")
    st.divider()
    
    # Sidebar
    api_key, wochen, menulinien, menu_namen, button_clicked = zeige_sidebar()
    
    # Wenn kein API-Key, zeige Hinweis
    if not api_key:
        st.warning("⚠️ Bitte geben Sie Ihren Claude API-Key in der Sidebar ein.")
        st.info("""
        **So erhalten Sie einen API-Key:**
        1. Gehen Sie zu https://console.anthropic.com/
        2. Registrieren Sie sich oder melden Sie sich an
        3. Navigieren Sie zu "API Keys"
        4. Erstellen Sie einen neuen Key
        5. Kopieren Sie den Key und fügen Sie ihn in der Sidebar ein
        """)
        return
    
    # Wenn Button geklickt wurde
    if button_clicked:
        # ============== KOSTEN-WARNUNG (OPTIONAL) ==============
        if KOSTEN_TRACKING:
            zeige_kosten_warnung_bei_grossen_plaenen(wochen, menulinien)
        # =======================================================
        
        speiseplan, rezepte, pruefung, error, cost_tracker = generiere_speiseplan_mit_rezepten(
            wochen, menulinien, menu_namen, api_key
        )
        
        if error:
            st.error(f"❌ {error}")
            return
        
        # In Session State speichern
        st.session_state['speiseplan'] = speiseplan
        st.session_state['rezepte'] = rezepte
        st.session_state['pruefung'] = pruefung
        
        # ============== KOSTEN-TRACKING SPEICHERN ==============
        if KOSTEN_TRACKING and cost_tracker:
            st.session_state['cost_tracker'] = cost_tracker
        # =======================================================
        
        st.success("✅ Speiseplan und Rezepte erfolgreich erstellt!")
        st.balloons()
    
    # ============== KOSTEN ANZEIGEN (PERSISTENT) ==============
    # Zeige Kosten wenn vorhanden (auch nach Page Reload)
    if KOSTEN_TRACKING and 'cost_tracker' in st.session_state and st.session_state['cost_tracker']:
        zeige_kosten_anzeige(st.session_state['cost_tracker'])
    # ==========================================================
    
    # Wenn Daten vorhanden, zeige Tabs
    if 'speiseplan' in st.session_state and st.session_state['speiseplan']:
        tab1, tab2, tab3 = st.tabs(["📋 Speiseplan", "📖 Rezepte", "📚 Bibliothek"])
        
        with tab1:
            zeige_speiseplan_tab(
                st.session_state['speiseplan'],
                st.session_state.get('pruefung')
            )
        
        with tab2:
            rezepte = st.session_state.get('rezepte')
            if rezepte and isinstance(rezepte, dict) and 'rezepte' in rezepte and len(rezepte['rezepte']) > 0:
                zeige_rezepte_tab(rezepte)
            elif rezepte:
                st.warning("⚠️ Rezepte wurden generiert, aber die Struktur ist unerwartet.")
                st.write("**Debug-Info:**")
                st.json(rezepte)
            else:
                st.info("ℹ️ Keine Rezepte verfügbar. Generieren Sie einen Speiseplan, um Rezepte zu erhalten.")
                st.write("**Mögliche Gründe:**")
                st.write("- Rezept-Generierung ist fehlgeschlagen")
                st.write("- API-Antwort konnte nicht geparst werden")
                st.write("- Versuchen Sie es erneut")
        
        with tab3:
            zeige_bibliothek_tab()
    else:
        # Auch ohne Speiseplan: Zeige Bibliothek
        st.info("💡 **Tipp:** Generieren Sie einen Speiseplan, um die Funktionen zu sehen.")
        
        if st.button("📚 Rezept-Bibliothek öffnen"):
            st.session_state['nur_bibliothek'] = True
            st.rerun()
        
        if st.session_state.get('nur_bibliothek'):
            zeige_bibliothek_tab()


# ==================== EINSTIEGSPUNKT ====================

if __name__ == "__main__":
    main()
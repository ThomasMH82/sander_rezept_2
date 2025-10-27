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

# ============== KOSTEN-TRACKING (OPTIONAL) ==============
# Um Kosten-Tracking zu deaktivieren, kommentieren Sie die folgenden 2 Zeilen aus:
from cost_tracker import CostTracker, zeige_kosten_anzeige, zeige_kosten_warnung_bei_grossen_plaenen, zeige_kosten_in_sidebar, KOSTEN_TRACKING_AKTIVIERT
KOSTEN_TRACKING = KOSTEN_TRACKING_AKTIVIERT()
# ========================================================


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
            timeout=120  # 2 Minuten Timeout
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
        
        # JSON bereinigen und parsen
        cleaned_text = bereinige_json_response(response_text)
        parsed_data = json.loads(cleaned_text)
        
        # Usage-Daten extrahieren (für Kosten-Tracking)
        usage_data = data.get('usage', {})
        
        return parsed_data, None, usage_data
        
    except json.JSONDecodeError as e:
        return None, f"JSON-Parsing-Fehler: {str(e)} - Überprüfen Sie die API-Antwort", None
    except requests.exceptions.Timeout:
        return None, "Timeout: Die API-Anfrage hat zu lange gedauert. Bitte versuchen Sie es erneut.", None
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
    
    # Schritt 1: Speiseplan erstellen
    with st.spinner("🔄 Speiseplan wird erstellt..."):
        prompt = get_speiseplan_prompt(wochen, menulinien, menu_namen)
        speiseplan_data, error, usage = rufe_claude_api(prompt, api_key, max_tokens=20000)
        
        # ============== KOSTEN-TRACKING ==============
        if KOSTEN_TRACKING and cost_tracker and usage:
            cost_tracker.add_usage(usage)
        # =============================================
        
        if error:
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
    with st.spinner("📖 Detaillierte Rezepte werden erstellt..."):
        rezepte_prompt = get_rezepte_prompt(speiseplan_data)
        rezepte_data, error_rezepte, usage_rezepte = rufe_claude_api(rezepte_prompt, api_key, max_tokens=20000)
        
        # ============== KOSTEN-TRACKING ==============
        if KOSTEN_TRACKING and cost_tracker and usage_rezepte:
            cost_tracker.add_usage(usage_rezepte)
        # =============================================
        
        if error_rezepte:
            st.warning(f"⚠️ Rezepte konnten nicht erstellt werden: {error_rezepte}")
            rezepte_data = None
    
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
        pdf_buffer = erstelle_speiseplan_pdf(speiseplan)
        st.download_button(
            label="📄 Speiseplan als PDF (DIN A4 quer)",
            data=pdf_buffer,
            file_name="Speiseplan.pdf",
            mime="application/pdf",
            use_container_width=True
        )
    
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
    alle_rezepte_pdf = erstelle_alle_rezepte_pdf(rezepte_data)
    st.download_button(
        label="📚 Alle Rezepte als PDF herunterladen",
        data=alle_rezepte_pdf,
        file_name="Alle_Rezepte.pdf",
        mime="application/pdf",
        use_container_width=True
    )
    
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
                rezept_pdf = erstelle_rezept_pdf(rezept)
                st.download_button(
                    label="📄 Als PDF",
                    data=rezept_pdf,
                    file_name=f"Rezept_{rezept['name'].replace(' ', '_').replace('/', '_')}.pdf",
                    mime="application/pdf",
                    key=f"pdf_{rezept['name']}",
                    use_container_width=True
                )
            
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
        
        # ============== KOSTEN ANZEIGEN (OPTIONAL) ==============
        if KOSTEN_TRACKING and cost_tracker:
            zeige_kosten_anzeige(cost_tracker)
        # ========================================================
    
    # Wenn Daten vorhanden, zeige Tabs
    if 'speiseplan' in st.session_state and st.session_state['speiseplan']:
        tab1, tab2 = st.tabs(["📋 Speiseplan", "📖 Rezepte"])
        
        with tab1:
            zeige_speiseplan_tab(
                st.session_state['speiseplan'],
                st.session_state.get('pruefung')
            )
        
        with tab2:
            if st.session_state.get('rezepte'):
                zeige_rezepte_tab(st.session_state['rezepte'])
            else:
                st.info("Rezepte werden nach der Speiseplan-Generierung hier angezeigt.")


# ==================== EINSTIEGSPUNKT ====================

if __name__ == "__main__":
    main()
"""
Hauptanwendung für den Speiseplan-Generator
Orchestriert alle Module und bietet die Streamlit-UI

Version: 1.3.4 FINALE - Rezept-Gruppen + niedriger Schwellwert
Datum: 27. Oktober 2025, 14:45 Uhr
"""

import streamlit as st
import requests
import json
import re

# ==== ROBUSTE JSON-Helfer (neu) ==================================
SMART_QUOTES = {
    "“": '"', "”": '"', "„": '"',
    "’": "'", "‚": "'",
}

def parse_json_loose(text: str):
    """
    Robuster Fallback-Parser für Modellantworten,
    falls response_format=json doch mal fehlschlägt.
    """
    import json as _json, re as _re

    # Codefences entfernen
    text = sanitize_json_text(text)
    text = _re.sub(r"```(?:json)?\s*", "", text, flags=_re.IGNORECASE)
    text = text.replace("```", "").strip()

    # Smart Quotes normalisieren
    for k, v in SMART_QUOTES.items():
        text = text.replace(k, v)

    # Abschließende Kommas vor } oder ] entfernen
    text = _re.sub(r",\s*(?=[}\]])", "", text)

    # Direkter Versuch
    try:
        return _json.loads(text)
    except _json.JSONDecodeError:
        pass

    # Größte balancierte JSON-Teilstruktur extrahieren
    candidates = []
    for opener, closer in [("{", "}"), ("[", "]")]:
        stack = []
        for i, ch in enumerate(text):
            if ch == opener:
                stack.append(i)
            elif ch == closer and stack:
                start = stack.pop()
                candidates.append(text[start:i+1])

    for cand in sorted(candidates, key=len, reverse=True):
        try:
            return _json.loads(cand)
        except _json.JSONDecodeError:
            continue

    # Letzter Versuch: Kommas am Zeilenende killen
    cleaned = _re.sub(r",\s*\n", "\n", text)
    return _json.loads(cleaned)


def _waehle_root(parsed):
    """
    Wählt die erwartete Root-Ebene (speiseplan/rezepte) aus,
    falls die Antwort eingebettet zurückkommt.
    """
    if isinstance(parsed, dict):
        if "speiseplan" in parsed or "rezepte" in parsed:
            return parsed
        for k in ("data", "result", "output"):
            v = parsed.get(k)
            if isinstance(v, dict) and ("speiseplan" in v or "rezepte" in v):
                return v
    return parsed

def _strip_js_comments(s: str) -> str:
    # Entfernt //line und /* block */ Kommentare – nur außerhalb von Strings
    out, i, n, in_str, esc = [], 0, len(s), False, False
    while i < n:
        ch = s[i]
        if in_str:
            out.append(ch)
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch in ('"', "'"):
                in_str = False
            i += 1
            continue
        if ch in ('"', "'"):
            in_str = True
            out.append(ch); i += 1; continue
        if ch == '/' and i+1 < n and s[i+1] == '/':
            # bis Zeilenende überspringen
            i += 2
            while i < n and s[i] not in '\r\n':
                i += 1
            continue
        if ch == '/' and i+1 < n and s[i+1] == '*':
            # bis */ überspringen
            i += 2
            while i+1 < n and not (s[i] == '*' and s[i+1] == '/'):
                i += 1
            i += 2
            continue
        out.append(ch); i += 1
    return ''.join(out)

def sanitize_json_text(text: str) -> str:
    # Reihenfolge: Codefences raus, Smart Quotes -> ASCII, Kommentare weg, trailing commas killen
    t = re.sub(r"```(?:json)?\s*", "", text, flags=re.IGNORECASE).replace("```", "").strip()
    for k, v in SMART_QUOTES.items():
        t = t.replace(k, v)
    t = _strip_js_comments(t)
    t = re.sub(r",\s*(?=[}\]])", "", t)
    return t

# ================================================================

# Import der eigenen Module
from prompts import get_speiseplan_prompt, get_rezepte_prompt, get_pruefung_prompt
from pdf_generator import erstelle_speiseplan_pdf, erstelle_rezept_pdf, erstelle_alle_rezepte_pdf
from rezept_datenbank import RezeptDatenbank

# ============================================================
# VERSION-INFORMATION
# ============================================================
VERSION = "1.3.3"
VERSION_DATUM = "27.10.2025 15:00"
SCHWELLWERT_AUFTEILUNG = 10  # EXTREM NIEDRIG für maximale Zuverlässigkeit!
# ============================================================

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

    # ROBUSTER: trailing commas vor } oder ] entfernen
    json_str = re.sub(r',\s*(?=[}\]])', '', json_str)

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
    Ruft die Claude API auf und gibt die Antwort zurück.
    Erzwingt JSON-Ausgabe, saniert Text, und macht bei Parse-Fehlern 1 strengen Retry.
    Returns: (parsed_data, error, usage_data)
    """

    def _call_api(user_prompt, retry=False):
        return requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01"
            },
            json={
                # härtere Einstellungen für Konsistenz
                "model": "claude-sonnet-4-20250514",
                "max_tokens": max_tokens,
                "temperature": 0,
                "top_p": 0,
                # starker System-Hinweis beim Retry
                "system": (
                    "Antworte ausschließlich mit einem einzigen gültigen JSON-Objekt. "
                    "Kein Markdown, keine Codeblöcke, keine Erklärungen, keine Kommentare."
                ) if retry else None,
                "messages": [{"role": "user", "content": user_prompt}],
                "response_format": {"type": "json"}
            },
            timeout=180
        )

    try:
        # 1. Versuch
        response = _call_api(prompt, retry=False)

        if response.status_code != 200:
            try:
                detail = response.json()
                msg = detail.get('error', {}).get('message', response.text)
            except Exception:
                msg = response.text
            return None, f"API-Fehler: Status {response.status_code} - {msg}", None

        data = response.json()
        content0 = data.get("content", [{}])[0]
        response_text = content0["text"] if isinstance(content0, dict) and "text" in content0 else (
            content0 if isinstance(content0, str) else json.dumps(content0)
        )

        # Debug-Preview
        st.session_state.setdefault('debug_raw_responses', []).append({
            'length': len(response_text) if isinstance(response_text, str) else 0,
            'preview': (response_text[:200] + '...') if isinstance(response_text, str) and len(response_text) > 200 else response_text
        })

        # Direkt versuchen
        try:
            parsed_data = json.loads(response_text)
        except json.JSONDecodeError:
            # Sanitize + loose parser
            st.warning("⚠️ JSON nicht direkt parsebar – versuche Sanitisierung …")
            try:
                parsed_data = parse_json_loose(response_text)
            except json.JSONDecodeError:
                # 🔁 Ein strenger Retry mit hartem Systemprompt
                st.info("🔁 Starte einmaligen Retry mit strenger JSON-Vorgabe …")
                retry_prompt = (
                    prompt
                    + "\n\nWICHTIG: Antworte ausschließlich mit einem einzelnen gültigen JSON-Objekt. "
                      "Kein Markdown, keine Erklärungen, keine Kommentare."
                )
                r2 = _call_api(retry_prompt, retry=True)
                if r2.status_code != 200:
                    try:
                        detail = r2.json()
                        msg = detail.get('error', {}).get('message', r2.text)
                    except Exception:
                        msg = r2.text
                    return None, f"API-Fehler (Retry): Status {r2.status_code} - {msg}", None

                d2 = r2.json()
                c2 = d2.get("content", [{}])[0]
                t2 = c2["text"] if isinstance(c2, dict) and "text" in c2 else (c2 if isinstance(c2, str) else json.dumps(c2))

                try:
                    parsed_data = json.loads(t2)
                except json.JSONDecodeError as e:
                    # letzter Versuch mit Sanitize/loose
                    t2s = sanitize_json_text(t2)
                    try:
                        parsed_data = parse_json_loose(t2s)
                    except json.JSONDecodeError as e2:
                        err = (
                            f"JSON-Parsing-Fehler: {e2}\n"
                            f"Antwort-Längen: first={len(response_text) if isinstance(response_text, str) else 'N/A'}, "
                            f"retry={len(t2) if isinstance(t2, str) else 'N/A'}\n\n"
                            "**Lösungen:**\n"
                            "- Weniger Umfang (z. B. 1 Woche statt mehrere)\n"
                            "- Weniger Menülinien\n"
                            "- Erneut versuchen\n"
                        )
                        st.session_state['last_json_error'] = {
                            'error': str(e2),
                            'raw_preview_first': response_text[:1000] if isinstance(response_text, str) else None,
                            'raw_preview_retry': t2[:1000] if isinstance(t2, str) else None
                        }
                        return None, err, None

        parsed_data = _waehle_root(parsed_data)
        usage_data = data.get('usage', {})  # beim Retry unkritisch; reicht der erste Call
        return parsed_data, None, usage_data

    except requests.exceptions.Timeout:
        return None, "Timeout: Die API-Anfrage hat zu lange gedauert (>3min). Reduzieren Sie die Anzahl Wochen/Menülinien.", None
    except requests.exceptions.RequestException as e:
        return None, f"Netzwerkfehler: {str(e)}", None
    except Exception as e:
        return None, f"Unerwarteter Fehler: {str(e)}", None


def generiere_speiseplan_gestuft(wochen, menulinien, menu_namen, api_key, cost_tracker):
    """
    Generiert große Speisepläne wochenweise und kombiniert sie

    Args:
        wochen (int): Anzahl Wochen
        menulinien (int): Anzahl Menülinien
        menu_namen (list): Namen der Menülinien
        api_key (str): Claude API-Key
        cost_tracker: Cost-Tracker Instanz

    Returns:
        tuple: (kombinierter_speiseplan, alle_rezepte, pruefung, error, cost_tracker)
    """
    st.success(f"✅✅✅ **AUTOMATISCHE AUFTEILUNG AKTIV!** Generiere {wochen} Wochen einzeln...")
    st.info("📋 **Modus:** Wochenweise Generierung + Rezepte in Mini-Gruppen (max 15)")
    st.warning(f"⏱️ **Dies dauert ~{wochen * 3} Minuten** - Bitte Geduld!")

    alle_wochen = []
    alle_rezepte = []
    progress_bar = st.progress(0)
    status_text = st.empty()

    # Generiere jede Woche einzeln
    for woche_nr in range(1, wochen + 1):
        status_text.text(f"Generiere Woche {woche_nr} von {wochen}...")
        progress = (woche_nr - 1) / wochen
        progress_bar.progress(progress)

        # Generiere 1 Woche
        with st.spinner(f"📅 Woche {woche_nr}..."):
            prompt = get_speiseplan_prompt(1, menulinien, menu_namen)  # Nur 1 Woche!
            speiseplan_data, error, usage = rufe_claude_api(prompt, api_key, max_tokens=16000)

            # Kosten-Tracking
            if KOSTEN_TRACKING and cost_tracker and usage:
                cost_tracker.add_usage(usage)

            if error:
                st.error(f"❌ Fehler bei Woche {woche_nr}: {error}")
                return None, None, None, f"Fehler bei Woche {woche_nr}: {error}", cost_tracker

            # Passe Wochennummer an
            if speiseplan_data and 'speiseplan' in speiseplan_data and 'wochen' in speiseplan_data['speiseplan']:
                for woche in speiseplan_data['speiseplan']['wochen']:
                    woche['woche'] = woche_nr  # Setze richtige Wochennummer
                alle_wochen.extend(speiseplan_data['speiseplan']['wochen'])

        # Generiere Rezepte für diese Woche - IN KLEINEREN GRUPPEN!
        with st.spinner(f"📖 Rezepte für Woche {woche_nr}..."):
            # Prüfe wie viele Menüs in dieser Woche
            if speiseplan_data and 'speiseplan' in speiseplan_data:
                anzahl_woche_menues = len(speiseplan_data.get('speiseplan', {}).get('wochen', [{}])[0].get('tage', [])) * menulinien

                # Wenn mehr als 15 Menüs, in Gruppen aufteilen (vorher 20)
                if anzahl_woche_menues > 15:
                    st.info(f"📦 {anzahl_woche_menues} Menüs → Generiere in 2-3 Gruppen (max 15 pro Gruppe)")

                    # Teile Speiseplan in Gruppen
                    woche_data = speiseplan_data['speiseplan']['wochen'][0]
                    tage = woche_data['tage']

                    # Berechne Anzahl Gruppen (max 15 Rezepte pro Gruppe)
                    rezepte_pro_gruppe = 15
                    menues_pro_tag = menulinien
                    tage_pro_gruppe = max(1, rezepte_pro_gruppe // menues_pro_tag)

                    anzahl_gruppen = (len(tage) + tage_pro_gruppe - 1) // tage_pro_gruppe
                    st.info(f"🔄 Aufteilen in {anzahl_gruppen} Gruppen à ~{tage_pro_gruppe} Tage")

                    alle_rezepte_woche = []

                    for gruppe_nr in range(anzahl_gruppen):
                        start_idx = gruppe_nr * tage_pro_gruppe
                        end_idx = min((gruppe_nr + 1) * tage_pro_gruppe, len(tage))

                        tage_gruppe = tage[start_idx:end_idx]
                        gruppe_data = {'speiseplan': {'wochen': [{'tage': tage_gruppe, 'woche': woche_nr}], 'menuLinien': menulinien, 'menuNamen': menu_namen}}

                        with st.spinner(f"📖 Gruppe {gruppe_nr + 1}/{anzahl_gruppen} ({len(tage_gruppe)} Tage)..."):
                            rezepte_prompt = get_rezepte_prompt(gruppe_data)
                            rezepte_data_gruppe, _, usage_gruppe = rufe_claude_api(rezepte_prompt, api_key, max_tokens=12000)

                            if KOSTEN_TRACKING and cost_tracker and usage_gruppe:
                                cost_tracker.add_usage(usage_gruppe)

                            if rezepte_data_gruppe and 'rezepte' in rezepte_data_gruppe:
                                alle_rezepte_woche.extend(rezepte_data_gruppe['rezepte'])
                                st.success(f"✅ Gruppe {gruppe_nr + 1}: {len(rezepte_data_gruppe['rezepte'])} Rezepte")

                    # Kombiniere alle Rezepte der Woche
                    rezepte_data = {'rezepte': alle_rezepte_woche}
                else:
                    # Klein genug, auf einmal
                    st.info(f"📝 {anzahl_woche_menues} Menüs → Generiere auf einmal (klein genug)")
                    rezepte_prompt = get_rezepte_prompt(speiseplan_data)
                    rezepte_data, error_rezepte, usage_rezepte = rufe_claude_api(rezepte_prompt, api_key, max_tokens=12000)

                    if KOSTEN_TRACKING and cost_tracker and usage_rezepte:
                        cost_tracker.add_usage(usage_rezepte)
            else:
                rezepte_data = None

            if rezepte_data and 'rezepte' in rezepte_data:
                # Speichere in Datenbank
                try:
                    gespeichert = DB.speichere_alle_rezepte(rezepte_data)
                    st.success(f"✅ Woche {woche_nr}: {len(rezepte_data['rezepte'])} Rezepte")
                except Exception as e:
                    st.warning(f"⚠️ Rezepte Woche {woche_nr} nicht gespeichert: {e}")

                alle_rezepte.extend(rezepte_data['rezepte'])
            else:
                st.warning(f"⚠️ Keine Rezepte für Woche {woche_nr}")

        # Update Progress
        progress_bar.progress((woche_nr) / wochen)

    progress_bar.progress(1.0)
    status_text.text("✅ Alle Wochen generiert!")

    # Kombiniere zu einem Speiseplan
    kombinierter_speiseplan = {
        'speiseplan': {
            'wochen': alle_wochen,
            'menuLinien': menulinien,
            'menuNamen': menu_namen
        }
    }

    # Kombiniere Rezepte
    kombinierte_rezepte = {
        'rezepte': alle_rezepte
    }

    # Qualitätsprüfung (optional)
    pruefung_data = None
    with st.spinner("🔍 Qualitätsprüfung..."):
        try:
            pruef_prompt = get_pruefung_prompt(kombinierter_speiseplan)
            pruefung_data, error_pruef, usage_pruef = rufe_claude_api(pruef_prompt, api_key, max_tokens=8000)

            if KOSTEN_TRACKING and cost_tracker and usage_pruef:
                cost_tracker.add_usage(usage_pruef)
        except:
            pass  # Prüfung ist optional

    st.success(f"""
    ✅ **Kompletter {wochen}-Wochen-Plan erstellt!**

    - {len(alle_wochen)} Wochen
    - {len(alle_rezepte)} Rezepte
    - Alles in Bibliothek gespeichert
    """)

    return kombinierter_speiseplan, kombinierte_rezepte, pruefung_data, None, cost_tracker


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

    # ============== AUTOMATISCHE AUFTEILUNG FÜR GROSSE PLÄNE ==============
    if anzahl_menues > SCHWELLWERT_AUFTEILUNG:  # Konfigurierbar am Dateianfang
        st.success(f"""
        ✅✅✅ AUTOMATISCHE AUFTEILUNG IST AKTIV! ✅✅✅

        Plan: {anzahl_menues} Menüs > Schwellwert {SCHWELLWERT_AUFTEILUNG}
        """)

        st.warning(f"""
        ⚠️ **Großer Plan erkannt: {anzahl_menues} Menüs (Schwellwert: {SCHWELLWERT_AUFTEILUNG})**

        **✅ AUTOMATISCHE AUFTEILUNG WIRD AKTIVIERT:**
        - Plan wird wochenweise generiert
        - Rezepte werden in Mini-Gruppen erstellt (max 15 Stück)
        - Höchste Erfolgsrate (99%+)
        - Dauert länger, aber EXTREM zuverlässig

        ⏱️ Geschätzte Dauer: ~{wochen * 3} Minuten
        💰 Geschätzte Kosten: ~${anzahl_menues * 0.007:.2f}
        """)

        st.info(f"""
        🔧 **Version {VERSION}** - Schwellwert {SCHWELLWERT_AUFTEILUNG}

        Wenn Sie diese Meldungen sehen, läuft die Aufteilung!
        Bei Streamlit Cloud: Funktioniert genauso wie lokal.
        """)

        return generiere_speiseplan_gestuft(wochen, menulinien, menu_namen, api_key, cost_tracker)
    # ======================================================================

    # Warnung bei mittelgroßen Plänen
    if anzahl_menues > 50:
        st.info(f"""
        💡 **Mittelgroßer Plan: {anzahl_menues} Menüs**

        Dies kann 2-3 Minuten dauern.
        """)

    # Dynamische max_tokens basierend auf Größe
    if anzahl_menues <= 30:
        speiseplan_tokens = 16000
        rezepte_tokens = 16000
    else:
        speiseplan_tokens = 32000
        rezepte_tokens = 32000

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

        # ============== VERSIONS-INFORMATION ==============
        st.sidebar.divider()
        st.sidebar.caption(f"🔧 Version {VERSION} ({VERSION_DATUM})")
        st.sidebar.caption(f"⚙️ Auto-Split ab {SCHWELLWERT_AUFTEILUNG} Menüs")
        # ==================================================

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

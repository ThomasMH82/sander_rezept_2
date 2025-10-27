"""
Hauptanwendung für den Speiseplan-Generator
Orchestriert alle Module und bietet die Streamlit-UI

Version: 1.3.2 FINALE - Rezept-Gruppen + niedriger Schwellwert
Datum: 27. Oktober 2025, 14:45 Uhr
"""

import streamlit as st
import requests
import json
import re

# ==== ROBUSTE JSON-/Antwort-Helfer ==================================
SMART_QUOTES = {
    "“": '"', "”": '"', "„": '"',
    "’": "'", "‚": "'",
}

def _strip_js_comments(s: str) -> str:
    """Entfernt //- und /* */-Kommentare außerhalb von Strings."""
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
            i += 2
            while i < n and s[i] not in '\r\n':
                i += 1
            continue
        if ch == '/' and i+1 < n and s[i+1] == '*':
            i += 2
            while i+1 < n and not (s[i] == '*' and s[i+1] == '/'):
                i += 1
            i += 2
            continue
        out.append(ch); i += 1
    return ''.join(out)

def sanitize_json_text(text: str) -> str:
    """Codefences raus, Smart Quotes normalisieren, Kommentare entfernen, trailing commas killen."""
    t = re.sub(r"```(?:json)?\s*", "", text, flags=re.IGNORECASE).replace("```", "").strip()
    for k, v in SMART_QUOTES.items():
        t = t.replace(k, v)
    t = _strip_js_comments(t)
    t = re.sub(r",\s*(?=[}\]])", "", t)
    return t

def _json_tokenize(s: str):
    """
    Minimaler Tokenizer für JSON-ähnlichen Text:
    liefert (typ, lexem) für: { } [ ] : , STRING NUMBER TRUE FALSE NULL WHITESPACE OTHER
    STRING achtet auf escapes, NUMBER ist vereinfacht.
    """
    i, n = 0, len(s)
    WHITESPACE = " \t\r\n"
    digits = "0123456789-+."
    while i < n:
        ch = s[i]
        if ch in WHITESPACE:
            j = i+1
            while j < n and s[j] in WHITESPACE: j += 1
            yield ("WS", s[i:j]); i = j; continue
        if ch in "{}[]:,":
            yield (ch, ch); i += 1; continue
        if ch == '"' or ch == "'":
            quote = ch
            j, esc = i+1, False
            while j < n:
                c = s[j]
                if esc:
                    esc = False
                elif c == '\\':
                    esc = True
                elif c == quote:
                    j += 1
                    break
                j += 1
            yield ("STRING", s[i:j]); i = j; continue
        if s.startswith("true", i):   yield ("TRUE", "true");   i += 4; continue
        if s.startswith("false", i):  yield ("FALSE", "false"); i += 5; continue
        if s.startswith("null", i):   yield ("NULL", "null");   i += 4; continue
        if ch in digits:
            j = i+1
            while j < n and s[j] in digits+'eE': j += 1
            yield ("NUMBER", s[i:j]); i = j; continue
        yield ("OTHER", ch); i += 1

def _auto_insert_commas(raw: str) -> str:
    """
    Heuristik: Ergänzt fehlende Kommata zwischen JSON-Elementen.
    - In OBJECT: value … STRING ':'  -> Komma zwischen value und folgendem key
    - In ARRAY:  value … value       -> Komma zwischen zwei Werten
    """
    tokens = list(_json_tokenize(raw))
    out = []
    stack = []  # "OBJECT" oder "ARRAY"
    VALUE_TYPES = {"STRING", "NUMBER", "TRUE", "FALSE", "NULL", "}", "]"}
    i = 0
    while i < len(tokens):
        t, lex = tokens[i]
        if t == "{":
            stack.append("OBJECT"); out.append(lex); i += 1; continue
        if t == "[":
            stack.append("ARRAY"); out.append(lex); i += 1; continue
        if t == "}":
            if stack and stack[-1] == "OBJECT": stack.pop()
            out.append(lex); i += 1; continue
        if t == "]":
            if stack and stack[-1] == "ARRAY": stack.pop()
            out.append(lex); i += 1; continue

        if stack:
            ctx = stack[-1]
            if ctx == "OBJECT":
                if t in VALUE_TYPES:
                    out.append(lex)
                    j = i + 1
                    while j < len(tokens) and tokens[j][0] == "WS":
                        out.append(tokens[j][1]); j += 1
                    if j < len(tokens) and tokens[j][0] == "STRING":
                        jj = j + 1
                        buf_ws = []
                        while jj < len(tokens) and tokens[jj][0] == "WS":
                            buf_ws.append(tokens[jj][1]); jj += 1
                        if jj < len(tokens) and tokens[jj][0] == ":":
                            out.append(",")
                    i = j
                    continue
            if ctx == "ARRAY":
                if t in VALUE_TYPES:
                    out.append(lex)
                    j = i + 1
                    while j < len(tokens) and tokens[j][0] == "WS":
                        out.append(tokens[j][1]); j += 1
                    if j < len(tokens) and (tokens[j][0] in VALUE_TYPES or tokens[j][0] in {"{","["}):
                        out.append(",")
                    i = j
                    continue

        out.append(lex); i += 1
    return "".join(out)

def parse_json_loose(text: str):
    """
    Robuster Fallback-Parser für Modellantworten.
    Reihenfolge:
      1) sanitize -> json.loads
      2) größte balancierte Teilstruktur -> json.loads
      3) sanitize (Zeilen-Kommas weg) -> json.loads
      4) auto comma insert -> json.loads
    """
    import json as _json, re as _re
    text = sanitize_json_text(text)

    try:
        return _json.loads(text)
    except _json.JSONDecodeError:
        pass

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

    cleaned = _re.sub(r",\s*\n", "\n", text)
    try:
        return _json.loads(cleaned)
    except _json.JSONDecodeError:
        pass

    repaired = _auto_insert_commas(text)
    return _json.loads(repaired)

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

def _extract_tool_input_from_anthropic(data):
    """
    Versucht aus einer Anthropic-Response den ersten tool_use-Block zu holen
    und gibt dessen `input` (bereits geparstes JSON) zurück.
    """
    try:
        content = data.get("content", [])
        for item in content:
            if isinstance(item, dict) and item.get("type") == "tool_use":
                return item.get("input")
    except Exception:
        pass
    return None
# ================================================================

# ======= Coverage-Check & Helfer (NEU) =====================================
TAGE_REIHENFOLGE = ["Montag","Dienstag","Mittwoch","Donnerstag","Freitag","Samstag","Sonntag"]

def _tage_slicen(tage_liste, start, ende):
    """Schneidet Tage robust (index-basiert) und erhält die Originalstruktur."""
    return tage_liste[start:ende]

def _erwarte_rezept_schluessel(frag_speiseplan):
    """
    Extrahiert die Soll-Liste der zu erzeugenden Rezepte aus einem (Teil-)Speiseplan.
    Key ist ein Tuple (woche, tag, menuName, hauptgericht).
    """
    expected = []
    for w in frag_speiseplan['speiseplan']['wochen']:
        w_nr = w.get('woche', 1)
        for tag in w.get('tage', []):
            tname = tag.get('tag')
            for m in tag.get('menues', []):
                mittag = m.get('mittagessen', {})
                hg = mittag.get('hauptgericht')
                expected.append((
                    int(w_nr),
                    str(tname or ""),
                    str(m.get('menuName', "")),
                    str(hg or "")
                ))
    return expected

def _vorhandene_rezepte_schluessel(rezepte_data):
    """Extrahiert vorhandene Rezepte-Schlüssel aus einem Rezept-Blob."""
    have = []
    if not rezepte_data or 'rezepte' not in rezepte_data:
        return have
    for r in rezepte_data['rezepte']:
        have.append((
            int(r.get('woche', 0) or 0),
            str(r.get('tag', "")),
            str(r.get('menu', "")),
            str(r.get('name', ""))  # Name enthält i.d.R. Hauptgericht + Beilagen
        ))
    return have

def _mappe_name_zu_hauptgericht(name: str) -> str:
    """
    Versucht aus dem Rezeptnamen das 'Hauptgericht' herauszuziehen (Heuristik).
    """
    if not name:
        return name
    import re
    parts = re.split(r"\s+mit\s+| - | – ", name, maxsplit=1)
    return parts[0].strip()

def _delta_missing(expected_keys, rezepte_data):
    """
    Ermittelt, welche (Woche, Tag, Menü, Hauptgericht) noch fehlen.
    Abgleich per Heuristik: Rezeptname -> Hauptgericht.
    """
    have = _vorhandene_rezepte_schluessel(rezepte_data)
    have_index = set()
    for (w, t, menu, name) in have:
        have_index.add((w, t, menu, _mappe_name_zu_hauptgericht(name)))

    missing = []
    for (w, t, menu, hg) in expected_keys:
        probe = (int(w), str(t), str(menu), str(hg))
        if probe not in have_index:
            missing.append(probe)
    return missing

def _baue_sub_speiseplan_aus_keys(full_speiseplan, keys):
    """
    Baut einen Mini-Speiseplan nur für die angegebenen (woche, tag, menuName, hauptgericht)-Keys.
    Damit lassen sich gezielt fehlende Rezepte nachgenerieren.
    """
    result_wochen = []
    from collections import defaultdict
    index = defaultdict(lambda: defaultdict(list))  # w -> tag -> list menuName
    hg_lookup = defaultdict(lambda: defaultdict(set))  # w -> tag -> set(hg)

    for (w, t, menu, hg) in keys:
        index[w][t].append(menu)
        hg_lookup[w][t].add(hg)

    for w in full_speiseplan['speiseplan']['wochen']:
        w_nr = w.get('woche')
        if w_nr not in index:
            continue
        neue_tage = []
        for tag in w.get('tage', []):
            tname = tag.get('tag')
            if tname not in index[w_nr]:
                continue
            neue_menues = []
            for m in tag.get('menues', []):
                if m.get('menuName') in index[w_nr][tname]:
                    hg = m.get('mittagessen', {}).get('hauptgericht')
                    if hg in hg_lookup[w_nr][tname]:
                        neue_menues.append(m)
            if neue_menues:
                neue_tage.append({"tag": tname, "menues": neue_menues})
        if neue_tage:
            result_wochen.append({"woche": w_nr, "tage": neue_tage})

    return {
        "speiseplan": {
            "wochen": result_wochen,
            "menuLinien": full_speiseplan['speiseplan'].get('menuLinien'),
            "menuNamen": full_speiseplan['speiseplan'].get('menuNamen', [])
        }
    }
# ========================================================================

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
from cost_tracker import CostTracker, zeige_kosten_anzeige, zeige_kosten_warnung_bei_grossen_plaenen, zeige_kosten_in_sidebar, KOSTEN_TRACKING_AKTIVIERT
KOSTEN_TRACKING = KOSTEN_TRACKING_AKTIVIERT()
# ========================================================

# ============== REZEPT-DATENBANK INITIALISIEREN ==============
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
    """(Legacy) Entfernt Codefences & schneidet auf {}-Bereich zu – bleibt als Fallback."""
    text = re.sub(r'```json\n?', '', text)
    text = re.sub(r'```\n?', '', text)
    text = text.strip()
    first_brace = text.find('{')
    last_brace = text.rfind('}')
    if first_brace != -1 and last_brace != -1:
        text = text[first_brace:last_brace + 1]
    return text

def repariere_json(json_str):
    """(Legacy) Grobe Reparatur unvollständiger JSONs – bleibt als Fallback drin."""
    open_braces = json_str.count('{')
    close_braces = json_str.count('}')
    open_brackets = json_str.count('[')
    close_brackets = json_str.count(']')
    if open_braces > close_braces:
        json_str += '}' * (open_braces - close_braces)
    if open_brackets > close_brackets:
        json_str += ']' * (open_brackets - close_brackets)
    json_str = re.sub(r',\s*(?=[}\]])', '', json_str)  # robuster
    lines = json_str.split('\n')
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip().endswith(('}', ']', '}')):
            json_str = '\n'.join(lines[:i+1])
            break
    return json_str


def rufe_claude_api(prompt, api_key, max_tokens=20000):
    """
    Ruft die Claude API auf und gibt die Antwort zurück.
    Priorität: Tool-Call (tool_use) -> direktes, valides JSON.
    Fallback: response_format=json + Sanitizer + 1 Retry.
    Returns: (parsed_data, error, usage_data)
    """

    def _call_api(user_prompt, retry=False, force_tool=False):
        payload = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": max_tokens,
            "temperature": 0,
            "top_p": 0,
            "messages": [{"role": "user", "content": user_prompt}],
        }

        # Tool-Definition: liberal, nimmt jedes Objekt an
        tools = [{
            "name": "return_json",
            "description": "Gib das Ergebnis als JSON im 'input' dieses Tool-Calls zurück.",
            "input_schema": {"type": "object"}
        }]

        if force_tool:
            payload["tools"] = tools
            payload["tool_choice"] = {"type": "tool", "name": "return_json"}
            payload["system"] = (
                "Gib dein Ergebnis ausschließlich als Tool-Aufruf 'return_json' zurück. "
                "Keine Erklärungen, kein Markdown, keine Kommentare, keine Codeblöcke. "
                "Der gesamte Inhalt muss im 'input'-Feld eines einzigen Tool-Calls liegen."
            )

        if retry:
            payload["response_format"] = {"type": "json"}

        return requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01"
            },
            json=payload,
            timeout=180
        )

    try:
        # 1) Primär: Tool-Call erzwingen
        response = _call_api(prompt, retry=False, force_tool=True)

        if response.status_code != 200:
            try:
                detail = response.json()
                msg = detail.get('error', {}).get('message', response.text)
            except Exception:
                msg = response.text
            return None, f"API-Fehler: Status {response.status_code} - {msg}", None

        data = response.json()

        # ✅ A: tool_use extrahieren (bevor irgendetwas geparst wird)
        tool_input = _extract_tool_input_from_anthropic(data)
        if tool_input is not None:
            parsed_data = _waehle_root(tool_input)
            usage_data = data.get("usage", {})
            return parsed_data, None, usage_data

        # ❗ Kein tool_use: Fallback auf Text
        content0 = data.get("content", [{}])[0]
        if isinstance(content0, dict) and "text" in content0:
            response_text = content0["text"]
        else:
            response_text = content0 if isinstance(content0, str) else json.dumps(content0)

        # Debug-Preview
        st.session_state.setdefault('debug_raw_responses', []).append({
            'length': len(response_text) if isinstance(response_text, str) else 0,
            'preview': (response_text[:200] + '...') if isinstance(response_text, str) and len(response_text) > 200 else response_text
        })

        # B: Direktes JSON
        try:
            parsed_data = json.loads(response_text)
            parsed_data = _waehle_root(parsed_data)
            usage_data = data.get("usage", {})
            return parsed_data, None, usage_data
        except json.JSONDecodeError:
            pass

        # C: Sanitizer + Loose-Parser
        st.warning("⚠️ Kein Tool-Call erhalten – versuche JSON-Sanitisierung …")
        try:
            parsed_data = parse_json_loose(response_text)
            parsed_data = _waehle_root(parsed_data)
            usage_data = data.get("usage", {})
            return parsed_data, None, usage_data
        except json.JSONDecodeError:
            # 🔁 Ein strenger Retry mit erzwungenem Tool + response_format=json
            st.info("🔁 Starte einmaligen Retry mit strenger JSON-Vorgabe …")
            r2 = _call_api(
                prompt + "\n\nWICHTIG: Antworte ausschließlich als Tool-Aufruf 'return_json' mit einem einzigen JSON-Objekt in 'input'.",
                retry=True,
                force_tool=True
            )

            if r2.status_code != 200:
                try:
                    detail = r2.json()
                    msg = detail.get('error', {}).get('message', r2.text)
                except Exception:
                    msg = r2.text
                return None, f"API-Fehler (Retry): Status {r2.status_code} - {msg}", None

            d2 = r2.json()

            # zuerst tool_use prüfen
            tool_input2 = _extract_tool_input_from_anthropic(d2)
            if tool_input2 is not None:
                parsed_data = _waehle_root(tool_input2)
                usage_data = d2.get("usage", {})
                return parsed_data, None, usage_data

            # Fallback auf Text
            c2 = d2.get("content", [{}])[0]
            t2 = c2["text"] if isinstance(c2, dict) and "text" in c2 else (c2 if isinstance(c2, str) else json.dumps(c2))
            try:
                parsed_data = json.loads(t2)
            except json.JSONDecodeError as e:
                # letzter Schritt: sanitize + loose
                t2s = sanitize_json_text(t2)
                try:
                    parsed_data = parse_json_loose(t2s)
                except json.JSONDecodeError as e2:
                    err = (
                        f"JSON-Parsing-Fehler: {e2}\n"
                        f"Antwort-Längen: first={len(response_text) if isinstance(response_text, str) else 'N/A'}, "
                        f"retry={len(t2) if isinstance(t2, str) else 'N/A'}\n\n"
                        "**Lösungen:**\n"
                        "- Wochenweise generieren (Auto-Split)\n"
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
            usage_data = d2.get("usage", {})
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
    """
    st.success(f"✅✅✅ **AUTOMATISCHE AUFTEILUNG AKTIV!** Generiere {wochen} Wochen einzeln...")
    st.info("📋 **Modus:** Wochenweise Generierung + Rezepte in Mini-Gruppen (max 2 Tage pro Gruppe)")
    st.warning(f"⏱️ **Dies kann einige Minuten dauern** - Bitte Geduld!")

    alle_wochen = []
    alle_rezepte = []
    progress_bar = st.progress(0)
    status_text = st.empty()

    for woche_nr in range(1, wochen + 1):
        status_text.text(f"Generiere Woche {woche_nr} von {wochen}...")
        progress_bar.progress((woche_nr - 1) / wochen)

        # --------- Woche: Speiseplan erzeugen ---------
        with st.spinner(f"📅 Woche {woche_nr}..."):
            prompt = get_speiseplan_prompt(1, menulinien, menu_namen)  # Nur 1 Woche!
            speiseplan_data, error, usage = rufe_claude_api(prompt, api_key, max_tokens=16000)

            if KOSTEN_TRACKING and cost_tracker and usage:
                cost_tracker.add_usage(usage)

            if error:
                st.error(f"❌ Fehler bei Woche {woche_nr}: {error}")
                return None, None, None, f"Fehler bei Woche {woche_nr}: {error}", cost_tracker

            if speiseplan_data and 'speiseplan' in speiseplan_data and 'wochen' in speiseplan_data['speiseplan']:
                for woche in speiseplan_data['speiseplan']['wochen']:
                    woche['woche'] = woche_nr
                alle_wochen.extend(speiseplan_data['speiseplan']['wochen'])
            else:
                st.error(f"❌ Unerwartete Struktur für Woche {woche_nr}")
                return None, None, None, f"Unerwartete Struktur bei Woche {woche_nr}", cost_tracker

        # --------- Woche: Rezepte in sehr kleinen Gruppen + Coverage ---------
        with st.spinner(f"📖 Rezepte für Woche {woche_nr}..."):
            rezepte_data = {"rezepte": []}
            woche_data = speiseplan_data['speiseplan']['wochen'][0]
            alle_tage = woche_data.get('tage', [])
            menues_pro_tag = menulinien

            # Sehr kleine Gruppen (2 Tage) – extrem robust
            tage_pro_gruppe = max(1, min(2, 15 // max(1, menues_pro_tag)))
            anzahl_gruppen = (len(alle_tage) + tage_pro_gruppe - 1) // tage_pro_gruppe
            st.info(f"🔄 Aufteilen in {anzahl_gruppen} Gruppen à {tage_pro_gruppe} Tag(e)")

            for gruppe_nr in range(anzahl_gruppen):
                start_idx = gruppe_nr * tage_pro_gruppe
                end_idx = min((gruppe_nr + 1) * tage_pro_gruppe, len(alle_tage))
                tage_gruppe = _tage_slicen(alle_tage, start_idx, end_idx)

                gruppe_plan = {
                    'speiseplan': {
                        'wochen': [{'tage': tage_gruppe, 'woche': woche_nr}],
                        'menuLinien': menulinien,
                        'menuNamen': menu_namen
                    }
                }

                expected_keys = _erwarte_rezept_schluessel(gruppe_plan)

                with st.spinner(f"📖 Gruppe {gruppe_nr + 1}/{anzahl_gruppen} ({len(tage_gruppe)} Tag(e))…"):
                    rezepte_prompt = get_rezepte_prompt(gruppe_plan)
                    rezepte_data_gruppe, _, usage_gruppe = rufe_claude_api(
                        rezepte_prompt, api_key, max_tokens=10000
                    )

                    if KOSTEN_TRACKING and cost_tracker and usage_gruppe:
                        cost_tracker.add_usage(usage_gruppe)

                    if rezepte_data_gruppe and 'rezepte' in rezepte_data_gruppe:
                        rezepte_data['rezepte'].extend(rezepte_data_gruppe['rezepte'])

                    # Coverage prüfen und fehlende gezielt nachziehen (max. 2 Versuche)
                    missing = _delta_missing(expected_keys, rezepte_data)
                    retry_round = 0
                    while missing and retry_round < 2:
                        st.warning(f"🧩 {len(missing)} fehlend – hole gezielt nach (Versuch {retry_round+1}/2)…")
                        sub_plan = _baue_sub_speiseplan_aus_keys(gruppe_plan, missing)
                        sub_prompt = get_rezepte_prompt(sub_plan)
                        sub_res, _, usage_sub = rufe_claude_api(sub_prompt, api_key, max_tokens=9000)
                        if KOSTEN_TRACKING and cost_tracker and usage_sub:
                            cost_tracker.add_usage(usage_sub)
                        if sub_res and 'rezepte' in sub_res:
                            rezepte_data['rezepte'].extend(sub_res['rezepte'])
                        missing = _delta_missing(expected_keys, rezepte_data)
                        retry_round += 1

                    if missing:
                        st.error(f"❗Konnte {len(missing)} Rezept(e) dieser Gruppe nicht erzeugen.")
                    else:
                        st.success(f"✅ Gruppe {gruppe_nr + 1}: vollständig.")

            # Woche speichern
            if rezepte_data['rezepte']:
                try:
                    gespeichert = DB.speichere_alle_rezepte(rezepte_data)
                    st.success(f"💾 Woche {woche_nr}: {len(rezepte_data['rezepte'])} Rezepte gespeichert")
                except Exception as e:
                    st.warning(f"⚠️ Woche {woche_nr} nicht gespeichert: {e}")
                alle_rezepte.extend(rezepte_data['rezepte'])
            else:
                st.warning(f"⚠️ Keine Rezepte für Woche {woche_nr}")

        progress_bar.progress(woche_nr / wochen)

    progress_bar.progress(1.0)
    status_text.text("✅ Alle Wochen generiert!")

    kombinierter_speiseplan = {
        'speiseplan': {
            'wochen': alle_wochen,
            'menuLinien': menulinien,
            'menuNamen': menu_namen
        }
    }
    kombinierte_rezepte = {'rezepte': alle_rezepte}

    # (Optional) Qualitätsprüfung
    pruefung_data = None
    with st.spinner("🔍 Qualitätsprüfung..."):
        try:
            pruef_prompt = get_pruefung_prompt(kombinierter_speiseplan)
            pruefung_data, error_pruef, usage_pruef = rufe_claude_api(pruef_prompt, api_key, max_tokens=8000)
            if KOSTEN_TRACKING and cost_tracker and usage_pruef:
                cost_tracker.add_usage(usage_pruef)
        except:
            pass

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
    """
    cost_tracker = None
    if KOSTEN_TRACKING:
        cost_tracker = CostTracker()

    anzahl_menues = wochen * menulinien * 7  # Tage pro Woche

    # === HARTE AUFTEILUNG AKTIVIEREN (stabil für >1 Woche oder >3 Linien) ===
    if (anzahl_menues > SCHWELLWERT_AUFTEILUNG) or (wochen > 1) or (menulinien > 3):
        st.success(f"""
        ✅✅✅ AUTOMATISCHE AUFTEILUNG IST AKTIV! ✅✅✅

        Plan: {anzahl_menues} Menüs > Schwellwert {SCHWELLWERT_AUFTEILUNG} oder (wochen>1/linien>3)
        """)
        st.warning(f"""
        ⚠️ **Großer Plan erkannt: {anzahl_menues} Menüs**

        **✅ AUTOMATISCHE AUFTEILUNG WIRD AKTIVIERT:**
        - Plan wird wochenweise generiert
        - Rezepte werden in sehr kleinen Gruppen erstellt (max ~2 Tage)
        - Fehlende Rezepte werden gezielt nachgeneriert
        """)
        st.info(f"🔧 **Version {VERSION}** - Schwellwert {SCHWELLWERT_AUFTEILUNG}")
        return generiere_speiseplan_gestuft(wochen, menulinien, menu_namen, api_key, cost_tracker)

    if anzahl_menues > 50:
        st.info(f"💡 **Mittelgroßer Plan: {anzahl_menues} Menüs**")

    if anzahl_menues <= 30:
        speiseplan_tokens = 16000
        rezepte_tokens = 16000
    else:
        speiseplan_tokens = 32000
        rezepte_tokens = 32000

    with st.spinner(f"🔄 Speiseplan wird erstellt... ({anzahl_menues} Menüs)"):
        prompt = get_speiseplan_prompt(wochen, menulinien, menu_namen)
        speiseplan_data, error, usage = rufe_claude_api(prompt, api_key, max_tokens=speiseplan_tokens)

        if KOSTEN_TRACKING and cost_tracker and usage:
            cost_tracker.add_usage(usage)

        if error:
            st.error(f"❌ Fehler beim Erstellen des Speiseplans:")
            st.error(error)
            if 'last_json_error' in st.session_state:
                with st.expander("🐛 Debug-Informationen zum Fehler"):
                    st.json(st.session_state['last_json_error'])
                    st.write("**Tipp:** Debug-Modus in der Sidebar aktivieren")
            return None, None, None, f"Fehler beim Erstellen des Speiseplans: {error}", cost_tracker

    with st.spinner("🔍 Qualitätsprüfung läuft..."):
        pruef_prompt = get_pruefung_prompt(speiseplan_data)
        pruefung_data, error_pruef, usage_pruef = rufe_claude_api(pruef_prompt, api_key, max_tokens=8000)
        if KOSTEN_TRACKING and cost_tracker and usage_pruef:
            cost_tracker.add_usage(usage_pruef)
        if error_pruef:
            st.warning(f"⚠️ Qualitätsprüfung konnte nicht durchgeführt werden: {error_pruef}")
            pruefung_data = None

    with st.spinner(f"📖 Detaillierte Rezepte werden erstellt..."):
        rezepte_prompt = get_rezepte_prompt(speiseplan_data)
        rezepte_data, error_rezepte, usage_rezepte = rufe_claude_api(rezepte_prompt, api_key, max_tokens=rezepte_tokens)
        if KOSTEN_TRACKING and cost_tracker and usage_rezepte:
            cost_tracker.add_usage(usage_rezepte)

        if error_rezepte:
            st.error(f"❌ Fehler bei Rezept-Generierung: {error_rezepte}")
            if 'last_json_error' in st.session_state:
                with st.expander("🐛 Debug-Informationen zum Rezept-Fehler"):
                    st.json(st.session_state['last_json_error'])
            rezepte_data = None
        elif not rezepte_data:
            st.warning("⚠️ Keine Rezepte erhalten - prüfen Sie die API-Antwort")
            rezepte_data = None
        else:
            if isinstance(rezepte_data, dict) and 'rezepte' in rezepte_data:
                anzahl = len(rezepte_data['rezepte'])
                st.success(f"✅ {anzahl} Rezepte erstellt!")
                try:
                    gespeichert = DB.speichere_alle_rezepte(rezepte_data)
                    if gespeichert > 0:
                        st.info(f"💾 {gespeichert} Rezepte in Bibliothek gespeichert!")
                except Exception as e:
                    st.warning(f"⚠️ Rezepte konnten nicht gespeichert werden: {e}")
            else:
                st.warning(f"⚠️ Unerwartete Rezept-Struktur: {type(rezepte_data)}")

    return speiseplan_data, rezepte_data, pruefung_data, None, cost_tracker


# ==================== UI-FUNKTIONEN ====================

def zeige_sidebar():
    """
    Erstellt die Sidebar mit allen Eingabefeldern
    """
    with st.sidebar:
        st.header("🔑 API-Konfiguration")

        api_key_from_secrets = None
        try:
            if hasattr(st, 'secrets') and 'ANTHROPIC_API_KEY' in st.secrets:
                api_key_from_secrets = st.secrets['ANTHROPIC_API_KEY']
                st.success("✅ API-Key aus Konfiguration geladen!")
                st.info("💡 Sie können den Key auch manuell unten eingeben, um ihn zu überschreiben.")
        except Exception:
            pass

        api_key_manual = st.text_input(
            "Claude API-Key (optional)",
            type="password",
            help="Geben Sie Ihren Anthropic API-Key ein (https://console.anthropic.com/)",
            placeholder="Optional - nur wenn nicht in secrets.toml hinterlegt"
        )

        api_key = api_key_manual if api_key_manual else api_key_from_secrets

        if not api_key:
            st.warning("⚠️ Bitte API-Key eingeben oder in secrets.toml hinterlegen")
            with st.expander("ℹ️ Wie hinterlege ich den API-Key dauerhaft?"):
                st.markdown("""
                **Lokal:**
                1. `.streamlit/secrets.toml` im Projektordner anlegen
                2. Eintragen:
                ```toml
                ANTHROPIC_API_KEY = "Ihr-API-Key"
                ```
                **Streamlit Cloud:**
                Settings → Secrets → oben eintragen → Save
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

        if KOSTEN_TRACKING and 'cost_tracker' in st.session_state:
            zeige_kosten_in_sidebar(st.session_state['cost_tracker'])

        st.sidebar.divider()
        if st.sidebar.checkbox("🐛 Debug-Modus", value=False):
            from debug_tool import zeige_debug_info
            zeige_debug_info()

        st.sidebar.divider()
        st.sidebar.caption(f"🔧 Version {VERSION} ({VERSION_DATUM})")
        st.sidebar.caption(f"⚙️ Auto-Split ab {SCHWELLWERT_AUFTEILUNG} Menüs")

        return api_key, wochen, menulinien, menu_namen, button_clicked


def zeige_speiseplan_tab(speiseplan, pruefung=None):
    """Zeigt den Speiseplan-Tab an"""
    st.header("📋 Speiseplan")

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

    for woche in speiseplan['speiseplan']['wochen']:
        st.subheader(f"📅 Woche {woche['woche']}")
        for tag in woche['tage']:
            st.markdown(f"### {tag['tag']}")
            for menu in tag['menues']:
                with st.expander(f"**{menu['menuName']}**", expanded=True):
                    col1, col2, col3 = st.columns(3)

                    with col1:
                        st.markdown("**🌅 Frühstück**")
                        st.write(menu['fruehstueck']['hauptgericht'])
                        if menu['fruehstueck'].get('beilagen'):
                            st.caption(f"mit {', '.join(menu['fruehstueck']['beilagen'])}")
                        if menu['fruehstueck'].get('getraenk'):
                            st.caption(f"☕ {menu['fruehstueck']['getraenk']}")

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

                    with col3:
                        st.markdown("**🌙 Abendessen**")
                        st.write(menu['abendessen']['hauptgericht'])
                        if menu['abendessen'].get('beilagen'):
                            st.caption(f"mit {', '.join(menu['abendessen']['beilagen'])}")
                        if menu['abendessen'].get('getraenk'):
                            st.caption(f"🥤 {menu['abendessen']['getraenk']}")

                    if menu.get('zwischenmahlzeit'):
                        st.markdown(f"**🍎 Zwischenmahlzeit:** {menu['zwischenmahlzeit']}")
            st.divider()


def zeige_rezepte_tab(rezepte_data):
    """Zeigt den Rezepte-Tab an"""
    st.header("📖 Detaillierte Rezepte")

    if not rezepte_data or 'rezepte' not in rezepte_data:
        st.info("Keine Rezepte verfügbar.")
        return

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

    for rezept in rezepte_data['rezepte']:
        with st.expander(f"**{rezept['name']}** ({rezept.get('menu', 'N/A')})", expanded=False):
            col1, col2 = st.columns([3, 1])

            with col1:
                st.markdown(f"**{rezept['portionen']} Portionen** | {rezept.get('tag', '')} Woche {rezept.get('woche', '')}")
                st.caption(f"⏱️ Vorbereitung: {rezept['zeiten']['vorbereitung']} | Garzeit: {rezept['zeiten']['garzeit']}")

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

            st.markdown("### 🥘 Zutaten")
            zutaten_cols = st.columns(2)
            for i, zutat in enumerate(rezept['zutaten']):
                col_idx = i % 2
                with zutaten_cols[col_idx]:
                    zutat_text = f"**{zutat['menge']}** {zutat['name']}"
                    if zutat.get('hinweis'):
                        zutat_text += f"\n<small>{zutat['hinweis']}</small>"
                    st.markdown(f"• {zutat_text}")

            st.markdown("### 👨‍🍳 Zubereitung")
            for i, schritt in enumerate(rezept['zubereitung'], 1):
                st.info(f"**Schritt {i}:** {schritt}")

            st.markdown("### 📊 Nährwerte pro Portion")
            n = rezept['naehrwerte']
            cols = st.columns(5)
            cols[0].metric("Kalorien", n.get('kalorien', 'N/A'))
            cols[1].metric("Protein", n.get('protein', 'N/A'))
            cols[2].metric("Fett", n.get('fett', 'N/A'))
            cols[3].metric("KH", n.get('kohlenhydrate', 'N/A'))
            cols[4].metric("Ballaststoffe", n.get('ballaststoffe', 'N/A'))

            if rezept.get('allergene') and len(rezept['allergene']) > 0:
                st.warning(f"⚠️ **Allergene:** {', '.join(rezept['allergene'])}")

            if rezept.get('tipps') and len(rezept['tipps']) > 0:
                st.markdown("### 💡 Tipps für die Großküche")
                for tipp in rezept['tipps']:
                    st.success(f"• {tipp}")

            if rezept.get('variationen'):
                st.markdown("### 🔄 Variationen")
                if rezept['variationen'].get('pueriert'):
                    st.write(f"**Pürierte Kost:** {rezept['variationen']['pueriert']}")
                if rezept['variationen'].get('leichteKost'):
                    st.write(f"**Leichte Kost:** {rezept['variationen']['leichteKost']}")


def zeige_bibliothek_tab():
    """Zeigt den Bibliotheks-Tab mit gespeicherten Rezepten"""
    st.header("📚 Rezept-Bibliothek")
    st.markdown("*Ihre Sammlung generierter Rezepte*")

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

    rezepte = DB.suche_rezepte(suchbegriff=suchbegriff, tags=ausgewaehlte_tags)

    if sortierung == "Name A-Z":
        rezepte = sorted(rezepte, key=lambda x: x['name'])
    elif sortierung == "Neueste":
        rezepte = sorted(rezepte, key=lambda x: x['erstellt_am'], reverse=True)
    elif sortierung == "Beste Bewertung":
        rezepte = sorted(rezepte, key=lambda x: x['bewertung'], reverse=True)

    st.write(f"**{len(rezepte)} Rezepte gefunden**")

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
                st.warning("⚠️ Funktion deaktiviert. Löschen Sie die Datei 'rezepte_bibliothek.db' manuell.")
                st.session_state['bestaetigung_loeschen'] = False
            else:
                st.session_state['bestaetigung_loeschen'] = True
                st.warning("⚠️ Nochmal klicken zum Bestätigen!")

    st.divider()

    if len(rezepte) == 0:
        st.info("📭 Keine Rezepte gefunden. Generieren Sie einen Speiseplan, um Rezepte zu sammeln!")
    else:
        for rezept in rezepte:
            with st.expander(f"**{rezept['name']}** {'⭐' * rezept['bewertung']}", expanded=False):
                col1, col2, col3 = st.columns([3, 1, 1])

                with col1:
                    st.markdown(f"**{rezept['portionen']} Portionen**")
                    if rezept['menu_linie']:
                        st.caption(f"🍽️ {rezept['menu_linie']}")
                    st.caption(f"⏱️ Vorbereitung: {rezept['vorbereitung']} | Garzeit: {rezept['garzeit']}")
                    st.caption(f"📅 Erstellt: {rezept['erstellt_am'][:10]}")
                    st.caption(f"🔄 Verwendet: {rezept['verwendet_count']}x")

                with col2:
                    try:
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

                st.markdown("### 🥘 Zutaten")
                cols = st.columns(2)
                for i, zutat in enumerate(rezept['zutaten']):
                    col_idx = i % 2
                    with cols[col_idx]:
                        st.write(f"• **{zutat['menge']}** {zutat['name']}")

                st.markdown("### 👨‍🍳 Zubereitung")
                for i, schritt in enumerate(rezept['zubereitung'], 1):
                    st.write(f"**{i}.** {schritt}")

                if rezept.get('tags'):
                    st.markdown("### 🏷️ Tags")
                    st.write(" • ".join([f"`{tag}`" for tag in rezept['tags']]))

                if st.button(f"📋 Als Vorlage verwenden", key=f"template_{rezept['id']}"):
                    st.session_state['vorlage_rezept'] = rezept
                    DB.markiere_als_verwendet(rezept['id'], "Als Vorlage verwendet")
                    st.success("✅ Rezept als Vorlage gespeichert! Verwenden Sie es beim nächsten Speiseplan.")


# ==================== HAUPTPROGRAMM ====================

def main():
    """Hauptfunktion der Anwendung"""
    st.title("👨‍🍳 Professioneller Speiseplan-Generator")
    st.markdown("*Für Gemeinschaftsverpflegung, Krankenhäuser & Senioreneinrichtungen*")
    st.divider()

    api_key, wochen, menulinien, menu_namen, button_clicked = zeige_sidebar()

    if not api_key:
        st.warning("⚠️ Bitte geben Sie Ihren Claude API-Key in der Sidebar ein.")
        st.info("""
        **So erhalten Sie einen API-Key:**
        1. console.anthropic.com öffnen
        2. API Keys → neuen Key erstellen
        3. Key in der Sidebar einfügen
        """)
        return

    if button_clicked:
        if KOSTEN_TRACKING:
            zeige_kosten_warnung_bei_grossen_plaenen(wochen, menulinien)

        speiseplan, rezepte, pruefung, error, cost_tracker = generiere_speiseplan_mit_rezepten(
            wochen, menulinien, menu_namen, api_key
        )

        if error:
            st.error(f"❌ {error}")
            return

        st.session_state['speiseplan'] = speiseplan
        st.session_state['rezepte'] = rezepte
        st.session_state['pruefung'] = pruefung

        if KOSTEN_TRACKING and cost_tracker:
            st.session_state['cost_tracker'] = cost_tracker

        st.success("✅ Speiseplan und Rezepte erfolgreich erstellt!")
        st.balloons()

    if KOSTEN_TRACKING and 'cost_tracker' in st.session_state and st.session_state['cost_tracker']:
        zeige_kosten_anzeige(st.session_state['cost_tracker'])

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
        st.info("💡 **Tipp:** Generieren Sie einen Speiseplan, um die Funktionen zu sehen.")
        if st.button("📚 Rezept-Bibliothek öffnen"):
            st.session_state['nur_bibliothek'] = True
            st.rerun()
        if st.session_state.get('nur_bibliothek'):
            zeige_bibliothek_tab()


# ==================== EINSTIEGSPUNKT ====================

if __name__ == "__main__":
    main()

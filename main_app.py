"""
Hauptanwendung für den Speiseplan-Generator
Neu designte, robuste Version: tageweise Plan-Erzeugung, 2-Tage Rezept-Gruppen,
Coverage-Check, Tool-Call-Erzwingung, Sanitizer, Auto-Comma-Fixer, Schema-Validator.

Version: 2.0.1 - FIXED
Datum: 27.10.2025
"""

import streamlit as st
import requests
import json
import re
from typing import List, Dict, Any, Tuple, Optional

# ===================== JSON/Parsing-Utilities =====================

SMART_QUOTES = {
    """: '"', """: '"', "„": '"',
    "'": "'", "‚": "'",
}

def _strip_js_comments(s: str) -> str:
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
    t = re.sub(r"```(?:json)?\s*", "", text, flags=re.IGNORECASE).replace("```", "").strip()
    for k, v in SMART_QUOTES.items():
        t = t.replace(k, v)
    t = _strip_js_comments(t)
    t = re.sub(r",\s*(?=[}\]])", "", t)
    return t

def _json_tokenize(s: str):
    i, n = 0, len(s)
    WS = " \t\r\n"
    digits = "0123456789-+."
    while i < n:
        ch = s[i]
        if ch in WS:
            j = i+1
            while j < n and s[j] in WS: j += 1
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
    tokens = list(_json_tokenize(raw))
    out, stack = [], []
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
    if isinstance(parsed, dict):
        if "speiseplan" in parsed or "rezepte" in parsed or "tag" in parsed:
            return parsed
        for k in ("data", "result", "output"):
            v = parsed.get(k)
            if isinstance(v, dict) and (("speiseplan" in v) or ("rezepte" in v) or ("tag" in v)):
                return v
    return parsed

def _extract_tool_input_from_anthropic(data):
    try:
        content = data.get("content", [])
        for item in content:
            if isinstance(item, dict) and item.get("type") == "tool_use":
                return item.get("input")
    except Exception:
        pass
    return None

# ===================== Coverage/Schema-Utilities =====================

TAGE = ["Montag","Dienstag","Mittwoch","Donnerstag","Freitag","Samstag","Sonntag"]

def _tage_slicen(tage_liste: List[Dict[str, Any]], start: int, ende: int):
    return tage_liste[start:ende]

def _erwarte_rezept_keys(sp_plan: Dict[str, Any]) -> List[Tuple[int,str,str,str]]:
    expect = []
    for w in sp_plan['speiseplan']['wochen']:
        wnr = int(w.get('woche', 1))
        for t in w.get('tage', []):
            tag = str(t.get('tag', ''))
            for m in t.get('menues', []):
                hg = m.get('mittagessen', {}).get('hauptgericht', '')
                expect.append((wnr, tag, str(m.get('menuName','')), str(hg)))
    return expect

def _vorhandene_rezepte_keys(rezepte: Dict[str, Any]) -> List[Tuple[int,str,str,str]]:
    have = []
    if not rezepte or 'rezepte' not in rezepte: return have
    for r in rezepte['rezepte']:
        have.append((
            int(r.get('woche', 0) or 0),
            str(r.get('tag','')),
            str(r.get('menu','')),
            str(r.get('name',''))
        ))
    return have

def _name_to_hg(name: str) -> str:
    if not name: return name
    import re
    parts = re.split(r"\s+mit\s+| - | – ", name, maxsplit=1)
    return parts[0].strip()

def _delta_missing(expected: List[Tuple[int,str,str,str]], rezepte: Dict[str, Any]):
    have_index = set()
    for (w,t,menu,name) in _vorhandene_rezepte_keys(rezepte):
        have_index.add((w,t,menu,_name_to_hg(name)))
    missing = []
    for (w,t,menu,hg) in expected:
        if (w,t,menu,hg) not in have_index:
            missing.append((w,t,menu,hg))
    return missing

def _mini_plan_from_keys(full_plan: Dict[str,Any], keys: List[Tuple[int,str,str,str]]):
    from collections import defaultdict
    by_w = defaultdict(lambda: defaultdict(lambda: {"need": set(), "menus": set()}))
    for (w,t,menu,hg) in keys:
        by_w[w][t]["need"].add(hg)
        by_w[w][t]["menus"].add(menu)
    out_weeks = []
    for w in full_plan['speiseplan']['wochen']:
        wnr = w.get('woche')
        if wnr not in by_w: continue
        new_tage = []
        for t in w.get('tage', []):
            tag = t.get('tag')
            if tag not in by_w[wnr]: continue
            new_menues = []
            need_hg = by_w[wnr][tag]["need"]
            need_menus = by_w[wnr][tag]["menus"]
            for m in t.get('menues', []):
                hg = m.get('mittagessen', {}).get('hauptgericht')
                if m.get('menuName') in need_menus and hg in need_hg:
                    new_menues.append(m)
            if new_menues:
                new_tage.append({"tag": tag, "menues": new_menues})
        if new_tage:
            out_weeks.append({"woche": wnr, "tage": new_tage})
    return {"speiseplan": {
        "wochen": out_weeks,
        "menuLinien": full_plan['speiseplan'].get('menuLinien'),
        "menuNamen": full_plan['speiseplan'].get('menuNamen', [])
    }}

# ------------------ Mini-Schema-Validator ------------------

def _validate_day_struct(day: Dict[str,Any], menulinien: int) -> List[str]:
    errs = []
    if not isinstance(day, dict):
        return ["Tag-Struktur ist kein Objekt."]
    if day.get("tag") not in TAGE:
        errs.append("Feld 'tag' fehlt/ungültig.")
    if "menues" not in day or not isinstance(day["menues"], list):
        errs.append("Feld 'menues' fehlt/ist keine Liste.")
        return errs
    if len(day["menues"]) != menulinien:
        errs.append(f"Anzahl 'menues' != {menulinien}.")
    for idx, m in enumerate(day["menues"], 1):
        if not isinstance(m, dict):
            errs.append(f"Menü {idx}: ist kein Objekt."); continue
        for key in ("menuName","fruehstueck","mittagessen","abendessen"):
            if key not in m:
                errs.append(f"Menü {idx}: '{key}' fehlt.")
        if "mittagessen" in m:
            mi = m["mittagessen"]
            for key in ("hauptgericht","beilagen"):
                if key not in mi:
                    errs.append(f"Menü {idx} Mittagessen: '{key}' fehlt.")
            if isinstance(mi.get("beilagen"), list) and len(mi["beilagen"]) < 2:
                errs.append(f"Menü {idx} Mittagessen: zu wenige Beilagen (<2).")
    return errs

def _validate_week_struct(week: Dict[str,Any], menulinien: int) -> List[str]:
    errs = []
    if "tage" not in week or not isinstance(week["tage"], list) or len(week["tage"]) != 7:
        errs.append("Woche hat nicht exakt 7 'tage'.")
        return errs
    for t in week["tage"]:
        errs.extend(_validate_day_struct(t, menulinien))
    return errs

# ===================== App-Module-Imports =====================

from prompts import get_speiseplan_prompt, get_rezepte_prompt, get_pruefung_prompt
from pdf_generator import erstelle_speiseplan_pdf, erstelle_rezept_pdf, erstelle_alle_rezepte_pdf
from rezept_datenbank import RezeptDatenbank
from cost_tracker import CostTracker, zeige_kosten_anzeige, zeige_kosten_warnung_bei_grossen_plaenen, zeige_kosten_in_sidebar, KOSTEN_TRACKING_AKTIVIERT

# ===================== Konfiguration =====================

VERSION = "2.0.1"
VERSION_DATUM = "27.10.2025"
SCHWELLWERT_AUFTEILUNG = 8  # sehr niedrig – zwingt Split früh

KOSTEN_TRACKING = KOSTEN_TRACKING_AKTIVIERT()

@st.cache_resource
def hole_datenbank():
    return RezeptDatenbank()

DB = hole_datenbank()

st.set_page_config(page_title="Speiseplan-Generator", layout="wide", page_icon="👨‍🍳")

# ===================== Anthropic-Client =====================

def _anthropic_call(payload: Dict[str,Any], api_key: str):
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

def rufe_claude_api(user_prompt: str, api_key: str, max_tokens: int = 20000):
    """
    Bevorzugt Tool-Call 'return_json'; fällt bei Bedarf auf Text + robustes Parsing zurück.
    """
    tools = [{
        "name": "return_json",
        "description": "Gib das Ergebnis als JSON im 'input' dieses Tool-Calls zurück.",
        "input_schema": {"type": "object"}
    }]
    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": max_tokens,
        "temperature": 0,
        "top_p": 0,
        "messages": [{"role": "user", "content": user_prompt}],
        "tools": tools,
        "tool_choice": {"type": "tool", "name": "return_json"},
        "system": (
            "Gib dein Ergebnis ausschließlich als Tool-Aufruf 'return_json' zurück. "
            "Keine Erklärungen, kein Markdown, keine Kommentare, keine Codeblöcke. "
            "Der gesamte Inhalt muss im 'input'-Feld eines einzigen Tool-Calls liegen."
        )
    }
    try:
        r = _anthropic_call(payload, api_key)
        if r.status_code != 200:
            try:
                detail = r.json()
                msg = detail.get('error', {}).get('message', r.text)
            except Exception:
                msg = r.text
            return None, f"API-Fehler: Status {r.status_code} - {msg}", None

        data = r.json()
        # 1) tool_use?
        ti = _extract_tool_input_from_anthropic(data)
        if ti is not None:
            return _waehle_root(ti), None, data.get("usage", {})

        # 2) Fallback: Text → robust parsen
        content0 = data.get("content", [{}])[0]
        response_text = content0.get("text") if isinstance(content0, dict) else str(content0)
        try:
            parsed = json.loads(response_text)
            return _waehle_root(parsed), None, data.get("usage", {})
        except json.JSONDecodeError:
            pass
        try:
            parsed = parse_json_loose(response_text)
            return _waehle_root(parsed), None, data.get("usage", {})
        except json.JSONDecodeError as e:
            # einmaliger Retry mit response_format=json
            payload_retry = dict(payload)
            payload_retry["response_format"] = {"type": "json"}
            r2 = _anthropic_call(payload_retry, api_key)
            if r2.status_code != 200:
                try:
                    detail = r2.json()
                    msg = detail.get('error', {}).get('message', r2.text)
                except Exception:
                    msg = r2.text
                return None, f"API-Fehler (Retry): Status {r2.status_code} - {msg}", None
            d2 = r2.json()
            ti2 = _extract_tool_input_from_anthropic(d2)
            if ti2 is not None:
                return _waehle_root(ti2), None, d2.get("usage", {})
            c2 = d2.get("content", [{}])[0]
            t2 = c2.get("text") if isinstance(c2, dict) else str(c2)
            try:
                parsed2 = json.loads(t2)
                return _waehle_root(parsed2), None, d2.get("usage", {})
            except json.JSONDecodeError as e2:
                t2s = sanitize_json_text(t2)
                parsed3 = parse_json_loose(t2s)
                return _waehle_root(parsed3), None, d2.get("usage", {})
    except requests.exceptions.Timeout:
        return None, "Timeout: Die API-Anfrage hat zu lange gedauert (>3min). Reduzieren Sie die Anzahl Wochen/Menülinien.", None
    except requests.exceptions.RequestException as e:
        return None, f"Netzwerkfehler: {str(e)}", None
    except Exception as e:
        return None, f"Unerwarteter Fehler: {str(e)}", None

# ===================== Plan-Erzeugung tageweise =====================

def _tag_prompt_ein_tag(tagname: str, menulinien: int, menu_namen: List[str]) -> str:
    menu_liste = "\n".join([f"{i+1}. {name}" for i, name in enumerate(menu_namen)])
    return (
        "Du bist ein diätisch ausgebildeter Küchenmeister für Gemeinschaftsverpflegung. "
        "ANTWORTFORMAT: Antworte ausschließlich als Tool-Aufruf 'return_json'. "
        "Gib das komplette Ergebnis als EIN JSON-Objekt im Feld 'input' zurück. "
        "Kein Markdown, keine Erklärungen.\n\n"
        f"AUFGABE: Erstelle einen professionellen Speiseplan **für genau einen Tag: {tagname}** "
        f"mit {menulinien} Menülinie(n).\n\n"
        f"MENÜLINIEN:\n{menu_liste}\n\n"
        "VORGABEN:\n"
        "- Seniorengerecht; Mittag mit 2–3 Beilagen + Allergenliste; Nährwerte (kcal, Protein)\n"
        "- Frühstück, Mittag (Vorspeise/Hauptgericht/Beilagen/Dessert/Nährwerte/Allergene), "
        "Abendessen, Zwischenmahlzeit\n\n"
        "ANTWORT-SCHEMA (JSON):\n"
        "{\n"
        f'  "tag": "{tagname}",\n'
        '  "menues": [\n'
        '    {\n'
        '      "menuName": "Name der Menülinie",\n'
        '      "fruehstueck": {"hauptgericht": "...", "beilagen": ["..."], "getraenk": "..."},\n'
        '      "mittagessen": {\n'
        '        "vorspeise": "...",\n'
        '        "hauptgericht": "...",\n'
        '        "beilagen": ["...", "...", "..."],\n'
        '        "nachspeise": "...",\n'
        '        "naehrwerte": {"kalorien": "ca. X kcal", "protein": "X g"},\n'
        '        "allergene": ["..."]\n'
        '      },\n'
        '      "zwischenmahlzeit": "...",\n'
        '      "abendessen": {"hauptgericht": "...", "beilagen": ["..."], "getraenk": "..."}\n'
        '    }\n'
        '  ]\n'
        '}\n'
        f'WICHTIG: Gib **genau {menulinien}** Einträge in "menues" zurück, je einen pro Menülinie.'
    )

def _generiere_woche_tageweise(api_key: str, menulinien: int, menu_namen: List[str]) -> Tuple[Optional[Dict[str,Any]], Optional[str]]:
    tage_struct = []
    for tag in TAGE:
        p = _tag_prompt_ein_tag(tag, menulinien, menu_namen)
        day_data, error, _ = rufe_claude_api(p, api_key, max_tokens=6000)
        if error:
            # Einmaliger Retry
            day_data2, error2, _ = rufe_claude_api(p, api_key, max_tokens=6000)
            if error2:
                return None, f"Tag '{tag}': {error2}"
            day_data = day_data2

        if not isinstance(day_data, dict) or "tag" not in day_data or "menues" not in day_data:
            return None, f"Unerwartete Tagesstruktur für {tag}"

        # Sicherheit: Anzahl linien erzwingen
        menues = day_data.get("menues", [])
        if len(menues) != menulinien:
            if len(menues) > menulinien:
                menues = menues[:menulinien]
            elif len(menues) < menulinien and len(menues) > 0:
                last = menues[-1]
                while len(menues) < menulinien:
                    menues.append(last)

        # Minimal-Validierung pro Tag
        errs = _validate_day_struct({"tag": day_data["tag"], "menues": menues}, menulinien)
        if errs:
            return None, f"{tag}: " + "; ".join(errs)

        tage_struct.append({"tag": day_data["tag"], "menues": menues})

    week = {"woche": 1, "tage": tage_struct}
    return week, None

# ===================== Geschäftslogik: Gestuft =====================

def generiere_speiseplan_gestuft(wochen: int, menulinien: int, menu_namen: List[str], api_key: str, cost_tracker):
    st.success(f"✅ **Gestufte Generierung aktiv** – {wochen} Woche(n) werden einzeln erzeugt.")
    alle_wochen, alle_rezepte = [], []
    progress_bar = st.progress(0)
    status_text = st.empty()

    for woche_nr in range(1, wochen + 1):
        status_text.text(f"Woche {woche_nr} von {wochen} – Plan")
        progress_bar.progress((woche_nr - 1) / wochen)

        with st.spinner(f"📅 Woche {woche_nr} (tageweise)…"):
            week_struct, week_err = _generiere_woche_tageweise(api_key, menulinien, menu_namen)
            if week_err:
                st.error(f"❌ Fehler bei Woche {woche_nr}: {week_err}")
                return None, None, None, f"Fehler bei Woche {woche_nr}: {week_err}", cost_tracker

            week_struct["woche"] = woche_nr
            # Wochen-Validierung
            w_errs = _validate_week_struct(week_struct, menulinien)
            if w_errs:
                return None, None, None, f"Strukturfehler in Woche {woche_nr}: {'; '.join(w_errs)}", cost_tracker

            alle_wochen.append(week_struct)
            # Für Rezepte brauchen wir ein Mini-Planobjekt
            speiseplan_week = {
                "speiseplan": {
                    "wochen": [week_struct],
                    "menuLinien": menulinien,
                    "menuNamen": menu_namen
                }
            }

        # Rezepte in 2-Tage-Häppchen + Coverage-Check
        with st.spinner(f"📖 Woche {woche_nr}: Rezepte erzeugen…"):
            w_tage = week_struct["tage"]
            tage_pro_gruppe = 2
            anzahl_gruppen = (len(w_tage) + tage_pro_gruppe - 1) // tage_pro_gruppe
            st.info(f"🔄 Woche {woche_nr}: {anzahl_gruppen} Gruppen à {tage_pro_gruppe} Tage")

            rezepte_data_w = {"rezepte": []}
            for g in range(anzahl_gruppen):
                start, end = g * tage_pro_gruppe, min((g+1) * tage_pro_gruppe, len(w_tage))
                gruppe_plan = {
                    "speiseplan": {
                        "wochen": [{"woche": woche_nr, "tage": _tage_slicen(w_tage, start, end)}],
                        "menuLinien": menulinien,
                        "menuNamen": menu_namen
                    }
                }
                expected = _erwarte_rezept_keys(gruppe_plan)

                with st.spinner(f"📦 Woche {woche_nr} – Gruppe {g+1}/{anzahl_gruppen}"):
                    rez_prompt = get_rezepte_prompt(gruppe_plan)
                    rez_res, _, usage = rufe_claude_api(rez_prompt, api_key, max_tokens=10000)
                    if KOSTEN_TRACKING and cost_tracker and usage:
                        cost_tracker.add_usage(usage)
                    if rez_res and "rezepte" in rez_res:
                        rezepte_data_w["rezepte"].extend(rez_res["rezepte"])

                    missing = _delta_missing(expected, rezepte_data_w)
                    tries = 0
                    while missing and tries < 2:
                        st.warning(f"🧩 Woche {woche_nr}, Gruppe {g+1}: {len(missing)} fehlend – Nachgenerierung…")
                        sub_plan = _mini_plan_from_keys(gruppe_plan, missing)
                        sub_prompt = get_rezepte_prompt(sub_plan)
                        sub_res, _, usage2 = rufe_claude_api(sub_prompt, api_key, max_tokens=9000)
                        if KOSTEN_TRACKING and cost_tracker and usage2:
                            cost_tracker.add_usage(usage2)
                        if sub_res and "rezepte" in sub_res:
                            rezepte_data_w["rezepte"].extend(sub_res["rezepte"])
                        missing = _delta_missing(expected, rezepte_data_w)
                        tries += 1

                    if missing:
                        st.error(f"❗ Woche {woche_nr}, Gruppe {g+1}: {len(missing)} Rezept(e) fehlen weiterhin.")

            # Woche speichern & sammeln
            if rezepte_data_w["rezepte"]:
                try:
                    DB.speichere_alle_rezepte(rezepte_data_w)
                except Exception as e:
                    st.warning(f"⚠️ Woche {woche_nr}: Speichern fehlgeschlagen: {e}")
                alle_rezepte.extend(rezepte_data_w["rezepte"])
            else:
                st.warning(f"⚠️ Woche {woche_nr}: Keine Rezepte erzeugt.")

        progress_bar.progress(woche_nr / wochen)

    # Gesamter Plan
    full_plan = {
        "speiseplan": {
            "wochen": alle_wochen,
            "menuLinien": menulinien,
            "menuNamen": menu_namen
        }
    }
    full_recipes = {"rezepte": alle_rezepte}

    # Optionale Prüfung
    pruefung_data = None
    with st.spinner("🔍 Qualitätsprüfung…"):
        try:
            pruef_prompt = get_pruefung_prompt(full_plan)
            pruefung_data, _, _ = rufe_claude_api(pruef_prompt, api_key, max_tokens=8000)
        except Exception:
            pass

    st.success(f"✅ Fertig: {wochen} Woche(n), {len(alle_rezepte)} Rezept(e)")
    return full_plan, full_recipes, pruefung_data, None, cost_tracker

# ===================== Orchestrierung =====================

def generiere_speiseplan_mit_rezepten(wochen: int, menulinien: int, menu_namen: List[str], api_key: str):
    cost_tracker = CostTracker() if KOSTEN_TRACKING else None
    total_menus = wochen * menulinien * 7

    # Gestufter Modus praktisch immer an, wenn > 1 Woche oder > 3 Linien
    if (total_menus > SCHWELLWERT_AUFTEILUNG) or (wochen > 1) or (menulinien > 3):
        st.info(f"🔧 Gestufter Modus aktiv (Plan={total_menus}, Split ab {SCHWELLWERT_AUFTEILUNG}).")
        return generiere_speiseplan_gestuft(wochen, menulinien, menu_namen, api_key, cost_tracker)

    # Kleiner Plan (selten)
    st.info("🧪 Kleiner Plan – Direktmodus (ohne Tages-Split).")
    sp_prompt = get_speiseplan_prompt(wochen, menulinien, menu_namen)
    sp_data, error, usage = rufe_claude_api(sp_prompt, api_key, max_tokens=16000)
    if KOSTEN_TRACKING and cost_tracker and usage:
        cost_tracker.add_usage(usage)
    if error:
        return None, None, None, f"Fehler beim Erstellen des Speiseplans: {error}", cost_tracker

    # Schnellvalidierung: 7 Tage je Woche
    for w in sp_data.get("speiseplan", {}).get("wochen", []):
        errs = _validate_week_struct(w, menulinien)
        if errs:
            return None, None, None, f"Strukturfehler im Direktmodus: {'; '.join(errs)}", cost_tracker

    rez_prompt = get_rezepte_prompt(sp_data)
    rez_data, err_r, usage2 = rufe_claude_api(rez_prompt, api_key, max_tokens=16000)
    if KOSTEN_TRACKING and cost_tracker and usage2:
        cost_tracker.add_usage(usage2)
    if err_r:
        return sp_data, None, None, f"Fehler bei Rezept-Generierung: {err_r}", cost_tracker

    return sp_data, rez_data, None, None, cost_tracker

# ===================== UI-Funktionen =====================

def zeige_sidebar():
    with st.sidebar:
        st.header("⚙️ Einstellungen")
        api_key = st.text_input("🔑 Anthropic API-Key", type="password", value=st.session_state.get('api_key',''))
        st.session_state['api_key'] = api_key
        st.divider()
        
        wochen = st.number_input("📅 Anzahl Wochen", min_value=1, max_value=4, value=1)
        menulinien = st.number_input("🍽️ Anzahl Menülinien", min_value=1, max_value=5, value=2)
        
        menu_namen = []
        if menulinien > 0:
            st.markdown("**Namen der Menülinien:**")
            default_namen = ["Vollkost", "Vegetarisch", "Schonkost", "Diabetiker", "Pürierkost"]
            for i in range(menulinien):
                default = default_namen[i] if i < len(default_namen) else f"Menülinie {i+1}"
                name = st.text_input(f"Menülinie {i+1}", value=default, key=f"menu_{i}")
                menu_namen.append(name)
        
        if KOSTEN_TRACKING:
            zeige_kosten_in_sidebar()
        
        start = st.button("🚀 Speiseplan generieren", type="primary", use_container_width=True)
        
        st.divider()
        with st.expander("ℹ️ Info"):
            st.caption(f"Version: {VERSION}")
            st.caption(f"Stand: {VERSION_DATUM}")
            st.caption("👨‍🍳 Professionell für Gemeinschaftsverpflegung")
        
    return api_key, wochen, menulinien, menu_namen, start

def zeige_speiseplan_tab(speiseplan, pruefung=None):
    st.header("📋 Ihr Speiseplan")
    
    try:
        pdf = erstelle_speiseplan_pdf(speiseplan)
        st.download_button("📄 PDF herunterladen", data=pdf, file_name="Speiseplan.pdf", mime="application/pdf", type="primary")
    except Exception as e:
        st.error(f"PDF-Fehler: {e}")
    
    if pruefung:
        with st.expander("🔍 Qualitätsprüfung", expanded=False):
            if 'bewertungen' in pruefung:
                cols = st.columns(len(pruefung['bewertungen']))
                for i, bew in enumerate(pruefung['bewertungen']):
                    with cols[i]:
                        st.metric(bew['kategorie'], f"{bew['punkte']}/10")
                        st.caption(bew['kommentar'])
            if 'fazit' in pruefung:
                st.info(pruefung['fazit'])

    for w in speiseplan['speiseplan']['wochen']:
        st.subheader(f"📅 Woche {w['woche']}")
        for t in w['tage']:
            st.markdown(f"### {t['tag']}")
            for m in t['menues']:
                with st.expander(f"**{m['menuName']}**", expanded=False):
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.markdown("**🌅 Frühstück**")
                        st.write(m['fruehstueck']['hauptgericht'])
                        if m['fruehstueck'].get('beilagen'):
                            st.caption(", ".join(m['fruehstueck']['beilagen']))
                        if m['fruehstueck'].get('getraenk'):
                            st.caption(f"Getränk: {m['fruehstueck']['getraenk']}")
                    with c2:
                        st.markdown("**🍽️ Mittagessen**")
                        if m['mittagessen'].get('vorspeise'):
                            st.caption(f"Vorspeise: {m['mittagessen']['vorspeise']}")
                        st.write(f"**{m['mittagessen']['hauptgericht']}**")
                        if m['mittagessen'].get('beilagen'):
                            st.success(f"Beilagen: {', '.join(m['mittagessen']['beilagen'])}")
                        if m['mittagessen'].get('nachspeise'):
                            st.caption(f"Nachspeise: {m['mittagessen']['nachspeise']}")
                        if m['mittagessen'].get('naehrwerte'):
                            st.caption(f"📊 {m['mittagessen']['naehrwerte'].get('kalorien','')} | Protein: {m['mittagessen']['naehrwerte'].get('protein','')}")
                        if m['mittagessen'].get('allergene'):
                            st.warning(f"⚠️ Allergene: {', '.join(m['mittagessen']['allergene'])}")
                    with c3:
                        st.markdown("**🌙 Abendessen**")
                        st.write(m['abendessen']['hauptgericht'])
                        if m['abendessen'].get('beilagen'):
                            st.caption(", ".join(m['abendessen']['beilagen']))
                        if m['abendessen'].get('getraenk'):
                            st.caption(f"Getränk: {m['abendessen']['getraenk']}")
            st.divider()

def zeige_rezepte_tab(rezepte_data):
    st.header("📖 Detaillierte Rezepte")
    if not rezepte_data or 'rezepte' not in rezepte_data or len(rezepte_data['rezepte']) == 0:
        st.info("Keine Rezepte verfügbar.")
        return
    try:
        pdf = erstelle_alle_rezepte_pdf(rezepte_data)
        st.download_button("📚 Alle Rezepte als PDF", data=pdf, file_name="Alle_Rezepte.pdf", mime="application/pdf")
    except Exception as e:
        st.error(f"PDF-Fehler: {e}")

    for r in rezepte_data['rezepte']:
        with st.expander(f"{r['name']} ({r.get('menu','')})"):
            c1, c2 = st.columns([3,1])
            with c1:
                st.caption(f"{r.get('tag','')} • Woche {r.get('woche','')}")
                st.caption(f"⏱️ Vorb.: {r['zeiten']['vorbereitung']} | Garzeit: {r['zeiten']['garzeit']}")
            with c2:
                try:
                    rp = erstelle_rezept_pdf(r)
                    st.download_button("📄 Als PDF", data=rp, file_name=f"Rezept_{r['name'].replace(' ','_')}.pdf", mime="application/pdf")
                except Exception as e:
                    st.error(f"PDF-Fehler: {e}")
            st.markdown("### Zutaten")
            cols = st.columns(2)
            for i, z in enumerate(r['zutaten']):
                with cols[i%2]:
                    txt = f"**{z['menge']}** {z['name']}"
                    if z.get('hinweis'): txt += f" – {z['hinweis']}"
                    st.write(f"• {txt}")
            st.markdown("### Zubereitung")
            for i, s in enumerate(r['zubereitung'], 1):
                st.write(f"**{i}.** {s}")
            st.markdown("### Nährwerte (pro Portion)")
            n = r['naehrwerte']; c = st.columns(5)
            c[0].metric("kcal", n.get('kalorien','N/A'))
            c[1].metric("Protein", n.get('protein','N/A'))
            c[2].metric("Fett", n.get('fett','N/A'))
            c[3].metric("KH", n.get('kohlenhydrate','N/A'))
            c[4].metric("Ballaststoffe", n.get('ballaststoffe','N/A'))
            if r.get('allergene'):
                st.warning("⚠️ " + ", ".join(r['allergene']))

def zeige_bibliothek_tab():
    st.header("📚 Rezept-Bibliothek")
    st.markdown("*Ihre Sammlung generierter Rezepte*")
    stats = DB.hole_statistiken()
    c = st.columns(4)
    c[0].metric("Rezepte", stats['anzahl_rezepte'])
    c[1].metric("Meistverwendet", stats['meistverwendet'][0][1] if stats['meistverwendet'] else 0)
    c[2].metric("Tags", len(stats['tags']))
    c[3].metric("Beste Bewertung", stats['bestbewertet'][0][1] if stats['bestbewertet'] else "-")

    st.divider()
    such = st.text_input("🔍 Suche nach Name/Zutat", "")
    tags = st.multiselect("🏷️ Tags", options=list(stats['tags'].keys()) if stats['tags'] else [])
    sortierung = st.selectbox("📊 Sortierung", ["Meistverwendet","Neueste","Name A-Z","Beste Bewertung"])

    rezepte = DB.suche_rezepte(suchbegriff=such, tags=tags)
    if sortierung == "Name A-Z":
        rezepte = sorted(rezepte, key=lambda x: x['name'])
    elif sortierung == "Neueste":
        rezepte = sorted(rezepte, key=lambda x: x['erstellt_am'], reverse=True)
    elif sortierung == "Beste Bewertung":
        rezepte = sorted(rezepte, key=lambda x: x['bewertung'], reverse=True)

    st.write(f"**{len(rezepte)}** Rezepte gefunden")
    st.divider()
    if not rezepte:
        st.info("Noch keine Rezepte vorhanden.")
        return

    for r in rezepte:
        with st.expander(f"{r['name']} {'⭐'*r['bewertung']}"):
            c1, c2, c3 = st.columns([3,1,1])
            with c1:
                st.caption(f"Portionen: {r['portionen']}")
                if r.get('menu_linie'): st.caption(f"🍽️ {r['menu_linie']}")
                st.caption(f"⏱️ {r['vorbereitung']} | {r['garzeit']}")
                st.caption(f"📅 {r['erstellt_am'][:10]} • 🔄 {r['verwendet_count']}x")
            with c2:
                try:
                    exportable = {
                        'name': r['name'],
                        'menu': r.get('menu_linie',''),
                        'tag': '',
                        'woche': '',
                        'portionen': r['portionen'],
                        'zeiten': {'vorbereitung': r['vorbereitung'], 'garzeit': r['garzeit'], 'gesamt': r.get('gesamtzeit','')},
                        'zutaten': r['zutaten'],
                        'zubereitung': r['zubereitung'],
                        'naehrwerte': r['naehrwerte'],
                        'allergene': r['allergene'],
                        'tipps': r['tipps'],
                        'variationen': r['variationen']
                    }
                    pdf = erstelle_rezept_pdf(exportable)
                    st.download_button("📄 PDF", data=pdf, file_name=f"Rezept_{r['name'].replace(' ','_')}.pdf", mime="application/pdf")
                except Exception as e:
                    st.error(f"PDF-Fehler: {e}")
            with c3:
                rating = st.select_slider("⭐ Bewertung", options=[0,1,2,3,4,5], value=r['bewertung'], key=f"rating_{r['id']}")
                if rating != r['bewertung']:
                    DB.bewerte_rezept(r['id'], rating)
                    st.rerun()
                if st.button("🗑️", key=f"del_{r['id']}"):
                    DB.loesche_rezept(r['id']); st.success("Gelöscht."); st.rerun()

# ===================== Main =====================

def main():
    st.title("👨‍🍳 Professioneller Speiseplan-Generator")
    st.markdown("*Für Gemeinschaftsverpflegung, Krankenhäuser & Senioreneinrichtungen*")
    st.divider()

    api_key, wochen, menulinien, menu_namen, start = zeige_sidebar()
    if not api_key:
        st.warning("Bitte API-Key eingeben.")
        return

    if start:
        if KOSTEN_TRACKING:
            zeige_kosten_warnung_bei_grossen_plaenen(wochen, menulinien)

        plan, rezepte, pruefung, error, tracker = generiere_speiseplan_mit_rezepten(
            wochen, menulinien, menu_namen, api_key
        )
        if error:
            st.error(error); return
        st.session_state['speiseplan'] = plan
        st.session_state['rezepte'] = rezepte
        st.session_state['pruefung'] = pruefung
        if KOSTEN_TRACKING and tracker:
            st.session_state['cost_tracker'] = tracker
        st.success("✅ Speiseplan & Rezepte erstellt!")
        st.balloons()

    if KOSTEN_TRACKING and st.session_state.get('cost_tracker'):
        zeige_kosten_anzeige(st.session_state['cost_tracker'])

    if st.session_state.get('speiseplan'):
        t1, t2, t3 = st.tabs(["📋 Speiseplan", "📖 Rezepte", "📚 Bibliothek"])
        with t1:
            zeige_speiseplan_tab(st.session_state['speiseplan'], st.session_state.get('pruefung'))
        with t2:
            zeige_rezepte_tab(st.session_state.get('rezepte'))
        with t3:
            zeige_bibliothek_tab()
    else:
        if st.button("📚 Rezept-Bibliothek öffnen"):
            zeige_bibliothek_tab()

if __name__ == "__main__":
    main()
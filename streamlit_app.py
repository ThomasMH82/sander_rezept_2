import streamlit as st
import requests
import json
import re
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_CENTER, TA_LEFT

st.set_page_config(page_title="Speiseplan-Generator", layout="wide", page_icon="👨‍🍳")

# Sidebar für API-Key
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
        help="Optional - nur wenn nicht in secrets.toml hinterlegt",
        placeholder="Optional - nur wenn nicht konfiguriert"
    )
    
    # Verwende manuellen Key wenn eingegeben, sonst den aus Secrets
    api_key = api_key_manual if api_key_manual else api_key_from_secrets
    
    if api_key:
        st.success("API-Key bereit!")
    else:
        st.warning("Bitte API-Key eingeben oder in secrets.toml hinterlegen")
        with st.expander("ℹ️ API-Key dauerhaft speichern"):
            st.markdown("""
            **Lokal:** Erstellen Sie `.streamlit/secrets.toml`:
            ```toml
            ANTHROPIC_API_KEY = "Ihr-Key"
            ```
            
            **Cloud:** In App-Settings → Secrets eintragen
            
            Details: Siehe API_KEY_ANLEITUNG.md
            """)
    
    st.divider()
    
    st.header("⚙️ Speiseplan-Konfiguration")
    wochen = st.number_input("Anzahl Wochen", min_value=1, max_value=4, value=1)
    menulinien = st.number_input("Anzahl Menülinien", min_value=1, max_value=5, value=2)
    
    st.subheader("Bezeichnung der Menülinien")
    menu_namen = []
    for i in range(menulinien):
        name = st.text_input(f"Menülinie {i+1}", value=f"Menü {i+1}", key=f"menu_{i}")
        menu_namen.append(name)

# Titel
st.title("👨‍🍳 Professioneller Speiseplan-Generator")
st.markdown("*Für Gemeinschaftsverpflegung, Krankenhäuser & Senioreneinrichtungen*")
st.divider()

def generiere_tages_prompt(tag, woche_nr, menulinien, menu_namen):
    """Generiert Prompt für einen einzelnen Tag"""
    menu_liste = "\n".join([f"{i+1}. {name}" for i, name in enumerate(menu_namen)])

    return f"""Du bist ein diätisch ausgebildeter Küchenmeister mit über 25 Jahren Erfahrung in der Gemeinschaftsverpflegung, spezialisiert auf Krankenhaus- und Seniorenverpflegung.

AUFGABE: Erstelle einen professionellen Speiseplan für {tag} (Woche {woche_nr}) mit {menulinien} Menülinie(n).

MENÜLINIEN:
{menu_liste}

WICHTIGE VORGABEN:
- Seniorengerechte Kost: leicht verdaulich, weiche Konsistenzen wo nötig
- Nährstoffdichte Gerichte (wichtig bei oft verringertem Appetit)
- Abwechslungsreich und ausgewogen
- IMMER mindestens 2-3 Beilagen zum Mittagessen (z.B. Kartoffeln/Reis/Nudeln UND Gemüse/Salat)
- Saisonale und regionale Produkte bevorzugen
- Klare Portionsangaben für Gemeinschaftsverpflegung (pro Person)
- Allergenkennzeichnung
- Pro Tag: Frühstück, Mittagessen (MIT BEILAGEN!), Abendessen + Zwischenmahlzeit

ERNÄHRUNGSPHYSIOLOGISCHE ANFORDERUNGEN:
- Ausreichend Protein (1,0-1,2g/kg Körpergewicht)
- Ballaststoffreich aber gut verträglich
- Calciumreich für Knochengesundheit
- Vitamin D Quellen einbauen
- Flüssigkeitsreiche Gerichte (Suppen, Eintöpfe)

WICHTIG: JEDES Mittagessen MUSS mindestens 2-3 Beilagen haben!

KRITISCH: Du MUSST mit einem JSON-Objekt antworten, das EXAKT diese Struktur hat:

STRUKTUR DER ANTWORT (JSON) - NUR FÜR DIESEN EINEN TAG:
{{
  "tag": "{tag}",
  "menues": [
    {{
      "menuName": "Name der Menülinie",
      "fruehstueck": {{
        "hauptgericht": "Gericht",
        "beilagen": ["Beilage 1", "Beilage 2"],
        "getraenk": "Getränk"
      }},
      "mittagessen": {{
        "vorspeise": "Suppe/Vorspeise",
        "hauptgericht": "Hauptgericht",
        "beilagen": ["Beilage 1 (z.B. Kartoffeln)", "Beilage 2 (z.B. Gemüse)", "Beilage 3 (z.B. Salat)"],
        "nachspeise": "Dessert",
        "naehrwerte": {{
          "kalorien": "ca. X kcal",
          "protein": "X g"
        }},
        "allergene": ["Liste der Allergene"]
      }},
      "zwischenmahlzeit": "Obst/Joghurt/etc.",
      "abendessen": {{
        "hauptgericht": "Gericht",
        "beilagen": ["Beilage 1", "Beilage 2"],
        "getraenk": "Getränk"
      }}
    }}
  ]
}}

WICHTIGE JSON-REGELN:
- Verwende AUSSCHLIESSLICH den Tool-Call 'return_json'
- Alle Strings in doppelten Anführungszeichen (")
- Kommata zwischen allen Feldern, KEINE trailing commas vor }} oder ]
- Alle Klammern müssen geschlossen sein: {{ }} [ ]
- Keine Kommentare im JSON
- Keine Sonderzeichen oder Smart Quotes

Antworte NUR mit dem return_json Tool-Call. Kein Text davor oder danach!"""

def generiere_rezepte_prompt(gerichte_batch):
    """
    Generiert Prompt für eine Batch von Gerichten

    Args:
        gerichte_batch: Liste von Dicts mit gericht, beilagen, woche, tag, menu
    """
    gerichte_liste = "\n".join([
        f"{i+1}. {g['gericht']} mit {', '.join(g['beilagen'])} (Woche {g['woche']}, {g['tag']}, {g['menu']})"
        for i, g in enumerate(gerichte_batch)
    ])
    
    return f"""Du bist ein diätisch ausgebildeter Küchenmeister mit 25+ Jahren Erfahrung.

AUFGABE: Erstelle detaillierte Rezepte für folgende Gerichte (für 10 Portionen):

{gerichte_liste}

ANFORDERUNGEN:
- Portionsangaben für 10 Personen
- Seniorengerechte Zubereitung
- Genaue Mengenangaben in Gramm/Liter
- Schritt-für-Schritt Anleitung
- Zeiten (Vorbereitung und Garzeit)
- Nährwertangaben pro Portion
- Allergenkennzeichnung
- Tipps für Großküche

JSON-FORMAT:
{{
  "rezepte": [
    {{
      "name": "Gerichtname",
      "woche": 1,
      "tag": "Montag",
      "menu": "Menüname",
      "portionen": 10,
      "zeiten": {{
        "vorbereitung": "X Minuten",
        "garzeit": "X Minuten"
      }},
      "zutaten": [
        {{
          "name": "Zutat",
          "menge": "X g/ml",
          "hinweis": "Optional"
        }}
      ],
      "zubereitung": [
        "Schritt 1 detailliert",
        "Schritt 2 detailliert"
      ],
      "naehrwerte": {{
        "kalorien": "X kcal",
        "protein": "X g",
        "fett": "X g",
        "kohlenhydrate": "X g",
        "ballaststoffe": "X g"
      }},
      "allergene": ["Liste"],
      "tipps": ["Tipp 1", "Tipp 2"]
    }}
  ]
}}

WICHTIGE JSON-REGELN:
- Verwende AUSSCHLIESSLICH den Tool-Call 'return_json'
- Alle Strings in doppelten Anführungszeichen (")
- Kommata zwischen allen Feldern, KEINE trailing commas
- Alle Klammern müssen geschlossen sein
- Keine Kommentare im JSON

Antworte NUR mit dem return_json Tool-Call!"""


def generiere_rezepte_batch(speiseplan, api_key, batch_size=10, progress_callback=None):
    """
    Generiert Rezepte in Batches um Timeouts zu vermeiden

    Args:
        speiseplan: Der generierte Speiseplan
        api_key: API-Schlüssel
        batch_size: Anzahl Rezepte pro Batch (Standard: 10)
        progress_callback: Optional - Funktion für Fortschrittsanzeige

    Returns:
        Tuple von (rezepte_data, error_message)
    """
    import time

    # Extrahiere alle Hauptgerichte
    alle_gerichte = []
    for woche in speiseplan['speiseplan']['wochen']:
        for tag in woche['tage']:
            for menu in tag['menues']:
                hauptgericht = menu.get('mittagessen', {}).get('hauptgericht')
                if hauptgericht:
                    alle_gerichte.append({
                        'gericht': hauptgericht,
                        'beilagen': menu['mittagessen'].get('beilagen', []),
                        'woche': woche['woche'],
                        'tag': tag['tag'],
                        'menu': menu['menuName']
                    })

    if not alle_gerichte:
        return None, "Keine Gerichte im Speiseplan gefunden"

    # Teile in Batches auf
    alle_rezepte = []
    anzahl_batches = (len(alle_gerichte) + batch_size - 1) // batch_size

    for i in range(0, len(alle_gerichte), batch_size):
        batch_nr = (i // batch_size) + 1
        batch = alle_gerichte[i:i + batch_size]

        if progress_callback:
            progress_callback(
                f"Generiere Rezepte... Batch {batch_nr}/{anzahl_batches} "
                f"({len(batch)} Rezepte)"
            )

        # Generiere Rezepte für diesen Batch
        prompt = generiere_rezepte_prompt(batch)
        rezepte_data, error = rufe_claude_api(prompt, api_key, max_tokens=16000, use_json_mode=True)

        if error:
            # Bei Fehler: Versuche mit kleinerem Batch
            if len(batch) > 5:
                if progress_callback:
                    progress_callback(f"⚠️ Batch zu groß, teile auf...")

                # Teile Batch in zwei Hälften
                mid = len(batch) // 2
                for sub_batch in [batch[:mid], batch[mid:]]:
                    prompt = generiere_rezepte_prompt(sub_batch)
                    rezepte_data, error = rufe_claude_api(prompt, api_key, max_tokens=16000, use_json_mode=True)

                    if not error and rezepte_data and 'rezepte' in rezepte_data:
                        alle_rezepte.extend(rezepte_data['rezepte'])
                    time.sleep(1)
            else:
                # Auch kleine Batches schlagen fehl, überspringe
                st.warning(f"⚠️ Rezeptgenerierung für Batch {batch_nr} fehlgeschlagen: {error}")
                continue
        else:
            if rezepte_data and 'rezepte' in rezepte_data:
                alle_rezepte.extend(rezepte_data['rezepte'])

        # Pause zwischen Batches
        time.sleep(0.5)

    if not alle_rezepte:
        return None, "Keine Rezepte konnten generiert werden"

    return {'rezepte': alle_rezepte}, None


def bereinige_json(text):
    """Bereinigt JSON-Text mit mehreren Fallback-Strategien"""
    if not text:
        return ""

    # Entferne Markdown Code-Blöcke
    text = re.sub(r'```json\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'```\s*', '', text)
    text = text.strip()

    # Ersetze typografische Anführungszeichen
    replacements = {
        '"': '"', '"': '"', '„': '"',  # Smart quotes
        ''': "'", ''': "'", '‚': "'",
        '–': '-', '—': '-',  # Dashes
        '\u200b': '',  # Zero-width space
        '\xa0': ' ',  # Non-breaking space
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    # Entferne JavaScript-style Kommentare
    text = re.sub(r'//.*?$', '', text, flags=re.MULTILINE)
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)

    # Entferne trailing commas (häufiger JSON-Fehler)
    text = re.sub(r',(\s*[}\]])', r'\1', text)

    # Finde das JSON-Objekt
    first_brace = text.find('{')
    last_brace = text.rfind('}')

    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        text = text[first_brace:last_brace + 1]

    # Normalisiere Whitespace
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()

    return text

def normalize_response_structure(data):
    """
    Normalisiert die Response-Struktur, um verschachtelte oder unerwartete Formate zu behandeln

    Args:
        data: Die rohe Response-Daten

    Returns:
        Normalisierte Daten-Struktur
    """
    if not isinstance(data, dict):
        return data

    # Wenn die Antwort bereits die erwarteten Felder hat, gib sie direkt zurück
    if "menues" in data or "rezepte" in data or "pruefung" in data:
        return data

    # Suche nach verschachtelten Strukturen
    for key in ["data", "result", "output", "response", "tag", "day", "menu_plan", "speiseplan"]:
        if key in data and isinstance(data[key], dict):
            nested = data[key]
            # Rekursiv normalisieren
            if "menues" in nested or "rezepte" in nested or "pruefung" in nested:
                return normalize_response_structure(nested)

    # Wenn nichts gefunden, gib die Original-Daten zurück
    return data

def rufe_claude_api(prompt, api_key, max_tokens=20000, use_json_mode=True):
    """
    Ruft Claude API auf mit verbessertem JSON-Parsing

    Args:
        prompt: Der Prompt-Text
        api_key: API-Schlüssel
        max_tokens: Maximale Token-Anzahl
        use_json_mode: Ob JSON-Tool-Call verwendet werden soll
    """
    try:
        # Request-Payload erstellen
        payload = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": max_tokens,
            "temperature": 0.0,  # Deterministisch für konsistente JSON-Ausgabe
            "messages": [{"role": "user", "content": prompt}]
        }

        # Optional: Tool-Call für strukturierte JSON-Ausgabe
        if use_json_mode:
            payload["system"] = (
                "Du bist ein diätisch ausgebildeter Küchenmeister. "
                "Gib dein Ergebnis AUSSCHLIESSLICH als Tool-Aufruf 'return_json' zurück. "
                "Das JSON muss PERFEKT valide sein: alle Strings in doppelten Anführungszeichen, "
                "korrekte Kommata zwischen Feldern, keine trailing commas. "
                "WICHTIG: Das JSON-Objekt MUSS die Top-Level-Felder haben, die im Prompt gefordert werden "
                "(z.B. 'tag' und 'menues' für Tagespläne, 'rezepte' für Rezepte). "
                "Erstelle KEINE verschachtelte Wrapper-Objekte. "
                "Keine Erklärungen, kein Markdown, nur strukturiertes JSON im Tool-Call."
            )
            payload["tools"] = [{
                "name": "return_json",
                "description": "Gibt strukturierte JSON-Daten zurück",
                "input_schema": {
                    "type": "object",
                    "properties": {}
                }
            }]
            payload["tool_choice"] = {"type": "tool", "name": "return_json"}

        # API-Aufruf
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01"
            },
            json=payload,
            timeout=180
        )

        if response.status_code != 200:
            error_detail = response.text[:500]
            return None, f"API-Fehler {response.status_code}: {error_detail}"

        data = response.json()

        # Strategie 1: Tool-Call Response parsen
        if use_json_mode and 'content' in data:
            for item in data['content']:
                if isinstance(item, dict) and item.get('type') == 'tool_use':
                    tool_input = item.get('input', {})
                    if tool_input:
                        # Normalisiere die Response - extrahiere verschachtelte Strukturen
                        return normalize_response_structure(tool_input), None

        # Strategie 2: Text-Response parsen
        if 'content' in data and data['content']:
            response_text = data['content'][0].get('text', '')

            if not response_text:
                return None, "Leere Antwort von API erhalten"

            # Mehrfache Parsing-Versuche
            parsing_strategies = [
                lambda t: json.loads(t),  # Direkt
                lambda t: json.loads(bereinige_json(t)),  # Nach Bereinigung
                lambda t: json.loads(extract_json_object(t)),  # Extrahiere größtes JSON
                lambda t: json.loads(fix_common_json_errors(bereinige_json(t)))  # Repariere häufige Fehler
            ]

            last_error = None
            for i, strategy in enumerate(parsing_strategies, 1):
                try:
                    parsed = strategy(response_text)
                    if parsed and isinstance(parsed, dict):
                        # Normalisiere die Struktur
                        return normalize_response_structure(parsed), None
                except json.JSONDecodeError as e:
                    last_error = e
                    continue
                except Exception as e:
                    last_error = e
                    continue

            # Alle Strategien fehlgeschlagen
            error_msg = f"JSON-Parsing fehlgeschlagen nach {len(parsing_strategies)} Versuchen. "
            error_msg += f"Letzter Fehler: {str(last_error)}"

            # Debug-Info (erste und letzte 200 Zeichen)
            debug_preview = response_text[:200] + "..." + response_text[-200:]
            error_msg += f"\n\nAntwort-Vorschau: {debug_preview}"

            return None, error_msg

        return None, "Unerwartetes Response-Format"

    except requests.exceptions.Timeout:
        return None, "API-Timeout: Anfrage dauerte zu lange (>180s)"
    except requests.exceptions.RequestException as e:
        return None, f"Netzwerkfehler: {str(e)}"
    except Exception as e:
        return None, f"Unerwarteter Fehler: {str(e)}"


def extract_json_object(text):
    """Extrahiert das größte JSON-Objekt aus Text"""
    stack = []
    start_idx = None

    for i, char in enumerate(text):
        if char in '{[':
            if not stack:
                start_idx = i
            stack.append(char)
        elif char in '}]':
            if stack:
                expected = '{' if char == '}' else '['
                if stack[-1] == expected:
                    stack.pop()
                    if not stack and start_idx is not None:
                        return text[start_idx:i+1]

    return text


def fix_common_json_errors(text):
    """Repariert häufige JSON-Fehler"""
    # Füge fehlende Kommata zwischen Objekten ein
    patterns = [
        # Nach String-Wert vor neuem Key
        (r'("(?:[^"\\]|\\.)*")\s*\n\s*(")', r'\1,\n\2'),
        # Nach Zahl vor neuem Key
        (r'(\d+)\s*\n\s*(")', r'\1,\n\2'),
        # Nach Boolean vor neuem Key
        (r'(true|false)\s*\n\s*(")', r'\1,\n\2'),
        # Nach geschlossener Klammer vor neuem Key
        (r'([}\]])\s*\n\s*(")', r'\1,\n\2'),
    ]

    for pattern, replacement in patterns:
        text = re.sub(pattern, replacement, text)

    return text

def generiere_speiseplan_inkrementell(wochen, menulinien, menu_namen, api_key, progress_callback=None):
    """
    Generiert Speiseplan inkrementell (Tag für Tag) um Timeouts zu vermeiden

    Args:
        wochen: Anzahl der Wochen
        menulinien: Anzahl der Menülinien
        menu_namen: Liste der Menünamen
        api_key: API-Schlüssel
        progress_callback: Optional - Funktion für Fortschrittsanzeige

    Returns:
        Tuple von (speiseplan_data, error_message)
    """
    import time

    WOCHENTAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]

    alle_wochen = []
    gesamt_tage = wochen * 7
    aktueller_tag = 0

    # Generiere Woche für Woche
    for woche_nr in range(1, wochen + 1):
        tage_daten = []

        # Generiere jeden Tag einzeln
        for tag_name in WOCHENTAGE:
            aktueller_tag += 1

            # Fortschrittsanzeige
            if progress_callback:
                progress_callback(
                    f"Generiere {tag_name}, Woche {woche_nr}... ({aktueller_tag}/{gesamt_tage} Tage)"
                )

            # Generiere Prompt für diesen Tag
            prompt = generiere_tages_prompt(tag_name, woche_nr, menulinien, menu_namen)

            # API-Aufruf für diesen einen Tag (mit mehreren Versuchen)
            max_retries = 3
            tag_data = None
            last_error = None

            for versuch in range(max_retries):
                tag_data, error = rufe_claude_api(prompt, api_key, max_tokens=8000, use_json_mode=True)

                if error:
                    last_error = error
                    if versuch < max_retries - 1:
                        wait_time = 2 * (versuch + 1)
                        if progress_callback:
                            progress_callback(f"⚠️ Fehler bei {tag_name}, Versuch {versuch + 1}/{max_retries}. Warte {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                    else:
                        return None, f"Fehler bei {tag_name}, Woche {woche_nr} nach {max_retries} Versuchen: {error}"

                # Validiere und repariere Struktur
                if tag_data:
                    # Prüfe Grundstruktur
                    if not isinstance(tag_data, dict):
                        last_error = f"tag_data ist kein Dictionary: {type(tag_data)}"
                        continue

                    # Versuche verschachtelte Strukturen zu extrahieren
                    # Manchmal gibt die API verschachtelte Responses zurück
                    if "menues" not in tag_data:
                        # Suche in verschachtelten Strukturen
                        for key in ["data", "result", "output", "tag", "day"]:
                            if key in tag_data and isinstance(tag_data[key], dict):
                                if "menues" in tag_data[key]:
                                    tag_data = tag_data[key]
                                    break

                    # Repariere fehlende Felder
                    if "tag" not in tag_data:
                        tag_data["tag"] = tag_name

                    if "menues" not in tag_data or not isinstance(tag_data.get("menues"), list):
                        # Erweiterte Debug-Informationen
                        debug_keys = list(tag_data.keys()) if isinstance(tag_data, dict) else []
                        last_error = f"Feld 'menues' fehlt oder ist keine Liste. Vorhandene Felder: {debug_keys}"

                        # Log die tatsächliche Struktur für Debugging
                        if progress_callback:
                            progress_callback(f"⚠️ Debug: API gab zurück: {json.dumps(tag_data, ensure_ascii=False)[:300]}...")

                        if versuch < max_retries - 1:
                            if progress_callback:
                                progress_callback(f"⚠️ Ungültige Struktur für {tag_name}, Versuch {versuch + 2}/{max_retries}...")
                            time.sleep(2)
                            continue
                        else:
                            # Letzte Rettungsversuch: Erstelle eine leere Struktur wenn gar nichts hilft
                            error_details = f"Ungültige Struktur für {tag_name}, Woche {woche_nr}\n"
                            error_details += f"Fehler: {last_error}\n\n"
                            error_details += "Erhaltene Daten-Struktur:\n"
                            error_details += json.dumps(tag_data, indent=2, ensure_ascii=False)[:1000]
                            return None, error_details

                    # Stelle sicher, dass wir die richtige Anzahl Menüs haben
                    anzahl_menues = len(tag_data.get("menues", []))
                    if anzahl_menues != menulinien:
                        if progress_callback:
                            progress_callback(f"⚠️ {tag_name}: Erwartete {menulinien} Menüs, erhielt {anzahl_menues}")

                        # Versuche zu reparieren
                        menues = tag_data["menues"]
                        if anzahl_menues > menulinien:
                            # Zu viele Menüs: Kürzen
                            tag_data["menues"] = menues[:menulinien]
                        elif anzahl_menues < menulinien and anzahl_menues > 0:
                            # Zu wenige Menüs: Dupliziere das letzte
                            while len(tag_data["menues"]) < menulinien:
                                dupliziertes_menu = dict(menues[-1])
                                idx = len(tag_data["menues"])
                                if idx < len(menu_namen):
                                    dupliziertes_menu["menuName"] = menu_namen[idx]
                                tag_data["menues"].append(dupliziertes_menu)

                            st.info(f"ℹ️ {tag_name}: Menüanzahl angepasst auf {menulinien}")
                        elif anzahl_menues == 0:
                            # Keine Menüs: Fehler
                            last_error = "Keine Menüs in der Antwort gefunden"
                            if versuch < max_retries - 1:
                                continue
                            else:
                                return None, f"Keine Menüs für {tag_name}, Woche {woche_nr} generiert"

                    # Validiere jedes Menü
                    for idx, menu in enumerate(tag_data["menues"], 1):
                        if not isinstance(menu, dict):
                            last_error = f"Menü {idx} ist kein Dictionary"
                            continue

                        # Prüfe Pflichtfelder
                        required = ["menuName", "fruehstueck", "mittagessen", "abendessen"]
                        missing = [f for f in required if f not in menu]
                        if missing:
                            last_error = f"Menü {idx}: Fehlende Felder: {', '.join(missing)}"
                            continue

                        # Prüfe Mittagessen-Struktur
                        if "mittagessen" in menu and isinstance(menu["mittagessen"], dict):
                            mittag = menu["mittagessen"]
                            if "hauptgericht" not in mittag:
                                last_error = f"Menü {idx}: Hauptgericht fehlt"
                                continue
                            if "beilagen" not in mittag or not isinstance(mittag["beilagen"], list):
                                # Setze leere Liste wenn fehlend
                                mittag["beilagen"] = []
                            if len(mittag["beilagen"]) < 2:
                                st.warning(f"⚠️ {tag_name}, Menü {idx}: Nur {len(mittag['beilagen'])} Beilagen (empfohlen: mindestens 2)")

                    # Wenn wir hier angekommen sind, ist die Struktur valide
                    tage_daten.append(tag_data)
                    break
                else:
                    last_error = "Keine Daten von API erhalten"
                    if versuch < max_retries - 1:
                        if progress_callback:
                            progress_callback(f"⚠️ Keine Daten für {tag_name}, Versuch {versuch + 2}/{max_retries}...")
                        time.sleep(2)
                        continue
                    else:
                        return None, f"Keine Daten für {tag_name}, Woche {woche_nr} nach {max_retries} Versuchen"

            # Wenn nach allen Versuchen immer noch kein valider Tag
            if not tag_data or tag_data not in tage_daten:
                debug_info = f"Letzter Fehler: {last_error}"
                if tag_data:
                    debug_info += f"\n\nErhaltene Daten-Struktur: {json.dumps(tag_data, indent=2, ensure_ascii=False)[:500]}..."
                return None, f"Ungültige Struktur für {tag_name}, Woche {woche_nr}\n\n{debug_info}"

            # Kleine Pause zwischen Anfragen um Rate-Limits zu vermeiden
            time.sleep(0.5)

        # Füge Woche hinzu
        wochen_data = {
            "woche": woche_nr,
            "tage": tage_daten
        }
        alle_wochen.append(wochen_data)

    # Erstelle finalen Speiseplan
    speiseplan = {
        "speiseplan": {
            "wochen": alle_wochen,
            "menuLinien": menulinien,
            "menuNamen": menu_namen
        }
    }

    return speiseplan, None


def erstelle_speiseplan_pdf(speiseplan):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=20*mm, leftMargin=20*mm,
                          topMargin=20*mm, bottomMargin=20*mm)
    
    elements = []
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#d97706'),
        spaceAfter=30,
        alignment=TA_CENTER
    )
    
    elements.append(Paragraph("Speiseplan", title_style))
    elements.append(Paragraph("Gemeinschaftsverpflegung", styles['Normal']))
    elements.append(Spacer(1, 20))
    
    for woche in speiseplan['speiseplan']['wochen']:
        woche_style = ParagraphStyle('Woche', parent=styles['Heading2'], fontSize=16, 
                                    textColor=colors.HexColor('#d97706'))
        elements.append(Paragraph(f"Woche {woche['woche']}", woche_style))
        elements.append(Spacer(1, 10))
        
        for tag in woche['tage']:
            tag_style = ParagraphStyle('Tag', parent=styles['Heading3'], fontSize=14)
            elements.append(Paragraph(tag['tag'], tag_style))
            elements.append(Spacer(1, 5))
            
            for menu in tag['menues']:
                data = [[Paragraph(f"<b>{menu['menuName']}</b>", styles['Normal'])]]
                
                hauptgericht = menu['mittagessen']['hauptgericht']
                beilagen = menu['mittagessen'].get('beilagen', [])
                beilagen_text = f"mit {', '.join(beilagen)}" if beilagen else ""
                
                data.append([Paragraph(f"{hauptgericht} {beilagen_text}", styles['Normal'])])
                
                t = Table(data, colWidths=[250*mm])
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#fff5f0')),
                    ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 10),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                    ('TOPPADDING', (0, 0), (-1, -1), 8),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
                ]))
                elements.append(t)
                elements.append(Spacer(1, 5))
            
            elements.append(Spacer(1, 10))
        
        elements.append(PageBreak())
    
    doc.build(elements)
    buffer.seek(0)
    return buffer

def erstelle_rezept_pdf(rezept):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=20*mm, leftMargin=20*mm,
                          topMargin=20*mm, bottomMargin=20*mm)
    
    elements = []
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=18, 
                                textColor=colors.HexColor('#d97706'))
    
    elements.append(Paragraph(rezept['name'], title_style))
    elements.append(Spacer(1, 10))
    elements.append(Paragraph(f"{rezept['portionen']} Portionen | {rezept['menu']} | {rezept['tag']}, Woche {rezept['woche']}", 
                             styles['Normal']))
    elements.append(Spacer(1, 5))
    elements.append(Paragraph(f"Vorbereitung: {rezept['zeiten']['vorbereitung']} | Garzeit: {rezept['zeiten']['garzeit']}", 
                             styles['Normal']))
    elements.append(Spacer(1, 15))
    
    # Zutaten
    elements.append(Paragraph("<b>Zutaten</b>", styles['Heading2']))
    for zutat in rezept['zutaten']:
        elements.append(Paragraph(f"• {zutat['menge']} {zutat['name']}", styles['Normal']))
    elements.append(Spacer(1, 15))
    
    # Zubereitung
    elements.append(Paragraph("<b>Zubereitung</b>", styles['Heading2']))
    for i, schritt in enumerate(rezept['zubereitung'], 1):
        elements.append(Paragraph(f"<b>Schritt {i}:</b> {schritt}", styles['Normal']))
        elements.append(Spacer(1, 5))
    elements.append(Spacer(1, 15))
    
    # Nährwerte
    elements.append(Paragraph("<b>Nährwerte pro Portion</b>", styles['Heading2']))
    naehr = rezept['naehrwerte']
    elements.append(Paragraph(
        f"{naehr['kalorien']} | Protein: {naehr['protein']} | Fett: {naehr['fett']} | KH: {naehr['kohlenhydrate']} | Ballaststoffe: {naehr['ballaststoffe']}", 
        styles['Normal']))
    
    if rezept.get('allergene'):
        elements.append(Spacer(1, 10))
        elements.append(Paragraph(f"<b>Allergene:</b> {', '.join(rezept['allergene'])}", styles['Normal']))
    
    if rezept.get('tipps'):
        elements.append(Spacer(1, 10))
        elements.append(Paragraph("<b>Tipps für die Großküche</b>", styles['Heading2']))
        for tipp in rezept['tipps']:
            elements.append(Paragraph(f"• {tipp}", styles['Normal']))
    
    doc.build(elements)
    buffer.seek(0)
    return buffer

def erstelle_alle_rezepte_pdf(rezepte_data):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=20*mm, leftMargin=20*mm,
                          topMargin=20*mm, bottomMargin=20*mm)
    
    elements = []
    styles = getSampleStyleSheet()
    
    for i, rezept in enumerate(rezepte_data['rezepte']):
        if i > 0:
            elements.append(PageBreak())
        
        title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=18, 
                                    textColor=colors.HexColor('#d97706'))
        
        elements.append(Paragraph(rezept['name'], title_style))
        elements.append(Spacer(1, 10))
        elements.append(Paragraph(f"{rezept['portionen']} Portionen | {rezept['menu']}", styles['Normal']))
        elements.append(Spacer(1, 5))
        elements.append(Paragraph(f"Vorbereitung: {rezept['zeiten']['vorbereitung']} | Garzeit: {rezept['zeiten']['garzeit']}", 
                                 styles['Normal']))
        elements.append(Spacer(1, 15))
        
        elements.append(Paragraph("<b>Zutaten</b>", styles['Heading2']))
        for zutat in rezept['zutaten']:
            elements.append(Paragraph(f"• {zutat['menge']} {zutat['name']}", styles['Normal']))
        elements.append(Spacer(1, 15))
        
        elements.append(Paragraph("<b>Zubereitung</b>", styles['Heading2']))
        for j, schritt in enumerate(rezept['zubereitung'], 1):
            elements.append(Paragraph(f"<b>{j}.</b> {schritt}", styles['Normal']))
            elements.append(Spacer(1, 5))
        elements.append(Spacer(1, 15))
        
        elements.append(Paragraph("<b>Nährwerte pro Portion</b>", styles['Heading2']))
        naehr = rezept['naehrwerte']
        elements.append(Paragraph(
            f"{naehr['kalorien']} | Protein: {naehr['protein']} | Fett: {naehr['fett']} | KH: {naehr['kohlenhydrate']}", 
            styles['Normal']))
    
    doc.build(elements)
    buffer.seek(0)
    return buffer

# Hauptbereich
if not api_key:
    st.warning("⚠️ Bitte geben Sie Ihren Claude API-Key in der Sidebar ein.")
    st.info("Sie können einen API-Key unter https://console.anthropic.com/ erstellen.")
else:
    if st.sidebar.button("🚀 Speiseplan generieren & prüfen", type="primary", use_container_width=True):
        # Container für Fortschrittsanzeige
        progress_placeholder = st.empty()
        status_placeholder = st.empty()

        def zeige_fortschritt(nachricht):
            """Callback für Fortschrittsanzeige"""
            status_placeholder.info(f"🔄 {nachricht}")

        with st.spinner("⏳ Speiseplan wird erstellt (Tag für Tag)..."):
            # Verwende inkrementelle Generierung um Timeouts zu vermeiden
            speiseplan_data, error = generiere_speiseplan_inkrementell(
                wochen,
                menulinien,
                menu_namen,
                api_key,
                progress_callback=zeige_fortschritt
            )

            # Lösche Fortschrittsanzeige
            status_placeholder.empty()

            if error:
                st.error(f"❌ Fehler beim Erstellen des Speiseplans")

                # Zeige Fehlerdetails
                st.markdown(f"**Fehlerdetails:**")
                st.code(error, language="text")

                # Debug-Informationen in Expander
                with st.expander("🔍 Debug-Informationen und Lösungen"):
                    st.markdown("""
                    **Mögliche Ursachen:**
                    1. **Ungültige API-Antwort**: Die KI hat keine valide JSON-Struktur zurückgegeben
                    2. **API-Zeitüberschreitung**: Die Anfrage hat zu lange gedauert
                    3. **Rate-Limiting**: Zu viele Anfragen in kurzer Zeit
                    4. **Netzwerkprobleme**: Verbindungsfehler zur API

                    **Empfohlene Lösungen:**
                    - ✅ **Versuchen Sie es erneut**: Manchmal hilft ein zweiter Versuch
                    - 📉 **Reduzieren Sie die Komplexität**:
                      - Weniger Wochen (z.B. 1 statt 2)
                      - Weniger Menülinien (z.B. 2 statt 3)
                    - ⏱️ **Warten Sie kurz**: Bei Rate-Limiting 1-2 Minuten warten
                    - 🔑 **Prüfen Sie Ihren API-Key**: Stellen Sie sicher, dass er gültig ist
                    - 🌐 **Prüfen Sie Ihre Internetverbindung**

                    **Technische Details:**
                    Das System versucht automatisch 3x jeden Tag zu generieren und repariert
                    kleinere Strukturfehler automatisch. Wenn der Fehler weiterhin besteht,
                    könnte ein grundlegendes Problem mit der API-Kommunikation vorliegen.
                    """)

                    # Zeige letzte Konfiguration
                    st.divider()
                    st.markdown("**Ihre Konfiguration:**")
                    st.write(f"- Wochen: {wochen}")
                    st.write(f"- Menülinien: {menulinien}")
                    st.write(f"- Menü-Namen: {', '.join(menu_namen)}")

                    # Quick-Actions
                    st.divider()
                    st.markdown("**Schnellaktionen:**")
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("🔄 Mit 1 Woche erneut versuchen", key="retry_1week"):
                            st.info("Bitte setzen Sie die Wochenanzahl auf 1 in der Sidebar und klicken Sie erneut auf 'Speiseplan generieren'")
                    with col2:
                        if st.button("📋 Nur 1 Menülinie versuchen", key="retry_1menu"):
                            st.info("Bitte setzen Sie die Menülinien auf 1 in der Sidebar und klicken Sie erneut auf 'Speiseplan generieren'")
            else:
                st.session_state['speiseplan'] = speiseplan_data
                st.success("✅ Speiseplan erfolgreich erstellt!")

                # Rezepte in Batches generieren
                rezept_status = st.empty()
                def zeige_rezept_fortschritt(nachricht):
                    rezept_status.info(f"📖 {nachricht}")

                with st.spinner("📖 Rezepte werden erstellt (in Batches)..."):
                    rezepte_data, error2 = generiere_rezepte_batch(
                        speiseplan_data,
                        api_key,
                        batch_size=7,  # 7 Rezepte pro Batch (1 Tag)
                        progress_callback=zeige_rezept_fortschritt
                    )

                    rezept_status.empty()

                    if error2:
                        st.warning(f"⚠️ Speiseplan erstellt, aber Rezepte fehlgeschlagen: {error2}")
                        with st.expander("🔍 Rezept-Fehler Details"):
                            st.code(error2, language="text")
                        st.session_state['rezepte'] = None
                    else:
                        st.session_state['rezepte'] = rezepte_data
                        st.success(f"✅ {len(rezepte_data['rezepte'])} Rezepte erfolgreich erstellt!")

                st.balloons()

# Anzeige der Ergebnisse
if 'speiseplan' in st.session_state and st.session_state['speiseplan']:
    tab1, tab2 = st.tabs(["📋 Speiseplan", "📖 Rezepte"])
    
    with tab1:
        st.header("Speiseplan")
        
        # PDF-Export Button
        pdf_buffer = erstelle_speiseplan_pdf(st.session_state['speiseplan'])
        st.download_button(
            label="📄 Speiseplan als PDF herunterladen (DIN A4 quer)",
            data=pdf_buffer,
            file_name="Speiseplan.pdf",
            mime="application/pdf",
            use_container_width=True
        )
        
        st.divider()
        
        # Speiseplan anzeigen
        for woche in st.session_state['speiseplan']['speiseplan']['wochen']:
            st.subheader(f"Woche {woche['woche']}")
            
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
                        
                        with col2:
                            st.markdown("**🍽️ Mittagessen**")
                            st.write(f"**{menu['mittagessen']['hauptgericht']}**")
                            if menu['mittagessen'].get('beilagen'):
                                st.caption(f"🥔 Beilagen: {', '.join(menu['mittagessen']['beilagen'])}")
                            if menu['mittagessen'].get('naehrwerte'):
                                st.caption(f"📊 {menu['mittagessen']['naehrwerte']['kalorien']} | Protein: {menu['mittagessen']['naehrwerte']['protein']}")
                        
                        with col3:
                            st.markdown("**🌙 Abendessen**")
                            st.write(menu['abendessen']['hauptgericht'])
                            if menu['abendessen'].get('beilagen'):
                                st.caption(f"mit {', '.join(menu['abendessen']['beilagen'])}")
                
                st.divider()
    
    with tab2:
        if 'rezepte' in st.session_state and st.session_state['rezepte']:
            st.header("Detaillierte Rezepte")
            
            # Alle Rezepte PDF-Export
            alle_rezepte_pdf = erstelle_alle_rezepte_pdf(st.session_state['rezepte'])
            st.download_button(
                label="📚 Alle Rezepte als PDF herunterladen",
                data=alle_rezepte_pdf,
                file_name="Alle_Rezepte.pdf",
                mime="application/pdf",
                use_container_width=True
            )
            
            st.divider()
            
            for rezept in st.session_state['rezepte']['rezepte']:
                with st.expander(f"**{rezept['name']}** ({rezept['menu']})", expanded=False):
                    col1, col2 = st.columns([3, 1])
                    
                    with col1:
                        st.markdown(f"**{rezept['portionen']} Portionen** | {rezept['tag']}, Woche {rezept['woche']}")
                        st.caption(f"⏱️ Vorbereitung: {rezept['zeiten']['vorbereitung']} | Garzeit: {rezept['zeiten']['garzeit']}")
                    
                    with col2:
                        rezept_pdf = erstelle_rezept_pdf(rezept)
                        st.download_button(
                            label="📄 Als PDF",
                            data=rezept_pdf,
                            file_name=f"Rezept_{rezept['name'].replace(' ', '_')}.pdf",
                            mime="application/pdf",
                            key=f"pdf_{rezept['name']}"
                        )
                    
                    st.markdown("### Zutaten")
                    for zutat in rezept['zutaten']:
                        st.write(f"• **{zutat['menge']}** {zutat['name']}")
                    
                    st.markdown("### Zubereitung")
                    for i, schritt in enumerate(rezept['zubereitung'], 1):
                        st.info(f"**Schritt {i}:** {schritt}")
                    
                    st.markdown("### Nährwerte pro Portion")
                    n = rezept['naehrwerte']
                    cols = st.columns(5)
                    cols[0].metric("Kalorien", n['kalorien'])
                    cols[1].metric("Protein", n['protein'])
                    cols[2].metric("Fett", n['fett'])
                    cols[3].metric("KH", n['kohlenhydrate'])
                    cols[4].metric("Ballaststoffe", n['ballaststoffe'])
                    
                    if rezept.get('tipps'):
                        st.markdown("### 💡 Tipps für die Großküche")
                        for tipp in rezept['tipps']:
                            st.success(tipp)
        else:
            st.info("Rezepte werden nach der Speiseplan-Generierung hier angezeigt.")
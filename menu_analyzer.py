"""
Modul für die Analyse von Speiseplänen aus PDFs und Webseiten
"""

import PyPDF2
import requests
from bs4 import BeautifulSoup
from io import BytesIO
import re


def extrahiere_text_aus_pdf(pdf_file):
    """
    Extrahiert Text aus einer hochgeladenen PDF-Datei

    Args:
        pdf_file: Streamlit UploadedFile Objekt

    Returns:
        str: Extrahierter Text oder Fehlermeldung
    """
    try:
        # Erstelle BytesIO-Objekt aus der hochgeladenen Datei
        pdf_bytes = BytesIO(pdf_file.read())

        # PDF-Reader erstellen
        pdf_reader = PyPDF2.PdfReader(pdf_bytes)

        # Text aus allen Seiten extrahieren
        text_parts = []
        for page_num in range(len(pdf_reader.pages)):
            page = pdf_reader.pages[page_num]
            text = page.extract_text()
            if text:
                text_parts.append(f"=== Seite {page_num + 1} ===\n{text}")

        full_text = "\n\n".join(text_parts)

        if not full_text.strip():
            return None, "Fehler: Konnte keinen Text aus dem PDF extrahieren. Möglicherweise ist es ein Bild-PDF."

        return full_text, None

    except Exception as e:
        return None, f"Fehler beim Lesen der PDF-Datei: {str(e)}"


def extrahiere_text_aus_url(url):
    """
    Lädt eine Webseite herunter und extrahiert den Text

    Args:
        url: URL der Webseite

    Returns:
        str: Extrahierter Text oder Fehlermeldung
    """
    try:
        # Validiere URL
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        # Webseite laden
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        # HTML parsen
        soup = BeautifulSoup(response.content, 'lxml')

        # Entferne Script- und Style-Elemente
        for script in soup(['script', 'style', 'nav', 'footer', 'header']):
            script.decompose()

        # Text extrahieren
        text = soup.get_text()

        # Bereinige Text (entferne übermäßige Leerzeichen)
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)

        if not text.strip():
            return None, "Fehler: Konnte keinen Text von der Webseite extrahieren."

        return text, None

    except requests.exceptions.Timeout:
        return None, "Fehler: Zeitüberschreitung beim Laden der Webseite."
    except requests.exceptions.RequestException as e:
        return None, f"Fehler beim Laden der Webseite: {str(e)}"
    except Exception as e:
        return None, f"Unerwarteter Fehler: {str(e)}"


def analysiere_speiseplan_text(text, api_key, rufe_claude_api_func, tool_directive):
    """
    Analysiert einen Text mit Claude API und extrahiert Speiseplan-Informationen

    Args:
        text: Der zu analysierende Text
        api_key: API-Schlüssel für Claude
        rufe_claude_api_func: Die rufe_claude_api Funktion aus streamlit_app.py
        tool_directive: TOOL_DIRECTIVE aus prompts.py

    Returns:
        dict: Analyseergebnisse oder Fehlermeldung
    """

    # Kürze Text wenn zu lang (max ca. 15000 Zeichen für den Prompt)
    max_text_length = 12000
    if len(text) > max_text_length:
        text = text[:max_text_length] + "\n\n[Text gekürzt...]"

    prompt = f"""Du bist ein diätischer Küchenmeister mit 25 Jahren Berufserfahrung in der Gemeinschaftsverpflegung.
Du hast in Krankenhäusern, Senioreneinrichtungen und Großküchen gearbeitet und bist spezialisiert auf die Analyse von Speiseplänen.
Deine Aufgabe ist es, Speisepläne zu analysieren und klare, praktische Anweisungen für andere diätische Küchenmeister zu erstellen.

{tool_directive}

DEINE EXPERTISE UMFASST:
- Nährwertberechnung und -optimierung
- Allergenkennzeichnung und Unverträglichkeiten
- Verschiedene Kostformen (Vollkost, leichte Kost, pürierte Kost, Diäten)
- Saisonalität und Wirtschaftlichkeit
- Hygiene- und HACCP-Standards
- Menüplanung für verschiedene Zielgruppen

TEXT ZUR ANALYSE:
{text}

DEINE AUFGABEN ALS ERFAHRENER KÜCHENMEISTER:

1. SPEISEPLAN IDENTIFIZIEREN UND STRUKTURIEREN
   - Extrahiere alle Gerichte, Menüs und Mahlzeiten
   - Erkenne die zeitliche Struktur (Wochentage, Datum)
   - Identifiziere Menülinien und deren Bezeichnungen
   - Erfasse Hauptgerichte, Beilagen, Desserts, Vorspeisen

2. FACHLICHE BEWERTUNG
   - Bewerte die Ausgewogenheit der Menüs
   - Prüfe auf Abwechslung und Vielfalt
   - Erkenne potenzielle Nährwertdefizite oder -überschüsse
   - Identifiziere allergene und kritische Zutaten
   - Beurteile die Eignung für verschiedene Kostformen

3. PRAKTISCHE HINWEISE FÜR KOLLEGEN
   - Gib konkrete Umsetzungshinweise für die Küche
   - Weise auf besondere Zubereitungsanforderungen hin
   - Empfehle Optimierungen und Alternativen
   - Nenne kritische Punkte bei der Zubereitung
   - Gib Tipps zur Kostenoptimierung

4. QUALITÄTSSICHERUNG
   - Prüfe auf Vollständigkeit der Informationen
   - Weise auf fehlende Angaben hin (Allergene, Nährwerte)
   - Gib Empfehlungen zur Verbesserung der Speiseplan-Dokumentation

ANTWORT-FORMAT - FACHBERICHT FÜR KOLLEGEN:

Erstelle ein strukturiertes JSON-Objekt mit folgenden Abschnitten:

{{
  "gefunden": true,
  "anzahl_tage": 5,
  "anzahl_gerichte": 12,
  "anzahl_menulinien": 2,
  "struktur": "Detaillierte Beschreibung der Speiseplan-Struktur (z.B. 'Wochenspeiseplan mit 2 Menülinien, Montag-Freitag')",

  "speiseplan": [
    {{
      "tag": "Montag, 20.11.2025",
      "menues": [
        {{
          "name": "Menü 1 / Vollkost",
          "hauptgericht": "Schweinebraten",
          "beilagen": ["Kartoffelknödel", "Rotkohl"],
          "zusatzinfo": "Mit Bratensauce, ca. 650 kcal",
          "allergene": "Gluten, Sellerie",
          "eignung_kostformen": "Vollkost geeignet"
        }}
      ]
    }}
  ],

  "fachliche_bewertung": {{
    "ausgewogenheit": "Bewertung der Nährstoffbalance",
    "abwechslung": "Beurteilung der Menüvielfalt",
    "staerken": ["Positive Aspekt 1", "Positive Aspekt 2"],
    "schwaechen": ["Verbesserungspunkt 1", "Verbesserungspunkt 2"],
    "naehrwert_beurteilung": "Einschätzung der Nährwerte",
    "allergene_hinweise": "Kritische Allergene und Hinweise"
  }},

  "anweisungen_fuer_kollegen": [
    "WICHTIG: Konkrete Anweisung 1 für die Umsetzung in der Küche",
    "TIPP: Praktischer Hinweis 2 zur Zubereitung",
    "ACHTUNG: Kritischer Punkt 3 bei der Zubereitung",
    "ALTERNATIVE: Vorschlag 4 für Optimierung"
  ],

  "optimierungsvorschlaege": [
    {{
      "bereich": "Nährwerte / Abwechslung / Kosten / etc.",
      "problem": "Konkrete Beschreibung des Problems",
      "empfehlung": "Praktische Lösung für die Küche",
      "prioritaet": "hoch / mittel / niedrig"
    }}
  ],

  "zusammenfassung": "AUSFÜHRLICHE professionelle Zusammenfassung als erfahrener Küchenmeister. Beschreibe den Speiseplan, gib eine Gesamtbewertung und die wichtigsten Empfehlungen für deine Kollegen. Schreibe wie ein Mentor, der sein Wissen weitergibt.",

  "qualitaet_dokumentation": {{
    "vollstaendigkeit": "Bewertung der Dokumentation",
    "fehlende_angaben": ["Was fehlt im Speiseplan"],
    "verbesserungshinweise": ["Wie kann die Dokumentation verbessert werden"]
  }}
}}

WICHTIG:
- Schreibe professionell aber kollegial, wie ein erfahrener Kollege der sein Wissen teilt
- Sei konkret und praxisorientiert
- Gib umsetzbare Handlungsempfehlungen
- Nutze deine 25 Jahre Erfahrung in der Gemeinschaftsverpflegung
- Denke an die Bedürfnisse der Kollegen in der Großküche"""

    # Rufe Claude API auf
    result, error = rufe_claude_api_func(prompt, api_key, max_tokens=4000)

    if error:
        return None, error

    if not result:
        return None, "Keine Antwort von der API erhalten"

    return result, None


def formatiere_analyse_ergebnis(analyse_data):
    """
    Formatiert das Analyse-Ergebnis als professionellen Fachbericht

    Args:
        analyse_data: Dictionary mit Analyseergebnissen

    Returns:
        str: Formatierter professioneller Bericht
    """
    if not analyse_data:
        return "Keine Daten verfügbar"

    text_parts = []

    # Header
    text_parts.append("=" * 80)
    text_parts.append("FACHLICHE SPEISEPLAN-ANALYSE")
    text_parts.append("Erstellt von: Diätischer Küchenmeister (25 Jahre Erfahrung)")
    text_parts.append("=" * 80)
    text_parts.append("")

    # Übersicht
    if analyse_data.get('gefunden'):
        text_parts.append("📊 ÜBERSICHT:")
        text_parts.append(f"   ✅ Speiseplan erfolgreich identifiziert")
        text_parts.append(f"   📅 Anzahl Tage: {analyse_data.get('anzahl_tage', 'N/A')}")
        text_parts.append(f"   🍽️  Anzahl Gerichte: {analyse_data.get('anzahl_gerichte', 'N/A')}")
        if analyse_data.get('anzahl_menulinien'):
            text_parts.append(f"   📋 Anzahl Menülinien: {analyse_data.get('anzahl_menulinien')}")
        text_parts.append(f"   📝 Struktur: {analyse_data.get('struktur', 'N/A')}")
    else:
        text_parts.append("❌ Kein Speiseplan gefunden")

    text_parts.append("")
    text_parts.append("-" * 80)

    # Professionelle Zusammenfassung
    if analyse_data.get('zusammenfassung'):
        text_parts.append("💼 FACHLICHE ZUSAMMENFASSUNG:")
        text_parts.append("")
        text_parts.append(analyse_data['zusammenfassung'])
        text_parts.append("")
        text_parts.append("-" * 80)

    # Detaillierter Speiseplan
    if analyse_data.get('speiseplan'):
        text_parts.append("📋 DETAILLIERTER SPEISEPLAN:")
        text_parts.append("")

        for tag_info in analyse_data['speiseplan']:
            text_parts.append(f"📅 {tag_info.get('tag', 'N/A')}")
            text_parts.append("")

            for menu in tag_info.get('menues', []):
                text_parts.append(f"  🍽️  {menu.get('name', 'N/A')}")
                text_parts.append(f"     Hauptgericht: {menu.get('hauptgericht', 'N/A')}")

                if menu.get('beilagen'):
                    beilagen_text = ", ".join(menu['beilagen'])
                    text_parts.append(f"     Beilagen: {beilagen_text}")

                if menu.get('zusatzinfo'):
                    text_parts.append(f"     ℹ️  Info: {menu['zusatzinfo']}")

                if menu.get('allergene'):
                    text_parts.append(f"     ⚠️  Allergene: {menu['allergene']}")

                if menu.get('eignung_kostformen'):
                    text_parts.append(f"     ✓ Kostform: {menu['eignung_kostformen']}")

                text_parts.append("")

            text_parts.append("-" * 80)

    # Fachliche Bewertung
    if analyse_data.get('fachliche_bewertung'):
        text_parts.append("🎯 FACHLICHE BEWERTUNG:")
        text_parts.append("")
        bewertung = analyse_data['fachliche_bewertung']

        if bewertung.get('ausgewogenheit'):
            text_parts.append(f"⚖️  Ausgewogenheit: {bewertung['ausgewogenheit']}")
        if bewertung.get('abwechslung'):
            text_parts.append(f"🔄 Abwechslung: {bewertung['abwechslung']}")

        if bewertung.get('staerken'):
            text_parts.append("")
            text_parts.append("✅ STÄRKEN:")
            for staerke in bewertung['staerken']:
                text_parts.append(f"   • {staerke}")

        if bewertung.get('schwaechen'):
            text_parts.append("")
            text_parts.append("⚠️  VERBESSERUNGSPOTENZIAL:")
            for schwaeche in bewertung['schwaechen']:
                text_parts.append(f"   • {schwaeche}")

        if bewertung.get('naehrwert_beurteilung'):
            text_parts.append("")
            text_parts.append(f"📊 Nährwerte: {bewertung['naehrwert_beurteilung']}")

        if bewertung.get('allergene_hinweise'):
            text_parts.append(f"⚠️  Allergene: {bewertung['allergene_hinweise']}")

        text_parts.append("")
        text_parts.append("-" * 80)

    # Anweisungen für Kollegen
    if analyse_data.get('anweisungen_fuer_kollegen'):
        text_parts.append("👨‍🍳 ANWEISUNGEN FÜR KOLLEGEN IN DER KÜCHE:")
        text_parts.append("")
        for i, anweisung in enumerate(analyse_data['anweisungen_fuer_kollegen'], 1):
            text_parts.append(f"{i}. {anweisung}")
        text_parts.append("")
        text_parts.append("-" * 80)

    # Optimierungsvorschläge
    if analyse_data.get('optimierungsvorschlaege'):
        text_parts.append("💡 OPTIMIERUNGSVORSCHLÄGE:")
        text_parts.append("")
        for i, vorschlag in enumerate(analyse_data['optimierungsvorschlaege'], 1):
            prioritaet_icon = "🔴" if vorschlag.get('prioritaet') == 'hoch' else "🟡" if vorschlag.get('prioritaet') == 'mittel' else "🟢"
            text_parts.append(f"{i}. {prioritaet_icon} {vorschlag.get('bereich', 'N/A')}")
            text_parts.append(f"   Problem: {vorschlag.get('problem', 'N/A')}")
            text_parts.append(f"   Empfehlung: {vorschlag.get('empfehlung', 'N/A')}")
            text_parts.append("")
        text_parts.append("-" * 80)

    # Qualität der Dokumentation
    if analyse_data.get('qualitaet_dokumentation'):
        text_parts.append("📝 QUALITÄT DER DOKUMENTATION:")
        text_parts.append("")
        qual = analyse_data['qualitaet_dokumentation']

        if qual.get('vollstaendigkeit'):
            text_parts.append(f"Vollständigkeit: {qual['vollstaendigkeit']}")

        if qual.get('fehlende_angaben'):
            text_parts.append("")
            text_parts.append("❌ Fehlende Angaben:")
            for fehlend in qual['fehlende_angaben']:
                text_parts.append(f"   • {fehlend}")

        if qual.get('verbesserungshinweise'):
            text_parts.append("")
            text_parts.append("💡 Verbesserungshinweise:")
            for hinweis in qual['verbesserungshinweise']:
                text_parts.append(f"   • {hinweis}")

        text_parts.append("")
        text_parts.append("-" * 80)

    text_parts.append("")
    text_parts.append("=" * 80)
    text_parts.append("Ende der fachlichen Analyse")
    text_parts.append("=" * 80)

    return "\n".join(text_parts)

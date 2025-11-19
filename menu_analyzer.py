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


def analysiere_speiseplan_text(text, api_key, rufe_claude_api_func):
    """
    Analysiert einen Text mit Claude API und extrahiert Speiseplan-Informationen

    Args:
        text: Der zu analysierende Text
        api_key: API-Schlüssel für Claude
        rufe_claude_api_func: Die rufe_claude_api Funktion aus streamlit_app.py

    Returns:
        dict: Analyseergebnisse oder Fehlermeldung
    """

    # Kürze Text wenn zu lang (max ca. 15000 Zeichen für den Prompt)
    max_text_length = 12000
    if len(text) > max_text_length:
        text = text[:max_text_length] + "\n\n[Text gekürzt...]"

    prompt = f"""Du bist ein Experte für die Analyse von Speiseplänen.

Analysiere den folgenden Text und extrahiere alle Informationen über Speisepläne, Menüs, Gerichte und Mahlzeiten.

TEXT:
{text}

AUFGABE:
1. Identifiziere alle Gerichte, Menüs und Speisepläne im Text
2. Extrahiere Informationen über:
   - Wochentage/Datum
   - Menübezeichnungen (z.B. Menü 1, Menü 2, vegetarisch, etc.)
   - Hauptgerichte
   - Beilagen
   - Desserts oder Vorspeisen (falls vorhanden)
   - Nährwerte (falls vorhanden)
   - Allergene (falls vorhanden)
   - Preise (falls vorhanden)

3. Strukturiere die Informationen übersichtlich

4. Gib eine textuelle Zusammenfassung der gefundenen Speisepläne aus

Antworte in folgendem JSON-Format:
{{
  "gefunden": true/false,
  "anzahl_tage": Anzahl der gefundenen Tage,
  "anzahl_gerichte": Anzahl der gefundenen Gerichte,
  "struktur": "Beschreibung der Speiseplan-Struktur",
  "speiseplan": [
    {{
      "tag": "Tag/Datum",
      "menues": [
        {{
          "name": "Menü-Bezeichnung",
          "hauptgericht": "Gericht",
          "beilagen": ["Beilage 1", "Beilage 2"],
          "zusatzinfo": "Weitere Infos falls vorhanden"
        }}
      ]
    }}
  ],
  "zusammenfassung": "Detaillierte textuelle Beschreibung der gefundenen Speisepläne",
  "besonderheiten": ["Besonderheit 1", "Besonderheit 2"],
  "hinweise": "Wichtige Hinweise zur Qualität der Extraktion"
}}

Sei gründlich und extrahiere alle verfügbaren Informationen!"""

    # Rufe Claude API auf
    result, error = rufe_claude_api_func(prompt, api_key, max_tokens=4000)

    if error:
        return None, error

    if not result:
        return None, "Keine Antwort von der API erhalten"

    return result, None


def formatiere_analyse_ergebnis(analyse_data):
    """
    Formatiert das Analyse-Ergebnis als lesbaren Text

    Args:
        analyse_data: Dictionary mit Analyseergebnissen

    Returns:
        str: Formatierter Text
    """
    if not analyse_data:
        return "Keine Daten verfügbar"

    text_parts = []

    # Header
    text_parts.append("=" * 80)
    text_parts.append("SPEISEPLAN-ANALYSE ERGEBNIS")
    text_parts.append("=" * 80)
    text_parts.append("")

    # Übersicht
    if analyse_data.get('gefunden'):
        text_parts.append(f"✅ Speiseplan gefunden!")
        text_parts.append(f"   Anzahl Tage: {analyse_data.get('anzahl_tage', 'N/A')}")
        text_parts.append(f"   Anzahl Gerichte: {analyse_data.get('anzahl_gerichte', 'N/A')}")
        text_parts.append(f"   Struktur: {analyse_data.get('struktur', 'N/A')}")
    else:
        text_parts.append("❌ Kein Speiseplan gefunden")

    text_parts.append("")
    text_parts.append("-" * 80)

    # Zusammenfassung
    if analyse_data.get('zusammenfassung'):
        text_parts.append("ZUSAMMENFASSUNG:")
        text_parts.append("")
        text_parts.append(analyse_data['zusammenfassung'])
        text_parts.append("")
        text_parts.append("-" * 80)

    # Detaillierter Speiseplan
    if analyse_data.get('speiseplan'):
        text_parts.append("DETAILLIERTER SPEISEPLAN:")
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
                    text_parts.append(f"     Info: {menu['zusatzinfo']}")

                text_parts.append("")

            text_parts.append("-" * 80)

    # Besonderheiten
    if analyse_data.get('besonderheiten'):
        text_parts.append("BESONDERHEITEN:")
        for besonderheit in analyse_data['besonderheiten']:
            text_parts.append(f"  • {besonderheit}")
        text_parts.append("")
        text_parts.append("-" * 80)

    # Hinweise
    if analyse_data.get('hinweise'):
        text_parts.append("HINWEISE:")
        text_parts.append(analyse_data['hinweise'])
        text_parts.append("")

    text_parts.append("=" * 80)

    return "\n".join(text_parts)

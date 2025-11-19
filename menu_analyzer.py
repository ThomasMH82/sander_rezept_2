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

    Verwendet den professionellen Analyse-Prompt aus prompts.py, der einen
    diätischen Küchenmeister mit 25 Jahren Erfahrung simuliert.

    Args:
        text: Der zu analysierende Text
        api_key: API-Schlüssel für Claude
        rufe_claude_api_func: Die rufe_claude_api Funktion aus streamlit_app.py

    Returns:
        dict: Analyseergebnisse oder Fehlermeldung
    """
    # Importiere den professionellen Analyse-Prompt
    from prompts import get_analyse_prompt

    # Erstelle den Prompt mit der optimierten Funktion
    prompt = get_analyse_prompt(text)

    # Rufe Claude API auf mit erhöhtem max_tokens für detaillierte Analyse
    result, error = rufe_claude_api_func(prompt, api_key, max_tokens=6000)

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
    text_parts.append("PROFESSIONELLE SPEISEPLAN-ANALYSE")
    text_parts.append("Erstellt von einem diätischen Küchenmeister")
    text_parts.append("=" * 80)
    text_parts.append("")

    # Übersicht
    if analyse_data.get('gefunden'):
        text_parts.append(f"✅ Speiseplan erfolgreich analysiert!")
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

    # FACHLICHE BEWERTUNG (NEU!)
    if analyse_data.get('fachliche_bewertung'):
        text_parts.append("FACHLICHE BEWERTUNG:")
        text_parts.append("")
        bewertung = analyse_data['fachliche_bewertung']

        if bewertung.get('gesamtnote'):
            text_parts.append(f"  Gesamtnote: {bewertung['gesamtnote'].upper()}")
            text_parts.append("")

        if bewertung.get('abwechslung'):
            text_parts.append(f"  • Abwechslung: {bewertung['abwechslung']}")
        if bewertung.get('ausgewogenheit'):
            text_parts.append(f"  • Ausgewogenheit: {bewertung['ausgewogenheit']}")
        if bewertung.get('seniorengerechtigkeit'):
            text_parts.append(f"  • Seniorengerechtigkeit: {bewertung['seniorengerechtigkeit']}")
        if bewertung.get('saisonalitaet'):
            text_parts.append(f"  • Saisonalität: {bewertung['saisonalitaet']}")

        text_parts.append("")
        text_parts.append("-" * 80)

    # EMPFEHLUNGEN FÜR KÜCHENMEISTER (NEU!)
    if analyse_data.get('empfehlungen_fuer_kuechenmeister'):
        text_parts.append("ANWEISUNGEN FÜR DIE KÜCHE:")
        text_parts.append("")
        for i, empfehlung in enumerate(analyse_data['empfehlungen_fuer_kuechenmeister'], 1):
            text_parts.append(f"  {i}. {empfehlung}")
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

    # VERBESSERUNGSVORSCHLÄGE
    if analyse_data.get('verbesserungsvorschlaege'):
        text_parts.append("VERBESSERUNGSVORSCHLÄGE:")
        text_parts.append("")
        for vorschlag in analyse_data['verbesserungsvorschlaege']:
            text_parts.append(f"  Bereich: {vorschlag.get('bereich', 'N/A')}")
            text_parts.append(f"  Problem: {vorschlag.get('problem', 'N/A')}")
            text_parts.append(f"  Empfehlung: {vorschlag.get('empfehlung', 'N/A')}")
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

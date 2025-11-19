import streamlit as st
import requests
import json
import re
from datetime import datetime
from io import BytesIO
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_CENTER, TA_LEFT

# WICHTIG: Importiere die optimierten Prompts!
from prompts import get_speiseplan_prompt, get_rezepte_prompt, get_pruefung_prompt, TOOL_DIRECTIVE

# Import für Menü-Analyse
from menu_analyzer import (
    extrahiere_text_aus_pdf,
    extrahiere_text_aus_url,
    analysiere_speiseplan_text,
    formatiere_analyse_ergebnis
)

st.set_page_config(page_title="Speiseplan-Generator", layout="wide", page_icon="👨‍🍳")

# ===================== KONFIGURATION =====================
API_BASE_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-sonnet-4-20250514"
API_TIMEOUT = 180

# ===================== API-FUNKTIONEN =====================

def rufe_claude_api(prompt, api_key, max_tokens=16000, max_retries=3):
    """
    Ruft die Claude API mit Tool-Use auf (return_json)
    Mit automatischem Retry bei Überlastung
    """
    if not api_key:
        return None, "Kein API-Key vorhanden"
    
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": API_VERSION
    }
    
    # Tool-Definition für JSON-Return
    tools = [{
        "name": "return_json",
        "description": "Gibt ein JSON-Objekt zurück",
        "input_schema": {
            "type": "object",
            "properties": {
                "input": {
                    "type": "object",
                    "description": "Das JSON-Objekt mit den Daten"
                }
            },
            "required": ["input"]
        }
    }]
    
    payload = {
        "model": DEFAULT_MODEL,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
        "tools": tools,
        "tool_choice": {"type": "tool", "name": "return_json"}
    }
    
    # Retry-Schleife mit Exponential Backoff
    import time
    for versuch in range(max_retries):
        try:
            response = requests.post(
                API_BASE_URL,
                headers=headers,
                json=payload,
                timeout=API_TIMEOUT
            )
            
            # Bei Erfolg: Weiter wie bisher
            if response.status_code == 200:
                break
            
            # Bei Überlastung (529) oder Rate Limit (429): Retry
            elif response.status_code in [429, 529]:
                wartezeit = (2 ** versuch) * 2  # Exponential: 2s, 4s, 8s
                if versuch < max_retries - 1:  # Nicht beim letzten Versuch
                    st.warning(f"⏳ API überlastet (Fehler {response.status_code}). Warte {wartezeit}s und versuche es erneut... (Versuch {versuch + 1}/{max_retries})")
                    time.sleep(wartezeit)
                    continue
                else:
                    return None, f"API überlastet nach {max_retries} Versuchen. Bitte später erneut versuchen."
            
            # Bei anderen Fehlern: Sofort abbrechen
            else:
                response.raise_for_status()
        
        except requests.exceptions.Timeout:
            if versuch < max_retries - 1:
                st.warning(f"⏳ Timeout. Versuche erneut... (Versuch {versuch + 1}/{max_retries})")
                time.sleep(2)
                continue
            return None, "API-Timeout - Anfrage dauerte zu lange"
        
        except requests.exceptions.RequestException as e:
            if versuch < max_retries - 1 and "529" in str(e):
                wartezeit = (2 ** versuch) * 2
                st.warning(f"⏳ API überlastet. Warte {wartezeit}s... (Versuch {versuch + 1}/{max_retries})")
                time.sleep(wartezeit)
                continue
            return None, f"API-Fehler: {str(e)}"
    
    # Nach erfolgreicher Response oder Fehler
    try:
        data = response.json()
        
        # Debug: Zeige Antwort-Struktur in Session State
        if 'debug_responses' not in st.session_state:
            st.session_state['debug_responses'] = []
        st.session_state['debug_responses'].append({
            'timestamp': str(datetime.now()),
            'has_content': 'content' in data,
            'content_blocks': len(data.get('content', [])) if 'content' in data else 0
        })
        
        # Extrahiere JSON aus Tool-Use Response
        if 'content' in data:
            for block in data['content']:
                if block.get('type') == 'tool_use' and block.get('name') == 'return_json':
                    # Versuche verschiedene Strukturen
                    try:
                        # Variante 1: block['input']['input']
                        if 'input' in block and isinstance(block['input'], dict) and 'input' in block['input']:
                            return block['input']['input'], None
                        # Variante 2: block['input'] ist direkt das Objekt
                        elif 'input' in block and isinstance(block['input'], dict):
                            return block['input'], None
                        else:
                            st.warning(f"⚠️ Unerwartete Tool-Response-Struktur: {list(block.keys())}")
                            # Speichere für Debug
                            st.session_state['last_tool_response'] = block
                    except KeyError as e:
                        return None, f"Tool-Response-Struktur-Fehler: {e}. Keys: {list(block.keys())}"
        
        # Fallback: Versuche Text-Content zu parsen
        if 'content' in data and len(data['content']) > 0:
            text_content = data['content'][0].get('text', '')
            if text_content:
                # Bereinige und parse JSON
                cleaned = bereinigeJSON(text_content)
                try:
                    return json.loads(cleaned), None
                except json.JSONDecodeError as e:
                    st.session_state['last_json_error'] = {
                        'error': str(e),
                        'text': text_content[:500]
                    }
                    return None, f"JSON-Parsing fehlgeschlagen: {e}"
        
        return None, "Keine gültige Antwort von API"
        
    except Exception as e:
        # Bessere Fehlerausgabe
        import traceback
        error_details = traceback.format_exc()
        st.session_state['last_exception'] = error_details
        return None, f"Unerwarteter Fehler: {str(e)}"


def bereinigeJSON(text):
    """Bereinigt JSON-Text von Markdown und anderen Artefakten"""
    # Entferne Markdown Code-Blöcke
    text = re.sub(r"```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = text.replace("```", "").strip()
    
    # Ersetze Smart Quotes
    replacements = {
        """: '"', """: '"', "„": '"',
        "'": "'", "‚": "'", "'": "'",
        "–": "-", "—": "-"
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    
    # Entferne trailing commas
    text = re.sub(r",\s*(?=[}\]])", "", text)
    
    return text.strip()


# ===================== SPEISEPLAN-GENERIERUNG =====================

def generiere_speiseplan(wochen, menulinien, menu_namen, api_key, produktliste=None, produktlisten_prozent=0):
    """
    Generiert den kompletten Speiseplan mit den OPTIMIERTEN Prompts
    """
    st.info("🔄 Starte Speiseplan-Generierung mit optimierten Prompts...")
    
    if produktliste and produktlisten_prozent > 0:
        st.info(f"📦 Berücksichtige {len(produktliste)} Produkte ({produktlisten_prozent}% Verwendung)")
    
    # Verwende die optimierte Prompt-Funktion aus prompts.py
    prompt = get_speiseplan_prompt(wochen, menulinien, menu_namen, produktliste, produktlisten_prozent)
    
    # Debug: Zeige einen Teil des Prompts
    with st.expander("🔍 Verwendeter Prompt (erste 1000 Zeichen)"):
        st.code(prompt[:1000] + "...", language="text")
    
    # API-Aufruf
    speiseplan, error = rufe_claude_api(prompt, api_key, max_tokens=16000)
    
    if error:
        return None, error
    
    if not speiseplan or 'speiseplan' not in speiseplan:
        return None, "Ungültige Speiseplan-Struktur"
    
    return speiseplan, None


def generiere_einzelnes_rezept(gericht_info, produktliste=None, produktlisten_prozent=0, api_key=None):
    """
    Generiert ein einzelnes Rezept
    
    Args:
        gericht_info: Dict mit 'gericht', 'beilagen', 'woche', 'tag', 'menu'
        produktliste: Optional - Verfügbare Produkte
        produktlisten_prozent: 0-100
        api_key: API-Key
    
    Returns:
        (rezept_dict, error)
    """
    # Produktlisten-Text für einzelnes Rezept
    produktlisten_text = ""
    if produktliste and produktlisten_prozent > 0:
        # Limitiere auf 50 Produkte für einzelne Rezepte
        liste = produktliste[:50] if len(produktliste) > 50 else produktliste
        produkte_string = "\n".join([f"- {p}" for p in liste])
        
        if produktlisten_prozent == 100:
            produktlisten_text = f"""
VERFÜGBARE PRODUKTE ({len(liste)} Artikel - STRIKTE VERWENDUNG):
{produkte_string}

KRITISCH: Verwende NUR Produkte aus dieser Liste!
"""
        elif produktlisten_prozent >= 80:
            produktlisten_text = f"""
VERFÜGBARE PRODUKTE ({len(liste)} Artikel - {produktlisten_prozent}% Verwendung):
{produkte_string}

WICHTIG: Mindestens {produktlisten_prozent}% der Zutaten müssen aus dieser Liste sein!
"""
        else:
            produktlisten_text = f"""
VERFÜGBARE PRODUKTE ({len(liste)} Artikel - empfohlene Verwendung):
{produkte_string}

Nutze diese Produkte bevorzugt, ergänze nach Bedarf.
"""
    
    # Kompakter Prompt für einzelnes Rezept
    beilagen_text = ', '.join(gericht_info['beilagen']) if gericht_info['beilagen'] else "ohne Beilagen"
    
    prompt = f"""Du bist ein Küchenmeister für Gemeinschaftsverpflegung. {TOOL_DIRECTIVE}

{produktlisten_text}

AUFGABE: Erstelle EIN detailliertes Rezept für:

**{gericht_info['gericht']} mit {beilagen_text}**
- Für: {gericht_info['menu']} | {gericht_info['tag']}, Woche {gericht_info['woche']}

ANFORDERUNGEN:
- Rezept für 10 Personen
- Mengenangaben in g/ml
- Detaillierte Zubereitungsschritte für Hauptgericht UND alle Beilagen
- Nährwerte pro Portion
- Allergenkennzeichnung
- Praktische Tipps für die Großküche

ANTWORT-SCHEMA (JSON-OBJEKT):
{{
  "name": "{gericht_info['gericht']} mit {beilagen_text}",
  "woche": {gericht_info['woche']},
  "tag": "{gericht_info['tag']}",
  "menu": "{gericht_info['menu']}",
  "portionen": 10,
  "zeiten": {{
    "vorbereitung": "X Minuten",
    "garzeit": "X Minuten",
    "gesamt": "X Minuten"
  }},
  "zutaten": [
    {{ "name": "Zutat", "menge": "X g/ml", "hinweis": "Optional" }}
  ],
  "zubereitung": [
    "Schritt 1 ausführlich beschrieben",
    "Schritt 2 ausführlich beschrieben"
  ],
  "naehrwerte": {{
    "kalorien": "X kcal",
    "protein": "X g",
    "fett": "X g",
    "kohlenhydrate": "X g",
    "ballaststoffe": "X g"
  }},
  "allergene": ["Allergen1", "Allergen2"],
  "tipps": ["Tipp 1 für Großküche", "Tipp 2"],
  "variationen": {{
    "pueriert": "Anleitung für pürierte Kost",
    "leichteKost": "Anpassung für leichte Vollkost"
  }}
}}

Gib das komplette Rezept mit allen Details zurück!"""
    
    # API-Call
    rezept_data, error = rufe_claude_api(prompt, api_key, max_tokens=4000)
    
    if error:
        return None, error
    
    if not rezept_data:
        return None, "Keine Daten erhalten"
    
    # Validiere dass es ein Rezept-Objekt ist
    if not isinstance(rezept_data, dict):
        return None, f"Ungültige Antwort-Struktur: {type(rezept_data)}"
    
    # Stelle sicher dass wichtige Felder vorhanden sind
    if 'name' not in rezept_data:
        rezept_data['name'] = f"{gericht_info['gericht']} mit {beilagen_text}"
    if 'woche' not in rezept_data:
        rezept_data['woche'] = gericht_info['woche']
    if 'tag' not in rezept_data:
        rezept_data['tag'] = gericht_info['tag']
    if 'menu' not in rezept_data:
        rezept_data['menu'] = gericht_info['menu']
    
    return rezept_data, None


def generiere_rezepte_einzeln(speiseplan, api_key, produktliste=None, produktlisten_prozent=0):
    """
    Generiert Rezepte einzeln nacheinander (robuster!)
    
    Returns:
        (rezepte_dict, error)
    """
    # Sammle alle Gerichte
    alle_gerichte = []
    for woche in speiseplan['speiseplan']['wochen']:
        for tag in woche['tage']:
            for menu in tag['menues']:
                if 'mittagessen' in menu:
                    beilagen = menu['mittagessen'].get('beilagen', [])
                    alle_gerichte.append({
                        'gericht': menu['mittagessen']['hauptgericht'],
                        'beilagen': beilagen,
                        'woche': woche['woche'],
                        'tag': tag['tag'],
                        'menu': menu['menuName']
                    })
    
    # Dedupliziere
    unique_gerichte = {}
    for g in alle_gerichte:
        key = (g['gericht'], tuple(sorted(g['beilagen'])))
        if key not in unique_gerichte:
            unique_gerichte[key] = g
    
    alle_gerichte = list(unique_gerichte.values())
    anzahl = len(alle_gerichte)
    
    # Info-Anzeige
    st.info(f"📖 Generiere {anzahl} Rezepte einzeln nacheinander...")
    if produktliste and produktlisten_prozent > 0:
        st.info(f"📦 Berücksichtige {len(produktliste)} Produkte ({produktlisten_prozent}%)")
    
    # Progress Bar
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # Sammle generierte Rezepte
    erfolgreiche_rezepte = []
    fehlgeschlagene = []
    
    # Generiere jedes Rezept einzeln
    for i, gericht in enumerate(alle_gerichte, 1):
        # Update Progress
        progress = i / anzahl
        progress_bar.progress(progress)
        beilagen_text = ', '.join(gericht['beilagen']) if gericht['beilagen'] else "ohne Beilagen"
        status_text.text(f"📖 Rezept {i}/{anzahl}: {gericht['gericht']} mit {beilagen_text}")
        
        # Generiere Rezept
        rezept, error = generiere_einzelnes_rezept(
            gericht, 
            produktliste, 
            produktlisten_prozent,
            api_key
        )
        
        if error:
            fehlgeschlagene.append({
                'gericht': gericht['gericht'],
                'fehler': error
            })
            st.warning(f"⚠️ Rezept {i} fehlgeschlagen: {gericht['gericht']} - {error}")
        else:
            erfolgreiche_rezepte.append(rezept)
            st.success(f"✅ Rezept {i}/{anzahl} erfolgreich: {gericht['gericht']}")
        
        # Kurze Pause zwischen Anfragen (Rate Limiting vermeiden)
        if i < anzahl:
            import time
            time.sleep(0.5)
    
    # Fertig
    progress_bar.progress(1.0)
    status_text.empty()
    
    # Ergebnis
    if not erfolgreiche_rezepte:
        return None, f"Alle {anzahl} Rezepte fehlgeschlagen!"
    
    if fehlgeschlagene:
        st.warning(f"⚠️ {len(fehlgeschlagene)} von {anzahl} Rezepten fehlgeschlagen:")
        for f in fehlgeschlagene:
            st.write(f"- {f['gericht']}: {f['fehler']}")
    
    return {'rezepte': erfolgreiche_rezepte}, None
    """
    Generiert Rezepte in Batches
    """
    # Sammle alle Gerichte
    alle_gerichte = []
    for woche in speiseplan['speiseplan']['wochen']:
        for tag in woche['tage']:
            for menu in tag['menues']:
                if 'mittagessen' in menu:
                    beilagen = menu['mittagessen'].get('beilagen', [])
                    alle_gerichte.append({
                        'gericht': menu['mittagessen']['hauptgericht'],
                        'beilagen': beilagen,
                        'woche': woche['woche'],
                        'tag': tag['tag'],
                        'menu': menu['menuName']
                    })
    
    # Dedupliziere
    unique_gerichte = {}
    for g in alle_gerichte:
        key = (g['gericht'], tuple(sorted(g['beilagen'])))
        if key not in unique_gerichte:
            unique_gerichte[key] = g
    
    alle_gerichte = list(unique_gerichte.values())
    
    if progress_callback:
        progress_callback(f"Starte Rezept-Generierung für {len(alle_gerichte)} Gerichte")
        if produktliste and produktlisten_prozent > 0:
            progress_callback(f"Verwende Produktliste mit {len(produktliste)} Artikeln ({produktlisten_prozent}%)")
    
    # WICHTIG: Bei langen Produktlisten, limitiere für Rezepte auf 100
    rezept_produktliste = produktliste
    if produktliste and len(produktliste) > 100:
        if progress_callback:
            progress_callback(f"⚠️ Produktliste sehr lang ({len(produktliste)} Artikel) - verwende Top 100 für Rezepte")
        rezept_produktliste = produktliste[:100]
    
    # Verwende optimierte Rezept-Prompt-Funktion mit limitierter Produktliste
    prompt = get_rezepte_prompt(speiseplan, rezept_produktliste, produktlisten_prozent)
    
    # Debug: Zeige Prompt-Statistiken
    if progress_callback:
        progress_callback(f"Prompt: {len(prompt)} Zeichen (~{len(prompt)//4} Tokens)")
    
    st.session_state['last_rezept_prompt_length'] = len(prompt)
    
    # Erhöhe max_tokens für Rezepte (sind länger als Speisepläne)
    rezepte_data, error = rufe_claude_api(prompt, api_key, max_tokens=16000)
    
    if error:
        st.session_state['last_rezept_error'] = {
            'error': str(error),
            'prompt_length': len(prompt),
            'produktliste_size': len(produktliste) if produktliste else 0
        }
        return None, error
    
    # Validiere Struktur
    if not rezepte_data:
        st.session_state['last_rezept_error'] = {
            'error': 'Keine Daten empfangen',
            'response_was_none': True,
            'prompt_length': len(prompt)
        }
        return None, "Keine Daten von API erhalten. Bitte öffnen Sie den Debug-Bereich unten für Details."
    
    if not isinstance(rezepte_data, dict):
        st.session_state['last_rezept_error'] = {
            'error': 'Falscher Datentyp',
            'type': str(type(rezepte_data)),
            'data_preview': str(rezepte_data)[:500]
        }
        return None, f"API gab kein Dictionary zurück, sondern: {type(rezepte_data)}"
    
    # Debug: Speichere in Session State für Analyse
    st.session_state['last_rezepte_raw'] = rezepte_data
    
    if 'rezepte' not in rezepte_data:
        # Versuche zu reparieren falls die Struktur anders ist
        # Manchmal gibt die API direkt eine Liste zurück
        if isinstance(rezepte_data, list):
            rezepte_data = {'rezepte': rezepte_data}
        else:
            return None, f"Rezepte-Key fehlt. Vorhandene Keys: {list(rezepte_data.keys())}"
    
    return rezepte_data, None


def generiere_pruefung(speiseplan, api_key):
    """
    Generiert Qualitätsprüfung
    """
    prompt = get_pruefung_prompt(speiseplan)
    pruefung, error = rufe_claude_api(prompt, api_key, max_tokens=4000)
    
    if error:
        return None, error
    
    return pruefung, None


# ===================== PDF-GENERIERUNG =====================

def erstelle_speiseplan_pdf(speiseplan_data):
    """Erstellt PDF im Querformat (DIN A4 Landscape)"""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=15*mm,
        leftMargin=15*mm,
        topMargin=15*mm,
        bottomMargin=15*mm
    )
    
    styles = getSampleStyleSheet()
    
    # Custom Styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#FF6B35'),
        spaceAfter=6*mm,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.grey,
        spaceAfter=10*mm,
        alignment=TA_CENTER
    )
    
    week_style = ParagraphStyle(
        'WeekStyle',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor('#FF8C42'),
        spaceAfter=5*mm,
        fontName='Helvetica-Bold'
    )
    
    day_style = ParagraphStyle(
        'DayStyle',
        parent=styles['Heading3'],
        fontSize=12,
        textColor=colors.HexColor('#333333'),
        spaceBefore=3*mm,
        spaceAfter=2*mm,
        fontName='Helvetica-Bold'
    )
    
    story = []
    
    # Titel
    story.append(Paragraph("Speiseplan", title_style))
    story.append(Paragraph("Gemeinschaftsverpflegung", subtitle_style))
    
    # Speiseplan-Daten
    for woche in speiseplan_data['speiseplan']['wochen']:
        story.append(Paragraph(f"Woche {woche['woche']}", week_style))
        story.append(Spacer(1, 3*mm))
        
        for tag in woche['tage']:
            story.append(Paragraph(tag['tag'], day_style))
            
            # Tabelle für Menüs
            table_data = []
            
            for menu in tag['menues']:
                menu_text = []
                menu_text.append(Paragraph(f"<b>{menu['menuName']}</b>", styles['Normal']))
                
                if 'mittagessen' in menu:
                    hauptgericht = menu['mittagessen']['hauptgericht']
                    beilagen = menu['mittagessen'].get('beilagen', [])
                    beilagen_text = ', '.join(beilagen) if beilagen else ''
                    
                    gericht_text = f"{hauptgericht}"
                    if beilagen_text:
                        gericht_text += f" mit {beilagen_text}"
                    
                    menu_text.append(Paragraph(gericht_text, styles['Normal']))
                
                table_data.append(menu_text)
            
            # Erstelle Tabelle
            if table_data:
                col_width = (landscape(A4)[0] - 30*mm) / len(table_data)
                
                table = Table([table_data], colWidths=[col_width] * len(table_data))
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F5F5F5')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 9),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                    ('TOPPADDING', (0, 0), (-1, 0), 8),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 5),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 5),
                ]))
                
                story.append(table)
                story.append(Spacer(1, 5*mm))
    
    doc.build(story)
    buffer.seek(0)
    return buffer


def erstelle_rezept_pdf(rezept):
    """Erstellt PDF für ein einzelnes Rezept"""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    
    styles = getSampleStyleSheet()
    story = []
    
    # Titel
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=20, spaceAfter=10)
    story.append(Paragraph(rezept['name'], title_style))
    story.append(Spacer(1, 10))
    
    # Info
    info_text = f"<b>Portionen:</b> {rezept.get('portionen', 100)} | "
    info_text += f"<b>Vorbereitung:</b> {rezept.get('zeiten', {}).get('vorbereitung', 'N/A')} | "
    info_text += f"<b>Garzeit:</b> {rezept.get('zeiten', {}).get('garzeit', 'N/A')}"
    story.append(Paragraph(info_text, styles['Normal']))
    story.append(Spacer(1, 10))
    
    # Zutaten
    story.append(Paragraph("<b>Zutaten</b>", styles['Heading2']))
    for zutat in rezept.get('zutaten', []):
        text = f"• {zutat.get('menge', '')} {zutat.get('name', '')}"
        story.append(Paragraph(text, styles['Normal']))
    story.append(Spacer(1, 10))
    
    # Zubereitung
    story.append(Paragraph("<b>Zubereitung</b>", styles['Heading2']))
    for i, schritt in enumerate(rezept.get('zubereitung', []), 1):
        story.append(Paragraph(f"<b>{i}.</b> {schritt}", styles['Normal']))
        story.append(Spacer(1, 5))
    
    doc.build(story)
    buffer.seek(0)
    return buffer


def erstelle_alle_rezepte_pdf(rezepte_data):
    """Erstellt PDF mit allen Rezepten"""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    
    styles = getSampleStyleSheet()
    story = []
    
    # Titel
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=24, spaceAfter=20, alignment=TA_CENTER)
    story.append(Paragraph("Rezeptsammlung", title_style))
    story.append(Spacer(1, 20))
    
    # Jedes Rezept
    for i, rezept in enumerate(rezepte_data.get('rezepte', []), 1):
        if i > 1:
            story.append(PageBreak())
        
        # Rezept-Titel
        story.append(Paragraph(f"{i}. {rezept['name']}", styles['Heading2']))
        story.append(Spacer(1, 10))
        
        # Info
        info_text = f"<b>Portionen:</b> {rezept.get('portionen', 100)} | "
        info_text += f"<b>Vorbereitung:</b> {rezept.get('zeiten', {}).get('vorbereitung', 'N/A')} | "
        info_text += f"<b>Garzeit:</b> {rezept.get('zeiten', {}).get('garzeit', 'N/A')}"
        story.append(Paragraph(info_text, styles['Normal']))
        story.append(Spacer(1, 10))
        
        # Zutaten
        story.append(Paragraph("<b>Zutaten</b>", styles['Heading3']))
        for zutat in rezept.get('zutaten', []):
            text = f"• {zutat.get('menge', '')} {zutat.get('name', '')}"
            story.append(Paragraph(text, styles['Normal']))
        story.append(Spacer(1, 10))
        
        # Zubereitung
        story.append(Paragraph("<b>Zubereitung</b>", styles['Heading3']))
        for j, schritt in enumerate(rezept.get('zubereitung', []), 1):
            story.append(Paragraph(f"<b>{j}.</b> {schritt}", styles['Normal']))
            story.append(Spacer(1, 5))
    
    doc.build(story)
    buffer.seek(0)
    return buffer


# ===================== UI =====================

# Sidebar für API-Key
with st.sidebar:
    st.header("🔑 API-Konfiguration")
    
    # Versuche API-Key aus Secrets zu laden
    api_key_from_secrets = None
    try:
        if hasattr(st, 'secrets') and 'ANTHROPIC_API_KEY' in st.secrets:
            api_key_from_secrets = st.secrets['ANTHROPIC_API_KEY']
            st.success("✅ API-Key aus Konfiguration geladen!")
    except Exception:
        pass
    
    # Manueller API-Key Input
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
    
    st.divider()
    
    st.header("⚙️ Speiseplan-Konfiguration")
    wochen = st.number_input("Anzahl Wochen", min_value=1, max_value=4, value=1)
    menulinien = st.number_input("Anzahl Menülinien", min_value=1, max_value=5, value=2)
    
    st.subheader("Bezeichnung der Menülinien")
    menu_namen = []
    for i in range(menulinien):
        name = st.text_input(f"Menülinie {i+1}", value=f"Menü {i+1}", key=f"menu_{i}")
        menu_namen.append(name)
    
    st.divider()
    
    st.header("📦 Produktliste (optional)")
    st.caption("Laden Sie Ihre verfügbaren Produkte hoch, um die Rezepte darauf abzustimmen")
    
    # File Upload
    uploaded_file = st.file_uploader(
        "Produktliste hochladen",
        type=['txt', 'xlsx', 'xls', 'csv'],
        help="TXT (ein Produkt pro Zeile), Excel oder CSV mit Produktnamen"
    )
    
    produktliste = None
    if uploaded_file is not None:
        try:
            # Parse je nach Dateityp
            if uploaded_file.name.endswith('.txt'):
                # TXT-Datei: eine Zeile pro Produkt
                content = uploaded_file.read().decode('utf-8')
                produktliste = [line.strip() for line in content.split('\n') if line.strip()]
            
            elif uploaded_file.name.endswith(('.xlsx', '.xls')):
                # Excel-Datei - intelligente Verarbeitung für ERP-Exporte
                df = pd.read_excel(uploaded_file)
                
                # Sammle alle Produktnamen aus verschiedenen Quellen
                produktliste = []
                
                # 1. Spaltenname als Produkt (typisch bei ERP-Exporten)
                if len(df.columns) > 0:
                    # Erste Spalte Header kann ein Produkt sein
                    header_name = str(df.columns[0]).strip()
                    if header_name and header_name.lower() not in ['produktname', 'artikel', 'name', 'produkt', 'bezeichnung', 'unnamed']:
                        produktliste.append(header_name)
                
                # 2. Alle Werte aus der ersten Spalte
                if len(df.columns) > 0:
                    erste_spalte = df.iloc[:, 0].dropna().astype(str).tolist()
                    produktliste.extend([p.strip() for p in erste_spalte if p.strip()])
                
                # 3. Falls mehrere Spalten: prüfe ob eine "Produktname" heißt
                for col in df.columns:
                    col_lower = str(col).lower()
                    if col_lower in ['produktname', 'artikel', 'artikelname', 'bezeichnung', 'name']:
                        produkte_aus_spalte = df[col].dropna().astype(str).tolist()
                        produktliste.extend([p.strip() for p in produkte_aus_spalte if p.strip()])
                        break
                
                # Dedupliziere
                produktliste = list(dict.fromkeys(produktliste))  # Behält Reihenfolge
            
            elif uploaded_file.name.endswith('.csv'):
                # CSV-Datei - ähnliche Logik wie Excel
                df = pd.read_csv(uploaded_file)
                
                produktliste = []
                
                # Header könnte Produkt sein
                if len(df.columns) > 0:
                    header_name = str(df.columns[0]).strip()
                    if header_name and header_name.lower() not in ['produktname', 'artikel', 'name', 'produkt', 'bezeichnung', 'unnamed']:
                        produktliste.append(header_name)
                
                # Erste Spalte
                if len(df.columns) > 0:
                    erste_spalte = df.iloc[:, 0].dropna().astype(str).tolist()
                    produktliste.extend([p.strip() for p in erste_spalte if p.strip()])
                
                # Dedupliziere
                produktliste = list(dict.fromkeys(produktliste))
            
            if produktliste:
                st.success(f"✅ {len(produktliste)} Produkte geladen!")
                with st.expander("📋 Produktliste anzeigen (erste 50)"):
                    for i, produkt in enumerate(produktliste[:50], 1):
                        st.write(f"{i}. {produkt}")
                    if len(produktliste) > 50:
                        st.caption(f"... und {len(produktliste) - 50} weitere Produkte")
        except Exception as e:
            st.error(f"❌ Fehler beim Laden der Datei: {e}")
            with st.expander("🔍 Debug-Info"):
                st.code(f"Fehler: {str(e)}\nDateiname: {uploaded_file.name}")
            produktliste = None
    
    # Schieberegler für Produktlisten-Verwendung
    if produktliste:
        st.subheader("🎯 Produktlisten-Verwendung")
        produktlisten_prozent = st.slider(
            "Wie viel % der Zutaten sollen aus der Liste stammen?",
            min_value=0,
            max_value=100,
            value=80,
            step=5,
            help=(
                "100% = Nur Produkte aus der Liste\n"
                "80% = Hauptsächlich aus Liste, Rest flexibel\n"
                "50% = Halb/halb\n"
                "0% = Liste nur als Empfehlung"
            )
        )
        
        # Erklärung basierend auf Wert
        if produktlisten_prozent == 100:
            st.info("🔒 **Strikt:** Nur Produkte aus Ihrer Liste werden verwendet")
        elif produktlisten_prozent >= 80:
            st.info("✅ **Bevorzugt:** Hauptsächlich Ihre Produkte, gelegentlich Alternativen")
        elif produktlisten_prozent >= 50:
            st.info("⚖️ **Ausgewogen:** Mix aus Ihren Produkten und Standardzutaten")
        elif produktlisten_prozent >= 20:
            st.info("💡 **Flexibel:** Liste als Empfehlung, freie Rezeptgestaltung")
        else:
            st.info("🆓 **Frei:** Liste wird kaum berücksichtigt")
    else:
        produktlisten_prozent = 0
        st.info("💡 Laden Sie eine Produktliste hoch, um Rezepte darauf abzustimmen")
    
    # Speichere in Session State für Verwendung in Prompts
    st.session_state['produktliste'] = produktliste
    st.session_state['produktlisten_prozent'] = produktlisten_prozent

# Titel
st.title("👨‍🍳 Professioneller Speiseplan-Generator")
st.markdown("*Für Gemeinschaftsverpflegung, Krankenhäuser & Senioreneinrichtungen*")
st.markdown("**✨ Mit optimierten Prompts für maximale Abwechslung!**")
st.divider()

# ===================== MENÜ-ANALYSE BEREICH =====================
st.header("📤 Speiseplan aus PDF/Webseite analysieren")
st.markdown("**Lade ein PDF hoch oder gib eine URL ein, um vorhandene Speisepläne zu analysieren**")

# Tabs für Upload-Optionen
upload_tab1, upload_tab2 = st.tabs(["📄 PDF hochladen", "🌐 Webseite analysieren"])

with upload_tab1:
    st.markdown("### PDF-Datei hochladen")
    st.caption("Lade eine PDF-Datei mit einem Speiseplan hoch (z.B. Restaurant-Menü, Kantine-Speiseplan)")

    uploaded_pdf = st.file_uploader(
        "PDF-Datei auswählen",
        type=['pdf'],
        key="pdf_uploader",
        help="Wähle eine PDF-Datei aus, die einen Speiseplan enthält"
    )

    if uploaded_pdf is not None:
        st.success(f"✅ Datei hochgeladen: {uploaded_pdf.name}")

        if st.button("🔍 PDF analysieren", type="primary", key="analyze_pdf_btn"):
            if not api_key:
                st.error("❌ Bitte API-Key eingeben!")
            else:
                with st.spinner("⏳ Extrahiere Text aus PDF..."):
                    text, error = extrahiere_text_aus_pdf(uploaded_pdf)

                    if error:
                        st.error(f"❌ {error}")
                    else:
                        st.success(f"✅ Text extrahiert ({len(text)} Zeichen)")

                        # Zeige einen Ausschnitt des extrahierten Textes
                        with st.expander("📝 Extrahierter Text (Vorschau)"):
                            st.text(text[:1000] + "..." if len(text) > 1000 else text)

                        # Analysiere mit Claude
                        with st.spinner("🤖 Analysiere Speiseplan mit KI..."):
                            analyse_result, error = analysiere_speiseplan_text(
                                text,
                                api_key,
                                rufe_claude_api,
                                TOOL_DIRECTIVE
                            )

                            if error:
                                st.error(f"❌ Analyse fehlgeschlagen: {error}")
                            else:
                                st.success("✅ Analyse abgeschlossen!")

                                # Formatiere und zeige Ergebnis
                                formatted_text = formatiere_analyse_ergebnis(analyse_result)

                                st.markdown("### 📊 Analyse-Ergebnis")
                                st.text(formatted_text)

                                # Download-Button für Ergebnis
                                st.download_button(
                                    label="💾 Analyse als Textdatei herunterladen",
                                    data=formatted_text,
                                    file_name=f"Speiseplan_Analyse_{uploaded_pdf.name}.txt",
                                    mime="text/plain"
                                )

                                # Zeige auch das rohe JSON
                                with st.expander("🔍 Rohdaten (JSON)"):
                                    st.json(analyse_result)

with upload_tab2:
    st.markdown("### Webseite analysieren")
    st.caption("Gib die URL einer Webseite ein, die einen Speiseplan enthält (z.B. Restaurant-Website, Kantine)")

    url_input = st.text_input(
        "URL eingeben",
        placeholder="https://beispiel-restaurant.de/speiseplan",
        key="url_input",
        help="Vollständige URL zur Webseite mit dem Speiseplan"
    )

    if url_input:
        if st.button("🔍 Webseite analysieren", type="primary", key="analyze_url_btn"):
            if not api_key:
                st.error("❌ Bitte API-Key eingeben!")
            else:
                with st.spinner(f"⏳ Lade Webseite von {url_input}..."):
                    text, error = extrahiere_text_aus_url(url_input)

                    if error:
                        st.error(f"❌ {error}")
                    else:
                        st.success(f"✅ Webseite geladen ({len(text)} Zeichen)")

                        # Zeige einen Ausschnitt des extrahierten Textes
                        with st.expander("📝 Extrahierter Text (Vorschau)"):
                            st.text(text[:1000] + "..." if len(text) > 1000 else text)

                        # Analysiere mit Claude
                        with st.spinner("🤖 Analysiere Speiseplan mit KI..."):
                            analyse_result, error = analysiere_speiseplan_text(
                                text,
                                api_key,
                                rufe_claude_api,
                                TOOL_DIRECTIVE
                            )

                            if error:
                                st.error(f"❌ Analyse fehlgeschlagen: {error}")
                            else:
                                st.success("✅ Analyse abgeschlossen!")

                                # Formatiere und zeige Ergebnis
                                formatted_text = formatiere_analyse_ergebnis(analyse_result)

                                st.markdown("### 📊 Analyse-Ergebnis")
                                st.text(formatted_text)

                                # Download-Button für Ergebnis
                                st.download_button(
                                    label="💾 Analyse als Textdatei herunterladen",
                                    data=formatted_text,
                                    file_name="Speiseplan_Analyse_Webseite.txt",
                                    mime="text/plain"
                                )

                                # Zeige auch das rohe JSON
                                with st.expander("🔍 Rohdaten (JSON)"):
                                    st.json(analyse_result)

st.divider()
st.markdown("---")

# ===================== STANDARD SPEISEPLAN-GENERIERUNG =====================
st.header("🎨 Oder: Neuen Speiseplan generieren")
st.markdown("**Erstelle einen komplett neuen Speiseplan basierend auf deinen Vorgaben**")
st.divider()

# Generierungs-Button
if st.button("🚀 Speiseplan generieren", type="primary", use_container_width=True):
    if not api_key:
        st.error("❌ Bitte API-Key eingeben!")
    else:
        # Hole Produktliste aus Session State
        produktliste = st.session_state.get('produktliste')
        produktlisten_prozent = st.session_state.get('produktlisten_prozent', 0)
        
        with st.spinner("⏳ Generiere Speiseplan..."):
            speiseplan_data, error = generiere_speiseplan(
                wochen, 
                menulinien, 
                menu_namen, 
                api_key,
                produktliste,
                produktlisten_prozent
            )
            
            if error:
                st.error(f"❌ Fehler: {error}")
                
                # Hilfreiche Tipps bei bestimmten Fehlern
                if "529" in str(error) or "überlastet" in str(error).lower():
                    st.info("""
                    💡 **API überlastet - Was tun?**
                    
                    Die Anthropic API ist momentan stark ausgelastet. Probieren Sie:
                    
                    1. ⏳ **Warten Sie 1-2 Minuten** und versuchen Sie es erneut
                    2. 🕐 **Andere Tageszeit**: Weniger Last außerhalb der Stoßzeiten (z.B. nachts)
                    3. 📉 **Kleinerer Plan**: Reduzieren Sie auf 1 Woche oder 1 Menülinie
                    4. 🔄 **Automatische Wiederholung**: Die App versucht es bereits 3x automatisch
                    
                    Dies ist ein temporäres Problem auf Seiten von Anthropic, nicht Ihrer App!
                    """)
                elif "timeout" in str(error).lower():
                    st.info("""
                    💡 **Timeout - Was tun?**
                    
                    1. ⏳ Warten Sie einen Moment und versuchen Sie es erneut
                    2. 📉 Reduzieren Sie die Komplexität (weniger Wochen/Menülinien)
                    3. 🌐 Prüfen Sie Ihre Internetverbindung
                    """)
            else:
                st.session_state['speiseplan'] = speiseplan_data
                
                # Generiere auch Prüfung
                with st.spinner("🔍 Führe Qualitätsprüfung durch..."):
                    pruefung, _ = generiere_pruefung(speiseplan_data, api_key)
                    if pruefung:
                        st.session_state['pruefung'] = pruefung
                
                st.success("✅ Speiseplan erfolgreich erstellt!")
                st.balloons()

# Anzeige der Ergebnisse
if 'speiseplan' in st.session_state and st.session_state['speiseplan']:
    tab1, tab2, tab3 = st.tabs(["📋 Speiseplan", "🔍 Qualitätsprüfung", "📖 Rezepte"])
    
    with tab1:
        st.header("Speiseplan")
        
        # PDF-Export Button
        pdf_buffer = erstelle_speiseplan_pdf(st.session_state['speiseplan'])
        st.download_button(
            label="📄 Speiseplan als PDF herunterladen",
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
                        if 'mittagessen' in menu:
                            st.markdown("**🍽️ Mittagessen**")
                            st.write(f"**{menu['mittagessen']['hauptgericht']}**")
                            if menu['mittagessen'].get('beilagen'):
                                st.caption(f"🥔 Beilagen: {', '.join(menu['mittagessen']['beilagen'])}")
                            if menu['mittagessen'].get('naehrwerte'):
                                st.caption(f"📊 {menu['mittagessen']['naehrwerte'].get('kalorien', 'N/A')} | Protein: {menu['mittagessen']['naehrwerte'].get('protein', 'N/A')}")
                
                st.divider()
    
    with tab2:
        st.header("🔍 Qualitätsprüfung")
        
        if 'pruefung' in st.session_state and st.session_state['pruefung']:
            pruefung = st.session_state['pruefung']
            
            # Gesamtbewertung
            col1, col2 = st.columns(2)
            with col1:
                bewertung = pruefung.get('gesamtbewertung', 'N/A')
                if bewertung == 'sehr gut':
                    st.success(f"### ✅ Bewertung: {bewertung}")
                elif bewertung == 'gut':
                    st.info(f"### ℹ️ Bewertung: {bewertung}")
                else:
                    st.warning(f"### ⚠️ Bewertung: {bewertung}")
            
            with col2:
                st.metric("Punktzahl", pruefung.get('punktzahl', 'N/A'))
            
            st.divider()
            
            # Abwechslungsprüfung (NEU!)
            if 'abwechslungspruefung' in pruefung:
                st.subheader("🔄 Abwechslungsprüfung")
                abw = pruefung['abwechslungspruefung']
                
                if abw.get('wiederholungen'):
                    st.error("❌ **Gefundene Wiederholungen:**")
                    for wdh in abw['wiederholungen']:
                        st.write(f"• {wdh}")
                else:
                    st.success("✅ Keine Wiederholungen gefunden - ausgezeichnet!")
                
                if abw.get('bewertung'):
                    st.write(f"**Bewertung:** {abw['bewertung']}")
                
                st.divider()
            
            # Positive Aspekte
            if pruefung.get('positiveAspekte'):
                st.subheader("✅ Positive Aspekte")
                for aspekt in pruefung['positiveAspekte']:
                    st.success(f"• {aspekt}")
            
            # Verbesserungsvorschläge
            if pruefung.get('verbesserungsvorschlaege'):
                st.subheader("💡 Verbesserungsvorschläge")
                for vorschlag in pruefung['verbesserungsvorschlaege']:
                    with st.expander(f"**{vorschlag.get('bereich', 'N/A')}**"):
                        st.write(f"**Problem:** {vorschlag.get('problem', 'N/A')}")
                        st.write(f"**Empfehlung:** {vorschlag.get('empfehlung', 'N/A')}")
            
            # Fazit
            if pruefung.get('fazit'):
                st.divider()
                st.subheader("📋 Fazit")
                st.info(pruefung['fazit'])
        else:
            st.info("Keine Qualitätsprüfung vorhanden")
    
    with tab3:
        st.header("Detaillierte Rezepte")
        
        if 'rezepte' in st.session_state and st.session_state['rezepte']:
            # Rezepte sind vorhanden
            alle_rezepte_pdf = erstelle_alle_rezepte_pdf(st.session_state['rezepte'])
            st.download_button(
                label="📚 Alle Rezepte als PDF",
                data=alle_rezepte_pdf,
                file_name="Alle_Rezepte.pdf",
                mime="application/pdf",
                use_container_width=True
            )
            
            st.divider()
            
            for rezept in st.session_state['rezepte']['rezepte']:
                with st.expander(f"**{rezept['name']}**", expanded=False):
                    col1, col2 = st.columns([3, 1])
                    
                    with col1:
                        st.markdown(f"**{rezept.get('portionen', 100)} Portionen** | {rezept.get('tag', 'N/A')}, Woche {rezept.get('woche', 'N/A')}")
                        zeiten = rezept.get('zeiten', {})
                        st.caption(f"⏱️ Vorbereitung: {zeiten.get('vorbereitung', 'N/A')} | Garzeit: {zeiten.get('garzeit', 'N/A')}")
                    
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
                    for zutat in rezept.get('zutaten', []):
                        st.write(f"• **{zutat.get('menge', '')}** {zutat.get('name', '')}")
                    
                    st.markdown("### Zubereitung")
                    for i, schritt in enumerate(rezept.get('zubereitung', []), 1):
                        st.info(f"**Schritt {i}:** {schritt}")
        else:
            # Rezepte generieren
            st.info("💡 Rezepte noch nicht generiert. Klicken Sie auf den Button um sie zu erstellen.")
            
            if st.button("📖 Rezepte jetzt generieren", type="primary", use_container_width=True):
                # Hole Produktliste aus Session State
                produktliste = st.session_state.get('produktliste')
                produktlisten_prozent = st.session_state.get('produktlisten_prozent', 0)
                
                # Verwende neue einzelne Generierung (robuster!)
                rezepte_data, error = generiere_rezepte_einzeln(
                    st.session_state['speiseplan'],
                    api_key,
                    produktliste,
                    produktlisten_prozent
                )
                
                if error:
                    st.error(f"❌ Fehler: {error}")
                elif not rezepte_data:
                    st.error("❌ Keine Rezepte-Daten erhalten")
                elif 'rezepte' not in rezepte_data:
                    st.error(f"❌ Ungültige Rezepte-Struktur. Erhaltene Keys: {list(rezepte_data.keys()) if isinstance(rezepte_data, dict) else 'Kein Dict'}")
                    st.session_state['last_invalid_rezepte'] = rezepte_data
                    with st.expander("🔍 Erhaltene Daten"):
                        st.json(rezepte_data)
                else:
                    st.session_state['rezepte'] = rezepte_data
                    anzahl = len(rezepte_data['rezepte']) if isinstance(rezepte_data.get('rezepte'), list) else 0
                    st.success(f"🎉 {anzahl} Rezepte erfolgreich erstellt!")
                    st.balloons()
                    st.rerun()

# ===================== DEBUG-BEREICH =====================
st.divider()
with st.expander("🔧 Debug-Informationen (bei Problemen öffnen)"):
    st.markdown("### Session State")
    st.write(f"**Speiseplan vorhanden:** {'speiseplan' in st.session_state}")
    st.write(f"**Rezepte vorhanden:** {'rezepte' in st.session_state}")
    st.write(f"**Prüfung vorhanden:** {'pruefung' in st.session_state}")
    
    # Rezept-spezifische Fehler
    if 'last_rezept_error' in st.session_state:
        st.markdown("### ❌ Letzter Rezept-Fehler")
        fehler = st.session_state['last_rezept_error']
        st.json(fehler)
        
        if 'prompt_length' in fehler:
            tokens_ca = fehler['prompt_length'] // 4
            st.warning(f"⚠️ Prompt-Länge: {fehler['prompt_length']:,} Zeichen (~{tokens_ca:,} Tokens)")
            if tokens_ca > 15000:
                st.error("🚨 Prompt ist sehr lang! Das könnte das Problem sein.")
    
    # Rezept-Prompt-Statistiken
    if 'last_rezept_prompt_length' in st.session_state:
        st.markdown("### 📊 Rezept-Prompt-Statistiken")
        length = st.session_state['last_rezept_prompt_length']
        tokens = length // 4
        st.write(f"**Länge:** {length:,} Zeichen")
        st.write(f"**~Tokens:** {tokens:,}")
        
        if tokens > 15000:
            st.error("⚠️ Prompt ist zu lang für die API!")
        elif tokens > 10000:
            st.warning("⚠️ Prompt ist sehr lang, könnte problematisch sein")
        else:
            st.success("✅ Prompt-Länge ist OK")
    
    if 'last_rezepte_raw' in st.session_state:
        st.markdown("### 📦 Letzte Rezepte-Raw-Daten")
        st.json(st.session_state['last_rezepte_raw'])
    
    if 'last_invalid_rezepte' in st.session_state:
        st.markdown("### ⚠️ Letzte ungültige Rezepte-Struktur")
        st.json(st.session_state['last_invalid_rezepte'])
    
    if 'last_exception' in st.session_state:
        st.markdown("### ❌ Letzter Fehler")
        st.code(st.session_state['last_exception'], language="python")
    
    if 'last_tool_response' in st.session_state:
        st.markdown("### 🔧 Letzte Tool-Response")
        st.json(st.session_state['last_tool_response'])
    
    if 'last_json_error' in st.session_state:
        st.markdown("### 📝 Letzter JSON-Parse-Fehler")
        st.json(st.session_state['last_json_error'])
    
    if 'debug_responses' in st.session_state and st.session_state['debug_responses']:
        st.markdown("### 📊 API-Response-Historie")
        for i, resp in enumerate(st.session_state['debug_responses'][-3:], 1):
            st.write(f"{i}. {resp}")

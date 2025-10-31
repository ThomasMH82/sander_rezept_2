import streamlit as st
import requests
import json
import re
from datetime import datetime
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_CENTER, TA_LEFT

# WICHTIG: Importiere die optimierten Prompts!
from prompts import get_speiseplan_prompt, get_rezepte_prompt, get_pruefung_prompt

st.set_page_config(page_title="Speiseplan-Generator", layout="wide", page_icon="👨‍🍳")

# ===================== KONFIGURATION =====================
API_BASE_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-sonnet-4-20250514"
API_TIMEOUT = 180

# ===================== API-FUNKTIONEN =====================

def rufe_claude_api(prompt, api_key, max_tokens=16000):
    """
    Ruft die Claude API mit Tool-Use auf (return_json)
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
    
    try:
        response = requests.post(
            API_BASE_URL,
            headers=headers,
            json=payload,
            timeout=API_TIMEOUT
        )
        response.raise_for_status()
        
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
        
    except requests.exceptions.Timeout:
        return None, "API-Timeout - Anfrage dauerte zu lange"
    except requests.exceptions.RequestException as e:
        return None, f"API-Fehler: {str(e)}"
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

def generiere_speiseplan(wochen, menulinien, menu_namen, api_key):
    """
    Generiert den kompletten Speiseplan mit den OPTIMIERTEN Prompts
    """
    st.info("🔄 Starte Speiseplan-Generierung mit optimierten Prompts...")
    
    # Verwende die optimierte Prompt-Funktion aus prompts.py
    prompt = get_speiseplan_prompt(wochen, menulinien, menu_namen)
    
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


def generiere_rezepte_batch(speiseplan, api_key, batch_size=7, progress_callback=None):
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
    
    # Verwende optimierte Rezept-Prompt-Funktion
    prompt = get_rezepte_prompt(speiseplan)
    
    # Debug: Zeige Prompt-Länge
    if progress_callback:
        progress_callback(f"Prompt-Länge: {len(prompt)} Zeichen")
    
    rezepte_data, error = rufe_claude_api(prompt, api_key, max_tokens=10000)
    
    if error:
        return None, error
    
    # Validiere Struktur
    if not rezepte_data:
        return None, "Keine Daten von API erhalten"
    
    if not isinstance(rezepte_data, dict):
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

# Titel
st.title("👨‍🍳 Professioneller Speiseplan-Generator")
st.markdown("*Für Gemeinschaftsverpflegung, Krankenhäuser & Senioreneinrichtungen*")
st.markdown("**✨ Mit optimierten Prompts für maximale Abwechslung!**")
st.divider()

# Generierungs-Button
if st.button("🚀 Speiseplan generieren", type="primary", use_container_width=True):
    if not api_key:
        st.error("❌ Bitte API-Key eingeben!")
    else:
        with st.spinner("⏳ Generiere Speiseplan..."):
            speiseplan_data, error = generiere_speiseplan(wochen, menulinien, menu_namen, api_key)
            
            if error:
                st.error(f"❌ Fehler: {error}")
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
                with st.spinner("📖 Generiere Rezepte..."):
                    rezepte_data, error = generiere_rezepte_batch(
                        st.session_state['speiseplan'],
                        api_key
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
                        st.success(f"✅ {anzahl} Rezepte erstellt!")
                        st.rerun()

# ===================== DEBUG-BEREICH =====================
st.divider()
with st.expander("🔧 Debug-Informationen (bei Problemen öffnen)"):
    st.markdown("### Session State")
    st.write(f"**Speiseplan vorhanden:** {'speiseplan' in st.session_state}")
    st.write(f"**Rezepte vorhanden:** {'rezepte' in st.session_state}")
    st.write(f"**Prüfung vorhanden:** {'pruefung' in st.session_state}")
    
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

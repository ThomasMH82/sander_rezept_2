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

def generiere_speiseplan_prompt(wochen, menulinien, menu_namen):
    menu_liste = "\n".join([f"{i+1}. {name}" for i, name in enumerate(menu_namen)])
    
    return f"""Du bist ein diätisch ausgebildeter Küchenmeister mit über 25 Jahren Erfahrung in der Gemeinschaftsverpflegung, spezialisiert auf Krankenhaus- und Seniorenverpflegung.

AUFGABE: Erstelle einen professionellen Speiseplan für {wochen} Woche(n) mit {menulinien} Menülinie(n).

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

STRUKTUR DER ANTWORT (JSON):
{{
  "speiseplan": {{
    "wochen": [
      {{
        "woche": 1,
        "tage": [
          {{
            "tag": "Montag",
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
        ]
      }}
    ]
  }}
}}

WICHTIG: Antworte NUR mit validem JSON. Keine Markdown-Formatierung, keine Backticks.
STARTE MIT {{ UND ENDE MIT }}
KEIN TEXT DAVOR ODER DANACH!"""

def generiere_rezepte_prompt(speiseplan):
    alle_gerichte = []
    for woche in speiseplan['speiseplan']['wochen']:
        for tag in woche['tage']:
            for menu in tag['menues']:
                alle_gerichte.append({
                    'gericht': menu['mittagessen']['hauptgericht'],
                    'beilagen': menu['mittagessen'].get('beilagen', []),
                    'woche': woche['woche'],
                    'tag': tag['tag'],
                    'menu': menu['menuName']
                })
    
    gerichte_liste = "\n".join([
        f"{i+1}. {g['gericht']} mit {', '.join(g['beilagen'])}" 
        for i, g in enumerate(alle_gerichte)
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

NUR JSON! KEIN ANDERER TEXT!"""

def bereinige_json(text):
    """Bereinigt Text für robustes JSON-Parsing mit mehreren Strategien"""
    if not text:
        return ""

    # Entferne Markdown-Code-Blöcke
    text = re.sub(r'```json\n?', '', text)
    text = re.sub(r'```\n?', '', text)
    text = text.strip()

    # Ersetze Smart Quotes und typografische Zeichen
    replacements = {
        '"': '"', '"': '"', '„': '"',
        ''': "'", '‚': "'", ''': "'",
        '–': '-', '—': '-'
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    # Entferne Kommentare (JavaScript-Style)
    text = re.sub(r'//.*?$', '', text, flags=re.MULTILINE)  # Einzeilige Kommentare
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)  # Mehrzeilige Kommentare

    # Entferne trailing commas vor schließenden Klammern
    text = re.sub(r',\s*([}\]])', r'\1', text)

    # Extrahiere JSON-Objekt
    first_brace = text.find('{')
    last_brace = text.rfind('}')

    if first_brace != -1 and last_brace != -1:
        text = text[first_brace:last_brace + 1]

    return text

def parse_json_mit_fallbacks(text):
    """Versucht JSON mit mehreren Strategien zu parsen"""
    if not text:
        return None

    # Strategie 1: Direktes Parsing
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategie 2: Nach Bereinigung
    cleaned = bereinige_json(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Strategie 3: Versuche fehlende Kommata zu ergänzen
    # Füge Komma zwischen } und " ein (häufiger Fehler)
    text_with_commas = re.sub(r'}\s*"', r'}, "', cleaned)
    text_with_commas = re.sub(r']\s*"', r'], "', text_with_commas)
    # Füge Komma zwischen "wert" und "key" ein
    text_with_commas = re.sub(r'(".*?")\s+(".*?":\s*)', r'\1, \2', text_with_commas)

    try:
        return json.loads(text_with_commas)
    except json.JSONDecodeError:
        pass

    # Strategie 4: Extrahiere größtes gültiges JSON-Objekt
    stack = []
    start_idx = None

    for i, char in enumerate(cleaned):
        if char == '{':
            if not stack:
                start_idx = i
            stack.append(char)
        elif char == '}':
            if stack and stack[-1] == '{':
                stack.pop()
                if not stack and start_idx is not None:
                    # Versuche dieses Objekt zu parsen
                    try:
                        candidate = cleaned[start_idx:i+1]
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        continue

    return None

def rufe_claude_api(prompt, api_key, max_tokens=20000):
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
            }
        )

        if response.status_code != 200:
            return None, f"API-Fehler: Status {response.status_code} - {response.text}"

        data = response.json()
        response_text = data['content'][0]['text']

        # Verwende robuste Parsing-Funktion mit Fallbacks
        parsed_data = parse_json_mit_fallbacks(response_text)

        if parsed_data is None:
            # Wenn alle Strategien fehlschlagen, zeige den Anfang der Antwort zur Diagnose
            preview = response_text[:500] if len(response_text) > 500 else response_text
            return None, f"JSON-Parsing fehlgeschlagen. Antwort-Vorschau:\n{preview}\n\n...Bitte versuchen Sie es erneut."

        return parsed_data, None

    except json.JSONDecodeError as e:
        return None, f"JSON-Parsing-Fehler: {str(e)}"
    except Exception as e:
        return None, f"Fehler: {str(e)}"

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
        with st.spinner("⏳ Speiseplan wird erstellt..."):
            prompt = generiere_speiseplan_prompt(wochen, menulinien, menu_namen)
            speiseplan_data, error = rufe_claude_api(prompt, api_key)
            
            if error:
                st.error(f"❌ Fehler beim Erstellen des Speiseplans: {error}")
            else:
                st.session_state['speiseplan'] = speiseplan_data
                
                with st.spinner("🔍 Rezepte werden erstellt..."):
                    rezepte_prompt = generiere_rezepte_prompt(speiseplan_data)
                    rezepte_data, error2 = rufe_claude_api(rezepte_prompt, api_key)
                    
                    if error2:
                        st.warning(f"⚠️ Speiseplan erstellt, aber Rezepte fehlgeschlagen: {error2}")
                        st.session_state['rezepte'] = None
                    else:
                        st.session_state['rezepte'] = rezepte_data
                
                st.success("✅ Speiseplan und Rezepte erfolgreich erstellt!")
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
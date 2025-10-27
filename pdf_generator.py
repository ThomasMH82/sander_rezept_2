"""
PDF-Generator für Speisepläne und Rezepte
Erstellt professionell formatierte PDFs mit ReportLab
"""

from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_CENTER, TA_LEFT


def erstelle_speiseplan_pdf(speiseplan):
    """
    Erstellt ein PDF des Speiseplans im DIN A4 Querformat
    Optimal zum Ausdrucken und Aufhängen
    
    Args:
        speiseplan (dict): Der Speiseplan-Daten
        
    Returns:
        BytesIO: PDF als Byte-Stream
    """
    buffer = BytesIO()
    
    # Dokument im Querformat erstellen
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=landscape(A4),
        rightMargin=20*mm, 
        leftMargin=20*mm,
        topMargin=20*mm, 
        bottomMargin=20*mm
    )
    
    elements = []
    styles = getSampleStyleSheet()
    
    # Titel-Style
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#d97706'),
        spaceAfter=30,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    # Untertitel-Style
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=12,
        textColor=colors.grey,
        spaceAfter=20,
        alignment=TA_CENTER
    )
    
    # Titel
    elements.append(Paragraph("Speiseplan", title_style))
    elements.append(Paragraph("Gemeinschaftsverpflegung", subtitle_style))
    elements.append(Spacer(1, 20))
    
    # Wochenstil
    woche_style = ParagraphStyle(
        'Woche', 
        parent=styles['Heading2'], 
        fontSize=16,
        textColor=colors.HexColor('#d97706'),
        spaceAfter=10,
        spaceBefore=10,
        fontName='Helvetica-Bold'
    )
    
    # Tagstil
    tag_style = ParagraphStyle(
        'Tag', 
        parent=styles['Heading3'], 
        fontSize=14,
        textColor=colors.HexColor('#555555'),
        spaceAfter=5,
        fontName='Helvetica-Bold'
    )
    
    # Durch alle Wochen iterieren
    for woche in speiseplan['speiseplan']['wochen']:
        elements.append(Paragraph(f"Woche {woche['woche']}", woche_style))
        elements.append(Spacer(1, 10))
        
        for tag in woche['tage']:
            elements.append(Paragraph(tag['tag'], tag_style))
            elements.append(Spacer(1, 5))
            
            # Tabelle für Menüs erstellen
            for menu in tag['menues']:
                # Daten für die Tabelle
                data = []
                
                # Menüname als Header
                menu_header = Paragraph(
                    f"<b>{menu['menuName']}</b>", 
                    styles['Normal']
                )
                data.append([menu_header])
                
                # Hauptgericht
                hauptgericht = menu['mittagessen']['hauptgericht']
                beilagen = menu['mittagessen'].get('beilagen', [])
                
                if beilagen:
                    beilagen_text = f"mit {', '.join(beilagen)}"
                    gericht_text = f"{hauptgericht}<br/><font size='9' color='#666666'>{beilagen_text}</font>"
                else:
                    gericht_text = hauptgericht
                
                data.append([Paragraph(gericht_text, styles['Normal'])])
                
                # Tabelle erstellen
                t = Table(data, colWidths=[250*mm])
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#fff5f0')),
                    ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 10),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                    ('TOPPADDING', (0, 0), (-1, -1), 8),
                    ('LEFTPADDING', (0, 0), (-1, -1), 10),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 10),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ]))
                
                elements.append(t)
                elements.append(Spacer(1, 5))
            
            elements.append(Spacer(1, 10))
        
        # Neue Seite für jede Woche (außer bei der letzten)
        if woche != speiseplan['speiseplan']['wochen'][-1]:
            elements.append(PageBreak())
    
    # PDF erstellen
    doc.build(elements)
    buffer.seek(0)
    return buffer


def erstelle_rezept_pdf(rezept):
    """
    Erstellt ein PDF für ein einzelnes Rezept
    
    Args:
        rezept (dict): Die Rezept-Daten
        
    Returns:
        BytesIO: PDF als Byte-Stream
    """
    buffer = BytesIO()
    
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=A4,
        rightMargin=20*mm, 
        leftMargin=20*mm,
        topMargin=20*mm, 
        bottomMargin=20*mm
    )
    
    elements = []
    styles = getSampleStyleSheet()
    
    # Header-Box Style
    header_style = ParagraphStyle(
        'HeaderStyle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.white,
        spaceAfter=5,
        fontName='Helvetica-Bold'
    )
    
    info_style = ParagraphStyle(
        'InfoStyle',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.white,
        spaceAfter=3
    )
    
    # Farbiger Header
    header_data = [
        [Paragraph(rezept['name'], header_style)],
        [Paragraph(f"{rezept['menu']} | {rezept['tag']}, Woche {rezept['woche']}", info_style)],
        [Paragraph(f"{rezept['portionen']} Portionen", info_style)]
    ]
    
    header_table = Table(header_data, colWidths=[170*mm])
    header_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#d97706')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 15),
        ('RIGHTPADDING', (0, 0), (-1, -1), 15),
        ('TOPPADDING', (0, 0), (0, 0), 15),
        ('BOTTOMPADDING', (-1, -1), (-1, -1), 15),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    
    elements.append(header_table)
    elements.append(Spacer(1, 20))
    
    # Zeiten
    section_style = ParagraphStyle(
        'SectionStyle',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#d97706'),
        spaceAfter=10,
        spaceBefore=10,
        fontName='Helvetica-Bold'
    )
    
    zeiten_text = f"⏱️ Vorbereitung: {rezept['zeiten']['vorbereitung']} | Garzeit: {rezept['zeiten']['garzeit']}"
    if 'gesamt' in rezept['zeiten']:
        zeiten_text += f" | Gesamt: {rezept['zeiten']['gesamt']}"
    
    elements.append(Paragraph(zeiten_text, styles['Normal']))
    elements.append(Spacer(1, 15))
    
    # Zutaten
    elements.append(Paragraph("Zutaten", section_style))
    
    for zutat in rezept['zutaten']:
        zutat_text = f"• <b>{zutat['menge']}</b> {zutat['name']}"
        if zutat.get('hinweis'):
            zutat_text += f" <font size='9' color='#666666'>({zutat['hinweis']})</font>"
        
        elements.append(Paragraph(zutat_text, styles['Normal']))
        elements.append(Spacer(1, 3))
    
    elements.append(Spacer(1, 15))
    
    # Zubereitung
    elements.append(Paragraph("Zubereitung", section_style))
    
    schritt_style = ParagraphStyle(
        'SchrittStyle',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=8,
        leftIndent=10,
        borderWidth=0,
        borderColor=colors.HexColor('#d97706'),
        borderPadding=10,
        backColor=colors.HexColor('#f9fafb')
    )
    
    for i, schritt in enumerate(rezept['zubereitung'], 1):
        schritt_text = f"<b>Schritt {i}:</b> {schritt}"
        elements.append(Paragraph(schritt_text, schritt_style))
        elements.append(Spacer(1, 5))
    
    elements.append(Spacer(1, 15))
    
    # Nährwerte
    elements.append(Paragraph("Nährwerte pro Portion", section_style))
    
    naehr = rezept['naehrwerte']
    naehrwerte_data = [[
        Paragraph(f"<b>Kalorien</b><br/>{naehr['kalorien']}", styles['Normal']),
        Paragraph(f"<b>Protein</b><br/>{naehr['protein']}", styles['Normal']),
        Paragraph(f"<b>Fett</b><br/>{naehr['fett']}", styles['Normal']),
        Paragraph(f"<b>Kohlenhydrate</b><br/>{naehr['kohlenhydrate']}", styles['Normal']),
        Paragraph(f"<b>Ballaststoffe</b><br/>{naehr.get('ballaststoffe', 'N/A')}", styles['Normal'])
    ]]
    
    naehr_table = Table(naehrwerte_data, colWidths=[34*mm]*5)
    naehr_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f0f9ff')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
    ]))
    
    elements.append(naehr_table)
    elements.append(Spacer(1, 15))
    
    # Allergene
    if rezept.get('allergene') and len(rezept['allergene']) > 0:
        allergene_text = f"<b>⚠️ Allergene:</b> {', '.join(rezept['allergene'])}"
        allergene_para = Paragraph(allergene_text, styles['Normal'])
        
        allergene_table = Table([[allergene_para]], colWidths=[170*mm])
        allergene_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fee')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#c00')),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        
        elements.append(allergene_table)
        elements.append(Spacer(1, 15))
    
    # Tipps
    if rezept.get('tipps') and len(rezept['tipps']) > 0:
        elements.append(Paragraph("💡 Tipps für die Großküche", section_style))
        for tipp in rezept['tipps']:
            elements.append(Paragraph(f"• {tipp}", styles['Normal']))
            elements.append(Spacer(1, 3))
        elements.append(Spacer(1, 15))
    
    # Variationen
    if rezept.get('variationen'):
        elements.append(Paragraph("Variationen", section_style))
        
        if rezept['variationen'].get('pueriert'):
            elements.append(Paragraph(
                f"<b>Pürierte Kost:</b> {rezept['variationen']['pueriert']}", 
                styles['Normal']
            ))
            elements.append(Spacer(1, 5))
        
        if rezept['variationen'].get('leichteKost'):
            elements.append(Paragraph(
                f"<b>Leichte Kost:</b> {rezept['variationen']['leichteKost']}", 
                styles['Normal']
            ))
    
    # PDF erstellen
    doc.build(elements)
    buffer.seek(0)
    return buffer


def erstelle_alle_rezepte_pdf(rezepte_data):
    """
    Erstellt ein PDF mit allen Rezepten
    
    Args:
        rezepte_data (dict): Dictionary mit 'rezepte'-Liste
        
    Returns:
        BytesIO: PDF als Byte-Stream
    """
    buffer = BytesIO()
    
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=A4,
        rightMargin=20*mm, 
        leftMargin=20*mm,
        topMargin=20*mm, 
        bottomMargin=20*mm
    )
    
    elements = []
    styles = getSampleStyleSheet()
    
    # Inhaltsverzeichnis
    title_style = ParagraphStyle(
        'Title',
        parent=styles['Heading1'],
        fontSize=20,
        textColor=colors.HexColor('#d97706'),
        spaceAfter=20,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    elements.append(Paragraph("Rezeptsammlung", title_style))
    elements.append(Paragraph(
        f"Alle {len(rezepte_data['rezepte'])} Rezepte für die Gemeinschaftsverpflegung", 
        styles['Normal']
    ))
    elements.append(Spacer(1, 20))
    
    # Inhaltsverzeichnis erstellen
    elements.append(Paragraph("Inhaltsverzeichnis", styles['Heading2']))
    for i, rezept in enumerate(rezepte_data['rezepte'], 1):
        elements.append(Paragraph(
            f"{i}. {rezept['name']} ({rezept['menu']})", 
            styles['Normal']
        ))
    
    elements.append(PageBreak())
    
    # Alle Rezepte durchgehen
    for i, rezept in enumerate(rezepte_data['rezepte']):
        if i > 0:
            elements.append(PageBreak())
        
        # Rezept-Header
        header_style = ParagraphStyle(
            'HeaderStyle',
            parent=styles['Heading1'],
            fontSize=18,
            textColor=colors.white,
            spaceAfter=5,
            fontName='Helvetica-Bold'
        )
        
        info_style = ParagraphStyle(
            'InfoStyle',
            parent=styles['Normal'],
            fontSize=11,
            textColor=colors.white
        )
        
        header_data = [
            [Paragraph(rezept['name'], header_style)],
            [Paragraph(f"{rezept['menu']} | {rezept.get('tag', '')}, Woche {rezept.get('woche', '')}", info_style)],
            [Paragraph(f"{rezept['portionen']} Portionen", info_style)]
        ]
        
        header_table = Table(header_data, colWidths=[170*mm])
        header_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#d97706')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('LEFTPADDING', (0, 0), (-1, -1), 15),
            ('TOPPADDING', (0, 0), (0, 0), 15),
            ('BOTTOMPADDING', (-1, -1), (-1, -1), 15),
        ]))
        
        elements.append(header_table)
        elements.append(Spacer(1, 20))
        
        # Zeiten
        zeiten_text = f"⏱️ Vorbereitung: {rezept['zeiten']['vorbereitung']} | Garzeit: {rezept['zeiten']['garzeit']}"
        elements.append(Paragraph(zeiten_text, styles['Normal']))
        elements.append(Spacer(1, 15))
        
        # Zutaten
        section_style = ParagraphStyle(
            'SectionStyle',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#d97706'),
            spaceAfter=10,
            fontName='Helvetica-Bold'
        )
        
        elements.append(Paragraph("Zutaten", section_style))
        for zutat in rezept['zutaten']:
            zutat_text = f"• <b>{zutat['menge']}</b> {zutat['name']}"
            elements.append(Paragraph(zutat_text, styles['Normal']))
        
        elements.append(Spacer(1, 15))
        
        # Zubereitung
        elements.append(Paragraph("Zubereitung", section_style))
        for j, schritt in enumerate(rezept['zubereitung'], 1):
            elements.append(Paragraph(f"<b>{j}.</b> {schritt}", styles['Normal']))
            elements.append(Spacer(1, 5))
        
        elements.append(Spacer(1, 15))
        
        # Nährwerte kompakt
        naehr = rezept['naehrwerte']
        naehr_text = f"<b>Nährwerte:</b> {naehr['kalorien']} | Protein: {naehr['protein']} | Fett: {naehr['fett']} | KH: {naehr['kohlenhydrate']}"
        elements.append(Paragraph(naehr_text, styles['Normal']))
    
    # PDF erstellen
    doc.build(elements)
    buffer.seek(0)
    return buffer
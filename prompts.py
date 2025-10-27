"""
Prompts für den Speiseplan-Generator
Alle Prompt-Templates zentral verwaltet
"""

def get_speiseplan_prompt(wochen, menulinien, menu_namen):
    """
    Erstellt den Prompt für die Speiseplan-Generierung
    
    Args:
        wochen (int): Anzahl der Wochen (1-4)
        menulinien (int): Anzahl der Menülinien (1-5)
        menu_namen (list): Liste der Menülinienbeschreibungen
        
    Returns:
        str: Formatierter Prompt
    """
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
- Reduzierter Salzgehalt, aber schmackhaft gewürzt

WICHTIG: JEDES Mittagessen MUSS mindestens 2-3 Beilagen haben!
Beispiele für gute Beilagenkombinationen:
- Salzkartoffeln, Buttergemüse, gemischter Salat
- Reis, Ratatouille, Gurkensalat
- Spätzle, Rotkohl, grüner Salat
- Kartoffelpüree, Erbsen-Möhren-Gemüse, Tomatensalat

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


def get_rezepte_prompt(speiseplan):
    """
    Erstellt den Prompt für die Rezept-Generierung
    
    Args:
        speiseplan (dict): Der generierte Speiseplan
        
    Returns:
        str: Formatierter Prompt
    """
    alle_gerichte = []
    for woche in speiseplan['speiseplan']['wochen']:
        for tag in woche['tage']:
            for menu in tag['menues']:
                beilagen = menu['mittagessen'].get('beilagen', [])
                beilagen_text = ', '.join(beilagen) if beilagen else "ohne Beilagen"
                alle_gerichte.append({
                    'gericht': menu['mittagessen']['hauptgericht'],
                    'beilagen': beilagen,
                    'beilagen_text': beilagen_text,
                    'woche': woche['woche'],
                    'tag': tag['tag'],
                    'menu': menu['menuName']
                })
    
    gerichte_liste = "\n".join([
        f"{i+1}. {g['gericht']} mit {g['beilagen_text']}" 
        for i, g in enumerate(alle_gerichte)
    ])
    
    anzahl_gerichte = len(alle_gerichte)
    
    return f"""Du bist ein erfahrener Küchenmeister für Gemeinschaftsverpflegung.

AUFGABE: Erstelle {anzahl_gerichte} detaillierte Rezepte für folgende Gerichte:

{gerichte_liste}

WICHTIG:
- Jedes Rezept MUSS das Hauptgericht UND ALLE Beilagen enthalten
- Portionsangaben für 10 Personen
- Genaue Mengenangaben in Gramm/Liter
- Zubereitungsschritte für ALLE Komponenten
- Nährwertangaben pro Portion
- Allergenkennzeichnung

JSON-FORMAT (GENAU SO):
{{
  "rezepte": [
    {{
      "name": "Gerichtname mit allen Beilagen",
      "woche": 1,
      "tag": "Montag",
      "menu": "Menüname",
      "portionen": 10,
      "zeiten": {{
        "vorbereitung": "X Minuten",
        "garzeit": "X Minuten",
        "gesamt": "X Minuten"
      }},
      "zutaten": [
        {{
          "name": "Zutat",
          "menge": "X g/ml",
          "hinweis": "Optional: für welche Komponente"
        }}
      ],
      "zubereitung": [
        "Schritt 1 ausführlich",
        "Schritt 2 ausführlich",
        "Schritt 3 ausführlich"
      ],
      "naehrwerte": {{
        "kalorien": "X kcal",
        "protein": "X g",
        "fett": "X g",
        "kohlenhydrate": "X g",
        "ballaststoffe": "X g"
      }},
      "allergene": ["Allergen1", "Allergen2"],
      "tipps": [
        "Tipp für Großküche 1",
        "Tipp für Großküche 2"
      ],
      "variationen": {{
        "pueriert": "Anleitung für pürierte Kost",
        "leichteKost": "Anpassung für leichte Vollkost"
      }}
    }}
  ]
}}

KRITISCH WICHTIG:
- Antworte NUR mit diesem JSON
- KEIN Text vor oder nach dem JSON
- KEINE Markdown-Formatierung
- KEINE Backticks
- Starte direkt mit {{ und ende mit }}
- Erstelle ein Rezept für JEDES der {anzahl_gerichte} Gerichte oben"""


def get_pruefung_prompt(speiseplan):
    """
    Erstellt den Prompt für die Qualitätsprüfung
    
    Args:
        speiseplan (dict): Der zu prüfende Speiseplan
        
    Returns:
        str: Formatierter Prompt
    """
    return f"""Du bist ein erfahrener diätisch ausgebildeter Küchenmeister mit Spezialisierung auf Seniorenheime, Krankenhäuser und Gemeinschaftsverpflegung. Du hast über 30 Jahre Erfahrung.

AUFGABE: Prüfe den folgenden Speiseplan auf:
1. Ernährungsphysiologische Ausgewogenheit
2. Seniorengerechte Zusammenstellung
3. Praktikabilität in der Gemeinschaftsverpflegung
4. Abwechslung und Attraktivität
5. Nährstoffdichte und -verteilung
6. Verträglichkeit und Konsistenz
7. Einhaltung von DGE-Richtlinien für Seniorenernährung
8. WICHTIG: Sind ausreichend Beilagen vorhanden?

SPEISEPLAN ZU PRÜFEN:
{json.dumps(speiseplan, ensure_ascii=False, indent=2)}

ANTWORTFORMAT (JSON):
{{
  "gesamtbewertung": "sehr gut / gut / zufriedenstellend / verbesserungswürdig",
  "punktzahl": "X/10",
  "positiveAspekte": [
    "Aspekt 1",
    "Aspekt 2",
    "Aspekt 3"
  ],
  "verbesserungsvorschlaege": [
    {{
      "bereich": "z.B. Woche 1, Tag 2, Menü 1",
      "problem": "Beschreibung des Problems",
      "empfehlung": "Konkrete Verbesserungsempfehlung"
    }}
  ],
  "naehrstoffanalyse": {{
    "protein": "Bewertung der Proteinversorgung",
    "vitamine": "Bewertung Vitaminversorgung",
    "mineralstoffe": "Bewertung Mineralstoffversorgung",
    "ballaststoffe": "Bewertung Ballaststoffversorgung"
  }},
  "praxistauglichkeit": {{
    "kuechentechnisch": "Bewertung der küchentechnischen Umsetzbarkeit",
    "wirtschaftlichkeit": "Bewertung der Wirtschaftlichkeit",
    "personalaufwand": "Bewertung des Personalaufwands"
  }},
  "fazit": "Zusammenfassende Bewertung und Gesamtempfehlung (2-3 Sätze)"
}}

NUR JSON! KEIN ANDERER TEXT!"""

import json
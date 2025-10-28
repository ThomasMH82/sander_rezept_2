import json

"""
Prompts für den Speiseplan-Generator
Alle Prompt-Templates zentral verwaltet
"""

# Einheitliche, klare Tool-Direktive – passt zu rufe_claude_api (tool_choice=return_json)
TOOL_DIRECTIVE = (
    "ANTWORTFORMAT: Antworte ausschließlich als Tool-Aufruf 'return_json'. "
    "Gib das komplette Ergebnis als EIN JSON-Objekt im Feld 'input' zurück. "
    "\n\nWICHTIGE JSON-REGELN:\n"
    "- Alle Strings in doppelten Anführungszeichen (\")\n"
    "- Kommata zwischen allen Feldern, KEINE trailing commas vor } oder ]\n"
    "- Alle Klammern müssen geschlossen sein: { } [ ]\n"
    "- Keine Kommentare im JSON\n"
    "- Keine Sonderzeichen oder Smart Quotes\n"
    "- JSON muss PERFEKT valide sein\n\n"
    "Kein Markdown, keine Erklärungen, keine Codeblöcke. "
    "Kein Text vor oder nach dem JSON-Objekt."
)

def get_speiseplan_prompt(wochen, menulinien, menu_namen):
    """
    Erstellt den Prompt für die Speiseplan-Generierung
    """
    menu_liste = "\n".join([f"{i+1}. {name}" for i, name in enumerate(menu_namen)])

    # Kompaktes, eindeutiges Schema. Doppelklammern weil f-String.
    schema = (
        "{{\n"
        "  \"speiseplan\": {{\n"
        "    \"wochen\": [\n"
        "      {{\n"
        "        \"woche\": 1,\n"
        "        \"tage\": [\n"
        "          {{\n"
        "            \"tag\": \"Montag\",\n"
        "            \"menues\": [\n"
        "              {{\n"
        "                \"menuName\": \"Name der Menülinie\",\n"
        "                \"fruehstueck\": {{\n"
        "                  \"hauptgericht\": \"Gericht\",\n"
        "                  \"beilagen\": [\"Beilage 1\", \"Beilage 2\"],\n"
        "                  \"getraenk\": \"Getränk\"\n"
        "                }},\n"
        "                \"mittagessen\": {{\n"
        "                  \"vorspeise\": \"Suppe/Vorspeise\",\n"
        "                  \"hauptgericht\": \"Hauptgericht\",\n"
        "                  \"beilagen\": [\n"
        "                    \"Beilage 1 (z.B. Kartoffeln)\",\n"
        "                    \"Beilage 2 (z.B. Gemüse)\",\n"
        "                    \"Beilage 3 (z.B. Salat)\"\n"
        "                  ],\n"
        "                  \"nachspeise\": \"Dessert\",\n"
        "                  \"naehrwerte\": {{\n"
        "                    \"kalorien\": \"ca. X kcal\",\n"
        "                    \"protein\": \"X g\"\n"
        "                  }},\n"
        "                  \"allergene\": [\"Liste der Allergene\"]\n"
        "                }},\n"
        "                \"zwischenmahlzeit\": \"Obst/Joghurt/etc.\",\n"
        "                \"abendessen\": {{\n"
        "                  \"hauptgericht\": \"Gericht\",\n"
        "                  \"beilagen\": [\"Beilage 1\", \"Beilage 2\"],\n"
        "                  \"getraenk\": \"Getränk\"\n"
        "                }}\n"
        "              }}\n"
        "            ]\n"
        "          }}\n"
        "        ]\n"
        "      }}\n"
        "    ],\n"
        "    \"menuLinien\": " + str(menulinien) + ",\n"
        "    \"menuNamen\": " + json.dumps(menu_namen, ensure_ascii=False) + "\n"
        "  }}\n"
        "}}"
    )

    return (
        f"Du bist ein diätisch ausgebildeter Küchenmeister mit 25+ Jahren Erfahrung in der "
        f"Gemeinschaftsverpflegung (Krankenhaus/Senioren). {TOOL_DIRECTIVE}\n\n"
        f"AUFGABE: Erstelle einen professionellen Speiseplan für {wochen} Woche(n) mit {menulinien} Menülinie(n).\n\n"
        f"MENÜLINIEN:\n{menu_liste}\n\n"
        "VORGABEN:\n"
        "- Seniorengerechte Kost, gut verträglich, ggf. weichere Konsistenzen\n"
        "- Hohe Nährstoffdichte; Protein ca. 1,0–1,2 g/kg; Ballaststoffe gut verträglich\n"
        "- Saisonale/regionale Produkte bevorzugt; reduzierte Salzmenge, dennoch schmackhaft\n"
        "- Pro Tag: Frühstück, Mittagessen (mit 2–3 Beilagen), Abendessen, Zwischenmahlzeit\n"
        "- Klare Portions-/Nährwertangaben zum Mittag; Allergenkennzeichnung\n\n"
        "BEILAGENBEISPIELE:\n"
        "- Salzkartoffeln, Buttergemüse, gemischter Salat\n"
        "- Reis, Ratatouille, Gurkensalat\n"
        "- Spätzle, Rotkohl, grüner Salat\n"
        "- Kartoffelpüree, Erbsen-Möhren-Gemüse, Tomatensalat\n\n"
        "ANTWORT-SCHEMA (JSON-OBJEKT):\n"
        f"{schema}\n"
        "HINWEIS: Gib die realen Inhalte vollständig zurück; das Schema ist nur die Struktur."
    )


def get_rezepte_prompt(speiseplan):
    """
    Erstellt den Prompt für die Rezept-Generierung
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
        f"{i+1}. {g['gericht']} mit {g['beilagen_text']}  |  Woche {g['woche']}  |  {g['tag']}  |  {g['menu']}"
        for i, g in enumerate(alle_gerichte)
    ])
    anzahl_gerichte = len(alle_gerichte)

    schema = (
        "{{\n"
        "  \"rezepte\": [\n"
        "    {{\n"
        "      \"name\": \"Gerichtname mit allen Beilagen\",\n"
        "      \"woche\": 1,\n"
        "      \"tag\": \"Montag\",\n"
        "      \"menu\": \"Menüname\",\n"
        "      \"portionen\": 10,\n"
        "      \"zeiten\": {{\n"
        "        \"vorbereitung\": \"X Minuten\",\n"
        "        \"garzeit\": \"X Minuten\",\n"
        "        \"gesamt\": \"X Minuten\"\n"
        "      }},\n"
        "      \"zutaten\": [\n"
        "        {{ \"name\": \"Zutat\", \"menge\": \"X g/ml\", \"hinweis\": \"Optional\" }}\n"
        "      ],\n"
        "      \"zubereitung\": [\n"
        "        \"Schritt 1 ausführlich\",\n"
        "        \"Schritt 2 ausführlich\",\n"
        "        \"Schritt 3 ausführlich\"\n"
        "      ],\n"
        "      \"naehrwerte\": {{\n"
        "        \"kalorien\": \"X kcal\",\n"
        "        \"protein\": \"X g\",\n"
        "        \"fett\": \"X g\",\n"
        "        \"kohlenhydrate\": \"X g\",\n"
        "        \"ballaststoffe\": \"X g\"\n"
        "      }},\n"
        "      \"allergene\": [\"Allergen1\", \"Allergen2\"],\n"
        "      \"tipps\": [\"Tipp 1\", \"Tipp 2\"],\n"
        "      \"variationen\": {{\n"
        "        \"pueriert\": \"Anleitung für pürierte Kost\",\n"
        "        \"leichteKost\": \"Anpassung für leichte Vollkost\"\n"
        "      }}\n"
        "    }}\n"
        "  ]\n"
        "}}"
    )

    return (
        f"Du bist ein Küchenmeister für Gemeinschaftsverpflegung. {TOOL_DIRECTIVE}\n\n"
        f"AUFGABE: Erstelle {anzahl_gerichte} detaillierte Rezepte für folgende Gerichte:\n\n"
        f"{gerichte_liste}\n\n"
        "ANFORDERUNGEN:\n"
        "- Jedes Rezept umfasst Hauptgericht UND alle Beilagen\n"
        "- Portionsangaben für 10 Personen; Mengen in g/ml\n"
        "- Zubereitungsschritte für alle Komponenten\n"
        "- Nährwerte pro Portion; Allergenkennzeichnung\n\n"
        "ANTWORT-SCHEMA (JSON-OBJEKT):\n"
        f"{schema}\n"
        "HINWEIS: Gib die realen Inhalte vollständig zurück; das Schema ist nur die Struktur."
    )


def get_pruefung_prompt(speiseplan):
    """
    Erstellt den Prompt für die Qualitätsprüfung
    """
    plan_json = json.dumps(speiseplan, ensure_ascii=False)

    schema = (
        "{{\n"
        "  \"gesamtbewertung\": \"sehr gut | gut | zufriedenstellend | verbesserungswürdig\",\n"
        "  \"punktzahl\": \"X/10\",\n"
        "  \"positiveAspekte\": [\"Aspekt 1\", \"Aspekt 2\"],\n"
        "  \"verbesserungsvorschlaege\": [\n"
        "    {{\n"
        "      \"bereich\": \"z.B. Woche 1, Tag 2, Menü 1\",\n"
        "      \"problem\": \"Beschreibung\",\n"
        "      \"empfehlung\": \"Konkrete Verbesserung\"\n"
        "    }}\n"
        "  ],\n"
        "  \"naehrstoffanalyse\": {{\n"
        "    \"protein\": \"Bewertung\",\n"
        "    \"vitamine\": \"Bewertung\",\n"
        "    \"mineralstoffe\": \"Bewertung\",\n"
        "    \"ballaststoffe\": \"Bewertung\"\n"
        "  }},\n"
        "  \"praxistauglichkeit\": {{\n"
        "    \"kuechentechnisch\": \"Bewertung\",\n"
        "    \"wirtschaftlichkeit\": \"Bewertung\",\n"
        "    \"personalaufwand\": \"Bewertung\"\n"
        "  }},\n"
        "  \"fazit\": \"2–3 Sätze Gesamtempfehlung\"\n"
        "}}"
    )

    return (
        f"Du bist ein diätisch ausgebildeter Küchenmeister (30+ Jahre) für Senioren/ Krankenhaus/ GV. "
        f"{TOOL_DIRECTIVE}\n\n"
        "AUFGABE: Prüfe den folgenden Speiseplan auf\n"
        "1) ernährungsphysiologische Ausgewogenheit, 2) Seniorengerechtigkeit, 3) Praktikabilität, "
        "4) Abwechslung/Attraktivität, 5) Nährstoffdichte/-verteilung, 6) Verträglichkeit/Konsistenz, "
        "7) DGE-Konformität, 8) ausreichende Beilagen.\n\n"
        "SPEISEPLAN (JSON):\n"
        f"{plan_json}\n\n"
        "ANTWORT-SCHEMA (JSON-OBJEKT):\n"
        f"{schema}\n"
        "HINWEIS: Nur strukturierte Bewertung nach Schema zurückgeben."
    )

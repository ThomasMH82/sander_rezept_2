import json

"""
Prompts für den Speiseplan-Generator
Alle Prompt-Templates zentral verwaltet - OPTIMIERTE VERSION
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

def get_speiseplan_prompt(wochen, menulinien, menu_namen, produktliste=None, produktlisten_prozent=0):
    """
    Erstellt den OPTIMIERTEN Prompt für die Speiseplan-Generierung
    MIT GARANTIERTER ABWECHSLUNG
    
    Args:
        wochen: Anzahl Wochen
        menulinien: Anzahl Menülinien
        menu_namen: Liste der Menünamen
        produktliste: Optional - Liste verfügbarer Produkte
        produktlisten_prozent: 0-100, wie viel % aus Liste stammen soll
    """
    menu_liste = "\n".join([f"{i+1}. {name}" for i, name in enumerate(menu_namen)])
    
    # Berechne Anzahl benötigter Gerichte
    anzahl_tage = wochen * 7
    anzahl_gerichte_gesamt = anzahl_tage * menulinien
    
    # Produktlisten-Anweisungen
    produktlisten_text = ""
    if produktliste and produktlisten_prozent > 0:
        produkte_string = "\n".join([f"- {p}" for p in produktliste[:100]])  # Max 100 anzeigen
        if len(produktliste) > 100:
            produkte_string += f"\n... und {len(produktliste) - 100} weitere"
        
        if produktlisten_prozent == 100:
            produktlisten_text = f"""
╔═══════════════════════════════════════════════════════════════════════════╗
║  📦 PRODUKTLISTE - STRIKTE VERWENDUNG (100%)                              ║
║                                                                             ║
║  Du MUSST AUSSCHLIESSLICH Produkte aus der folgenden Liste verwenden!     ║
║  KEINE anderen Zutaten sind erlaubt!                                       ║
╚═══════════════════════════════════════════════════════════════════════════╝

VERFÜGBARE PRODUKTE ({len(produktliste)} Artikel):
{produkte_string}

KRITISCH: Verwende NUR diese Produkte! Keine Ausnahmen!
"""
        elif produktlisten_prozent >= 80:
            produktlisten_text = f"""
╔═══════════════════════════════════════════════════════════════════════════╗
║  📦 PRODUKTLISTE - BEVORZUGTE VERWENDUNG ({produktlisten_prozent}%)                      ║
║                                                                             ║
║  Verwende HAUPTSÄCHLICH Produkte aus der Liste.                            ║
║  Nur bei Bedarf andere Standardzutaten verwenden.                          ║
╚═══════════════════════════════════════════════════════════════════════════╝

VERFÜGBARE PRODUKTE ({len(produktliste)} Artikel):
{produkte_string}

WICHTIG: Mindestens {produktlisten_prozent}% aller Zutaten müssen aus dieser Liste stammen!
"""
        elif produktlisten_prozent >= 50:
            produktlisten_text = f"""
═══════════════════════════════════════════════════════════════════════════
📦 PRODUKTLISTE - AUSGEWOGENE VERWENDUNG ({produktlisten_prozent}%)
═══════════════════════════════════════════════════════════════════════════

VERFÜGBARE PRODUKTE ({len(produktliste)} Artikel):
{produkte_string}

Ziel: Ca. {produktlisten_prozent}% der Zutaten aus dieser Liste, Rest Standard-Zutaten.
"""
        else:
            produktlisten_text = f"""
═══════════════════════════════════════════════════════════════════════════
📦 PRODUKTLISTE - FLEXIBLE VERWENDUNG ({produktlisten_prozent}%)
═══════════════════════════════════════════════════════════════════════════

VERFÜGBARE PRODUKTE ({len(produktliste)} Artikel):
{produkte_string}

Empfehlung: Nutze diese Produkte wo sinnvoll, aber freie Rezeptgestaltung hat Priorität.
"""
    
    # Kompaktes, eindeutiges Schema. Doppelklammern wegen f-String.
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

    return f"""Du bist ein diätisch ausgebildeter Küchenmeister mit 25+ Jahren Erfahrung in der Gemeinschaftsverpflegung (Krankenhaus/Senioren). {TOOL_DIRECTIVE}

╔═══════════════════════════════════════════════════════════════════════════╗
║  🚫 ABSOLUTE REGEL #1 - KEINE WIEDERHOLUNGEN VON HAUPTGERICHTEN 🚫       ║
║                                                                             ║
║  Du musst {anzahl_gerichte_gesamt} KOMPLETT UNTERSCHIEDLICHE Hauptgerichte erstellen!        ║
║                                                                             ║
║  ❌ VERBOTEN: "Seelachsfilet" an Montag UND Dienstag                      ║
║  ❌ VERBOTEN: "Hühnerfrikassee" mehr als 1x im gesamten Plan              ║
║  ✅ RICHTIG: Jeden Tag ein völlig anderes Hauptgericht                    ║
║                                                                             ║
║  BEVOR DU ANTWORTEST - PRÜFE:                                              ║
║  □ Kommt irgendein Hauptgericht 2x vor? → FEHLER! → NEUSTART!            ║
║  □ Sind alle {anzahl_gerichte_gesamt} Hauptgerichte unterschiedlich? → OK!              ║
╚═══════════════════════════════════════════════════════════════════════════╝

{produktlisten_text}

AUFGABE: Erstelle einen professionellen Speiseplan für {wochen} Woche(n) mit {menulinien} Menülinie(n).

MENÜLINIEN:
{menu_liste}

═══════════════════════════════════════════════════════════════════════════
SCHRITT-FÜR-SCHRITT VORGEHEN:
═══════════════════════════════════════════════════════════════════════════

SCHRITT 1: ERSTELLE ZUNÄCHST EINE LISTE MIT {anzahl_gerichte_gesamt} VERSCHIEDENEN HAUPTGERICHTEN

Beispiel-Gerichte zur Inspiration (nutze diese und viele weitere!):
- Rinderroulade mit Rotkohl
- Schweinebraten mit Knödeln
- Hähnchenbrust in Champignonsauce
- Scholle Müllerin Art
- Lachsfilet mit Kräuterbutter
- Gulasch mit Spätzle
- Geschnetzeltes Züricher Art
- Sauerbraten mit dunkler Soße
- Hackbraten mit Bratensoße
- Hausgemachte Frikadellen
- Wiener Schnitzel paniert
- Kasseler mit Sauerkraut
- Eisbein mit Erbspüree
- Schweinekotelett gegrillt
- Kalbsleber in Zwiebelsoße
- Ochsenschwanz geschmort
- Rinderbrust gekocht
- Zander gebraten
- Kabeljaufilet gedünstet
- Seelachsfilet in Dillsauce
- Matjeshering nach Hausfrauenart
- Forelle blau
- Putenschnitzel natur
- Hühnerfrikassee klassisch
- Gänsekeule geschmort
- Entenbrust rosa gebraten
- Hackfleischpfanne mediterran
- Königsberger Klopse
- Leberknödel in Brühe
- Nürnberger Rostbratwürste
- Currywurst hausgemacht
- Tafelspitz mit Meerrettichsauce
- Fischstäbchen hausgemacht
- Backfisch in Biersauce
- Heringssalat klassisch
- Matjesbrötchen nordisch
- Vegetarische Gemüsepfanne
- Käsespätzle überbacken
- Gemüselasagne
- Gefüllte Paprika mit Hackfleisch
- Rinderschmorbraten
- Schweineschnitzel Wiener Art
- Schollenfilet gedünstet
- Rotbarschfilet mediterran
- Hähnchenschenkel gegrillt
- Putengeschnetzeltes
- Kalbsschnitzel paniert
- Rindergeschnetzeltes
- Schweinegulasch ungarisch

WICHTIG: Jedes dieser Gerichte darf NUR EINMAL im gesamten Plan vorkommen!

═══════════════════════════════════════════════════════════════════════════

SCHRITT 2: WEISE JEDEM TAG EIN EINZIGARTIGES GERICHT ZU

Woche 1:
- Montag, Menü 1: [Gericht 1]
- Montag, Menü 2: [Gericht 2] ← MUSS komplett anders sein als Gericht 1!
- Dienstag, Menü 1: [Gericht 3] ← MUSS komplett anders sein als Gericht 1+2!
- Dienstag, Menü 2: [Gericht 4] ← MUSS komplett anders sein als Gericht 1+2+3!
... und so weiter für alle {anzahl_gerichte_gesamt} Gerichte!

═══════════════════════════════════════════════════════════════════════════

SCHRITT 3: VARIIERE AUCH DIE BEILAGEN

Kartoffelvariationen (abwechseln!):
- Salzkartoffeln, Petersilienkartoffeln, Kartoffelpüree, Bratkartoffeln, 
  Kroketten, Kartoffelgratin, Rosmarinkartoffeln, Herzoginkartoffeln

Weitere Beilagen:
- Butterreis, Basmatireis, Risotto, Nudeln, Spätzle, Knödel, Semmelknödel,
  Schupfnudeln, Gnocchi, Polenta

Gemüse (täglich anders!):
- Möhren, Erbsen, Blumenkohl, Brokkoli, Bohnen, Rotkohl, Wirsing, 
  Spinat, Rosenkohl, Kohlrabi, Schwarzwurzeln, Mangold, Fenchel

Salate (täglich anders!):
- Blattsalat, Gurkensalat, Tomatensalat, Krautsalat, Kartoffelsalat,
  Bohnensalat, Möhrensalat, Feldsalat, Radieschensalat

═══════════════════════════════════════════════════════════════════════════

NEGATIVBEISPIEL - SO NICHT!
═══════════════════════════════════════════════════════════════════════════
❌ FALSCH:
Montag: Seelachsfilet mit Petersilienkartoffeln
Dienstag: Seelachsfilet mit Petersilienkartoffeln ← FEHLER! Wiederholung!
Mittwoch: Seelachsfilet mit Petersilienkartoffeln ← FEHLER! Wiederholung!

✅ RICHTIG:
Montag: Seelachsfilet mit Petersilienkartoffeln
Dienstag: Rinderroulade mit Salzkartoffeln
Mittwoch: Hähnchenbrust mit Butterreis

═══════════════════════════════════════════════════════════════════════════

WEITERE VORGABEN:
═══════════════════════════════════════════════════════════════════════════
- Seniorengerechte Kost, gut verträglich, ggf. weichere Konsistenzen
- Hohe Nährstoffdichte; Protein ca. 1,0–1,2 g/kg; Ballaststoffe gut verträglich
- Saisonale/regionale Produkte bevorzugt; reduzierte Salzmenge, dennoch schmackhaft
- Pro Tag: Frühstück, Mittagessen (mit 3 Beilagen), Abendessen, Zwischenmahlzeit
- Klare Portions-/Nährwertangaben zum Mittag; Allergenkennzeichnung

BEI MEHREREN MENÜLINIEN AM SELBEN TAG:
- Komplett verschiedene Gerichte wählen
- Wenn Menü 1 Fisch hat → Menü 2 Fleisch oder vegetarisch
- Nicht beide Schnitzel, nicht beide Fisch, nicht beide ähnlich

═══════════════════════════════════════════════════════════════════════════
FINALE KONTROLLE VOR DEM ABSENDEN:
═══════════════════════════════════════════════════════════════════════════
Gehe jeden Tag durch und stelle sicher:
□ Montag Menü 1 ≠ Montag Menü 2
□ Montag Menü 1 ≠ Dienstag Menü 1
□ Montag Menü 1 ≠ Dienstag Menü 2
□ ... und so weiter für ALLE {anzahl_gerichte_gesamt} Kombinationen

WENN EIN GERICHT 2x VORKOMMT → BEGINNE VON VORNE!

═══════════════════════════════════════════════════════════════════════════

ANTWORT-SCHEMA (JSON-OBJEKT):
{schema}

HINWEIS: Gib die realen Inhalte vollständig zurück; das Schema ist nur die Struktur.
"""


def get_rezepte_prompt(speiseplan, produktliste=None, produktlisten_prozent=0):
    """
    Erstellt den Prompt für die Rezept-Generierung
    
    Args:
        speiseplan: Der generierte Speiseplan
        produktliste: Optional - Liste verfügbarer Produkte
        produktlisten_prozent: 0-100, wie viel % aus Liste stammen soll
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

    # Dedupliziere Gerichte basierend auf Hauptgericht und Beilagen
    # Verwende ein Dictionary mit (gericht, beilagen) als Key
    unique_gerichte = {}
    for gericht_info in alle_gerichte:
        # Erstelle einen eindeutigen Key aus Gericht und sortierten Beilagen
        key = (gericht_info['gericht'], tuple(sorted(gericht_info['beilagen'])))
        # Speichere nur das erste Vorkommen
        if key not in unique_gerichte:
            unique_gerichte[key] = gericht_info

    # Ersetze die Liste mit den deduplizierten Gerichten
    alle_gerichte = list(unique_gerichte.values())

    gerichte_liste = "\n".join([
        f"{i+1}. {g['gericht']} mit {g['beilagen_text']}  |  Woche {g['woche']}  |  {g['tag']}  |  {g['menu']}"
        for i, g in enumerate(alle_gerichte)
    ])
    anzahl_gerichte = len(alle_gerichte)
    
    # Produktlisten-Anweisungen für Rezepte
    produktlisten_text = ""
    if produktliste and produktlisten_prozent > 0:
        produkte_string = "\n".join([f"- {p}" for p in produktliste[:100]])
        if len(produktliste) > 100:
            produkte_string += f"\n... und {len(produktliste) - 100} weitere"
        
        if produktlisten_prozent == 100:
            produktlisten_text = f"""
╔═══════════════════════════════════════════════════════════════════════════╗
║  📦 ZUTATEN NUR AUS PRODUKTLISTE (100%)                                   ║
║                                                                             ║
║  ALLE Zutaten MÜSSEN aus der folgenden Liste stammen!                     ║
║  Verwende KEINE anderen Produkte oder Zutaten!                            ║
╚═══════════════════════════════════════════════════════════════════════════╝

VERFÜGBARE PRODUKTE ({len(produktliste)} Artikel):
{produkte_string}

KRITISCH: Jede Zutat im Rezept muss aus dieser Liste sein!
"""
        elif produktlisten_prozent >= 80:
            produktlisten_text = f"""
═══════════════════════════════════════════════════════════════════════════
📦 ZUTATEN HAUPTSÄCHLICH AUS PRODUKTLISTE ({produktlisten_prozent}%)
═══════════════════════════════════════════════════════════════════════════

VERFÜGBARE PRODUKTE ({len(produktliste)} Artikel):
{produkte_string}

WICHTIG: Mindestens {produktlisten_prozent}% der Zutaten (nach Gewicht) müssen aus dieser Liste sein!
Nur Gewürze, Öl und kleine Hilfszutaten dürfen zusätzlich verwendet werden.
"""
        else:
            produktlisten_text = f"""
═══════════════════════════════════════════════════════════════════════════
📦 VERFÜGBARE PRODUKTE - Verwendung empfohlen ({produktlisten_prozent}%)
═══════════════════════════════════════════════════════════════════════════

VERFÜGBARE PRODUKTE ({len(produktliste)} Artikel):
{produkte_string}

Nutze diese Produkte bevorzugt, aber ergänze nach Bedarf mit Standard-Zutaten.
"""

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
        f"{produktlisten_text}\n\n"
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
    MIT EXPLIZITER PRÜFUNG AUF WIEDERHOLUNGEN
    """
    plan_json = json.dumps(speiseplan, ensure_ascii=False)

    schema = (
        "{{\n"
        "  \"gesamtbewertung\": \"sehr gut | gut | zufriedenstellend | verbesserungswürdig\",\n"
        "  \"punktzahl\": \"X/10\",\n"
        "  \"positiveAspekte\": [\"Aspekt 1\", \"Aspekt 2\"],\n"
        "  \"abwechslungspruefung\": {{\n"
        "    \"wiederholungen\": [\"Liste aller wiederholten Hauptgerichte mit Angabe der Tage\"],\n"
        "    \"bewertung\": \"Bewertung der Abwechslung (KRITISCH wenn Wiederholungen vorhanden!)\",\n"
        "    \"anzahlEinzigartigerGerichte\": \"X von Y Gerichten sind einzigartig\"\n"
        "  }},\n"
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
        f"Du bist ein diätisch ausgebildeter Küchenmeister (30+ Jahre) für Senioren/Krankenhaus/GV. "
        f"{TOOL_DIRECTIVE}\n\n"
        "AUFGABE: Prüfe den folgenden Speiseplan auf\n\n"
        "═══════════════════════════════════════════════════════════════════════════\n"
        "PRIORITÄT 1 - ABWECHSLUNGSPRÜFUNG:\n"
        "═══════════════════════════════════════════════════════════════════════════\n"
        "- Gehe durch ALLE Hauptgerichte im gesamten Speiseplan\n"
        "- Liste ALLE Gerichte auf, die mehr als 1x vorkommen\n"
        "- Gib an: 'Seelachsfilet in Dillsauce' kommt vor am: Montag Menü 1, Dienstag Menü 1, ...\n"
        "- Wenn IRGENDEIN Gericht wiederholt wird → Gesamtbewertung maximal 'verbesserungswürdig'\n"
        "- Wenn mehr als 3 Gerichte wiederholt werden → Gesamtbewertung 'unzureichend'\n\n"
        "WEITERE PRÜFPUNKTE:\n"
        "2) Ernährungsphysiologische Ausgewogenheit\n"
        "3) Seniorengerechtigkeit\n"
        "4) Praktikabilität\n"
        "5) Attraktivität\n"
        "6) Nährstoffdichte/-verteilung\n"
        "7) Verträglichkeit/Konsistenz\n"
        "8) DGE-Konformität\n"
        "9) Ausreichende Beilagen\n\n"
        "SPEISEPLAN (JSON):\n"
        f"{plan_json}\n\n"
        "ANTWORT-SCHEMA (JSON-OBJEKT):\n"
        f"{schema}\n"
        "HINWEIS: Nur strukturierte Bewertung nach Schema zurückgeben. "
        "Sei besonders kritisch bei Wiederholungen von Hauptgerichten!"
    )


def get_analyse_prompt(text):
    """
    Erstellt den Prompt für die Speiseplan-Analyse

    Stellt einen diätischen Küchenmeister mit 25 Jahren Erfahrung in der
    Gemeinschaftsverpflegung dar, spezialisiert auf die Analyse von Speiseplänen
    und die Erstellung klarer Anweisungen für weitere diätische Küchenmeister.

    Args:
        text: Der zu analysierende Speiseplan-Text (aus PDF oder Webseite)

    Returns:
        str: Vollständiger Prompt für die Analyse
    """
    # Kürze Text wenn zu lang (max ca. 12000 Zeichen)
    max_text_length = 12000
    if len(text) > max_text_length:
        text = text[:max_text_length] + "\n\n[Text wurde gekürzt...]"

    schema = (
        "{{\n"
        "  \"gefunden\": true,\n"
        "  \"anzahl_tage\": 7,\n"
        "  \"anzahl_gerichte\": 14,\n"
        "  \"struktur\": \"Beschreibung der Speiseplan-Struktur (z.B. 'Wochenplan mit 2 Menülinien')\",\n"
        "  \"speiseplan\": [\n"
        "    {{\n"
        "      \"tag\": \"Montag, 20.01.2025\",\n"
        "      \"menues\": [\n"
        "        {{\n"
        "          \"name\": \"Menü 1\",\n"
        "          \"hauptgericht\": \"Schweinebraten\",\n"
        "          \"beilagen\": [\"Semmelknödel\", \"Blaukraut\", \"Salat\"],\n"
        "          \"zusatzinfo\": \"Allergene: Gluten, Milch | Kalorien: 650 kcal | Preis: 5,50 EUR\"\n"
        "        }}\n"
        "      ]\n"
        "    }}\n"
        "  ],\n"
        "  \"zusammenfassung\": \"Detaillierte Beschreibung des Speiseplans\",\n"
        "  \"fachliche_bewertung\": {{\n"
        "    \"abwechslung\": \"Bewertung der Vielfalt\",\n"
        "    \"ausgewogenheit\": \"Ernährungsphysiologische Bewertung\",\n"
        "    \"seniorengerechtigkeit\": \"Eignung für Senioren/Krankenhaus\",\n"
        "    \"saisonalitaet\": \"Verwendung saisonaler Produkte\",\n"
        "    \"gesamtnote\": \"sehr gut | gut | befriedigend | ausreichend | mangelhaft\"\n"
        "  }},\n"
        "  \"empfehlungen_fuer_kuechenmeister\": [\n"
        "    \"Konkrete Anweisung 1 für die Küche\",\n"
        "    \"Konkrete Anweisung 2 für die Küche\",\n"
        "    \"Konkrete Anweisung 3 für die Küche\"\n"
        "  ],\n"
        "  \"verbesserungsvorschlaege\": [\n"
        "    {{\n"
        "      \"bereich\": \"z.B. 'Mittwoch Menü 2'\",\n"
        "      \"problem\": \"Identifiziertes Problem\",\n"
        "      \"empfehlung\": \"Konkrete Verbesserung\"\n"
        "    }}\n"
        "  ],\n"
        "  \"besonderheiten\": [\n"
        "    \"Besonderheit 1 (z.B. Vegetarische Optionen vorhanden)\",\n"
        "    \"Besonderheit 2 (z.B. Regionale Produkte gekennzeichnet)\"\n"
        "  ],\n"
        "  \"hinweise\": \"Wichtige Hinweise zur Qualität der Extraktion und Analyse\"\n"
        "}}"
    )

    return f"""Du bist ein diätisch ausgebildeter Küchenmeister mit 25 Jahren Berufserfahrung in der Gemeinschaftsverpflegung (Krankenhaus, Seniorenheime, Kantinen). {TOOL_DIRECTIVE}

╔═══════════════════════════════════════════════════════════════════════════╗
║  👨‍🍳 DEINE EXPERTISE                                                       ║
╚═══════════════════════════════════════════════════════════════════════════╝

Du verfügst über:
✓ 25 Jahre praktische Erfahrung in der Großküche
✓ Diätische Ausbildung und Ernährungswissen
✓ Expertise in der Speiseplan-Gestaltung für verschiedene Zielgruppen
✓ Kenntnis der DGE-Qualitätsstandards
✓ Erfahrung mit Allergenkennzeichnung und Nährwertberechnung
✓ Wissen über saisonale und regionale Produkte
✓ Praktische Kenntnis der Küchenprozesse und Wirtschaftlichkeit

═══════════════════════════════════════════════════════════════════════════
DEINE AUFGABE: PROFESSIONELLE SPEISEPLAN-ANALYSE
═══════════════════════════════════════════════════════════════════════════

Analysiere den folgenden Text mit deinem Fachwissen und extrahiere alle
relevanten Informationen. Erstelle danach klare, präzise Anweisungen für
deine Kollegen in der Küche.

TEXT DES SPEISEPLANS:
───────────────────────────────────────────────────────────────────────────
{text}
───────────────────────────────────────────────────────────────────────────

═══════════════════════════════════════════════════════════════════════════
SCHRITT 1: INFORMATIONEN EXTRAHIEREN
═══════════════════════════════════════════════════════════════════════════

Identifiziere und extrahiere:
1. **Struktur**: Wie ist der Speiseplan aufgebaut?
   - Einzeltage oder Wochenplan?
   - Wie viele Menülinien?
   - Welche Bezeichnungen haben die Menüs?

2. **Gerichte**: Für jeden Tag und jedes Menü:
   - Hauptgericht (exakte Bezeichnung)
   - Alle Beilagen (einzeln aufgelistet)
   - Vorspeisen, Desserts falls vorhanden
   - Besondere Kennzeichnungen (vegetarisch, vegan, etc.)

3. **Zusatzinformationen** (falls vorhanden):
   - Allergene
   - Nährwerte
   - Preise
   - Portionsgrößen
   - Saisonale Hinweise

═══════════════════════════════════════════════════════════════════════════
SCHRITT 2: FACHLICHE BEWERTUNG
═══════════════════════════════════════════════════════════════════════════

Bewerte den Speiseplan professionell nach folgenden Kriterien:

1. **Abwechslung**:
   - Wiederholen sich Gerichte?
   - Ist die Vielfalt ausreichend?
   - Verschiedene Fleisch-/Fischsorten?

2. **Ernährungsphysiologische Ausgewogenheit**:
   - Ausreichend Protein, Vitamine, Ballaststoffe?
   - Gemüseanteil angemessen?
   - Einseitige Ernährung vermieden?

3. **Seniorengerechtigkeit** (falls zutreffend):
   - Weiche, gut kaubare Konsistenzen?
   - Verträgliche Zutaten?
   - Ausreichend Energie und Nährstoffe?

4. **Saisonalität & Regionalität**:
   - Werden saisonale Produkte verwendet?
   - Regionale Besonderheiten berücksichtigt?

5. **Praktikabilität**:
   - Umsetzbar in der Großküche?
   - Wirtschaftlich vertretbar?
   - Realistischer Personalaufwand?

═══════════════════════════════════════════════════════════════════════════
SCHRITT 3: ANWEISUNGEN FÜR KÜCHENMEISTER FORMULIEREN
═══════════════════════════════════════════════════════════════════════════

Erstelle 5-10 konkrete, klare Anweisungen für deine Kollegen:

✓ **Konkret**: "Für Mittwoch Semmelknödel vorbereiten, ca. 2 pro Person"
✗ **Nicht**: "Beilagen vorbereiten"

✓ **Praxisnah**: "Montags früh Schweinebraten marinieren für Dienstag"
✗ **Nicht**: "Fleisch vorbereiten"

✓ **Mit Begründung**: "Donnerstag Fisch, daher Mittwoch Fleischlieferung prüfen"
✗ **Nicht**: "Lieferung checken"

Beispiele für gute Anweisungen:
• "Am Montag 3 kg Kartoffeln schälen für Salzkartoffeln (Menü 1)"
• "Dienstag früh Rindfleisch für Gulasch würfeln und anbraten"
• "Allergenkennzeichnung für Menü 2 beachten: Gluten, Sellerie, Milch"
• "Saisonales Gemüse bevorzugt: Aktuell Kürbis, Kohl, Wurzelgemüse"
• "Für Senioren: Fleisch besonders zart garen (mindestens 2 Stunden)"

═══════════════════════════════════════════════════════════════════════════
SCHRITT 4: VERBESSERUNGSVORSCHLÄGE
═══════════════════════════════════════════════════════════════════════════

Identifiziere Schwachstellen und schlage Verbesserungen vor:
- Wo wiederholen sich Gerichte zu oft?
- Wo fehlt Abwechslung?
- Welche Beilagen könnten variiert werden?
- Gibt es ernährungsphysiologische Lücken?
- Sind bestimmte Allergene überrepräsentiert?

═══════════════════════════════════════════════════════════════════════════
WICHTIGE HINWEISE FÜR DEINE ANALYSE
═══════════════════════════════════════════════════════════════════════════

✓ Sei gründlich - extrahiere ALLE verfügbaren Informationen
✓ Sei präzise - verwende exakte Bezeichnungen aus dem Text
✓ Sei kritisch - benenne Schwachstellen klar und konstruktiv
✓ Sei praxisorientiert - deine Anweisungen müssen in der Küche umsetzbar sein
✓ Sei professionell - nutze dein Fachwissen und deine Erfahrung

✗ Erfinde KEINE Informationen, die nicht im Text stehen
✗ Spekuliere NICHT über fehlende Details
✗ Bei unklaren Informationen: Vermerke dies in "hinweise"

═══════════════════════════════════════════════════════════════════════════

ANTWORT-SCHEMA (JSON-OBJEKT):
{schema}

WICHTIG: Antworte NUR mit dem JSON-Objekt. Keine zusätzlichen Erklärungen!
"""
    

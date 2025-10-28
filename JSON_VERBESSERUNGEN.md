# JSON-Parsing Verbesserungen

## Übersicht der Änderungen (2025-10-28)

Dieses Update behebt JSON-Parsing-Fehler durch mehrere Verbesserungsschichten.

---

## 🔧 Hauptverbesserungen

### 1. **Robuste JSON-Bereinigung**
- Entfernung von Markdown-Code-Blöcken
- Ersetzung typografischer Anführungszeichen (Smart Quotes)
- Entfernung von JavaScript-Kommentaren
- Beseitigung von trailing commas
- Normalisierung von Whitespace

### 2. **Mehrschichtige Parsing-Strategien**
Die API-Funktion versucht nun 4 verschiedene Parsing-Methoden:
1. Direktes JSON-Parsing
2. Parsing nach Bereinigung
3. Extraktion des größten JSON-Objekts
4. Reparatur häufiger JSON-Fehler + Parsing

### 3. **Tool-Call Integration**
- Verwendung des `return_json` Tool-Calls für strukturierte Ausgabe
- System-Message mit klaren JSON-Regeln
- Temperature 0.0 für deterministische Ausgabe

### 4. **Verbesserte Prompts**
Die Prompts enthalten jetzt explizite JSON-Regeln:
- Doppelte Anführungszeichen für Strings
- Korrekte Komma-Platzierung
- Keine trailing commas
- Geschlossene Klammern
- Keine Sonderzeichen

### 5. **Besseres Error-Handling**
- Detaillierte Fehlermeldungen mit Debug-Informationen
- Preview der API-Response bei Fehlern
- UI-Expander mit Lösungsvorschlägen
- Timeout-Handling (180s)

---

## 📁 Geänderte Dateien

### `streamlit_app.py`
- **bereinige_json()**: Erweitert um Smart-Quote-Ersetzung und Kommentar-Entfernung
- **rufe_claude_api()**: Komplett überarbeitet mit Tool-Call-Support und Retry-Strategien
- **extract_json_object()**: Neue Funktion zum Extrahieren des größten JSON-Objekts
- **fix_common_json_errors()**: Neue Funktion zur automatischen JSON-Reparatur
- **UI-Verbesserungen**: Debug-Expander bei Fehlern

### `prompts.py`
- **TOOL_DIRECTIVE**: Erweitert um explizite JSON-Regeln
- Bessere Formatierungshinweise für das LLM

### `main_app.py`
- Bereits vorhandene `JSONProcessor` Klasse ist kompatibel
- Verwendet ebenfalls den `return_json` Tool-Call

---

## 🎯 Behobene Probleme

### Vorher:
❌ `JSON-Parsing-Fehler: Expecting ',' delimiter: line 1476 column 18`

### Nachher:
✅ Robustes Parsing mit mehreren Fallback-Strategien
✅ Automatische Reparatur häufiger JSON-Fehler
✅ Klare Fehlermeldungen mit Debug-Informationen
✅ Tool-Call für strukturierte Ausgabe

---

## 🚀 Verwendung

### Normale Verwendung:
```python
# Mit Tool-Call (Standard, empfohlen)
speiseplan, error = rufe_claude_api(prompt, api_key, use_json_mode=True)

# Ohne Tool-Call (Fallback)
speiseplan, error = rufe_claude_api(prompt, api_key, use_json_mode=False)
```

### Bei Fehlern:
1. Prüfen Sie die Debug-Informationen im UI-Expander
2. Reduzieren Sie ggf. die Anzahl der Wochen/Menülinien
3. Versuchen Sie es erneut (das LLM kann variieren)

---

## 🔍 Debug-Funktionen

Bei JSON-Parsing-Fehlern zeigt die Anwendung jetzt:
- Den vollständigen Fehlertext
- Preview der API-Response (erste + letzte 200 Zeichen)
- Anzahl der Parsing-Versuche
- Konkrete Lösungsvorschläge

---

## 📊 Technische Details

### JSON-Bereinigung:
```python
- Smart Quotes: " " „ → "
- Smart Apostrophes: ' ' ‚ → '
- Dashes: – — → -
- Zero-width spaces → (entfernt)
- Non-breaking spaces → (normale Leerzeichen)
- Trailing commas: ,} → }
- JS-Kommentare: // und /* */ → (entfernt)
```

### Parsing-Reihenfolge:
```
1. json.loads(text)
2. json.loads(bereinige_json(text))
3. json.loads(extract_json_object(text))
4. json.loads(fix_common_json_errors(bereinige_json(text)))
```

---

## ⚡ Performance

- Temperature: 0.0 (deterministisch)
- Timeout: 180s (erhöht für große Pläne)
- Max Tokens: 20000 (Speiseplan), 20000 (Rezepte)

---

## 📝 Best Practices

1. **Kleine Pläne zuerst testen**: Beginnen Sie mit 1 Woche, 2 Menülinien
2. **Bei Fehlern**: Nutzen Sie die Debug-Informationen
3. **Große Pläne**: Die inkrementelle Generierung (main_app.py) ist robuster
4. **API-Key**: Stellen Sie sicher, dass Ihr Key gültig ist

---

## 🆘 Support

Bei anhaltenden Problemen:
1. Prüfen Sie die Debug-Ausgabe
2. Testen Sie mit minimaler Konfiguration (1 Woche, 1 Menülinie)
3. Überprüfen Sie Ihre API-Key-Gültigkeit
4. Erstellen Sie ein Issue mit den Debug-Informationen

---

**Version:** 1.1.0
**Datum:** 2025-10-28
**Kompatibilität:** Alle bestehenden Daten bleiben erhalten

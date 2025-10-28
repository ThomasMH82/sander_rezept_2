# Rezept-Datenbank Anleitung

## Übersicht

Die Anwendung speichert alle generierten Rezepte automatisch in einer lokalen SQLite-Datenbank (`rezepte_bibliothek.db`).

## Features

### 1. Automatische Speicherung
- Beim Generieren von Rezepten können diese automatisch in der Datenbank gespeichert werden
- Checkbox "Rezepte in Datenbank speichern" aktivieren (standardmäßig aktiviert)

### 2. Rezept-Bibliothek
Die Bibliothek bietet:
- 📊 **Schnell-Statistiken**: Gesamt-Anzahl, Top-Rezept, Tags, Beste Bewertung
- 📋 **Detaillierte Statistiken**: Erweiterbarer Bereich mit:
  - Top 5 meistverwendete Rezepte
  - Top 5 best bewertete Rezepte
  - Zuletzt hinzugefügte Rezepte
  - Häufigste Tags
- 🔍 **Such-Funktion**: Suche nach Namen oder Zutaten
- 🏷️ **Tag-Filter**: Filtere nach Tags
- 📊 **Sortierung**: Nach Neueste, Name, Bewertung, Verwendungen
- ⭐ **Favoriten-Filter**: Zeige nur Rezepte mit Bewertung ≥ 4

### 3. Rezept-Verwaltung
Für jedes Rezept kannst du:
- ⭐ **Bewerten** (1-5 Sterne)
- 📄 **Als PDF exportieren**
- 🗑️ **Löschen**
- 🔄 **Verwendung tracken** (automatisch)

## Hilfsskripte

### Datenbank initialisieren
```bash
python init_database.py
```
Erstellt die Datenbank-Datei und die notwendigen Tabellen.

### Datenbank-Übersicht anzeigen
```bash
python zeige_datenbank_uebersicht.py
```
Zeigt eine detaillierte Übersicht über alle Rezepte in der Datenbank:
- Gesamtstatistiken
- Top-Listen (meistverwendet, best bewertet, neueste)
- Häufigste Tags
- Detaillierte Liste aller Rezepte

## Datenbank-Struktur

### Tabellen
- **rezepte**: Speichert alle Rezept-Informationen
- **verwendungen**: Tracking der Rezept-Verwendungen

### Gespeicherte Informationen
- Name, Menu-Linie, Portionen
- Zeiten (Vorbereitung, Garzeit, Gesamt)
- Zutaten, Zubereitung
- Nährwerte, Allergene
- Tipps, Variationen
- Tags (automatisch generiert)
- Bewertung, Verwendungs-Counter
- Erstellungs- und Verwendungs-Zeitstempel

## Deployment auf Streamlit.app

### Wichtig für Streamlit Cloud:
Auf Streamlit Cloud ist das Dateisystem **ephemeral** (temporär). Das bedeutet:
- Die Datenbank wird bei jedem Neustart gelöscht
- Verwende **Streamlit Secrets** oder **externe Datenbank** für persistente Speicherung

### Alternativen für persistente Speicherung:
1. **Streamlit File Upload/Download**: Exportiere die Datenbank als JSON
2. **SQLite auf persistentem Storage**: Z.B. mit Supabase, PostgreSQL
3. **Cloud Storage**: AWS S3, Google Cloud Storage

### Export/Import für Backup
```python
# In der App:
db.exportiere_als_json("rezepte_backup.json")
db.importiere_aus_json("rezepte_backup.json")
```

## Troubleshooting

### Datenbank existiert nicht
```bash
python init_database.py
```

### Datenbank ist leer
- Generiere Rezepte in der App
- Stelle sicher, dass "Rezepte in Datenbank speichern" aktiviert ist

### Fehler beim Speichern
- Prüfe Schreibrechte im Verzeichnis
- Stelle sicher, dass die Datenbank nicht von einem anderen Prozess verwendet wird

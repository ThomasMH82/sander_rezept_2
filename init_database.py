"""
Initialisiert die Rezept-Datenbank
Dieses Skript erstellt die Datenbank-Datei und die notwendigen Tabellen
"""

from rezept_datenbank import RezeptDatenbank
import os

def main():
    print("Initialisiere Rezept-Datenbank...")

    # Erstelle Datenbankinstanz (erstellt automatisch Tabellen)
    db = RezeptDatenbank()

    # Prüfe ob Datei existiert
    if os.path.exists(db.db_path):
        print(f"✓ Datenbank erfolgreich erstellt: {db.db_path}")

        # Hole Statistiken
        stats = db.hole_statistiken()
        print(f"\nDatenbank-Statistiken:")
        print(f"  - Anzahl Rezepte: {stats['anzahl_rezepte']}")

        if stats['anzahl_rezepte'] > 0:
            print(f"\n  Neueste Rezepte:")
            for name, datum in stats['neueste']:
                print(f"    • {name} ({datum[:10]})")
        else:
            print("\n  Noch keine Rezepte in der Datenbank.")
            print("  Generiere Rezepte in der App und aktiviere 'Rezepte in Datenbank speichern'")
    else:
        print("✗ Fehler beim Erstellen der Datenbank")

if __name__ == "__main__":
    main()

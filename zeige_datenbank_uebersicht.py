"""
Zeigt eine detaillierte Übersicht über alle Rezepte in der Datenbank
"""

from rezept_datenbank import RezeptDatenbank
import os

def zeige_rezept_uebersicht():
    """Zeigt eine formatierte Übersicht aller Rezepte"""

    db = RezeptDatenbank()

    if not os.path.exists(db.db_path):
        print("❌ Datenbank-Datei nicht gefunden!")
        print("Führen Sie 'python init_database.py' aus, um die Datenbank zu erstellen.")
        return

    # Hole Statistiken
    stats = db.hole_statistiken()

    print("\n" + "="*70)
    print("📊 REZEPT-DATENBANK ÜBERSICHT")
    print("="*70)

    # Grundlegende Statistiken
    print(f"\n📖 GESAMT-STATISTIKEN:")
    print(f"   Anzahl Rezepte: {stats['anzahl_rezepte']}")
    print(f"   Verschiedene Tags: {len(stats['tags'])}")

    # Meistverwendete Rezepte
    if stats['meistverwendet']:
        print(f"\n🏆 TOP 5 - MEISTVERWENDETE REZEPTE:")
        for i, (name, count) in enumerate(stats['meistverwendet'], 1):
            print(f"   {i}. {name}")
            print(f"      └─ {count}x verwendet")

    # Best bewertete Rezepte
    if stats['bestbewertet']:
        print(f"\n⭐ TOP 5 - BEST BEWERTETE REZEPTE:")
        for i, (name, bewertung) in enumerate(stats['bestbewertet'], 1):
            sterne = "⭐" * bewertung
            print(f"   {i}. {name}")
            print(f"      └─ {sterne} ({bewertung}/5)")

    # Neueste Rezepte
    if stats['neueste']:
        print(f"\n🆕 ZULETZT HINZUGEFÜGT:")
        for i, (name, datum) in enumerate(stats['neueste'], 1):
            print(f"   {i}. {name}")
            print(f"      └─ {datum[:10]}")

    # Tags
    if stats['tags']:
        print(f"\n🏷️ HÄUFIGSTE TAGS:")
        sorted_tags = sorted(stats['tags'].items(), key=lambda x: x[1], reverse=True)
        for i, (tag, count) in enumerate(sorted_tags[:10], 1):
            print(f"   {i}. {tag}: {count}x")

    print("\n" + "="*70)

    # Detaillierte Rezeptliste
    if stats['anzahl_rezepte'] > 0:
        print("\n📋 ALLE REZEPTE IM DETAIL:")
        print("-"*70)

        alle_rezepte = db.suche_rezepte(limit=1000)

        for i, rezept in enumerate(alle_rezepte, 1):
            print(f"\n{i}. {rezept['name']}")
            print(f"   ID: {rezept['id']}")
            print(f"   Menu-Linie: {rezept.get('menu_linie', 'N/A')}")
            print(f"   Portionen: {rezept.get('portionen', 'N/A')}")
            print(f"   Bewertung: {'⭐' * rezept.get('bewertung', 0)} ({rezept.get('bewertung', 0)}/5)")
            print(f"   Verwendet: {rezept.get('verwendet_count', 0)}x")
            print(f"   Erstellt am: {rezept['erstellt_am'][:10]}")

            # Zeiten
            if rezept.get('vorbereitung') or rezept.get('garzeit'):
                print(f"   Zeiten:")
                if rezept.get('vorbereitung'):
                    print(f"      - Vorbereitung: {rezept['vorbereitung']}")
                if rezept.get('garzeit'):
                    print(f"      - Garzeit: {rezept['garzeit']}")
                if rezept.get('gesamtzeit'):
                    print(f"      - Gesamt: {rezept['gesamtzeit']}")

            # Zutaten (erste 5)
            if rezept.get('zutaten'):
                print(f"   Zutaten ({len(rezept['zutaten'])} total):")
                for zutat in rezept['zutaten'][:5]:
                    print(f"      - {zutat.get('menge', '')} {zutat.get('name', '')}")
                if len(rezept['zutaten']) > 5:
                    print(f"      ... und {len(rezept['zutaten']) - 5} weitere")

            # Allergene
            if rezept.get('allergene'):
                print(f"   Allergene: {', '.join(rezept['allergene'])}")

            # Tags
            if rezept.get('tags'):
                print(f"   Tags: {', '.join(rezept['tags'])}")

            print("-"*70)

    print("\n✅ Übersicht abgeschlossen!\n")


def main():
    try:
        zeige_rezept_uebersicht()
    except Exception as e:
        print(f"\n❌ Fehler beim Anzeigen der Übersicht: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

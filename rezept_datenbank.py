"""
Rezept-Datenbank - Speichert und verwaltet generierte Rezepte
Verwendet SQLite für lokale Speicherung
"""

import sqlite3
import json
import os
from datetime import datetime
from typing import List, Dict, Optional, Tuple


class RezeptDatenbank:
    """
    Verwaltet eine lokale Datenbank mit allen generierten Rezepten
    """
    
    def __init__(self, db_path: str = "rezepte_bibliothek.db"):
        """
        Initialisiert die Datenbank
        
        Args:
            db_path (str): Pfad zur Datenbank-Datei
        """
        self.db_path = db_path
        self._erstelle_tabellen()
    
    def _erstelle_tabellen(self):
        """Erstellt die notwendigen Tabellen wenn sie nicht existieren"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Rezepte-Tabelle
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rezepte (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                menu_linie TEXT,
                portionen INTEGER DEFAULT 10,
                vorbereitung TEXT,
                garzeit TEXT,
                gesamtzeit TEXT,
                zutaten TEXT NOT NULL,
                zubereitung TEXT NOT NULL,
                naehrwerte TEXT,
                allergene TEXT,
                tipps TEXT,
                variationen TEXT,
                tags TEXT,
                erstellt_am TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                verwendet_count INTEGER DEFAULT 0,
                zuletzt_verwendet TIMESTAMP,
                bewertung INTEGER DEFAULT 0,
                notizen TEXT
            )
        """)
        
        # Index für schnellere Suche
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_name ON rezepte(name)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tags ON rezepte(tags)
        """)
        
        # Verwendungs-Historie
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS verwendungen (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rezept_id INTEGER,
                datum TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                speiseplan_info TEXT,
                FOREIGN KEY (rezept_id) REFERENCES rezepte(id)
            )
        """)
        
        conn.commit()
        conn.close()
    
    def speichere_rezept(self, rezept: Dict, tags: List[str] = None) -> int:
        """
        Speichert ein Rezept in der Datenbank
        
        Args:
            rezept (dict): Rezept-Daten
            tags (list): Optional, zusätzliche Tags
            
        Returns:
            int: ID des gespeicherten Rezepts
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Extrahiere Felder
        name = rezept.get('name', 'Unbekannt')
        menu_linie = rezept.get('menu', '')
        portionen = rezept.get('portionen', 10)
        
        zeiten = rezept.get('zeiten', {})
        vorbereitung = zeiten.get('vorbereitung', '')
        garzeit = zeiten.get('garzeit', '')
        gesamtzeit = zeiten.get('gesamt', '')
        
        zutaten = json.dumps(rezept.get('zutaten', []), ensure_ascii=False)
        zubereitung = json.dumps(rezept.get('zubereitung', []), ensure_ascii=False)
        naehrwerte = json.dumps(rezept.get('naehrwerte', {}), ensure_ascii=False)
        allergene = json.dumps(rezept.get('allergene', []), ensure_ascii=False)
        tipps = json.dumps(rezept.get('tipps', []), ensure_ascii=False)
        variationen = json.dumps(rezept.get('variationen', {}), ensure_ascii=False)
        
        # Automatische Tags aus dem Rezept
        auto_tags = []
        if menu_linie:
            auto_tags.append(menu_linie.lower())
        
        # Hauptzutat als Tag
        if rezept.get('zutaten') and len(rezept['zutaten']) > 0:
            hauptzutat = rezept['zutaten'][0]['name'].split()[0].lower()
            auto_tags.append(hauptzutat)
        
        # Benutzerdefinierte Tags
        if tags:
            auto_tags.extend([t.lower() for t in tags])
        
        tags_str = json.dumps(list(set(auto_tags)), ensure_ascii=False)
        
        # Prüfe ob Rezept bereits existiert
        cursor.execute("SELECT id FROM rezepte WHERE name = ?", (name,))
        existing = cursor.fetchone()
        
        if existing:
            # Update bestehendes Rezept
            rezept_id = existing[0]
            cursor.execute("""
                UPDATE rezepte SET
                    menu_linie = ?,
                    portionen = ?,
                    vorbereitung = ?,
                    garzeit = ?,
                    gesamtzeit = ?,
                    zutaten = ?,
                    zubereitung = ?,
                    naehrwerte = ?,
                    allergene = ?,
                    tipps = ?,
                    variationen = ?,
                    tags = ?
                WHERE id = ?
            """, (menu_linie, portionen, vorbereitung, garzeit, gesamtzeit,
                  zutaten, zubereitung, naehrwerte, allergene, tipps, 
                  variationen, tags_str, rezept_id))
        else:
            # Neues Rezept
            cursor.execute("""
                INSERT INTO rezepte (
                    name, menu_linie, portionen, vorbereitung, garzeit, gesamtzeit,
                    zutaten, zubereitung, naehrwerte, allergene, tipps, 
                    variationen, tags
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (name, menu_linie, portionen, vorbereitung, garzeit, gesamtzeit,
                  zutaten, zubereitung, naehrwerte, allergene, tipps, 
                  variationen, tags_str))
            rezept_id = cursor.lastrowid
        
        conn.commit()
        conn.close()
        
        return rezept_id
    
    def speichere_alle_rezepte(self, rezepte_data: Dict) -> int:
        """
        Speichert alle Rezepte aus einer Generierung
        
        Args:
            rezepte_data (dict): Dictionary mit 'rezepte'-Liste
            
        Returns:
            int: Anzahl gespeicherter Rezepte
        """
        if not rezepte_data or 'rezepte' not in rezepte_data:
            return 0
        
        count = 0
        for rezept in rezepte_data['rezepte']:
            self.speichere_rezept(rezept)
            count += 1
        
        return count
    
    def suche_rezepte(self, suchbegriff: str = "", tags: List[str] = None,
                      limit: int = 50) -> List[Dict]:
        """
        Sucht Rezepte nach Namen, Zutaten oder Tags
        
        Args:
            suchbegriff (str): Suchbegriff für Name
            tags (list): Tags zum Filtern
            limit (int): Maximum Anzahl Ergebnisse
            
        Returns:
            list: Liste von Rezept-Dictionaries
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        query = "SELECT * FROM rezepte WHERE 1=1"
        params = []
        
        if suchbegriff:
            query += " AND (name LIKE ? OR zutaten LIKE ?)"
            params.extend([f"%{suchbegriff}%", f"%{suchbegriff}%"])
        
        if tags:
            for tag in tags:
                query += " AND tags LIKE ?"
                params.append(f"%{tag.lower()}%")
        
        query += " ORDER BY verwendet_count DESC, erstellt_am DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        rezepte = []
        for row in rows:
            rezept = dict(row)
            # Parse JSON-Felder
            rezept['zutaten'] = json.loads(rezept['zutaten'])
            rezept['zubereitung'] = json.loads(rezept['zubereitung'])
            rezept['naehrwerte'] = json.loads(rezept['naehrwerte'])
            rezept['allergene'] = json.loads(rezept['allergene'])
            rezept['tipps'] = json.loads(rezept['tipps']) if rezept['tipps'] else []
            rezept['variationen'] = json.loads(rezept['variationen']) if rezept['variationen'] else {}
            rezept['tags'] = json.loads(rezept['tags']) if rezept['tags'] else []
            rezepte.append(rezept)
        
        conn.close()
        return rezepte
    
    def hole_rezept(self, rezept_id: int) -> Optional[Dict]:
        """
        Holt ein einzelnes Rezept
        
        Args:
            rezept_id (int): ID des Rezepts
            
        Returns:
            dict: Rezept-Daten oder None
        """
        rezepte = self.suche_rezepte()
        for rezept in rezepte:
            if rezept['id'] == rezept_id:
                return rezept
        return None
    
    def markiere_als_verwendet(self, rezept_id: int, speiseplan_info: str = ""):
        """
        Markiert ein Rezept als verwendet
        
        Args:
            rezept_id (int): ID des Rezepts
            speiseplan_info (str): Optional, Info zum Speiseplan
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Inkrementiere Counter
        cursor.execute("""
            UPDATE rezepte SET
                verwendet_count = verwendet_count + 1,
                zuletzt_verwendet = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (rezept_id,))
        
        # Füge Verwendungs-Eintrag hinzu
        cursor.execute("""
            INSERT INTO verwendungen (rezept_id, speiseplan_info)
            VALUES (?, ?)
        """, (rezept_id, speiseplan_info))
        
        conn.commit()
        conn.close()
    
    def bewerte_rezept(self, rezept_id: int, bewertung: int):
        """
        Bewertet ein Rezept (1-5 Sterne)
        
        Args:
            rezept_id (int): ID des Rezepts
            bewertung (int): Bewertung 1-5
        """
        if bewertung < 1 or bewertung > 5:
            return
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE rezepte SET bewertung = ? WHERE id = ?
        """, (bewertung, rezept_id))
        
        conn.commit()
        conn.close()
    
    def loesche_rezept(self, rezept_id: int):
        """
        Löscht ein Rezept
        
        Args:
            rezept_id (int): ID des Rezepts
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM verwendungen WHERE rezept_id = ?", (rezept_id,))
        cursor.execute("DELETE FROM rezepte WHERE id = ?", (rezept_id,))
        
        conn.commit()
        conn.close()
    
    def hole_statistiken(self) -> Dict:
        """
        Holt Statistiken über die Datenbank
        
        Returns:
            dict: Statistiken
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Anzahl Rezepte
        cursor.execute("SELECT COUNT(*) FROM rezepte")
        anzahl_rezepte = cursor.fetchone()[0]
        
        # Meistverwendete Rezepte
        cursor.execute("""
            SELECT name, verwendet_count 
            FROM rezepte 
            ORDER BY verwendet_count DESC 
            LIMIT 5
        """)
        meistverwendet = cursor.fetchall()
        
        # Neueste Rezepte
        cursor.execute("""
            SELECT name, erstellt_am 
            FROM rezepte 
            ORDER BY erstellt_am DESC 
            LIMIT 5
        """)
        neueste = cursor.fetchall()
        
        # Beste bewertete
        cursor.execute("""
            SELECT name, bewertung 
            FROM rezepte 
            WHERE bewertung > 0
            ORDER BY bewertung DESC 
            LIMIT 5
        """)
        bestbewertet = cursor.fetchall()
        
        # Alle Tags
        cursor.execute("SELECT tags FROM rezepte WHERE tags IS NOT NULL")
        alle_tags = []
        for row in cursor.fetchall():
            if row[0]:
                tags = json.loads(row[0])
                alle_tags.extend(tags)
        
        from collections import Counter
        tag_counts = Counter(alle_tags)
        
        conn.close()
        
        return {
            'anzahl_rezepte': anzahl_rezepte,
            'meistverwendet': meistverwendet,
            'neueste': neueste,
            'bestbewertet': bestbewertet,
            'tags': dict(tag_counts.most_common(10))
        }
    
    def exportiere_als_json(self, dateiname: str = "rezepte_backup.json"):
        """
        Exportiert alle Rezepte als JSON
        
        Args:
            dateiname (str): Dateiname für Export
        """
        rezepte = self.suche_rezepte(limit=10000)
        
        with open(dateiname, 'w', encoding='utf-8') as f:
            json.dump(rezepte, f, ensure_ascii=False, indent=2)
        
        return dateiname
    
    def importiere_aus_json(self, dateiname: str) -> int:
        """
        Importiert Rezepte aus JSON
        
        Args:
            dateiname (str): Dateiname zum Import
            
        Returns:
            int: Anzahl importierter Rezepte
        """
        with open(dateiname, 'r', encoding='utf-8') as f:
            rezepte = json.load(f)
        
        count = 0
        for rezept in rezepte:
            # Entferne DB-spezifische Felder
            rezept.pop('id', None)
            rezept.pop('erstellt_am', None)
            rezept.pop('verwendet_count', None)
            rezept.pop('zuletzt_verwendet', None)
            
            self.speichere_rezept(rezept)
            count += 1
        
        return count
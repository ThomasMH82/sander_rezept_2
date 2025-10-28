"""
Professioneller Speiseplan-Generator für Gemeinschaftsverpflegung
================================================================
Optimierte Version mit verbesserter Struktur und Fehlerbehandlung

Version: 3.0.0 - Professional Edition
Datum: 27.10.2025
Author: Diätisch ausgebildeter Küchenmeister-KI-Assistent
"""

import streamlit as st
import requests
import json
import re
import logging
from typing import List, Dict, Any, Tuple, Optional, Union
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import time
from functools import wraps

# ===================== KONFIGURATION =====================

# Version und Metadaten
VERSION = "3.0.0"
VERSION_DATUM = "27.10.2025"
BUILD_TYPE = "Professional"

# API-Konfiguration
API_BASE_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-sonnet-4-20250514"
API_TIMEOUT = 180
MAX_RETRIES = 3
RETRY_DELAY = 2

# Planungs-Parameter
SCHWELLWERT_AUFTEILUNG = 8
TAGE_PRO_GRUPPE = 2
MAX_WOCHEN = 4
MAX_MENULINIEN = 5
MIN_BEILAGEN = 2
MAX_TOKENS_SPEISEPLAN = 16000
MAX_TOKENS_REZEPTE = 10000
MAX_TOKENS_TAG = 6000

# UI-Konfiguration
PAGE_TITLE = "Speiseplan-Generator Professional"
PAGE_ICON = "👨‍🍳"
LAYOUT = "wide"

# ===================== LOGGING SETUP =====================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ===================== ENUMS UND DATENKLASSEN =====================

class MenuTyp(Enum):
    """Menülinien-Typen für die Gemeinschaftsverpflegung"""
    VOLLKOST = "Vollkost"
    VEGETARISCH = "Vegetarisch"
    SCHONKOST = "Schonkost"
    DIABETIKER = "Diabetiker"
    PUERIERKOST = "Pürierkost"
    VEGAN = "Vegan"
    GLUTENFREI = "Glutenfrei"
    LAKTOSEFREI = "Laktosefrei"

@dataclass
class APIConfig:
    """API-Konfigurationsobjekt"""
    api_key: str
    model: str = DEFAULT_MODEL
    max_retries: int = MAX_RETRIES
    timeout: int = API_TIMEOUT
    
    def __post_init__(self):
        if not self.api_key:
            raise ValueError("API-Key ist erforderlich")

@dataclass
class PlanConfig:
    """Speiseplan-Konfiguration"""
    wochen: int
    menulinien: int
    menu_namen: List[str]
    
    def __post_init__(self):
        # Validierung
        if not 1 <= self.wochen <= MAX_WOCHEN:
            raise ValueError(f"Wochen muss zwischen 1 und {MAX_WOCHEN} liegen")
        if not 1 <= self.menulinien <= MAX_MENULINIEN:
            raise ValueError(f"Menülinien muss zwischen 1 und {MAX_MENULINIEN} liegen")
        if len(self.menu_namen) != self.menulinien:
            raise ValueError("Anzahl der Menünamen muss mit Anzahl Menülinien übereinstimmen")

# ===================== DEKORATOREN =====================

def retry_on_error(max_retries: int = MAX_RETRIES, delay: float = RETRY_DELAY):
    """Decorator für automatische Wiederholung bei Fehlern"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger.warning(f"Versuch {attempt + 1} fehlgeschlagen: {e}")
                        time.sleep(delay * (attempt + 1))
                    else:
                        logger.error(f"Alle Versuche fehlgeschlagen: {e}")
            raise last_exception
        return wrapper
    return decorator

def measure_time(func):
    """Decorator zur Zeitmessung"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        end = time.time()
        logger.info(f"{func.__name__} dauerte {end - start:.2f} Sekunden")
        return result
    return wrapper

# ===================== JSON-VERARBEITUNG =====================

class JSONProcessor:
    """Robuste JSON-Verarbeitung mit mehreren Fallback-Strategien"""
    
    # Smart Quotes Mapping
    SMART_QUOTES = {
        """: '"', """: '"', "„": '"',
        "'": "'", "‚": "'", "'": "'",
        "–": "-", "—": "-"
    }
    
    @classmethod
    def sanitize_text(cls, text: str) -> str:
        """Bereinigt Text für JSON-Parsing"""
        if not text:
            return ""
            
        # Entferne Markdown-Code-Blöcke
        text = re.sub(r"```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = text.replace("```", "").strip()
        
        # Ersetze Smart Quotes
        for old, new in cls.SMART_QUOTES.items():
            text = text.replace(old, new)
        
        # Entferne Kommentare
        text = cls._remove_comments(text)
        
        # Entferne trailing commas
        text = re.sub(r",\s*(?=[}\]])", "", text)
        
        # Normalisiere Whitespace
        text = re.sub(r"\s+", " ", text)
        
        return text.strip()
    
    @staticmethod
    def _remove_comments(text: str) -> str:
        """Entfernt JavaScript-style Kommentare aus Text"""
        # Einzeilige Kommentare
        text = re.sub(r"//.*?$", "", text, flags=re.MULTILINE)
        # Mehrzeilige Kommentare
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
        return text
    
    @classmethod
    def parse_json_safe(cls, text: str) -> Optional[Dict]:
        """
        Versucht JSON mit mehreren Strategien zu parsen
        
        Returns:
            Geparster JSON oder None bei Fehler
        """
        if not text:
            return None
            
        # Strategie 1: Direktes Parsing
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # Strategie 2: Nach Bereinigung
        cleaned = cls.sanitize_text(text)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
        
        # Strategie 3: Extrahiere größtes JSON-Objekt
        extracted = cls._extract_json_object(cleaned)
        if extracted:
            try:
                return json.loads(extracted)
            except json.JSONDecodeError:
                pass
        
        # Strategie 4: Repariere fehlende Kommata
        repaired = cls._auto_fix_commas(cleaned)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError as e:
            logger.error(f"JSON-Parsing endgültig fehlgeschlagen: {e}")
            return None
    
    @staticmethod
    def _extract_json_object(text: str) -> Optional[str]:
        """Extrahiert das größte JSON-Objekt aus Text"""
        stack = []
        start_idx = None
        
        for i, char in enumerate(text):
            if char in '{[':
                if not stack:
                    start_idx = i
                stack.append(char)
            elif char in '}]':
                if stack:
                    opener = stack.pop()
                    expected = '{' if char == '}' else '['
                    if opener == expected and not stack and start_idx is not None:
                        return text[start_idx:i+1]
        
        return None
    
    @staticmethod
    def _auto_fix_commas(text: str) -> str:
        """Versucht fehlende Kommata automatisch zu ergänzen"""
        # Füge Kommata zwischen aufeinanderfolgenden JSON-Werten ein
        patterns = [
            (r'("\w+":\s*"[^"]*")\s+(")', r'\1, \2'),
            (r'("\w+":\s*\d+)\s+(")', r'\1, \2'),
            (r'("\w+":\s*true)\s+(")', r'\1, \2'),
            (r'("\w+":\s*false)\s+(")', r'\1, \2'),
            (r'("\w+":\s*null)\s+(")', r'\1, \2'),
            (r'(})\s+(")', r'\1, \2'),
            (r'(])\s+(")', r'\1, \2'),
        ]
        
        for pattern, replacement in patterns:
            text = re.sub(pattern, replacement, text)
        
        return text

# ===================== WOCHENTAGE =====================

WOCHENTAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]

# ===================== VALIDIERUNG =====================

class PlanValidator:
    """Validierung von Speiseplan-Strukturen"""
    
    @staticmethod
    def validate_day_structure(day: Dict[str, Any], menulinien: int) -> List[str]:
        """
        Validiert die Struktur eines Tages
        
        Returns:
            Liste von Fehlermeldungen (leer wenn valide)
        """
        errors = []
        
        if not isinstance(day, dict):
            return ["Tag-Struktur ist kein Dictionary"]
        
        # Prüfe Tag-Name
        if "tag" not in day:
            errors.append("Feld 'tag' fehlt")
        elif day["tag"] not in WOCHENTAGE:
            errors.append(f"Ungültiger Tag: {day.get('tag')}")
        
        # Prüfe Menüs
        if "menues" not in day:
            errors.append("Feld 'menues' fehlt")
            return errors
        
        if not isinstance(day["menues"], list):
            errors.append("'menues' ist keine Liste")
            return errors
        
        if len(day["menues"]) != menulinien:
            errors.append(f"Anzahl Menüs ({len(day['menues'])}) != {menulinien}")
        
        # Validiere jedes Menü
        for idx, menu in enumerate(day["menues"], 1):
            menu_errors = PlanValidator._validate_menu_structure(menu, idx)
            errors.extend(menu_errors)
        
        return errors
    
    @staticmethod
    def _validate_menu_structure(menu: Dict[str, Any], idx: int) -> List[str]:
        """Validiert die Struktur eines einzelnen Menüs"""
        errors = []
        
        if not isinstance(menu, dict):
            return [f"Menü {idx}: ist kein Dictionary"]
        
        # Pflichtfelder
        required_fields = ["menuName", "fruehstueck", "mittagessen", "abendessen"]
        for field in required_fields:
            if field not in menu:
                errors.append(f"Menü {idx}: Feld '{field}' fehlt")
        
        # Validiere Mittagessen im Detail
        if "mittagessen" in menu:
            mittag = menu["mittagessen"]
            if not isinstance(mittag, dict):
                errors.append(f"Menü {idx}: 'mittagessen' ist kein Dictionary")
            else:
                # Pflichtfelder für Mittagessen
                mittag_required = ["hauptgericht", "beilagen"]
                for field in mittag_required:
                    if field not in mittag:
                        errors.append(f"Menü {idx} Mittagessen: '{field}' fehlt")
                
                # Validiere Beilagen
                if "beilagen" in mittag:
                    if not isinstance(mittag["beilagen"], list):
                        errors.append(f"Menü {idx}: 'beilagen' ist keine Liste")
                    elif len(mittag["beilagen"]) < MIN_BEILAGEN:
                        errors.append(f"Menü {idx}: Zu wenige Beilagen ({len(mittag['beilagen'])} < {MIN_BEILAGEN})")
                
                # Validiere Nährwerte
                if "naehrwerte" in mittag and isinstance(mittag["naehrwerte"], dict):
                    nw = mittag["naehrwerte"]
                    if "kalorien" not in nw or "protein" not in nw:
                        errors.append(f"Menü {idx}: Unvollständige Nährwerte")
        
        return errors
    
    @staticmethod
    def validate_week_structure(week: Dict[str, Any], menulinien: int) -> List[str]:
        """Validiert die Struktur einer Woche"""
        errors = []
        
        if not isinstance(week, dict):
            return ["Wochen-Struktur ist kein Dictionary"]
        
        if "woche" not in week:
            errors.append("Feld 'woche' fehlt")
        
        if "tage" not in week:
            errors.append("Feld 'tage' fehlt")
            return errors
        
        if not isinstance(week["tage"], list):
            errors.append("'tage' ist keine Liste")
            return errors
        
        if len(week["tage"]) != 7:
            errors.append(f"Woche hat {len(week['tage'])} Tage statt 7")
        
        # Validiere jeden Tag
        for tag in week["tage"]:
            day_errors = PlanValidator.validate_day_structure(tag, menulinien)
            errors.extend(day_errors)
        
        return errors

# ===================== ANTHROPIC API CLIENT =====================

class AnthropicClient:
    """Verbesserter Anthropic API Client mit Fehlerbehandlung"""
    
    def __init__(self, config: APIConfig):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "x-api-key": config.api_key,
            "anthropic-version": API_VERSION
        })
    
    @retry_on_error(max_retries=3)
    def call_api(
        self,
        prompt: str,
        max_tokens: int = MAX_TOKENS_SPEISEPLAN,
        use_tool_call: bool = True
    ) -> Tuple[Optional[Dict], Optional[str], Optional[Dict]]:
        """
        Ruft die Anthropic API auf
        
        Returns:
            Tuple von (parsed_response, error_message, usage_info)
        """
        payload = self._build_payload(prompt, max_tokens, use_tool_call)
        
        try:
            response = self.session.post(
                API_BASE_URL,
                json=payload,
                timeout=self.config.timeout
            )
            
            if response.status_code != 200:
                error_msg = self._extract_error_message(response)
                logger.error(f"API-Fehler: {error_msg}")
                return None, error_msg, None
            
            data = response.json()
            parsed = self._extract_response(data)
            usage = data.get("usage", {})
            
            if parsed is None:
                return None, "Konnte Antwort nicht parsen", usage
            
            return parsed, None, usage
            
        except requests.exceptions.Timeout:
            error_msg = "API-Timeout: Anfrage dauerte zu lange"
            logger.error(error_msg)
            return None, error_msg, None
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Netzwerkfehler: {str(e)}"
            logger.error(error_msg)
            return None, error_msg, None
            
        except Exception as e:
            error_msg = f"Unerwarteter Fehler: {str(e)}"
            logger.error(error_msg)
            return None, error_msg, None
    
    def _build_payload(
        self,
        prompt: str,
        max_tokens: int,
        use_tool_call: bool
    ) -> Dict[str, Any]:
        """Erstellt das API-Payload"""
        
        base_payload = {
            "model": self.config.model,
            "max_tokens": max_tokens,
            "temperature": 0,
            "top_p": 0.1,
            "messages": [{"role": "user", "content": prompt}]
        }
        
        if use_tool_call:
            base_payload["tools"] = [{
                "name": "return_json",
                "description": "Rückgabe des Ergebnisses als strukturiertes JSON",
                "input_schema": {"type": "object"}
            }]
            base_payload["tool_choice"] = {"type": "tool", "name": "return_json"}
            base_payload["system"] = (
                "Du bist ein diätisch ausgebildeter Küchenmeister mit 25 Jahren Erfahrung. "
                "Gib dein Ergebnis AUSSCHLIESSLICH als Tool-Aufruf 'return_json' zurück. "
                "Keine Erklärungen, kein Markdown, nur strukturiertes JSON im Tool-Call."
            )
        
        return base_payload
    
    def _extract_response(self, data: Dict[str, Any]) -> Optional[Dict]:
        """Extrahiert die Antwort aus der API-Response"""
        
        # Versuche Tool-Call zu extrahieren
        content = data.get("content", [])
        for item in content:
            if isinstance(item, dict) and item.get("type") == "tool_use":
                tool_input = item.get("input")
                if tool_input:
                    return self._normalize_response(tool_input)
        
        # Fallback: Text-Response parsen
        if content and isinstance(content[0], dict):
            text = content[0].get("text", "")
            if text:
                parsed = JSONProcessor.parse_json_safe(text)
                if parsed:
                    return self._normalize_response(parsed)
        
        return None
    
    def _normalize_response(self, data: Any) -> Optional[Dict]:
        """Normalisiert die Response-Struktur"""
        if not isinstance(data, dict):
            return None
        
        # Prüfe auf erwartete Strukturen
        if any(key in data for key in ["speiseplan", "rezepte", "tag", "pruefung"]):
            return data
        
        # Prüfe verschachtelte Strukturen
        for key in ["data", "result", "output"]:
            if key in data and isinstance(data[key], dict):
                nested = data[key]
                if any(k in nested for k in ["speiseplan", "rezepte", "tag"]):
                    return nested
        
        return data
    
    def _extract_error_message(self, response: requests.Response) -> str:
        """Extrahiert Fehlermeldung aus Response"""
        try:
            error_data = response.json()
            if "error" in error_data:
                return error_data["error"].get("message", str(error_data["error"]))
            return response.text
        except:
            return f"Status {response.status_code}: {response.text[:200]}"

# ===================== PROMPT GENERATOR =====================

class PromptGenerator:
    """Generiert optimierte Prompts für verschiedene Aufgaben"""
    
    @staticmethod
    def create_day_prompt(tag: str, config: PlanConfig) -> str:
        """Erstellt Prompt für einen einzelnen Tag"""
        
        menu_list = "\n".join([
            f"  {i+1}. {name}"
            for i, name in enumerate(config.menu_namen)
        ])
        
        return f"""Du bist ein diätisch ausgebildeter Küchenmeister mit 25 Jahren Erfahrung in der Gemeinschaftsverpflegung.

AUFGABE: Erstelle einen professionellen Speiseplan für {tag} mit {config.menulinien} Menülinie(n).

MENÜLINIEN:
{menu_list}

QUALITÄTSKRITERIEN:
✓ Seniorengerechte Zubereitung (leicht kaubar, gut verdaulich)
✓ Ausgewogene Ernährung nach DGE-Standards
✓ Saisonale und regionale Zutaten bevorzugen
✓ Abwechslungsreich und appetitlich
✓ Berücksichtigung häufiger Unverträglichkeiten

STRUKTUR PRO MENÜLINIE:
• Frühstück: Hauptkomponente + Beilagen + Getränk
• Mittagessen: Vorspeise + Hauptgericht + 2-3 Beilagen + Nachspeise + Nährwerte + Allergene
• Zwischenmahlzeit: Kleine Stärkung am Nachmittag
• Abendessen: Hauptkomponente + Beilagen + Getränk

ANTWORT-SCHEMA (exakt einhalten):
{{
  "tag": "{tag}",
  "menues": [
    {{
      "menuName": "Exakter Name der Menülinie",
      "fruehstueck": {{
        "hauptgericht": "Beschreibung",
        "beilagen": ["Beilage 1", "Beilage 2"],
        "getraenk": "Getränk"
      }},
      "mittagessen": {{
        "vorspeise": "Beschreibung",
        "hauptgericht": "Ausführliche Beschreibung",
        "beilagen": ["Beilage 1", "Beilage 2", "Beilage 3"],
        "nachspeise": "Beschreibung",
        "naehrwerte": {{
          "kalorien": "ca. XXX kcal",
          "protein": "XX g",
          "fett": "XX g",
          "kohlenhydrate": "XX g",
          "ballaststoffe": "X g"
        }},
        "allergene": ["Gluten", "Milch", "Ei", ...]
      }},
      "zwischenmahlzeit": "Beschreibung",
      "abendessen": {{
        "hauptgericht": "Beschreibung",
        "beilagen": ["Beilage 1", "Beilage 2"],
        "getraenk": "Getränk"
      }}
    }}
  ]
}}

WICHTIG: Erstelle GENAU {config.menulinien} Menü-Einträge, einen für jede Menülinie."""
    
    @staticmethod
    def create_recipe_prompt(speiseplan: Dict[str, Any], max_recipes: int = 10) -> str:
        """Erstellt Prompt für Rezepte basierend auf Speiseplan"""
        
        # Extrahiere Hauptgerichte für Rezepte
        gerichte = []
        for woche in speiseplan.get("speiseplan", {}).get("wochen", []):
            woche_nr = woche.get("woche", 1)
            for tag in woche.get("tage", []):
                tag_name = tag.get("tag", "")
                for menu in tag.get("menues", []):
                    menu_name = menu.get("menuName", "")
                    hauptgericht = menu.get("mittagessen", {}).get("hauptgericht", "")
                    if hauptgericht:
                        gerichte.append({
                            "woche": woche_nr,
                            "tag": tag_name,
                            "menu": menu_name,
                            "gericht": hauptgericht
                        })
        
        # Limitiere Anzahl wenn nötig
        if len(gerichte) > max_recipes:
            gerichte = gerichte[:max_recipes]
        
        gerichte_text = "\n".join([
            f"- Woche {g['woche']}, {g['tag']}, {g['menu']}: {g['gericht']}"
            for g in gerichte
        ])
        
        return f"""Erstelle detaillierte Rezepte für folgende Hauptgerichte aus dem Speiseplan:

{gerichte_text}

ANFORDERUNGEN:
✓ Professionelle Großküchen-Rezepte (100 Portionen)
✓ Präzise Mengenangaben in kg/L/Stück
✓ HACCP-konforme Zubereitungsschritte
✓ Genaue Zeit- und Temperaturangaben
✓ Allergen-Kennzeichnung nach LMIV
✓ Nährwertangaben pro Portion

ANTWORT-SCHEMA:
{{
  "rezepte": [
    {{
      "name": "Exakter Name des Gerichts",
      "woche": X,
      "tag": "Wochentag",
      "menu": "Menülinie",
      "portionen": 100,
      "zeiten": {{
        "vorbereitung": "XX Minuten",
        "garzeit": "XX Minuten",
        "gesamt": "XX Minuten"
      }},
      "zutaten": [
        {{
          "name": "Zutat",
          "menge": "X kg/L/Stück",
          "hinweis": "optional: Verarbeitungshinweis"
        }}
      ],
      "zubereitung": [
        "Schritt 1: Detaillierte Anweisung mit Temperatur/Zeit",
        "Schritt 2: ...",
        "Schritt 3: ..."
      ],
      "naehrwerte": {{
        "kalorien": "XXX kcal",
        "protein": "XX g",
        "fett": "XX g",
        "kohlenhydrate": "XX g",
        "ballaststoffe": "X g",
        "salz": "X g"
      }},
      "allergene": ["Gluten", "Milch", ...],
      "tipps": "Professionelle Hinweise für optimale Qualität",
      "variationen": "Alternative Zubereitungsmöglichkeiten",
      "haccp": {{
        "kritische_punkte": ["Erhitzung auf min. 75°C Kerntemperatur"],
        "lagerung": "Kühlkette einhalten, max. 7°C"
      }}
    }}
  ]
}}"""
    
    @staticmethod
    def create_validation_prompt(speiseplan: Dict[str, Any]) -> str:
        """Erstellt Prompt für Qualitätsprüfung"""
        
        return f"""Prüfe den folgenden Speiseplan auf Qualität und DGE-Standards:

{json.dumps(speiseplan, ensure_ascii=False, indent=2)}

PRÜFKRITERIEN:
1. Nährstoffbalance (40 Punkte)
   - Ausgewogenheit der Makronährstoffe
   - Vitamine und Mineralstoffe
   - DGE-Empfehlungen

2. Abwechslung (30 Punkte)
   - Vielfalt der Gerichte
   - Keine Wiederholungen
   - Verschiedene Zubereitungsarten

3. Seniorengerechtheit (30 Punkte)
   - Leichte Kaubarkeit
   - Gute Verdaulichkeit
   - Appetitliche Präsentation

ANTWORT-SCHEMA:
{{
  "pruefung": {{
    "bewertungen": [
      {{
        "kategorie": "Nährstoffbalance",
        "punkte": X,
        "max_punkte": 40,
        "kommentar": "Detaillierte Bewertung",
        "verbesserungen": ["Vorschlag 1", "Vorschlag 2"]
      }}
    ],
    "gesamtpunkte": XX,
    "max_gesamtpunkte": 100,
    "note": "Sehr gut/Gut/Befriedigend/Ausreichend",
    "fazit": "Zusammenfassende Bewertung",
    "empfehlungen": ["Konkrete Verbesserungsvorschläge"]
  }}
}}"""

# ===================== PLAN GENERATOR =====================

class SpeiseplanGenerator:
    """Hauptklasse für die Speiseplan-Generierung"""
    
    def __init__(self, api_client: AnthropicClient):
        self.api_client = api_client
        self.prompt_generator = PromptGenerator()
        self.validator = PlanValidator()
        self.json_processor = JSONProcessor()
    
    @measure_time
    def generate_complete_plan(
        self,
        config: PlanConfig,
        progress_callback=None
    ) -> Tuple[Optional[Dict], Optional[Dict], Optional[Dict], Optional[str]]:
        """
        Generiert kompletten Speiseplan mit Rezepten und Prüfung
        
        Returns:
            Tuple von (speiseplan, rezepte, pruefung, error_message)
        """
        
        logger.info(f"Starte Generierung: {config.wochen} Wochen, {config.menulinien} Linien")
        
        # Entscheide Generierungsstrategie
        total_days = config.wochen * 7
        if total_days > 7 or config.menulinien > 3:
            return self._generate_incremental(config, progress_callback)
        else:
            return self._generate_direct(config, progress_callback)
    
    def _generate_incremental(
        self,
        config: PlanConfig,
        progress_callback=None
    ) -> Tuple[Optional[Dict], Optional[Dict], Optional[Dict], Optional[str]]:
        """Generiert Plan inkrementell (Woche für Woche, Tag für Tag)"""
        
        all_weeks = []
        all_recipes = []
        
        for week_num in range(1, config.wochen + 1):
            if progress_callback:
                progress_callback(f"Generiere Woche {week_num} von {config.wochen}")
            
            # Generiere Woche
            week_data, error = self._generate_week(config, week_num)
            if error:
                return None, None, None, error
            
            all_weeks.append(week_data)
            
            # Generiere Rezepte für diese Woche
            week_plan = {
                "speiseplan": {
                    "wochen": [week_data],
                    "menuLinien": config.menulinien,
                    "menuNamen": config.menu_namen
                }
            }
            
            recipes, recipe_error = self._generate_recipes(week_plan)
            if not recipe_error and recipes:
                all_recipes.extend(recipes.get("rezepte", []))
        
        # Kombiniere alles
        complete_plan = {
            "speiseplan": {
                "wochen": all_weeks,
                "menuLinien": config.menulinien,
                "menuNamen": config.menu_namen
            }
        }
        
        complete_recipes = {"rezepte": all_recipes} if all_recipes else None
        
        # Qualitätsprüfung
        validation = self._validate_plan(complete_plan)
        
        return complete_plan, complete_recipes, validation, None
    
    def _generate_week(
        self,
        config: PlanConfig,
        week_num: int
    ) -> Tuple[Optional[Dict], Optional[str]]:
        """Generiert eine einzelne Woche"""
        
        week_days = []
        
        for day in WOCHENTAGE:
            # Generiere Tag
            prompt = self.prompt_generator.create_day_prompt(day, config)
            result, error, _ = self.api_client.call_api(prompt, MAX_TOKENS_TAG)
            
            if error:
                logger.error(f"Fehler bei Tag {day}: {error}")
                # Retry einmal
                result, error, _ = self.api_client.call_api(prompt, MAX_TOKENS_TAG)
                if error:
                    return None, f"Fehler bei {day}: {error}"
            
            # Validiere Tag
            if result and "tag" in result and "menues" in result:
                errors = self.validator.validate_day_structure(result, config.menulinien)
                if errors:
                    logger.warning(f"Validierungsfehler für {day}: {errors}")
                    # Versuche zu korrigieren
                    result = self._fix_day_structure(result, config)
                
                week_days.append(result)
            else:
                return None, f"Ungültige Struktur für {day}"
        
        week_data = {
            "woche": week_num,
            "tage": week_days
        }
        
        return week_data, None
    
    def _fix_day_structure(self, day: Dict, config: PlanConfig) -> Dict:
        """Versucht, Strukturfehler in Tagesplan zu beheben"""
        
        # Stelle sicher, dass richtige Anzahl Menüs vorhanden
        if "menues" in day:
            menus = day["menues"]
            
            # Zu viele Menüs: Kürzen
            if len(menus) > config.menulinien:
                day["menues"] = menus[:config.menulinien]
            
            # Zu wenige Menüs: Duplizieren
            elif len(menus) < config.menulinien and menus:
                while len(day["menues"]) < config.menulinien:
                    # Dupliziere letztes Menü mit angepasstem Namen
                    last_menu = dict(menus[-1])
                    idx = len(day["menues"])
                    if idx < len(config.menu_namen):
                        last_menu["menuName"] = config.menu_namen[idx]
                    day["menues"].append(last_menu)
        
        return day
    
    def _generate_recipes(
        self,
        speiseplan: Dict
    ) -> Tuple[Optional[Dict], Optional[str]]:
        """Generiert Rezepte für Speiseplan"""
        
        prompt = self.prompt_generator.create_recipe_prompt(speiseplan)
        result, error, _ = self.api_client.call_api(prompt, MAX_TOKENS_REZEPTE)
        
        if error:
            logger.error(f"Fehler bei Rezeptgenerierung: {error}")
            return None, error
        
        if result and "rezepte" in result:
            return result, None
        
        return None, "Ungültige Rezeptstruktur"
    
    def _validate_plan(self, speiseplan: Dict) -> Optional[Dict]:
        """Führt Qualitätsprüfung durch"""
        
        try:
            prompt = self.prompt_generator.create_validation_prompt(speiseplan)
            result, error, _ = self.api_client.call_api(prompt, 8000)
            
            if not error and result:
                return result.get("pruefung")
        except Exception as e:
            logger.error(f"Fehler bei Validierung: {e}")
        
        return None
    
    def _generate_direct(
        self,
        config: PlanConfig,
        progress_callback=None
    ) -> Tuple[Optional[Dict], Optional[Dict], Optional[Dict], Optional[str]]:
        """Direkte Generierung für kleine Pläne"""
        
        # Generiere komplette Woche
        week_data, error = self._generate_week(config, 1)
        if error:
            return None, None, None, error
        
        complete_plan = {
            "speiseplan": {
                "wochen": [week_data],
                "menuLinien": config.menulinien,
                "menuNamen": config.menu_namen
            }
        }
        
        # Generiere Rezepte
        recipes, recipe_error = self._generate_recipes(complete_plan)
        
        # Qualitätsprüfung
        validation = self._validate_plan(complete_plan)
        
        return complete_plan, recipes, validation, None

# ===================== DATENBANK-INTEGRATION =====================

from prompts import get_speiseplan_prompt, get_rezepte_prompt, get_pruefung_prompt
from pdf_generator import erstelle_speiseplan_pdf, erstelle_rezept_pdf, erstelle_alle_rezepte_pdf
from rezept_datenbank import RezeptDatenbank
from cost_tracker import (
    CostTracker,
    zeige_kosten_anzeige,
    zeige_kosten_warnung_bei_grossen_plaenen,
    zeige_kosten_in_sidebar,
    KOSTEN_TRACKING_AKTIVIERT
)

# ===================== STREAMLIT UI =====================

class StreamlitUI:
    """Streamlit User Interface Handler"""
    
    def __init__(self):
        self.setup_page()
        self.db = self.get_database()
    
    def setup_page(self):
        """Konfiguriert Streamlit-Seite"""
        st.set_page_config(
            page_title=PAGE_TITLE,
            layout=LAYOUT,
            page_icon=PAGE_ICON,
            initial_sidebar_state="expanded"
        )
    
    @st.cache_resource
    def get_database(self):
        """Holt Datenbank-Instanz (cached)"""
        return RezeptDatenbank()
    
    def show_header(self):
        """Zeigt Header der Anwendung"""
        st.title(f"{PAGE_ICON} {PAGE_TITLE}")
        st.markdown(f"*Version {VERSION} - {BUILD_TYPE}*")
        st.markdown("**Für Gemeinschaftsverpflegung, Krankenhäuser & Senioreneinrichtungen**")
        st.divider()
    
    def show_sidebar(self) -> Tuple[str, PlanConfig, bool]:
        """
        Zeigt Sidebar mit Einstellungen
        
        Returns:
            Tuple von (api_key, plan_config, start_button_pressed)
        """
        with st.sidebar:
            st.header("⚙️ Konfiguration")
            
            # API Key
            api_key = st.text_input(
                "🔑 Anthropic API-Key",
                type="password",
                help="Ihr Claude API-Schlüssel",
                value=st.session_state.get("api_key", "")
            )
            st.session_state["api_key"] = api_key
            
            st.divider()
            
            # Plan-Konfiguration
            st.subheader("📋 Speiseplan-Einstellungen")
            
            wochen = st.number_input(
                "📅 Anzahl Wochen",
                min_value=1,
                max_value=MAX_WOCHEN,
                value=1,
                help=f"Maximal {MAX_WOCHEN} Wochen möglich"
            )
            
            menulinien = st.number_input(
                "🍽️ Anzahl Menülinien",
                min_value=1,
                max_value=MAX_MENULINIEN,
                value=2,
                help=f"Maximal {MAX_MENULINIEN} Linien möglich"
            )
            
            # Menü-Namen
            st.subheader("📝 Menülinien-Namen")
            menu_namen = []
            default_names = [typ.value for typ in MenuTyp]
            
            for i in range(menulinien):
                default = default_names[i] if i < len(default_names) else f"Menülinie {i+1}"
                name = st.text_input(
                    f"Linie {i+1}:",
                    value=default,
                    key=f"menu_{i}"
                )
                menu_namen.append(name)
            
            # Erweiterte Optionen
            with st.expander("🔧 Erweiterte Optionen"):
                st.checkbox("Automatische Qualitätsprüfung", value=True, key="auto_validation")
                st.checkbox("Rezepte in Datenbank speichern", value=True, key="save_to_db")
                st.checkbox("HACCP-Hinweise generieren", value=True, key="haccp_mode")
            
            # Kosten-Tracking
            if KOSTEN_TRACKING_AKTIVIERT():
                st.divider()
                zeige_kosten_in_sidebar()
            
            # Start-Button
            st.divider()
            start = st.button(
                "🚀 Speiseplan generieren",
                type="primary",
                use_container_width=True,
                disabled=not api_key
            )
            
            # Info-Box
            st.divider()
            with st.expander("ℹ️ Information"):
                st.info(
                    f"**Version:** {VERSION}  \n"
                    f"**Stand:** {VERSION_DATUM}  \n"
                    f"**Build:** {BUILD_TYPE}  \n"
                    f"**Entwickelt für:** Professionelle Großküchen"
                )
            
            try:
                config = PlanConfig(wochen, menulinien, menu_namen) if start else None
                return api_key, config, start
            except ValueError as e:
                st.error(str(e))
                return api_key, None, False
    
    def show_progress(self, message: str):
        """Zeigt Fortschrittsanzeige"""
        return st.spinner(message)
    
    def show_speiseplan_tab(self, speiseplan: Dict, pruefung: Optional[Dict] = None):
        """Zeigt Speiseplan-Tab"""
        st.header("📋 Ihr Speiseplan")
        
        # PDF-Export
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            try:
                pdf = erstelle_speiseplan_pdf(speiseplan)
                st.download_button(
                    "📄 Speiseplan als PDF exportieren",
                    data=pdf,
                    file_name=f"Speiseplan_{datetime.now().strftime('%Y%m%d')}.pdf",
                    mime="application/pdf",
                    type="primary"
                )
            except Exception as e:
                st.error(f"PDF-Export fehlgeschlagen: {e}")
        
        # Qualitätsprüfung
        if pruefung:
            with st.expander("🔍 Qualitätsbewertung", expanded=False):
                if "bewertungen" in pruefung:
                    cols = st.columns(len(pruefung["bewertungen"]))
                    for i, bew in enumerate(pruefung["bewertungen"]):
                        with cols[i]:
                            prozent = (bew["punkte"] / bew["max_punkte"]) * 100
                            st.metric(
                                bew["kategorie"],
                                f"{bew['punkte']}/{bew['max_punkte']}",
                                f"{prozent:.0f}%"
                            )
                            st.caption(bew["kommentar"])
                
                if "gesamtpunkte" in pruefung:
                    st.divider()
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric(
                            "Gesamtbewertung",
                            f"{pruefung['gesamtpunkte']}/{pruefung['max_gesamtpunkte']}"
                        )
                    with col2:
                        st.metric("Note", pruefung.get("note", "N/A"))
                    with col3:
                        prozent = (pruefung["gesamtpunkte"] / pruefung["max_gesamtpunkte"]) * 100
                        st.metric("Erfüllungsgrad", f"{prozent:.0f}%")
                
                if "fazit" in pruefung:
                    st.info(f"**Fazit:** {pruefung['fazit']}")
                
                if "empfehlungen" in pruefung and pruefung["empfehlungen"]:
                    st.warning("**Verbesserungsvorschläge:**")
                    for emp in pruefung["empfehlungen"]:
                        st.write(f"• {emp}")
        
        # Speiseplan-Anzeige
        for woche in speiseplan["speiseplan"]["wochen"]:
            st.subheader(f"📅 Woche {woche['woche']}")
            
            for tag in woche["tage"]:
                with st.container():
                    st.markdown(f"### {tag['tag']}")
                    
                    # Zeige alle Menülinien für diesen Tag
                    cols = st.columns(len(tag["menues"]))
                    
                    for idx, menu in enumerate(tag["menues"]):
                        with cols[idx]:
                            with st.expander(f"**{menu['menuName']}**", expanded=True):
                                # Frühstück
                                st.markdown("**🌅 Frühstück**")
                                st.write(menu["fruehstueck"]["hauptgericht"])
                                if menu["fruehstueck"].get("beilagen"):
                                    st.caption(f"Mit: {', '.join(menu['fruehstueck']['beilagen'])}")
                                if menu["fruehstueck"].get("getraenk"):
                                    st.caption(f"Getränk: {menu['fruehstueck']['getraenk']}")
                                
                                st.divider()
                                
                                # Mittagessen
                                st.markdown("**🍽️ Mittagessen**")
                                if menu["mittagessen"].get("vorspeise"):
                                    st.caption(f"*Vorspeise:* {menu['mittagessen']['vorspeise']}")
                                st.write(f"**{menu['mittagessen']['hauptgericht']}**")
                                if menu["mittagessen"].get("beilagen"):
                                    st.success(f"Beilagen: {', '.join(menu['mittagessen']['beilagen'])}")
                                if menu["mittagessen"].get("nachspeise"):
                                    st.caption(f"*Nachspeise:* {menu['mittagessen']['nachspeise']}")
                                
                                # Nährwerte
                                if menu["mittagessen"].get("naehrwerte"):
                                    nw = menu["mittagessen"]["naehrwerte"]
                                    st.caption(
                                        f"📊 {nw.get('kalorien', 'N/A')} | "
                                        f"Protein: {nw.get('protein', 'N/A')} | "
                                        f"Fett: {nw.get('fett', 'N/A')}"
                                    )
                                
                                # Allergene
                                if menu["mittagessen"].get("allergene"):
                                    st.warning(
                                        f"⚠️ Allergene: {', '.join(menu['mittagessen']['allergene'])}"
                                    )
                                
                                # Zwischenmahlzeit
                                if menu.get("zwischenmahlzeit"):
                                    st.divider()
                                    st.markdown("**☕ Zwischenmahlzeit**")
                                    st.caption(menu["zwischenmahlzeit"])
                                
                                # Abendessen
                                st.divider()
                                st.markdown("**🌙 Abendessen**")
                                st.write(menu["abendessen"]["hauptgericht"])
                                if menu["abendessen"].get("beilagen"):
                                    st.caption(f"Mit: {', '.join(menu['abendessen']['beilagen'])}")
                                if menu["abendessen"].get("getraenk"):
                                    st.caption(f"Getränk: {menu['abendessen']['getraenk']}")
                
                st.divider()
    
    def show_recipes_tab(self, rezepte_data: Optional[Dict]):
        """Zeigt Rezepte-Tab"""
        st.header("📖 Detaillierte Rezepte")
        
        if not rezepte_data or "rezepte" not in rezepte_data or not rezepte_data["rezepte"]:
            st.info("Keine Rezepte verfügbar.")
            return
        
        # Export-Optionen
        col1, col2 = st.columns(2)
        with col1:
            try:
                pdf = erstelle_alle_rezepte_pdf(rezepte_data)
                st.download_button(
                    "📚 Alle Rezepte als PDF",
                    data=pdf,
                    file_name=f"Rezepte_{datetime.now().strftime('%Y%m%d')}.pdf",
                    mime="application/pdf",
                    type="primary"
                )
            except Exception as e:
                st.error(f"PDF-Export fehlgeschlagen: {e}")
        
        # Filter-Optionen
        st.divider()
        col1, col2, col3 = st.columns(3)
        with col1:
            woche_filter = st.selectbox(
                "Woche filtern:",
                ["Alle"] + list(set(str(r.get("woche", 1)) for r in rezepte_data["rezepte"]))
            )
        with col2:
            menu_filter = st.selectbox(
                "Menülinie filtern:",
                ["Alle"] + list(set(r.get("menu", "") for r in rezepte_data["rezepte"]))
            )
        with col3:
            suche = st.text_input("🔍 Rezept suchen:")
        
        # Rezepte anzeigen
        for rezept in rezepte_data["rezepte"]:
            # Filter anwenden
            if woche_filter != "Alle" and str(rezept.get("woche", "")) != woche_filter:
                continue
            if menu_filter != "Alle" and rezept.get("menu", "") != menu_filter:
                continue
            if suche and suche.lower() not in rezept["name"].lower():
                continue
            
            with st.expander(
                f"{rezept['name']} - {rezept.get('menu', '')} (Woche {rezept.get('woche', '')})"
            ):
                # Header-Informationen
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.caption(f"📅 {rezept.get('tag', '')} • Woche {rezept.get('woche', '')}")
                    st.caption(f"👥 {rezept.get('portionen', 100)} Portionen")
                with col2:
                    zeiten = rezept.get("zeiten", {})
                    st.caption(f"⏱️ Vorbereitung: {zeiten.get('vorbereitung', 'N/A')}")
                    st.caption(f"🔥 Garzeit: {zeiten.get('garzeit', 'N/A')}")
                    st.caption(f"⏰ Gesamt: {zeiten.get('gesamt', 'N/A')}")
                with col3:
                    try:
                        pdf = erstelle_rezept_pdf(rezept)
                        st.download_button(
                            "📄 PDF Export",
                            data=pdf,
                            file_name=f"Rezept_{rezept['name'].replace(' ', '_')}.pdf",
                            mime="application/pdf"
                        )
                    except Exception as e:
                        st.error(f"Export fehlgeschlagen: {e}")
                
                # Zutaten
                st.markdown("### 🥘 Zutaten")
                zutaten_cols = st.columns(2)
                for i, zutat in enumerate(rezept.get("zutaten", [])):
                    with zutaten_cols[i % 2]:
                        text = f"• **{zutat['menge']}** {zutat['name']}"
                        if zutat.get("hinweis"):
                            text += f" _{zutat['hinweis']}_"
                        st.write(text)
                
                # Zubereitung
                st.markdown("### 👨‍🍳 Zubereitung")
                for i, schritt in enumerate(rezept.get("zubereitung", []), 1):
                    st.write(f"**Schritt {i}:** {schritt}")
                
                # Nährwerte
                st.markdown("### 📊 Nährwerte pro Portion")
                nw = rezept.get("naehrwerte", {})
                nw_cols = st.columns(6)
                nw_cols[0].metric("Kalorien", nw.get("kalorien", "N/A"))
                nw_cols[1].metric("Protein", nw.get("protein", "N/A"))
                nw_cols[2].metric("Fett", nw.get("fett", "N/A"))
                nw_cols[3].metric("KH", nw.get("kohlenhydrate", "N/A"))
                nw_cols[4].metric("Ballaststoffe", nw.get("ballaststoffe", "N/A"))
                nw_cols[5].metric("Salz", nw.get("salz", "N/A"))
                
                # Allergene
                if rezept.get("allergene"):
                    st.warning(f"⚠️ **Allergene:** {', '.join(rezept['allergene'])}")
                
                # HACCP-Hinweise
                if rezept.get("haccp"):
                    with st.expander("🔒 HACCP-Hinweise"):
                        haccp = rezept["haccp"]
                        if haccp.get("kritische_punkte"):
                            st.write("**Kritische Kontrollpunkte:**")
                            for punkt in haccp["kritische_punkte"]:
                                st.write(f"• {punkt}")
                        if haccp.get("lagerung"):
                            st.info(f"**Lagerung:** {haccp['lagerung']}")
                
                # Tipps & Variationen
                col1, col2 = st.columns(2)
                with col1:
                    if rezept.get("tipps"):
                        st.info(f"💡 **Tipp:** {rezept['tipps']}")
                with col2:
                    if rezept.get("variationen"):
                        st.success(f"🔄 **Variationen:** {rezept['variationen']}")
    
    def show_statistics_dashboard(self, stats):
        """Zeigt erweitertes Statistik-Dashboard"""
        with st.expander("📊 Detaillierte Statistiken & Übersicht", expanded=False):
            st.subheader("Datenbank-Übersicht")

            # Zusammenfassung in Spalten
            col1, col2, col3 = st.columns(3)

            with col1:
                st.markdown("### 📖 Rezepte")
                st.metric("Gesamt", stats["anzahl_rezepte"])
                if stats["neueste"]:
                    st.caption(f"Neuestes: {stats['neueste'][0][0]}")
                    st.caption(f"am {stats['neueste'][0][1][:10]}")

            with col2:
                st.markdown("### 🏆 Top-Rezepte")
                if stats["meistverwendet"]:
                    for i, (name, count) in enumerate(stats["meistverwendet"][:3], 1):
                        st.write(f"{i}. {name}: **{count}x** verwendet")
                else:
                    st.info("Noch keine Verwendungen")

            with col3:
                st.markdown("### ⭐ Best bewertet")
                if stats["bestbewertet"]:
                    for name, bewertung in stats["bestbewertet"][:3]:
                        st.write(f"{'⭐' * bewertung} {name}")
                else:
                    st.info("Noch keine Bewertungen")

            st.divider()

            # Tag-Cloud
            if stats["tags"]:
                st.markdown("### 🏷️ Häufigste Tags")
                col1, col2 = st.columns(2)

                with col1:
                    sorted_tags = sorted(stats["tags"].items(), key=lambda x: x[1], reverse=True)
                    for tag, count in sorted_tags[:5]:
                        st.write(f"🏷️ **{tag}**: {count}x")

                with col2:
                    # Top-Tags als Badge-ähnliche Darstellung
                    tags_str = " • ".join([f"{tag} ({count})" for tag, count in sorted_tags[:5]])
                    st.info(tags_str)

            st.divider()

            # Neueste Rezepte
            if stats["neueste"]:
                st.markdown("### 🆕 Zuletzt hinzugefügt")
                for name, datum in stats["neueste"]:
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.write(f"• {name}")
                    with col2:
                        st.caption(datum[:10])

    def show_library_tab(self):
        """Zeigt Rezept-Bibliothek"""
        st.header("📚 Rezept-Bibliothek")
        st.markdown("*Ihre Sammlung bewährter Rezepte*")

        # Statistiken
        stats = self.db.hole_statistiken()

        # Quick Stats
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("📖 Gesamt", stats["anzahl_rezepte"])
        with col2:
            if stats["meistverwendet"]:
                st.metric("🏆 Top-Rezept", stats["meistverwendet"][0][1])
        with col3:
            st.metric("🏷️ Tags", len(stats["tags"]))
        with col4:
            if stats["bestbewertet"]:
                st.metric("⭐ Beste Bewertung", f"{stats['bestbewertet'][0][1]}/5")

        # Erweiterte Statistiken
        self.show_statistics_dashboard(stats)

        st.divider()
        
        # Such- und Filteroptionen
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            suche = st.text_input("🔍 Suche:", placeholder="Name oder Zutat...")
        with col2:
            tags = st.multiselect(
                "🏷️ Tags:",
                options=list(stats["tags"].keys()) if stats["tags"] else []
            )
        with col3:
            sortierung = st.selectbox(
                "📊 Sortierung:",
                ["Neueste", "Name A-Z", "Beste Bewertung", "Meistverwendet"]
            )
        with col4:
            nur_favoriten = st.checkbox("⭐ Nur Favoriten", value=False)
        
        # Rezepte laden und filtern
        rezepte = self.db.suche_rezepte(suchbegriff=suche, tags=tags)
        
        if nur_favoriten:
            rezepte = [r for r in rezepte if r.get("bewertung", 0) >= 4]
        
        # Sortierung anwenden
        if sortierung == "Name A-Z":
            rezepte = sorted(rezepte, key=lambda x: x["name"])
        elif sortierung == "Neueste":
            rezepte = sorted(rezepte, key=lambda x: x["erstellt_am"], reverse=True)
        elif sortierung == "Beste Bewertung":
            rezepte = sorted(rezepte, key=lambda x: x.get("bewertung", 0), reverse=True)
        elif sortierung == "Meistverwendet":
            rezepte = sorted(rezepte, key=lambda x: x.get("verwendet_count", 0), reverse=True)
        
        st.divider()
        st.write(f"**{len(rezepte)}** Rezepte gefunden")
        
        if not rezepte:
            st.info("Keine Rezepte in der Bibliothek vorhanden.")
            return
        
        # Rezepte anzeigen
        for rezept in rezepte:
            with st.expander(
                f"{rezept['name']} {'⭐' * rezept.get('bewertung', 0)}"
            ):
                col1, col2, col3 = st.columns([3, 1, 1])
                
                with col1:
                    st.caption(f"👥 {rezept.get('portionen', 100)} Portionen")
                    if rezept.get("menu_linie"):
                        st.caption(f"🍽️ {rezept['menu_linie']}")
                    st.caption(
                        f"⏱️ {rezept.get('vorbereitung', 'N/A')} | "
                        f"{rezept.get('garzeit', 'N/A')}"
                    )
                    st.caption(
                        f"📅 Erstellt: {rezept['erstellt_am'][:10]} | "
                        f"🔄 {rezept.get('verwendet_count', 0)}x verwendet"
                    )
                
                with col2:
                    # Bewertung
                    neue_bewertung = st.select_slider(
                        "Bewertung:",
                        options=[0, 1, 2, 3, 4, 5],
                        value=rezept.get("bewertung", 0),
                        key=f"rating_{rezept['id']}"
                    )
                    if neue_bewertung != rezept.get("bewertung", 0):
                        self.db.bewerte_rezept(rezept["id"], neue_bewertung)
                        st.rerun()
                
                with col3:
                    # Aktionen
                    if st.button("📄 PDF", key=f"pdf_{rezept['id']}"):
                        try:
                            # Konvertiere für PDF-Export
                            export_rezept = {
                                "name": rezept["name"],
                                "portionen": rezept.get("portionen", 100),
                                "zeiten": {
                                    "vorbereitung": rezept.get("vorbereitung", ""),
                                    "garzeit": rezept.get("garzeit", ""),
                                    "gesamt": rezept.get("gesamtzeit", "")
                                },
                                "zutaten": rezept.get("zutaten", []),
                                "zubereitung": rezept.get("zubereitung", []),
                                "naehrwerte": rezept.get("naehrwerte", {}),
                                "allergene": rezept.get("allergene", []),
                                "tipps": rezept.get("tipps", ""),
                                "variationen": rezept.get("variationen", "")
                            }
                            pdf = erstelle_rezept_pdf(export_rezept)
                            st.download_button(
                                "Download",
                                data=pdf,
                                file_name=f"{rezept['name'].replace(' ', '_')}.pdf",
                                mime="application/pdf",
                                key=f"dl_{rezept['id']}"
                            )
                        except Exception as e:
                            st.error(f"Export fehlgeschlagen: {e}")
                    
                    if st.button("🗑️ Löschen", key=f"del_{rezept['id']}"):
                        self.db.loesche_rezept(rezept["id"])
                        st.success("Rezept gelöscht")
                        st.rerun()

# ===================== HAUPTPROGRAMM =====================

def main():
    """Hauptfunktion der Anwendung"""
    
    # Initialisiere UI
    ui = StreamlitUI()
    ui.show_header()
    
    # Hole Konfiguration aus Sidebar
    api_key, config, start = ui.show_sidebar()
    
    if not api_key:
        st.warning("⚠️ Bitte geben Sie Ihren Anthropic API-Key in der Sidebar ein.")
        return
    
    # Generierung starten
    if start and config:
        try:
            # Initialisiere API-Client und Generator
            api_config = APIConfig(api_key=api_key)
            api_client = AnthropicClient(api_config)
            generator = SpeiseplanGenerator(api_client)
            
            # Kosten-Warnung bei großen Plänen
            if KOSTEN_TRACKING_AKTIVIERT():
                zeige_kosten_warnung_bei_grossen_plaenen(
                    config.wochen,
                    config.menulinien
                )
            
            # Progress-Container
            progress_container = st.container()
            with progress_container:
                with st.spinner("🔄 Generiere Speiseplan..."):
                    # Generiere Plan
                    speiseplan, rezepte, pruefung, error = generator.generate_complete_plan(
                        config,
                        progress_callback=lambda msg: st.info(msg)
                    )
                    
                    if error:
                        st.error(f"❌ Fehler: {error}")
                        return
                    
                    # Speichere in Session State
                    st.session_state["speiseplan"] = speiseplan
                    st.session_state["rezepte"] = rezepte
                    st.session_state["pruefung"] = pruefung
                    
                    # Speichere Rezepte in Datenbank
                    if rezepte and st.session_state.get("save_to_db", True):
                        try:
                            ui.db.speichere_alle_rezepte(rezepte)
                            st.success("✅ Rezepte in Datenbank gespeichert")
                        except Exception as e:
                            st.warning(f"⚠️ Datenbank-Speicherung fehlgeschlagen: {e}")
                    
                    st.success("✅ Speiseplan erfolgreich generiert!")
                    st.balloons()
        
        except Exception as e:
            st.error(f"❌ Unerwarteter Fehler: {str(e)}")
            logger.exception("Fehler bei Generierung")
            return
    
    # Zeige Ergebnisse in Tabs
    if st.session_state.get("speiseplan"):
        tab1, tab2, tab3 = st.tabs([
            "📋 Speiseplan",
            "📖 Rezepte",
            "📚 Bibliothek"
        ])
        
        with tab1:
            ui.show_speiseplan_tab(
                st.session_state["speiseplan"],
                st.session_state.get("pruefung")
            )
        
        with tab2:
            ui.show_recipes_tab(st.session_state.get("rezepte"))
        
        with tab3:
            ui.show_library_tab()
    
    else:
        # Zeige Willkommens-Nachricht
        st.info(
            "👋 Willkommen beim Professionellen Speiseplan-Generator!\n\n"
            "Bitte konfigurieren Sie Ihre Einstellungen in der Sidebar und "
            "klicken Sie auf 'Speiseplan generieren' um zu beginnen."
        )
        
        # Quick-Access zur Bibliothek
        if st.button("📚 Rezept-Bibliothek öffnen"):
            ui.show_library_tab()

# ===================== ENTRY POINT =====================

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        st.error(f"Kritischer Fehler: {str(e)}")
        logger.exception("Kritischer Anwendungsfehler")
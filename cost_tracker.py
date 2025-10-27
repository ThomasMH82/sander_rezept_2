"""
Kosten-Tracker für Claude API-Nutzung
Berechnet und zeigt die Kosten der API-Aufrufe an
"""

import streamlit as st

# Claude Sonnet 4 Preise (Stand: Oktober 2024)
# Diese können Sie anpassen wenn sich die Preise ändern
PREIS_PRO_1M_INPUT_TOKENS = 3.0   # $3 pro 1M Input-Tokens
PREIS_PRO_1M_OUTPUT_TOKENS = 15.0  # $15 pro 1M Output-Tokens


class CostTracker:
    """
    Tracked die Kosten von API-Aufrufen
    """
    
    def __init__(self):
        """Initialisiert den Cost-Tracker"""
        self.reset()
    
    def reset(self):
        """Setzt alle Zähler zurück"""
        self.input_tokens = 0
        self.output_tokens = 0
        self.api_calls = 0
    
    def add_usage(self, usage_data):
        """
        Fügt Nutzungsdaten hinzu
        
        Args:
            usage_data (dict): Usage-Daten von der API-Response
                Format: {'input_tokens': int, 'output_tokens': int}
        """
        if usage_data:
            self.input_tokens += usage_data.get('input_tokens', 0)
            self.output_tokens += usage_data.get('output_tokens', 0)
            self.api_calls += 1
    
    def get_costs(self):
        """
        Berechnet die Gesamtkosten
        
        Returns:
            dict: Dictionary mit Kostendetails
        """
        input_cost = (self.input_tokens / 1_000_000) * PREIS_PRO_1M_INPUT_TOKENS
        output_cost = (self.output_tokens / 1_000_000) * PREIS_PRO_1M_OUTPUT_TOKENS
        total_cost = input_cost + output_cost
        
        return {
            'input_tokens': self.input_tokens,
            'output_tokens': self.output_tokens,
            'total_tokens': self.input_tokens + self.output_tokens,
            'input_cost': input_cost,
            'output_cost': output_cost,
            'total_cost': total_cost,
            'api_calls': self.api_calls
        }
    
    def format_tokens(self, tokens):
        """
        Formatiert Token-Anzahl lesbar
        
        Args:
            tokens (int): Anzahl Tokens
            
        Returns:
            str: Formatierte String-Darstellung
        """
        if tokens >= 1_000_000:
            return f"{tokens / 1_000_000:.2f}M"
        elif tokens >= 1_000:
            return f"{tokens / 1_000:.1f}K"
        else:
            return str(tokens)
    
    def format_cost(self, cost):
        """
        Formatiert Kosten lesbar
        
        Args:
            cost (float): Kosten in USD
            
        Returns:
            str: Formatierte Kosten mit $-Zeichen
        """
        if cost < 0.01:
            return f"${cost:.4f}"
        elif cost < 1:
            return f"${cost:.3f}"
        else:
            return f"${cost:.2f}"


def zeige_kosten_anzeige(cost_tracker):
    """
    Zeigt eine schöne Kostenanzeige in Streamlit
    
    Args:
        cost_tracker (CostTracker): Der Cost-Tracker mit den Daten
    """
    costs = cost_tracker.get_costs()
    
    # Kosten-Container mit speziellem Styling
    st.markdown("---")
    st.markdown("### 💰 Kosten dieser Generierung")
    
    # Haupt-Metriken
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="Gesamtkosten",
            value=cost_tracker.format_cost(costs['total_cost']),
            help="Gesamtkosten für alle API-Aufrufe"
        )
    
    with col2:
        st.metric(
            label="Input-Tokens",
            value=cost_tracker.format_tokens(costs['input_tokens']),
            help=f"Kosten: {cost_tracker.format_cost(costs['input_cost'])}"
        )
    
    with col3:
        st.metric(
            label="Output-Tokens",
            value=cost_tracker.format_tokens(costs['output_tokens']),
            help=f"Kosten: {cost_tracker.format_cost(costs['output_cost'])}"
        )
    
    with col4:
        st.metric(
            label="API-Aufrufe",
            value=costs['api_calls'],
            help="Anzahl der Claude API-Aufrufe"
        )
    
    # Detaillierte Aufschlüsselung in Expander
    with st.expander("📊 Detaillierte Kostenaufschlüsselung"):
        st.markdown(f"""
        **Token-Nutzung:**
        - Input-Tokens: {costs['input_tokens']:,} ({cost_tracker.format_cost(costs['input_cost'])})
        - Output-Tokens: {costs['output_tokens']:,} ({cost_tracker.format_cost(costs['output_cost'])})
        - Gesamt: {costs['total_tokens']:,} Tokens
        
        **Kosten:**
        - Input-Kosten: {cost_tracker.format_cost(costs['input_cost'])} (${PREIS_PRO_1M_INPUT_TOKENS}/1M Tokens)
        - Output-Kosten: {cost_tracker.format_cost(costs['output_cost'])} (${PREIS_PRO_1M_OUTPUT_TOKENS}/1M Tokens)
        - **Gesamtkosten: {cost_tracker.format_cost(costs['total_cost'])}**
        
        **API-Aufrufe:** {costs['api_calls']} Aufrufe
        
        ---
        
        💡 **Hinweis:** Dies sind ungefähre Kosten basierend auf den aktuellen Claude Sonnet 4 Preisen.
        Die tatsächlichen Kosten können in Ihrer Anthropic-Rechnung leicht abweichen.
        """)
    
    st.markdown("---")


def zeige_kosten_warnung_bei_grossen_plaenen(wochen, menulinien):
    """
    Zeigt eine Warnung an, wenn die Generierung teuer werden könnte
    
    Args:
        wochen (int): Anzahl Wochen
        menulinien (int): Anzahl Menülinien
    """
    # Grobe Schätzung der Kosten basierend auf Komplexität
    geschaetzte_kosten = (wochen * menulinien * 0.05)  # ca. $0.05 pro Woche/Menülinie
    
    if geschaetzte_kosten > 0.50:
        st.warning(f"""
        ⚠️ **Hinweis zu Kosten:**
        
        Bei {wochen} Woche(n) und {menulinien} Menülinie(n) werden die geschätzten Kosten ca. 
        **{CostTracker().format_cost(geschaetzte_kosten)}** betragen.
        
        Die Generierung verwendet mehrere API-Aufrufe:
        - 1x Speiseplan-Erstellung
        - 1x Qualitätsprüfung
        - 1x Rezept-Generierung
        
        Möchten Sie fortfahren?
        """)
        return True
    
    return False


def zeige_kosten_in_sidebar(cost_tracker):
    """
    Zeigt aktuelle Kosten in der Sidebar (kompakt)
    
    Args:
        cost_tracker (CostTracker): Der Cost-Tracker
    """
    costs = cost_tracker.get_costs()
    
    if costs['total_cost'] > 0:
        st.sidebar.divider()
        st.sidebar.markdown("### 💰 Aktuelle Sitzung")
        st.sidebar.metric(
            "Kosten",
            cost_tracker.format_cost(costs['total_cost'])
        )
        st.sidebar.caption(f"{cost_tracker.format_tokens(costs['total_tokens'])} Tokens | {costs['api_calls']} API-Aufrufe")


# Funktion zum einfachen Auskommentieren
def KOSTEN_TRACKING_AKTIVIERT():
    """
    Gibt an, ob Kosten-Tracking aktiv ist
    
    ÄNDERN SIE DIES AUF False UM KOSTEN-TRACKING ZU DEAKTIVIEREN
    """
    return True  # ← Ändern Sie dies auf False um Tracking zu deaktivieren
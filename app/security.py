"""SQL Security Utilities Modul.

Bereit Sicherheitsfunktionen für SQL-Abfrageparameter, die nicht
parametrisiert werden können (wie ORDER BY, Spaltennamen usw.).
Implementiert Whitelist-basierte Validierung zur Verhinderung von SQL-Injection.
"""

from typing import Set, Tuple, Optional
from app.logger import logger


# ============================================================================
# ORDER BY Validierung
# ============================================================================

# Whitelist erlaubter ORDER BY Spalten für Telemetrie-Abfragen
ALLOWED_ORDER_COLUMNS = {
    "timestamp",
    "sensor_id",
    "sensor_type",
    "value",
    "room_number",
    "building",
    "unit",
    "device_id",  # Alternative column name
    "ts",         # Alternative for timestamp
    "created_at", # Alternative for timestamp
}

# Whitelist erlaubter Sortierrichtungen
ALLOWED_SORT_DIRECTIONS = {"asc", "desc"}


def validate_order_by(order_by: str, allowed_columns: Optional[Set[str]] = None) -> bool:
    """ORDER BY Klausel gegen Whitelist validieren.
    
    Führt strikte Validierung von ORDER BY Klauseln durch, um SQL-Injection zu verhindern.
    Akzeptiert nur explizit auf der Whitelist stehende Spalten und Sortierrichtungen.
    
    Args:
        order_by: ORDER BY Klausel zur Validierung (z.B. "timestamp DESC").
        allowed_columns: Optional benutzerdefinierte Menge erlaubter Spalten. Wenn None,
                        verwendet ALLOWED_ORDER_COLUMNS.
    
    Returns:
        bool: True wenn ORDER BY gültig ist, False andernfalls.
    
    Example:
        >>> validate_order_by("timestamp DESC")
        True
        >>> validate_order_by("timestamp DESC, value ASC")
        True
        >>> validate_order_by("timestamp; DROP TABLE users")
        False
        >>> validate_order_by("invalid_column ASC")
        False
    
    Security Note:
        Diese Funktion verwendet einen Whitelist-Ansatz und lehnt alles ab, was nicht
        explizit erlaubt ist. Dies ist der sicherste Ansatz zur Verhinderung von
        SQL-Injection in ORDER BY Klauseln.
    """
    if not order_by or not isinstance(order_by, str):
        return False
    
    columns = allowed_columns or ALLOWED_ORDER_COLUMNS
    
    # Nach Komma teilen, um mehrere Spalten zu behandeln
    parts = [p.strip() for p in order_by.split(",")]
    
    for part in parts:
        if not part:
            continue
            
        # In Spalte und Richtung teilen (z.B. "timestamp DESC" -> ["timestamp", "DESC"])
        tokens = part.split()
        
        if len(tokens) < 1 or len(tokens) > 2:
            logger.warning(f"Invalid ORDER BY format: {part}")
            return False
        
        column = tokens[0].lower()
        direction = tokens[1].lower() if len(tokens) == 2 else "asc"
        
        # Spaltennamen gegen Whitelist validieren
        if column not in columns:
            logger.warning(f"Spalte nicht in Whitelist: {column}")
            return False
        
        # Sortierrichtung validieren
        if direction not in ALLOWED_SORT_DIRECTIONS:
            logger.warning(f"Ungültige Sortierrichtung: {direction}")
            return False
    
    return True


def sanitize_order_by(order_by: str, allowed_columns: Optional[Set[str]] = None) -> str:
    """ORDER BY Klausel bereinigen und validieren.
    
    Gibt die bereinigte ORDER BY Klausel zurück, wenn gültig, ansonsten
    gibt den sicheren Standard "timestamp DESC" zurück.
    
    Args:
        order_by: ORDER BY Klausel zur Bereinigung.
        allowed_columns: Optional benutzerdefinierte Menge erlaubter Spalten.
    
    Returns:
        str: Gültige ORDER BY Klausel oder sicherer Standard.
    
    Example:
        >>> sanitize_order_by("timestamp DESC")
        'timestamp DESC'
        >>> sanitize_order_by("timestamp; DROP TABLE users")
        'timestamp DESC'  # Returns safe default
    """
    if validate_order_by(order_by, allowed_columns):
        return order_by
    
    logger.warning(f"Ungültige ORDER BY Klausel abgelehnt: {order_by}")
    return "timestamp DESC"


# ============================================================================
# Spaltennamen-Validierung
# ============================================================================

def validate_column_name(column: str, allowed_columns: Set[str]) -> bool:
    """Validieren, dass ein Spaltenname in der Whitelist ist.
    
    Args:
        column: Zu validierender Spaltenname.
        allowed_columns: Menge erlaubter Spaltennamen.
    
    Returns:
        bool: True wenn Spalte in Whitelist ist, False andernfalls.
    
    Sicherheitshinweis:
        Verwenden Sie dies für Filter- und Auswahlvorgänge, bei denen Spaltennamen
        nicht parametrisiert werden können.
    """
    if not column or not isinstance(column, str):
        return False
    
    # Anführungszeichen entfernen, falls vorhanden
    clean_column = column.strip('"').strip("'").lower()
    
    return clean_column in {col.lower() for col in allowed_columns}


# ============================================================================
# SQL-Injection-Erkennung
# ============================================================================

def detect_sql_injection_patterns(input_str: str) -> bool:
    """Häufige SQL-Injection-Muster in der Eingabe erkennen.
    
    Führt heuristische Erkennung von SQL-Injection-Versuchen durch,
    indem nach häufigen Injektionsmustern gesucht wird. Dies ist ein
    Defense-in-Depth-Maßnahme und sollte NICHT die Hauptverteidigung sein
    (Whitelist-Validierung ist primär).
    
    Args:
        input_str: Zu prüfende Eingabezeichenkette.
    
    Returns:
        bool: True wenn verdächtige Muster erkannt, False andernfalls.
    
    Example:
        >>> detect_sql_injection_patterns("timestamp DESC")
        False
        >>> detect_sql_injection_patterns("timestamp; DROP TABLE")
        True
    
    Hinweis:
        Dies ist kein vollständiger SQL-Injection-Schutz.
        Verwenden Sie immer Whitelist-Validierung als Primärverteidigung.
    """
    if not input_str or not isinstance(input_str, str):
        return False
    
    dangerous_patterns = [
        ";",          # Anweisungsterminator
        "--",         # Kommentar
        "/*",         # Blockkommentar-Start
        "*/",         # Blockkommentar-Ende
        "xp_",        # Erweiterte gespeicherte Prozedur
        "sp_",        # Gespeicherte Systemprozedur
        "drop",       # DROP Befehl
        "delete",     # DELETE Befehl
        "insert",     # INSERT Befehl
        "update",     # UPDATE Befehl
        "union",      # UNION Befehl
        "select",     # SELECT Befehl (in einigen Kontexten)
        "exec",       # EXEC Befehl
        "execute",    # EXECUTE Befehl
        "script",     # Script Tags
        "javascript", # JavaScript
        "on",         # Event-Handler (in einigen Kontexten)
    ]
    
    input_lower = input_str.lower()
    
    for pattern in dangerous_patterns:
        if pattern in input_lower:
            logger.warning(f"Verdächtiges Muster '{pattern}' in Eingabe erkannt: {input_str[:50]}")
            return True
    
    return False


# ============================================================================
# Security Validierungs-Wrapper
# ============================================================================

def validate_query_parameter(
    param: str,
    param_name: str,
    allowed_values: Optional[Set[str]] = None,
    check_patterns: bool = True
) -> Tuple[bool, Optional[str]]:
    """Umfassende Validierung für Abfrageparameter, die nicht parametrisiert werden können.
    
    Führt mehrere Validierungsebenen durch:
    1. Typ- und Basisformat-Prüfung
    2. SQL-Injection-Mustererkennung (heuristisch)
    3. Whitelist-Validierung (falls vorhanden)
    
    Args:
        param: Zu validierender Parameterwert.
        param_name: Name des Parameters (für Protokollierung).
        allowed_values: Optional Menge erlaubter Werte.
        check_patterns: Ob auf SQL-Injection-Muster geprüft werden soll.
    
    Returns:
        Tuple[bool, Optional[str]]: (ist_gültig, fehlermeldung)
    
    Example:
        >>> is_valid, error = validate_query_parameter(
        ...     "timestamp DESC",
        ...     "order_by",
        ...     {"timestamp desc", "value asc"}
        ... )
        >>> is_valid
        True
    """
    # Basisvalidierung
    if not param or not isinstance(param, str):
        return False, f"{param_name} muss eine nicht-leere Zeichenkette sein"
    
    # Mustererkennung (Defense-in-Depth)
    if check_patterns and detect_sql_injection_patterns(param):
        return False, f"{param_name} enthält verdächtige SQL-Muster"
    
    # Whitelist-Validierung
    if allowed_values:
        param_lower = param.lower()
        if param_lower not in {v.lower() for v in allowed_values}:
            return False, f"{param_name} '{param}' nicht in erlaubten Werten"
    
    return True, None

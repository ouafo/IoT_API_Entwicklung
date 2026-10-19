"""OData filter expression parsing."""

from typing import Tuple, List, Any, Dict, Optional
import re
from datetime import datetime
# Regex für Filter-Parsing
_FILTER_SPLIT_RE = re.compile(r"\s+(and|or)\s+", re.IGNORECASE)
_CMP_RE = re. compile(
    r"^\s*([a-zA-Z0-9_]+)\s+(eq|ne|gt|ge|lt|le)\s+(.+)\s*$",
    re. IGNORECASE,
)
def _normalize_value(val: str) -> Any:
    """String zu Python Type konvertieren."""
    val = val.strip()
    # ISO8601 Timestamp
    if val.endswith("Z"):
        try:
            return datetime.fromisoformat(val[:-1] + "+00:00")
        except Exception: 
            pass
    # Quoted String
    if val.startswith(("'", '"')) and val.endswith(("'", '"')):
        return val[1:-1]

    # Number
    try:
        if "." in val:
            return float(val)
        return int(val)
    except Exception: 
        return val

def parse_filter(
    filter_expr: str,
    allowed_columns: List[str],
    alias_map: Optional[Dict[str, str]] = None,
) -> Tuple[str, List[Any]]:
    """OData $filter zu SQL WHERE konvertieren.
    Beispiel:
        parse_filter("MeasureContent gt 22", ["MeasureContent"])
        → ("MeasureContent > %s", [22])
    Args:
        filter_expr: OData Filter (z.B. "MeasureContent gt 22")
        allowed_columns:  Erlaubte Spalten-Namen
        alias_map: Mapping für Spalten-Namen (optional)   
    Returns:
        (sql_condition, params) - OHNE "WHERE" keyword
    """
    if not filter_expr:
        return "", []

    tokens = _FILTER_SPLIT_RE.split(filter_expr)
    connectors = _FILTER_SPLIT_RE.findall(filter_expr)

    where_parts = []
    params = []

    for token in tokens: 
        token = token.strip()
        if not token or token.lower() in {"and", "or"}:
            continue

        m = _CMP_RE.match(token)
        if not m:
            continue

        col, op, raw_val = m.groups()
        
        # WICHTIG: Case-sensitive für OData (RoomID, BuildingID, etc.)
        # Nicht . lower() verwenden!
        
        # Validate column
        if col not in allowed_columns:
            continue

        # Alias-Mapping
        if alias_map:
            col = alias_map.get(col, col)

        # OData Operator zu SQL
        sql_op = {
            "eq": "=",
            "ne": "<>",
            "gt": ">",
            "ge": ">=",
            "lt": "<",
            "le": "<=",
        }[op.lower()]

        where_parts.append(f"{col} {sql_op} %s")
        params.append(_normalize_value(raw_val))

    if not where_parts: 
        return "", []

    # SQL mit Logical Operators
    sql = where_parts[0]
    for i, conn in enumerate(connectors):
        if i + 1 < len(where_parts):
            sql += f" {conn.upper()} {where_parts[i + 1]}"

    return sql, params


def parse_orderby(
    orderby_expr: str,
    allowed_columns: List[str],
    alias_map: Optional[Dict[str, str]] = None,
) -> str:
    """OData $orderby zu SQL ORDER BY konvertieren.
    
    Beispiel:
        parse_orderby("StartDateTime desc", ["StartDateTime"])
        → "StartDateTime DESC"
        
    Args:
        orderby_expr: OData OrderBy (z.B. "StartDateTime desc")
        allowed_columns:  Erlaubte Spalten
        alias_map: Spalten-Mapping (optional)
        
    Returns: 
        SQL ORDER BY clause (OHNE "ORDER BY" keyword)
    """
    if not orderby_expr:
        return ""
    
    parts = []
    for item in orderby_expr.split(","):
        item = item.strip()
        tokens = item.split()
        
        if len(tokens) == 0:
            continue
            
        col = tokens[0]
        direction = tokens[1]. upper() if len(tokens) > 1 else "ASC"
        
        # Validate
        if col not in allowed_columns:
            continue
        if direction not in ["ASC", "DESC"]: 
            direction = "ASC"
            
        # Alias-Mapping
        if alias_map:
            col = alias_map.get(col, col)
            
        parts. append(f"{col} {direction}")
    
    return ", ".join(parts) if parts else ""
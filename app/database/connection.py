"""Database connection pooling."""
import os
import sys
from queue import Queue, Empty
from typing import Optional
import psycopg
from app.config import settings
from app.logger import logger

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

_pool:  Optional[Queue] = None
def _make_conn() -> psycopg.Connection:
    """Neue PostgreSQL Connection erstellen."""
    connection_params = {
        "host": settings.DB_HOST,
        "port": int(settings.DB_PORT) if settings.DB_PORT else None,
        "dbname": settings.DB_NAME,
        "user": settings.DB_USER,
        "password":  settings.DB_PASSWORD,
    }
    connection_params = {k: v for k, v in connection_params.items() if v is not None}
    
    conn = psycopg.connect(**connection_params)
    # Schema setzen
    if settings.DB_SCHEMA:
        try:
            cur = conn.cursor()
            cur.execute(f"SET search_path TO {settings.DB_SCHEMA}, public")
            conn.commit()
            logger.debug(f"Schema gesetzt: {settings.DB_SCHEMA}")
        except Exception as e:
            logger.warning(f"Schema-Set fehlgeschlagen: {e}")  
    return conn
def init_db_pool() -> None:
    """Connection Pool initialisieren."""
    global _pool
    if _pool is not None:
        logger.warning("Pool bereits initialisiert")
        return
    
    _pool = Queue()
    pool_size = max(1, getattr(settings, 'DB_POOL_MIN', 1))
    
    for _ in range(pool_size):
        conn = _make_conn()
        _pool.put(conn)
    
    logger.info(f"Pool initialisiert: {pool_size} Connections")
def get_conn() -> psycopg.Connection:
    """Connection aus Pool holen."""
    global _pool
    if _pool is None:
        init_db_pool()
    try:
        conn = _pool. get(block=False)
        
        # Health Check
        if conn.closed:
            logger.warning("Tote Connection, neue erstellen")
            conn = _make_conn()
        else:
            try:
                cur = conn.cursor()
                cur.execute("SELECT 1")
                cur.fetchone()
            except Exception as e:
                logger.warning(f"Health Check failed: {e}")
                try:
                    conn.close()
                except:
                    pass
                conn = _make_conn()
        return conn
    except Empty:
        logger.debug("Pool leer, neue Connection")
        return _make_conn()
def put_conn(conn: psycopg.Connection) -> None:
    """Connection zurück in Pool."""
    global _pool
    if _pool is None:
        try:
            conn.close()
        except:
            pass
        return
    try: 
        _pool.put(conn)
    except Exception:
        logger.error("Fehler beim Zurückgeben")
        try:
            conn. close()
        except:
            pass
def close_db_pool() -> None:
    """Alle Connections schließen."""
    global _pool
    if _pool is None:
        return
    closed_count = 0
    while not _pool. empty():
        conn = _pool.get()
        try:
            conn.close()
            closed_count += 1
        except Exception as e:
            logger. error(f"Fehler beim Schließen: {e}")
    
    logger.info(f"Pool geschlossen:  {closed_count} Connections")
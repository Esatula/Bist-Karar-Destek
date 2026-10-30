"""
portfolio/db.py
---------------
Sanal portföy için SQLite kalıcı depolama katmanı.

Streamlit session state yerine SQLite kullanarak portföy verilerini
kalıcı hale getirir. Uygulama yeniden başlatıldığında veri kaybolmaz.

Tablolar:
    holdings     — Açık pozisyonlar (sembol, adet, maliyet)
    cash         — Nakit bakiye (tek satır)
    transactions — İşlem geçmişi (alım/satım logu)
"""

import sqlite3
import os
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = "data/portfolio.db"
_DEFAULT_CASH = 100_000.0


def _get_db_path(db_path: str | None = None) -> str:
    """Veritabanı yolunu döndürür, gerekirse klasörü oluşturur."""
    path = db_path or _DEFAULT_DB_PATH
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    return path


def _init_db(db_path: str | None = None):
    """Tablo şemasını oluşturur (idempotent)."""
    db_path = _get_db_path(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS holdings (
                symbol TEXT PRIMARY KEY,
                quantity REAL NOT NULL,
                average_cost REAL NOT NULL,
                buy_date TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cash (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                balance REAL NOT NULL DEFAULT 100000.0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                action TEXT NOT NULL CHECK (action IN ('BUY', 'SELL')),
                quantity REAL NOT NULL,
                price REAL NOT NULL,
                date TEXT NOT NULL
            )
        """)
        # Nakit kaydı yoksa başlangıç değeriyle oluştur
        cur = conn.execute("SELECT COUNT(*) FROM cash")
        if cur.fetchone()[0] == 0:
            conn.execute(
                "INSERT INTO cash (id, balance) VALUES (1, ?)",
                (_DEFAULT_CASH,),
            )


# ---------------------------------------------------------------------------
# Nakit İşlemleri
# ---------------------------------------------------------------------------

def get_cash(db_path: str | None = None) -> float:
    """Mevcut nakit bakiyeyi döndürür."""
    db_path = _get_db_path(db_path)
    _init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute("SELECT balance FROM cash WHERE id = 1")
        row = cur.fetchone()
        return row[0] if row else _DEFAULT_CASH


def set_cash(balance: float, db_path: str | None = None):
    """Nakit bakiyeyi doğrudan ayarlar."""
    db_path = _get_db_path(db_path)
    _init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE cash SET balance = ? WHERE id = 1", (balance,))


# ---------------------------------------------------------------------------
# Pozisyon İşlemleri
# ---------------------------------------------------------------------------

def get_holdings(db_path: str | None = None) -> list[dict]:
    """Tüm açık pozisyonları liste olarak döndürür."""
    db_path = _get_db_path(db_path)
    _init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT symbol, quantity, average_cost, buy_date FROM holdings"
        )
        return [dict(row) for row in cur.fetchall()]


def add_holding(
    symbol: str, quantity: float, price: float, db_path: str | None = None
):
    """
    Yeni alım kaydeder. Mevcut pozisyon varsa ortalama maliyet güncellenir.
    Nakit bakiyeden düşülür ve işlem loglanır.
    """
    db_path = _get_db_path(db_path)
    _init_db(db_path)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with sqlite3.connect(db_path) as conn:
        # Mevcut pozisyon var mı?
        cur = conn.execute(
            "SELECT quantity, average_cost FROM holdings WHERE symbol = ?",
            (symbol,),
        )
        row = cur.fetchone()

        if row:
            old_qty, old_cost = row
            new_qty = old_qty + quantity
            new_cost = ((old_qty * old_cost) + (quantity * price)) / new_qty
            conn.execute(
                "UPDATE holdings SET quantity = ?, average_cost = ?, buy_date = ? WHERE symbol = ?",
                (new_qty, new_cost, now, symbol),
            )
        else:
            conn.execute(
                "INSERT INTO holdings (symbol, quantity, average_cost, buy_date) VALUES (?, ?, ?, ?)",
                (symbol, quantity, price, now),
            )

        # Nakitten düş
        cost = quantity * price
        conn.execute(
            "UPDATE cash SET balance = balance - ? WHERE id = 1", (cost,)
        )

        # İşlem logu
        conn.execute(
            "INSERT INTO transactions (symbol, action, quantity, price, date) VALUES (?, 'BUY', ?, ?, ?)",
            (symbol, quantity, price, now),
        )


def remove_holding(
    symbol: str, quantity: float, price: float, db_path: str | None = None
):
    """
    Satış kaydeder. Pozisyon tamamen kapatılıyorsa holdings'ten silinir.
    Nakite eklenir ve işlem loglanır.
    """
    db_path = _get_db_path(db_path)
    _init_db(db_path)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(
            "SELECT quantity FROM holdings WHERE symbol = ?", (symbol,)
        )
        row = cur.fetchone()
        if not row:
            logger.warning("Satış başarısız: %s pozisyonu bulunamadı.", symbol)
            return

        old_qty = row[0]
        sell_qty = min(quantity, old_qty)
        remaining = old_qty - sell_qty

        if remaining <= 0.001:
            conn.execute("DELETE FROM holdings WHERE symbol = ?", (symbol,))
        else:
            conn.execute(
                "UPDATE holdings SET quantity = ? WHERE symbol = ?",
                (remaining, symbol),
            )

        # Nakite ekle
        revenue = sell_qty * price
        conn.execute(
            "UPDATE cash SET balance = balance + ? WHERE id = 1", (revenue,)
        )

        # İşlem logu
        conn.execute(
            "INSERT INTO transactions (symbol, action, quantity, price, date) VALUES (?, 'SELL', ?, ?, ?)",
            (symbol, sell_qty, price, now),
        )


# ---------------------------------------------------------------------------
# İşlem Geçmişi
# ---------------------------------------------------------------------------

def get_transactions(
    limit: int = 50, db_path: str | None = None
) -> list[dict]:
    """Son N işlemi tarihe göre azalan sırada döndürür."""
    db_path = _get_db_path(db_path)
    _init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT * FROM transactions ORDER BY date DESC LIMIT ?", (limit,)
        )
        return [dict(row) for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# Sıfırlama
# ---------------------------------------------------------------------------

def reset_portfolio(
    initial_cash: float = _DEFAULT_CASH, db_path: str | None = None
):
    """Portföyü sıfırlar: tüm pozisyonları kapatır, nakiti başlangıca döndürür."""
    db_path = _get_db_path(db_path)
    _init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM holdings")
        conn.execute("DELETE FROM transactions")
        conn.execute("UPDATE cash SET balance = ? WHERE id = 1", (initial_cash,))
    logger.info("Portföy sıfırlandı. Nakit: %.2f TL", initial_cash)

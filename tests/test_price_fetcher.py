"""
tests/test_price_fetcher.py
---------------------------
data.price_fetcher modülü için birim testler.

Çalıştırmak için (proje kökünde):
    pytest tests/test_price_fetcher.py -v
"""

import pandas as pd
import pytest

from data.price_fetcher import _to_yf_symbol, fetch_prices, load_prices, save_prices


# ---------------------------------------------------------------------------
# _to_yf_symbol testleri
# ---------------------------------------------------------------------------

class TestToYfSymbol:
    """_to_yf_symbol yardımcı fonksiyonu testleri."""

    def test_ekleme_yapilir(self):
        """'.IS' uzantısı eksikse eklenmeli."""
        assert _to_yf_symbol("THYAO") == "THYAO.IS"

    def test_ekleme_yapilmaz(self):
        """Zaten '.IS' ile bitiyorsa tekrar eklenmemeli."""
        assert _to_yf_symbol("THYAO.IS") == "THYAO.IS"

    def test_kucuk_harf_duzeltilir(self):
        """Küçük harf girişler büyük harfe çevrilmeli."""
        assert _to_yf_symbol("thyao") == "THYAO.IS"

    def test_bosluk_temizlenir(self):
        """Baştaki/sondaki boşluklar temizlenmeli."""
        assert _to_yf_symbol("  GARAN  ") == "GARAN.IS"


# ---------------------------------------------------------------------------
# fetch_prices testleri (gerçek ağ — kısa tarih aralığı kullanıyoruz)
# ---------------------------------------------------------------------------

class TestFetchPrices:
    """fetch_prices fonksiyonu için entegrasyon testleri."""

    def test_donus_bos_degil(self):
        """Geçerli bir sembol için dönen DataFrame boş olmamalı."""
        df = fetch_prices("THYAO", start="2023-01-01", end="2023-03-31")
        assert not df.empty, "THYAO için veri boş döndü!"

    def test_beklenen_kolonlar_var(self):
        """DataFrame'de Open, High, Low, Close, Volume kolonları bulunmalı."""
        df = fetch_prices("THYAO", start="2023-01-01", end="2023-03-31")
        assert not df.empty
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            assert col in df.columns, f"'{col}' kolonu bulunamadı!"

    def test_index_datetime(self):
        """Index, datetime tipinde olmalı."""
        df = fetch_prices("THYAO", start="2023-01-01", end="2023-03-31")
        assert not df.empty
        assert pd.api.types.is_datetime64_any_dtype(df.index), \
            "Index datetime64 tipinde değil!"

    def test_gecersiz_sembol_bos_doner(self):
        """Var olmayan bir sembol için boş DataFrame dönmeli, hata fırlatmamalı."""
        df = fetch_prices("XXXXXXXXXINVALID", start="2023-01-01", end="2023-03-31")
        assert isinstance(df, pd.DataFrame), "DataFrame dönmeli!"
        assert df.empty, "Geçersiz sembol için boş DataFrame beklendi!"

    def test_degerler_pozitif(self):
        """Fiyat ve hacim değerleri sıfırdan büyük olmalı."""
        df = fetch_prices("GARAN", start="2023-01-01", end="2023-03-31")
        assert not df.empty
        assert (df["Close"] > 0).all(), "Kapanış fiyatları negatif/sıfır olamaz!"
        assert (df["Volume"] >= 0).all(), "Hacim negatif olamaz!"


# ---------------------------------------------------------------------------
# save_prices / load_prices testleri
# ---------------------------------------------------------------------------

class TestSaveLoadPrices:
    """save_prices ve load_prices round-trip testleri."""

    def test_kaydet_yukle_round_trip(self, tmp_path):
        """Kaydedilen DataFrame yüklenince aynı veriye sahip olmalı."""
        df = fetch_prices("ASELS", start="2023-06-01", end="2023-07-31")
        assert not df.empty, "Test için veri çekilemedi."

        save_prices(df, symbol="ASELS", folder=str(tmp_path))
        loaded_df = load_prices("ASELS", folder=str(tmp_path))

        assert not loaded_df.empty, "Yüklenen DataFrame boş!"
        assert len(loaded_df) == len(df), "Satır sayısı uyuşmuyor!"
        assert list(loaded_df.columns) == list(df.columns), "Kolon isimleri uyuşmuyor!"

    def test_bos_df_kaydedilmez(self, tmp_path):
        """Boş DataFrame kaydedilmemeli, None dönmeli."""
        result = save_prices(pd.DataFrame(), symbol="TEST", folder=str(tmp_path))
        assert result is None, "Boş DataFrame için None beklendi!"

    def test_dosya_yoksa_bos_doner(self, tmp_path):
        """Parquet dosyası yoksa load_prices boş DataFrame dönmeli."""
        loaded = load_prices("YOKHISSE", folder=str(tmp_path))
        assert isinstance(loaded, pd.DataFrame)
        assert loaded.empty, "Olmayan dosya için boş DataFrame beklendi!"

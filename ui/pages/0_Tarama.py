"""
ui/pages/0_Tarama.py
---------------------
BIST-100 Evren Tarayıcı — Ana dashboard sayfası.

TradingView + Teknik + Haber sinyallerini birleştirerek
100 hisseyi ~10 saniyede tarar ve sıralı tablo halinde gösterir.
"""

import sys
import os
import time
import streamlit as st
import pandas as pd
import plotly.express as px

# sys.path güvencesi
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import yaml
from pathlib import Path

# ---------------------------------------------------------------------------
# Sayfa Konfigürasyonu
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="BIST-100 Tarama | BIST Bot",
    page_icon="🔍",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Config Yükleme
# ---------------------------------------------------------------------------
from config.manager import config as cfg_mgr
config = cfg_mgr.get_all()

if not config:
    st.error("Konfigürasyon dosyası (settings.yaml) bulunamadı veya yüklenemedi!")
    st.stop()

price_folder = os.path.join(project_root, config.get("storage", {}).get("price_data_folder", "data/raw"))
db_path      = os.path.join(project_root, config.get("storage", {}).get("news_db_path", "data/news/news.db"))
weights      = config.get("signal_weights", {"technical": 0.5, "tradingview": 0.2, "news": 0.3})
thresholds   = config.get("signal_thresholds", {"buy": 70, "sell": 30})
tv_interval  = config.get("tradingview", {}).get("interval", "1d")

# ---------------------------------------------------------------------------
# Tarama Fonksiyonu (Cache: 1 saat)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=3600, show_spinner=False)
def run_scan(tier: str, _price_folder: str, _db_path: str,
             _weights: tuple, _tv_interval: str,
             _buy_thr: float, _sell_thr: float) -> pd.DataFrame:
    """ttl=3600 → saatte bir otomatik yeniler. Yenile butonuyla zorla temizlenir."""
    from data.universe_scanner import quick_scan
    _w = dict(zip(["technical", "tradingview"], _weights))
    return quick_scan(
        tier=tier,
        price_folder=_price_folder,
        db_path=_db_path,
        tv_interval=_tv_interval,
        weights=_w,
        buy_threshold=_buy_thr,
        sell_threshold=_sell_thr,
        auto_update=True,
        max_age_hours=4,
    )

# ---------------------------------------------------------------------------
# Başlık + Kontroller
# ---------------------------------------------------------------------------
st.title("🔍 BIST-100 Evren Tarayıcı")
_tw = weights.get('technical', 0.8)
_tvw = weights.get('tradingview', 0.2)
_tot = _tw + _tvw if (_tw + _tvw) > 0 else 1.0
st.markdown(
    "TradingView + Teknik Analiz sinyallerinin birleşimi. "
    f"**Ağırlıklar:** Teknik `{_tw/_tot:.0%}` · "
    f"TV `{_tvw/_tot:.0%}`"
)

col_ctrl1, col_ctrl2, col_ctrl3, col_ctrl4 = st.columns([2, 2, 2, 1])

with col_ctrl1:
    tier = st.selectbox("Evren", ["bist100", "bist30"], index=0,
                        format_func=lambda x: "BIST-100 (~100 hisse)" if x == "bist100" else "BIST-30 (30 hisse)")

with col_ctrl2:
    sector_filter = st.selectbox("Sektör Filtresi", ["Tümü"])  # Sonradan dolduralacak

with col_ctrl3:
    rec_filter = st.multiselect("Öneri Filtresi", ["AL", "BEKLE", "SAT"],
                                default=["AL", "BEKLE", "SAT"])

with col_ctrl4:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔄 Yenile", use_container_width=True, type="primary"):
        st.cache_data.clear()
        st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# Tarama Çalıştır
# ---------------------------------------------------------------------------
w_tuple = (
    _tw / _tot,
    _tvw / _tot,
)

with st.spinner(f"⏳ {tier.upper()} taranıyor... (TV + Teknik + Haber, ~10 saniye)"):
    t0 = time.time()
    df_scan = run_scan(
        tier=tier,
        _price_folder=price_folder,
        _db_path=db_path,
        _weights=w_tuple,
        _tv_interval=tv_interval,
        _buy_thr=thresholds.get("buy", 70),
        _sell_thr=thresholds.get("sell", 30),
    )
    elapsed = time.time() - t0

if df_scan is None or df_scan.empty:
    st.error("Tarama sonucu boş. Veri dosyalarını kontrol edin: `python -m data.price_fetcher --live`")
    st.stop()

# Sektör filtresi seçeneklerini dinamik doldur
sectors = sorted(df_scan["sector"].unique().tolist())
sector_options = ["Tümü"] + sectors
# Sektör selectbox'ı güncelle (widget re-render olmayacak, bir sonraki açılışta)

# ---------------------------------------------------------------------------
# Üst Metrikler
# ---------------------------------------------------------------------------
al_count   = (df_scan["recommendation"] == "AL").sum()
sat_count  = (df_scan["recommendation"] == "SAT").sum()
bkl_count  = (df_scan["recommendation"] == "BEKLE").sum()
avg_score  = df_scan["final_score"].mean()
top_score  = df_scan["final_score"].max()
scan_count = len(df_scan)

m1, m2, m3, m4, m5, m6 = st.columns(6)
m1.metric("🟢 AL",    al_count,  delta=None)
m2.metric("🔴 SAT",   sat_count, delta=None)
m3.metric("⚪ BEKLE", bkl_count, delta=None)
m4.metric("Taranan",  scan_count)
m5.metric("Ort. Skor", f"{avg_score:.1f}")
m6.metric("⏱ Süre",  f"{elapsed:.1f}s")

st.divider()

# ---------------------------------------------------------------------------
# Filtreler Uygula
# ---------------------------------------------------------------------------
df_display = df_scan.copy()

if rec_filter:
    df_display = df_display[df_display["recommendation"].isin(rec_filter)]

# ---------------------------------------------------------------------------
# Sekmeli Görünüm
# ---------------------------------------------------------------------------
tab_table, tab_heatmap, tab_top = st.tabs(["📋 Tablo", "🎨 Isı Haritası", "🏆 Top 10"])

# ── Tab 1: Tablo ─────────────────────────────────────────────────────────
with tab_table:
    # Emoji ekle
    df_table = df_display.copy()
    df_table["Öneri"] = df_table["recommendation"].map(
        {"AL": "🟢 AL", "SAT": "🔴 SAT", "BEKLE": "⚪ BEKLE"}
    )
    df_table["TV"] = df_table["tv_rec"].apply(
        lambda x: ("🟢 " if "AL" in str(x) else "🔴 " if "SAT" in str(x) else "⚪ ") + str(x)
    )
    df_table["MACD"] = df_table["macd_bullish"].map({True: "↑ POZ", False: "↓ NEG"})
    df_table["Günlük%"] = df_table["daily_pct"].apply(
        lambda x: f"+{x:.1f}%" if x > 0 else f"{x:.1f}%"
    )

    show_cols = {
        "symbol":      "Sembol",
        "name":        "Şirket",
        "sector":      "Sektör",
        "last_price":  "Son Fiyat (₺)",
        "Günlük%":     "Günlük %",
        "final_score": "Skor",
        "Öneri":       "Öneri",
        "TV":          "TV Sinyali",
        "tech_score":  "Teknik",
        "rsi":         "RSI",
        "MACD":        "MACD",
        "adx":         "ADX",
        "regime":      "Rejim",
        "stop_loss":   "Zarar-Kes (₺)",
        "take_profit": "Kar-Al (₺)",
        "last_date":   "Son Veri",
    }

    df_view = df_table.rename(columns=show_cols)[[v for v in show_cols.values() if v in df_table.rename(columns=show_cols).columns]]

    st.dataframe(
        df_view.style.background_gradient(subset=["Skor"], cmap="RdYlGn", vmin=0, vmax=100),
        use_container_width=True,
        hide_index=True,
        height=600,
    )

    # İndir butonu
    csv = df_display.to_csv(index=False).encode("utf-8")
    st.download_button(
        "📥 CSV İndir",
        csv,
        file_name=f"bist100_tarama_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )

# ── Tab 2: Isı Haritası ──────────────────────────────────────────────────
with tab_heatmap:
    st.markdown("### Sektör Bazlı Skor Isı Haritası")

    if not df_display.empty:
        # Treemap: sektör → hisse → skor
        fig_tree = px.treemap(
            df_display,
            path=["sector", "symbol"],
            values="final_score",
            color="final_score",
            color_continuous_scale=["#ef4444", "#facc15", "#22c55e"],
            color_continuous_midpoint=50,
            custom_data=["name", "recommendation", "last_price", "daily_pct"],
            title="BIST-100 Sektör Ağırlıklı Skor Haritası",
        )
        fig_tree.update_traces(
            hovertemplate=(
                "<b>%{label}</b><br>"
                "%{customdata[0]}<br>"
                "Öneri: %{customdata[1]}<br>"
                "Skor: %{value:.1f}<br>"
                "Fiyat: ₺%{customdata[2]:.2f} (%{customdata[3]:+.1f}%)"
                "<extra></extra>"
            )
        )
        fig_tree.update_layout(height=550, margin=dict(l=0, r=0, t=40, b=0))
        st.plotly_chart(fig_tree, use_container_width=True)

    # Sektör bazlı ortalama skor
    st.markdown("#### Sektör Ortalamaları")
    sector_avg = (
        df_display.groupby("sector")[["final_score", "tv_score", "tech_score"]]
        .mean()
        .round(1)
        .sort_values("final_score", ascending=False)
    )
    st.dataframe(sector_avg, use_container_width=True)

# ── Tab 3: Top 10 ────────────────────────────────────────────────────────
with tab_top:
    col_al, col_sat = st.columns(2)

    with col_al:
        st.markdown("### 🟢 Top 10 AL")
        top_al = df_scan[df_scan["recommendation"] == "AL"].head(10)
        if top_al.empty:
            st.info("Şu an AL sinyali üretilen hisse yok.")
        else:
            for _, row in top_al.iterrows():
                daily_color = "green" if row["daily_pct"] >= 0 else "red"
                st.markdown(
                    f"**{row['symbol']}** — {row['name']}  \n"
                    f"Skor: `{row['final_score']:.0f}` | TV: `{row['tv_rec']}` | "
                    f"RSI: `{row['rsi']:.0f}` | "
                    f"Fiyat: ₺`{row['last_price']:.2f}` "
                    f"(:{daily_color}[{row['daily_pct']:+.1f}%])"
                )
                st.progress(int(min(row["final_score"], 100)))

    with col_sat:
        st.markdown("### 🔴 Top 10 SAT")
        top_sat = df_scan[df_scan["recommendation"] == "SAT"].sort_values("final_score").head(10)
        if top_sat.empty:
            st.info("Şu an SAT sinyali üretilen hisse yok.")
        else:
            for _, row in top_sat.iterrows():
                daily_color = "green" if row["daily_pct"] >= 0 else "red"
                st.markdown(
                    f"**{row['symbol']}** — {row['name']}  \n"
                    f"Skor: `{row['final_score']:.0f}` | TV: `{row['tv_rec']}` | "
                    f"RSI: `{row['rsi']:.0f}` | "
                    f"Fiyat: ₺`{row['last_price']:.2f}` "
                    f"(:{daily_color}[{row['daily_pct']:+.1f}%])"
                )
                st.progress(int(min(row["final_score"], 100)))

# ---------------------------------------------------------------------------
# Sidebar: Hızlı Filtre + Detay Linki
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## 🔍 Hızlı Filtre")

    search = st.text_input("Sembol Ara", placeholder="THYAO")
    if search:
        mask = df_scan["symbol"].str.contains(search.upper())
        st.dataframe(
            df_scan[mask][["symbol", "name", "final_score", "recommendation"]],
            use_container_width=True,
            hide_index=True,
        )

    st.divider()
    st.markdown("### 📊 Dağılım")
    dist_data = pd.DataFrame({
        "Öneri": ["🟢 AL", "⚪ BEKLE", "🔴 SAT"],
        "Sayı":  [al_count, bkl_count, sat_count],
    })
    fig_pie = px.pie(
        dist_data,
        values="Sayı",
        names="Öneri",
        color="Öneri",
        color_discrete_map={"🟢 AL": "#22c55e", "⚪ BEKLE": "#94a3b8", "🔴 SAT": "#ef4444"},
        height=250,
    )
    fig_pie.update_traces(textposition="inside", textinfo="percent+label")
    fig_pie.update_layout(showlegend=False, margin=dict(l=0, r=0, t=0, b=0))
    st.plotly_chart(fig_pie, use_container_width=True)

    st.divider()
    st.caption(f"Son güncelleme: {pd.Timestamp.now().strftime('%d.%m.%Y %H:%M')}")
    st.caption("Cache: 1 saat. Yenilemek için 🔄 butonunu kullanın.")

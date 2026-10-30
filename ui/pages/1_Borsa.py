"""
ui/pages/1_Borsa.py
-------------------
BIST Hisse senedi tarama ve detay sayfasi.
"""
import streamlit as st
import pandas as pd
import os

from config.manager import config as app_cfg
from data.price_fetcher import load_prices
from data.universe_scanner import quick_scan
from ui.data_layer import get_detail

config = app_cfg.get_all()
threshold = config.get("signal_thresholds", {"buy": 70, "sell": 40})
weights = config.get("signal_weights", {"technical": 0.8, "tradingview": 0.2})
price_folder = config.get("storage", {}).get("price_data_folder", "data/raw")
db_path = config.get("storage", {}).get("news_db_path", "data/news/news.db")
tv_interval = config.get("tradingview", {}).get("interval", "1d")

# ── Session State ─────────────────────────────────────────────────────────────
if "selected_stock" not in st.session_state:
    st.session_state.selected_stock = None

# ── Hisse Listesini Tara ──────────────────────────────────────────────────────
@st.cache_data(ttl=1800, show_spinner=False)
def scan_stocks():
    w = {"technical": weights.get("technical", 0.8), "tradingview": weights.get("tradingview", 0.2)}
    df = quick_scan(
        tier="bist100",
        price_folder=price_folder,
        db_path=db_path,
        tv_interval=tv_interval,
        weights=w,
        buy_threshold=threshold.get("buy", 70),
        sell_threshold=threshold.get("sell", 40),
        auto_update=False
    )
    
    if df is None or df.empty:
        return pd.DataFrame()
        
    # Formatlama for 1_Borsa UI
    df_fmt = df.rename(columns={
        "symbol": "Sembol",
        "name": "Şirket",
        "sector": "Sektör",
        "last_price": "Fiyat",
        "daily_pct": "Günlük%",
        "final_score": "Skor",
        "recommendation": "Sinyal",
        "rsi": "RSI",
        "tv_rec": "TV",
    })
    
    # Emojiler
    df_fmt["Trend"] = df_fmt.apply(lambda x: "✅" if x.get("macd_bullish") else "❌", axis=1)
    df_fmt["Momentum"] = df_fmt.apply(lambda x: "✅" if x.get("macd_bullish") else "❌", axis=1) # Simplified
    df_fmt["Hacim"] = "✅" 
    df_fmt["Temel"] = "✅"
    df_fmt["_reason"] = "Tarama Modu"
    
    return df_fmt

# ── Sayfa Başlığı ─────────────────────────────────────────────────────────────
st.title("📊 Borsa — BIST Hisse Ekranı")

selected = st.session_state.get("selected_stock")
if selected:
    with st.spinner(f"{selected} verileri yükleniyor..."):
        df_price, signal, news = get_detail(selected)
    
    from ui.components.stock_detail import render_stock_detail
    render_stock_detail(selected, df_price, signal, news)
    st.stop()  # Asagidaki ana tabloyu render etme

st.caption("Hisseye tıklayarak detaylarını açabilirsiniz. Tablo her 30 dakikada otomatik yenilenir.")
col_refresh, col_search = st.columns([1, 3])
with col_refresh:
    if st.button("🔄 Yenile", type="primary"):
        st.cache_data.clear()
        st.rerun()
with col_search:
    search = st.text_input("Hisse Ara (sembol veya şirket)", placeholder="THYAO, Garanti...")

# ── Hisse Tablosu ─────────────────────────────────────────────────────────────
with st.spinner("BIST-100 taranıyor..."):
    df_all = scan_stocks()

if df_all.empty:
    st.error("Hisse verisi yüklenemedi. `data/raw/` klasöründe parquet dosyaları olmalı.")
    st.stop()

# --- PORTFÖY YÖNETİCİSİ (Portfolio Manager) FİLTRESİ ---
try:
    from portfolio.portfolio_manager import PortfolioManager
    from data.price_fetcher import load_prices
    
    pm = PortfolioManager()
    
    # BIST100 uzerinden genel pazar Drawdown hesabi (Son 30 gun)
    mdd = 0.0
    df_xu = load_prices("XU100")
    if df_xu is not None and not df_xu.empty:
        last_30 = df_xu.tail(30)["Close"]
        peak = last_30.max()
        curr = last_30.iloc[-1]
        mdd = ((peak - curr) / peak) * 100.0

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🛡️ Portföy Yöneticisi")
    st.sidebar.metric("BIST100 MDD (30 Gün)", f"%{mdd:.1f}")
    if mdd > pm.max_drawdown_pct:
        st.sidebar.error("Maksimum Drawdown Aşıldı! Alımlar Durduruldu.")
    else:
        st.sidebar.success("Piyasa Riski Normal Seviyede")

    # AL sinyallerini puana gore sirala ve portfoye girmeye calisanlari denetle
    df_all = df_all.sort_values("Skor", ascending=False).reset_index(drop=True)
    simulated_portfolio = []
    
    for idx, row in df_all.iterrows():
        if row["Sinyal"] == "AL":
            approved, reason = pm.approve_signal(row["Sembol"], simulated_portfolio, mdd)
            if approved:
                simulated_portfolio.append(row["Sembol"])
            else:
                df_all.at[idx, "Sinyal"] = "BEKLE"
                df_all.at[idx, "_reason"] = f"Portföy Reddi: {reason}"
                
    st.sidebar.markdown(f"**Önerilen Portföy ({len(simulated_portfolio)}/{pm.max_positions}):**")
    st.sidebar.caption(", ".join(simulated_portfolio) if simulated_portfolio else "Boş")
except Exception as e:
    st.error(f"Portföy Yönetici Hatası: {e}")

# Arama filtresi
if search:
    mask = (df_all["Sembol"].str.contains(search.upper(), na=False) |
            df_all["Şirket"].str.contains(search, case=False, na=False))
    df_filtered = df_all[mask].copy()
else:
    df_filtered = df_all.copy()

# Renk sütunu (Sinyal)
def color_signal(val):
    if val == "AL":
        return "background-color: #052e16; color: #4ade80; font-weight:bold"
    elif val == "SAT":
        return "background-color: #450a0a; color: #f87171; font-weight:bold"
    return "background-color: #1e293b; color: #94a3b8"

def color_daily(val):
    if val > 0:
        return "color: #4ade80"
    elif val < 0:
        return "color: #f87171"
    return ""

# Gösterim tablosu (dahili sütunlar çıkar)
display_cols = ["Sembol", "Şirket", "Sektör", "Fiyat", "Günlük%", "Skor", "Sinyal", "RSI", "Trend", "Momentum", "Hacim", "Temel"]
df_display = df_filtered[display_cols].copy()

# Ayrı sekmede açılabilmesi için Detay URL'si ekle
df_display.insert(0, "Detay", "Detay?hisse=" + df_display["Sembol"])

st.markdown("### 📋 Hisse Listesi")
st.caption("👆 'Detay' sütunundaki linke tıklayarak (veya farenin orta tuşuyla) hisseyi ayrı sekmede açabilirsiniz.")

st.dataframe(
    df_display.style
        .map(color_signal, subset=["Sinyal"])
        .map(color_daily,  subset=["Günlük%"])
        .background_gradient(subset=["Skor"], cmap="RdYlGn", vmin=0, vmax=100),
    use_container_width=True,
    hide_index=True,
    height=420,
    column_config={
        "Detay": st.column_config.LinkColumn(
            "Detay",
            display_text="Aç 🔗",
            width="small"
        )
    }
)

# Hisse Seçim Kutusu (alternatif)
st.markdown("---")
all_syms  = df_filtered["Sembol"].tolist()
manual_select = st.selectbox(
    "Veya listeden seçip doğrudan gidin:",
    ["(Seçiniz)"] + all_syms,
    index=0,
    label_visibility="collapsed"
)
if manual_select != "(Seçiniz)":
    st.query_params["hisse"] = manual_select
    st.switch_page("pages/2_Detay.py")

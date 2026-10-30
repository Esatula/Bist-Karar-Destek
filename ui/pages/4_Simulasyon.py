import streamlit as st
import time
import pandas as pd
from datetime import datetime, timezone
import random
import os
import sqlite3

from data.bist_universe import get_universe
from data.price_fetcher import fetch_prices, save_prices, load_prices
from indicators.technical import calculate_indicators
from signals.signal_engine import _technical_score

# Ekran Ayarları
st.set_page_config(page_title="Simülasyon", page_icon="🔬", layout="wide")
st.title("🔬 BIST Karar Destek Sistemi: Backtest Simülasyonu")
st.markdown("Geçmiş verilere dayalı algoritmik trade testlerinizi bu ekrandan yapabilirsiniz.")

# --- Session State ---
if "sim_running" not in st.session_state:
    st.session_state.sim_running = False
if "sim_results" not in st.session_state:
    st.session_state.sim_results = None

# --- Veri Kaynağı ---
universe = get_universe("bist100")
all_symbols = [item["symbol"] for item in universe]

# --- Ana Ekran Ayarları ---
st.markdown("### ⚙️ Parametreler")
col1, col2, col3 = st.columns(3)

with col1:
    capital = st.number_input("Başlangıç Sermayesi (TL)", min_value=1000, value=100000, step=10000)
    months_back = st.selectbox("Vade", options=[1, 3, 6, 12, 24], index=2, format_func=lambda x: f"Son {x} Ay")

with col2:
    selection_type = st.radio("Hisse Seçimi", options=["Manuel", "Rastgele"])
    ai_mode = st.checkbox("Yapay Zeka (Haber Analizi)", value=False, disabled=True, help="Şu an devre dışı")

with col3:
    selected_stocks = []
    if selection_type == "Manuel":
        selected_stocks = st.multiselect("Test Edilecek Hisseler", options=all_symbols, default=["THYAO", "ASELS"])
    else:
        stock_count = st.slider("Hisse Sayısı", min_value=1, max_value=50, value=10)
        if st.button("Hisseleri Çek/Yenile"):
            selected_stocks = random.sample(all_symbols, stock_count)
            st.session_state.random_stocks = selected_stocks
        else:
            selected_stocks = st.session_state.get("random_stocks", random.sample(all_symbols, stock_count))
        st.caption("Seçilenler: " + ", ".join(selected_stocks))
        
with st.expander("🛠️ Gelişmiş Strateji Ayarları (Quant)"):
    qc1, qc2, qc3 = st.columns(3)
    with qc1:
        sim_slippage = st.number_input("Kayma (Slippage) Oranı (%)", min_value=0.0, max_value=5.0, value=0.2, step=0.1, help="Emir gerçekleşirken tahta derinliğinden yaşanan fiyat kayması")
        sim_commission = st.number_input("Komisyon Oranı (%)", min_value=0.0, max_value=2.0, value=0.1, step=0.05)
    with qc2:
        sim_use_atr = st.checkbox("Dinamik ATR Hedefleme (Önerilen)", value=True, help="Sabit % hedef yerine hisse volatilitesine göre hedef koyar")
        sim_atr_tp = st.number_input("ATR Kâr-Al Çarpanı", min_value=0.1, max_value=10.0, value=2.0, step=0.5, disabled=not sim_use_atr)
        sim_atr_sl = st.number_input("ATR Zarar-Kes Çarpanı", min_value=0.1, max_value=5.0, value=1.0, step=0.1, disabled=not sim_use_atr)
    with qc3:
        st.markdown("<br>", unsafe_allow_html=True)
        sim_tp_pct = st.number_input("Sabit Kâr-Al (%)", min_value=1.0, max_value=50.0, value=5.0, step=0.5, disabled=sim_use_atr)
        sim_sl_pct = st.number_input("Sabit Zarar-Kes (%)", min_value=0.5, max_value=25.0, value=2.5, step=0.5, disabled=sim_use_atr)
        
st.markdown("---")
start_btn = st.button("🚀 Simülasyonu Başlat", type="primary", use_container_width=True, disabled=st.session_state.sim_running)

# --- İlerleme ve Fonksiyonlar ---
if start_btn and len(selected_stocks) > 0:
    st.session_state.sim_running = True
    st.session_state.sim_results = None
    
    progress_text = st.empty()
    progress_bar = st.progress(0)
    
    with st.spinner("Hazırlık yapılıyor..."):
        # 1. Tarihleri hesapla
        from datetime import timedelta
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30 * months_back)
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")
        
        db_path = "data/news/news.db"
        
        progress_text.text(f"XU100 verisi güncelleniyor...")
        xu100_df_raw = fetch_prices("XU100", start_str, end_str)
        if not xu100_df_raw.empty:
            save_prices(xu100_df_raw, "XU100")
            xu100_df = calculate_indicators(xu100_df_raw)
        else:
            xu100_df = None
            
        progress_bar.progress(5)
        
        # 2. Hisse Fiyatlarını Çek
        stock_dfs = {}
        for i, sym in enumerate(selected_stocks):
            progress_text.text(f"Fiyatlar indiriliyor: {sym} ({i+1}/{len(selected_stocks)})")
            df = fetch_prices(sym, start_str, end_str)
            if not df.empty:
                save_prices(df, sym)
                stock_dfs[sym] = calculate_indicators(df)
            progress_bar.progress(5 + int(10 * (i+1)/len(selected_stocks))) # %5 to %15
            
        # 3. Haberleri Çek ve Analiz Et (AI Modu)
        if ai_mode:
            progress_text.text("Geçmiş haberler Google News'ten aranıyor...")
            import feedparser
            import urllib.parse
            from news.news_fetcher import save_news
            
            # Ayda max 3 haber alacak şekilde monkey-patch
            def fetch_limited(symbol, company_name, sd, ed):
                query = f'{symbol} OR "{company_name}" after:{sd} before:{ed}'
                encoded_query = urllib.parse.quote(query)
                url = f"https://news.google.com/rss/search?q={encoded_query}&hl=tr&gl=TR&ceid=TR:tr"
                feed = feedparser.parse(url)
                news_list = []
                for entry in feed.entries[:3]:
                    title = entry.get("title", "")
                    link = entry.get("link", "")
                    summary = entry.get("summary", "")
                    published_parsed = entry.get("published_parsed")
                    if published_parsed:
                        published_dt = datetime.fromtimestamp(time.mktime(published_parsed), tz=timezone.utc)
                        published_str = published_dt.strftime("%Y-%m-%dT%H:%M:%S")
                    else:
                        published_str = datetime.strptime(sd, "%Y-%m-%d").strftime("%Y-%m-%dT12:00:00")
                    news_list.append({
                        "title": title, "link": link, "summary": summary,
                        "published_at": published_str, "source": "Google News (Tarihsel)", "symbol_mentions": symbol
                    })
                return news_list
                
            import news.historical_fetcher
            news.historical_fetcher.fetch_historical_news = fetch_limited
            
            target_stocks = [item for item in universe if item["symbol"] in selected_stocks]
            
            # DB temizle ki yeni test temiz baslasin
            if os.path.exists(db_path):
                os.remove(db_path)
                
            news.historical_fetcher.run_historical_fetch_for_symbols(target_stocks, months_back=months_back, db_path=db_path)
            
            progress_bar.progress(25)
            
            # Haberleri oku
            from news.news_fetcher import load_news
            news_items = load_news(path=db_path, limit=5000)
            filtered_news = [n for n in news_items if n.get("symbol_mentions")]
            total_news = len(filtered_news)
            
            if total_news > 0:
                from llm.news_analyzer import analyze_headline, _DEFAULT_MODEL_PATH
                for i, item in enumerate(filtered_news):
                    progress_text.text(f"LLM Analizi (GPU): {item.get('symbol_mentions')} haberi okunuyor... ({i+1}/{total_news})")
                    analyze_headline(
                        title=item.get("title", ""),
                        summary=item.get("summary", ""),
                        symbol=item.get("symbol_mentions", ""),
                        link=item.get("link", ""),
                        db_path=db_path,
                        model=_DEFAULT_MODEL_PATH
                    )
                    pct = 25 + int(50 * (i+1)/total_news) # %25 to %75
                    progress_bar.progress(pct)
            else:
                progress_bar.progress(75)

        else:
            progress_bar.progress(75)
            
        # 4. Portföy Backtest Motoru
        progress_text.text("Portföy Simülasyonu çalıştırılıyor...")
        dfs_clean = {sym: df for sym, df in stock_dfs.items() if df is not None and not df.empty}
        
        score_dicts = {}
        total = len(dfs_clean)
        for i, (sym, df_ind) in enumerate(dfs_clean.items()):
            classic_scores = {}
            for date, row in df_ind.iterrows():
                window = df_ind.loc[:date]
                t_score, _ = _technical_score(window, xu100_df=xu100_df)
                classic_scores[date] = t_score
            score_dicts[sym] = pd.Series(classic_scores)
            progress_bar.progress(75 + int(25 * (i+1)/total) if total > 0 else 100)
            
        import importlib
        import backtest.portfolio_backtest
        importlib.reload(backtest.portfolio_backtest)
        from backtest.portfolio_backtest import run_portfolio_backtest
        
        res_portfolio = run_portfolio_backtest(
            dfs_clean, 
            signal_scores=score_dicts, 
            initial_capital=capital,
            commission_pct=sim_commission,
            slippage_pct=sim_slippage,
            use_atr_dynamic=sim_use_atr,
            atr_tp_multiplier=sim_atr_tp,
            atr_sl_multiplier=sim_atr_sl,
            take_profit_pct=sim_tp_pct / 100.0,
            stop_loss_pct=sim_sl_pct / 100.0
        )
        
        progress_text.text("Simülasyon Tamamlandı!")
        st.session_state.sim_results = res_portfolio
        st.session_state.sim_running = False

# --- Sonuç Ekranı ---
if st.session_state.sim_results:
    st.success("Portföy Simülasyonu başarıyla tamamlandı!")
    res = st.session_state.sim_results
    
    net_kar = res['final_capital'] - capital
    renk = "#4CAF50" if net_kar >= 0 else "#F44336"
    
    st.markdown(f"""
    <div style="padding: 20px; background-color: #1E1E1E; border-radius: 10px; border-left: 6px solid {renk}; margin-bottom: 25px;">
        <h3 style="margin-top: 0; color: #FFFFFF;">💰 Portföy Özeti</h3>
        <div style="display: flex; justify-content: space-between; font-size: 18px; color: #DDDDDD;">
            <div><b>Başlangıç Sermayesi:</b> <br> <span style="font-size: 24px; color: #FFFFFF;">{capital:,.2f} ₺</span></div>
            <div><b>Bitiş Sermayesi:</b> <br> <span style="font-size: 24px; color: #FFFFFF;">{res['final_capital']:,.2f} ₺</span></div>
            <div><b>Net Kâr / Zarar:</b> <br> <span style="font-size: 24px; color: {renk}; font-weight: bold;">{net_kar:,.2f} ₺</span></div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col3, col4 = st.columns(3)
    col1.metric("Toplam Getiri (%)", f"%{res['total_return']}")
    col3.metric("Kazanma Oranı", f"%{res['win_rate']*100:.1f}")
    col4.metric("Toplam İşlem", res['num_trades'])
    
    c1, c2, c4 = st.columns(3)
    c1.metric("Max Çekilme (Drawdown)", f"%{res['max_drawdown']}")
    c2.metric("Sharpe Oranı", res['sharpe_ratio'])
    c4.metric("Kazanç/Kayıp Oranı", res['avg_win_loss'])
    
    def color_profit(val):
        color = '#4CAF50' if val > 0 else '#F44336' if val < 0 else 'white'
        return f'color: {color}; font-weight: bold;'
    
    if res["trades"]:
        raw_trades = pd.DataFrame(res["trades"])
        
        # --- HİSSE BAZLI ÖZET TABLOSU ---
        st.subheader("📊 Hisse Bazlı Performans Özeti")
        summary_df = raw_trades.groupby("symbol").agg(
            islem_sayisi=("win", "count"),
            karli_islem=("win", "sum"),
            toplam_kar=("pnl", "sum"),
            ort_getiri=("pnl_pct", "mean")
        ).reset_index()
        
        summary_df["kazanma_orani"] = (summary_df["karli_islem"] / summary_df["islem_sayisi"]) * 100
        
        summary_df = summary_df.rename(columns={
            "symbol": "Hisse",
            "islem_sayisi": "Toplam İşlem",
            "karli_islem": "Başarılı İşlem",
            "kazanma_orani": "Kazanma Oranı (%)",
            "toplam_kar": "Net Kâr/Zarar (₺)",
            "ort_getiri": "Ort. İşlem Getirisi (%)"
        })
        
        # Toplam Kâr'a göre büyükten küçüğe sırala
        summary_df = summary_df.sort_values(by="Net Kâr/Zarar (₺)", ascending=False)
        
        st.dataframe(
            summary_df.style.map(
                color_profit, subset=["Net Kâr/Zarar (₺)", "Ort. İşlem Getirisi (%)"]
            ).format({
                "Net Kâr/Zarar (₺)": "{:,.2f} ₺",
                "Ort. İşlem Getirisi (%)": "%{:.2f}",
                "Kazanma Oranı (%)": "%{:.1f}"
            }),
            use_container_width=True,
            hide_index=True
        )
        
        # --- İŞLEM GEÇMİŞİ (TRADES) ---
        st.subheader("📜 Detaylı İşlem Geçmişi (Trades)")
        df_trades = pd.DataFrame(res["trades"])
        df_trades["buy_date"] = pd.to_datetime(df_trades["buy_date"]).dt.strftime("%Y-%m-%d")
        df_trades["sell_date"] = pd.to_datetime(df_trades["sell_date"]).dt.strftime("%Y-%m-%d")
        
        if "pnl_pct" not in df_trades.columns:
            df_trades["pnl_pct"] = 0.0
            
        df_trades["win"] = df_trades["win"].map({True: "✅ Kâr", False: "❌ Zarar"})
        
        df_trades = df_trades.rename(columns={
            "symbol": "Hisse", "buy_date": "Alış", "sell_date": "Satış",
            "buy_price": "Maliyet (₺)", "sell_price": "Satış Fiyatı (₺)",
            "pnl": "Net Kâr/Zarar", "pnl_pct": "Getiri (%)", "win": "Durum", "type": "Kapanış Tipi"
        })
        
        st.dataframe(
            df_trades.style.map(
                color_profit, subset=["Net Kâr/Zarar", "Getiri (%)"]
            ).map(
                lambda x: "color: #4CAF50; font-weight: bold;" if "✅" in str(x) else "color: #F44336; font-weight: bold;",
                subset=["Durum"]
            ).format({
                "Net Kâr/Zarar": "{:,.2f} ₺", 
                "Maliyet (₺)": "{:,.2f} ₺", 
                "Satış Fiyatı (₺)": "{:,.2f} ₺",
                "Getiri (%)": "%{:.2f}"
            }),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("Bu dönemde hiç işlem yapılmadı.")

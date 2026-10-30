import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import sqlite3

def render_header(sym: str, detail_data: dict, price_df: pd.DataFrame):
    """Sirket basligi ve fiyat ozet seridini cizer"""
    last_row = price_df.iloc[-1]
    prev_row = price_df.iloc[-2] if len(price_df) > 1 else last_row
    
    price = last_row["Close"]
    prev_close = prev_row["Close"]
    change_tl = price - prev_close
    change_pct = (change_tl / prev_close) * 100
    
    color = "normal" if change_pct == 0 else "inverse" if change_pct < 0 else "normal"
    sign = "+" if change_pct > 0 else ""
    
    col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 1, 1])
    
    with col1:
        st.markdown(f"## {sym}")
        st.caption(f"Son Güncelleme: {datetime.now().strftime('%H:%M')}")
        
    with col2:
        st.metric("Fiyat", f"{price:.2f} ₺", f"{sign}{change_tl:.2f} ({sign}{change_pct:.2f}%)", delta_color=color)
        
    with col3:
        st.metric("Açılış", f"{last_row.get('Open', price):.2f} ₺")
        
    with col4:
        st.metric("Gün İçi Yüksek", f"{last_row.get('High', price):.2f} ₺")
        st.metric("Gün İçi Düşük", f"{last_row.get('Low', price):.2f} ₺")
        
    with col5:
        volume = last_row.get("Volume", 0)
        st.metric("Hacim", f"{volume:,.0f}")
        
    st.markdown("---")

def render_speedometer(score: float, title: str):
    """Investing tarzi yarim daire (Gauge) sinyal ibresi"""
    if score >= 70:
        color = "#22c55e"
        text = "Güçlü AL"
    elif score >= 60:
        color = "#4ade80"
        text = "AL"
    elif score <= 30:
        color = "#ef4444"
        text = "Güçlü SAT"
    elif score <= 40:
        color = "#f87171"
        text = "SAT"
    else:
        color = "#94a3b8"
        text = "NÖTR"

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        domain={'x': [0, 1], 'y': [0, 1]},
        title={'text': f"<b>{title}</b><br><span style='color:{color}; font-size:24px'>{text}</span>", 'font': {'size': 18}},
        gauge={
            'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': "white"},
            'bar': {'color': color, 'thickness': 0.25},
            'bgcolor': "#1e293b",
            'borderwidth': 2,
            'bordercolor': "gray",
            'steps': [
                {'range': [0, 40], 'color': 'rgba(239, 68, 68, 0.3)'},
                {'range': [40, 60], 'color': 'rgba(148, 163, 184, 0.3)'},
                {'range': [60, 100], 'color': 'rgba(34, 197, 94, 0.3)'}
            ],
            'threshold': {
                'line': {'color': "white", 'width': 4},
                'thickness': 0.75,
                'value': score
            }
        }
    ))
    
    fig.update_layout(
        height=250, 
        margin=dict(l=10, r=10, t=50, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        font={'color': "#e2e8f0"}
    )
    st.plotly_chart(fig, use_container_width=True)

def render_price_chart(df: pd.DataFrame):
    """Plotly ile Lightweight stili Candlestick ve Hacim Grafigi"""
    # Alt panel hacim icin subplot kullaniyoruz (orani 0.8 / 0.2)
    from plotly.subplots import make_subplots
    
    # 150 gunluk kismi goster
    df_chart = df.tail(150)
    
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.03, subplot_titles=('', ''), 
                        row_width=[0.2, 0.7])
    
    # Candlestick
    fig.add_trace(go.Candlestick(
        x=df_chart.index,
        open=df_chart['Open'],
        high=df_chart['High'],
        low=df_chart['Low'],
        close=df_chart['Close'],
        name='Fiyat'
    ), row=1, col=1)
    
    # EMA'lar
    if "EMA_20" in df_chart.columns:
        fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart["EMA_20"], mode='lines', name='EMA 20', line=dict(color='#f59e0b', width=1.5)), row=1, col=1)
    if "EMA_50" in df_chart.columns:
        fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart["EMA_50"], mode='lines', name='EMA 50', line=dict(color='#3b82f6', width=1.5)), row=1, col=1)
        
    # Hacim Barlari
    colors = ['#22c55e' if row['Close'] >= row['Open'] else '#ef4444' for index, row in df_chart.iterrows()]
    fig.add_trace(go.Bar(
        x=df_chart.index,
        y=df_chart['Volume'],
        marker_color=colors,
        name='Hacim'
    ), row=2, col=1)
    
    fig.update_layout(
        title="Fiyat ve Hacim",
        yaxis_title="Fiyat",
        yaxis2_title="Hacim",
        xaxis2_rangeslider_visible=False,
        xaxis_rangeslider_visible=False,
        height=500,
        margin=dict(l=0, r=0, t=40, b=0),
        paper_bgcolor="#0f172a", plot_bgcolor="#0f172a",
        font=dict(color="#e2e8f0"),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    
    fig.update_xaxes(gridcolor="#1e293b", showgrid=True)
    fig.update_yaxes(gridcolor="#1e293b", showgrid=True)
    
    st.plotly_chart(fig, use_container_width=True)

def render_signal_details(detail_data: dict):
    """Sub-skorlar icin detay paneli"""
    st.markdown("### 🔍 Karar Gerekçesi (Sinyal Kırılımı)")
    
    # Teknik
    tech_score = detail_data.get("tech", 50)
    st.markdown(f"**Teknik Analiz Motoru:** {tech_score:.1f}/100")
    st.progress(int(tech_score))
    
    col1, col2 = st.columns(2)
    with col1:
        st.write("📈 **Trend:**", "Pozitif" if detail_data.get("trend") else "Negatif")
        st.write("🚀 **Momentum:**", "Pozitif" if detail_data.get("momentum") else "Negatif")
    with col2:
        st.write("📊 **Hacim Onayı:**", "Var" if detail_data.get("volume") else "Yok")
        st.write("📉 **RSI (14):**", detail_data.get("rsi", "Bilinmiyor"))
        
    st.info(f"Yapay Zeka Özeti: {detail_data.get('reason', 'N/A')}")
    
def render_fundamentals(sym: str):
    """Temel analiz verileri (Value Trap)"""
    from data.fundamentals import get_fundamental_data
    st.markdown("### 🏢 Temel Analiz Sağlığı")
    fund = get_fundamental_data(sym)
    
    if not fund:
        st.warning("Temel analiz verisi bulunamadı.")
        return
        
    pm = fund.get("profit_margin", 0)
    dte = fund.get("debt_to_equity", 0)
    pe = fund.get("trailing_pe", 0)
    
    col1, col2, col3 = st.columns(3)
    
    # Kar Marji
    pm_val = (pm * 100) if pm else 0.0
    pm_color = "normal" if pm_val > 0 else "inverse"
    col1.metric("Net Kâr Marjı", f"%{pm_val:.1f}", delta="Riskli!" if pm_val < 0 else "Pozitif", delta_color=pm_color)
    
    # Borc
    dte_val = dte if dte else 0.0
    dte_color = "inverse" if dte_val > 200 else "normal"
    col2.metric("Borç / Özkaynak", f"%{dte_val:.0f}", delta="Aşırı Borç" if dte_val > 200 else "Kabul Edilebilir", delta_color=dte_color)
    
    # F/K
    pe_val = pe if pe else 0.0
    col3.metric("F/K Oranı", f"{pe_val:.1f}")

def render_news_and_history(sym: str, news: list):
    """Haber akisi ve Gecmis isabet sekmesi"""
    tab1, tab2 = st.tabs(["📰 Haber Akışı", "🕰️ Geçmiş Sinyaller"])
    
    with tab1:
        if not news:
            st.info("Bu hisse için yakın zamanda önemli bir haber/KAP düşmedi.")
        else:
            for n in news:
                sentiment = n.get("sentiment", "neutral").lower()
                color = "green" if sentiment == "positive" else "red" if sentiment == "negative" else "gray"
                icon = "🟢" if sentiment == "positive" else "🔴" if sentiment == "negative" else "⚪"
                
                with st.expander(f"{icon} {n['date'][:10]} - {n['title']} ({n['source']})"):
                    st.write(n['summary'])
                    st.caption(f"[Haber Linki]({n.get('link', '#')})")
                    
    with tab2:
        st.markdown("*(Bu sekme TV geçmişini ve LLM başarı oranlarını içerir. Özellik test aşamasındadır.)*")
        st.info("BIST-100 geçmiş 30 günlük sinyal başarı haritası burada render edilecektir.")

def render_stock_detail(sym: str, df_price: pd.DataFrame, signal: dict, news: list):
    """Ana bilesen. 2_Detay.py icerisinden cagirilir."""
    
    if df_price is None or df_price.empty:
        st.error("Fiyat verisi bulunamadı!")
        return
        
    render_header(sym, signal, df_price)
    
    col_gauge1, col_gauge2 = st.columns(2)
    with col_gauge1:
        # Orta vade: Mevcut final skorumuz
        render_speedometer(signal["final"], "Orta Vade Skoru (1-3 Ay)")
    with col_gauge2:
        # Uzun Vade (Simulasyon): Temel Analiz agirligi artirilmis
        # Fundamentaldan kirmizi bayrak varsa puan dip, yoksa teknik+tv
        fund_score = 100 if signal.get("fundamental", True) else 30
        long_term_score = (signal["tech"] * 0.4) + (fund_score * 0.6)
        render_speedometer(long_term_score, "Uzun Vade Skoru (6-12 Ay)")

    # AI Sentezi kaldirildi
        
    st.markdown("---")
    render_price_chart(df_price)
    
    st.markdown("---")
    render_signal_details(signal)
    
    st.markdown("---")
    render_fundamentals(sym)
    
    st.markdown("---")
    render_news_and_history(sym, news)

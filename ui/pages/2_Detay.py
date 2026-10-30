"""
ui/pages/2_Detay.py
-------------------
Bireysel hisse senedi detay sayfası.
st.query_params üzerinden "?hisse=THYAO" parametresini alarak çalışır.
"""

import streamlit as st

from ui.data_layer import get_detail
from ui.components.stock_detail import render_stock_detail

sym = st.query_params.get("hisse")

if not sym:
    from data.bist_universe import get_symbols
    st.warning("⚠️ Lütfen Borsa sayfasından bir hisse seçin veya arama yapın.")
    symbols = get_symbols("bist100")
    search = st.selectbox("Veya Hisse Kodu Seçin/Yazın:", [""] + symbols)
    if search:
        st.query_params["hisse"] = search.upper()
        st.rerun()
    st.stop()

st.title(f"📈 {sym} — Detaylı Analiz")

with st.spinner(f"{sym} verileri yükleniyor, lütfen bekleyin..."):
    df_price, signal, news = get_detail(sym)
    
if df_price is None or df_price.empty:
    st.error(f"{sym} kodlu hisse için veri bulunamadı. Kodu yanlış yazmış olabilirsiniz.")
    if st.button("⬅️ Geri Dön"):
        st.switch_page("pages/1_Borsa.py")
    st.stop()

# Detay sayfasını render et
render_stock_detail(sym, df_price, signal, news)

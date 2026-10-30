"""
ui/pages/2_Hisselerim.py
------------------------
Sanal portföy durumu ve geçmiş işlemlerin (simüle edilmiş) izlendiği sayfa.
"""

import streamlit as st
import pandas as pd
import plotly.express as px

st.title("💼 Hisselerim (Portföy Simülasyonu)")
st.markdown("Bu sayfa, aracı kurum bağlantısı kurulana kadar simülasyon amaçlı sanal bir portföy gösterir.")

# Sanal Bakiye State'i Başlat
if "virtual_cash" not in st.session_state:
    st.session_state.virtual_cash = 100000.0  # 100.000 TL başlangıç

if "virtual_portfolio" not in st.session_state:
    # Dummy veri: Kullanıcının daha önceden almış olduğu varsayılan hisseler
    st.session_state.virtual_portfolio = [
        {"Sembol": "THYAO", "Adet": 50, "Maliyet": 250.50, "Guncel_Fiyat": 260.00},
        {"Sembol": "ASELS", "Adet": 200, "Maliyet": 45.20, "Guncel_Fiyat": 44.10},
    ]

# Bekleyen emirleri (Borsa sayfasından gelen) simüle ederek işlet (gerçekte backtest veya broker yapar)
if "pending_orders" in st.session_state and len(st.session_state.pending_orders) > 0:
    st.info(f"{len(st.session_state.pending_orders)} adet bekleyen emriniz var (Simülasyon arka planda işletiliyor).")
    # Gerçek bir sistemde burada bekleyen emirler listelenip iptal edilebilir.

# ---------------------------------------------------------------------------
# Portföy Hesaplamaları
# ---------------------------------------------------------------------------
df_port = pd.DataFrame(st.session_state.virtual_portfolio)

if not df_port.empty:
    df_port["Toplam_Maliyet"] = df_port["Adet"] * df_port["Maliyet"]
    df_port["Guncel_Deger"] = df_port["Adet"] * df_port["Guncel_Fiyat"]
    df_port["Kâr_Zarar"] = df_port["Guncel_Deger"] - df_port["Toplam_Maliyet"]
    df_port["Kâr_Zarar_%"] = (df_port["Kâr_Zarar"] / df_port["Toplam_Maliyet"]) * 100

    toplam_hisse_degeri = df_port["Guncel_Deger"].sum()
    toplam_maliyet = df_port["Toplam_Maliyet"].sum()
    toplam_kz = toplam_hisse_degeri - toplam_maliyet
else:
    toplam_hisse_degeri = 0
    toplam_kz = 0

toplam_varlik = st.session_state.virtual_cash + toplam_hisse_degeri

# ---------------------------------------------------------------------------
# Üst Panel: Özet Metrikler
# ---------------------------------------------------------------------------
st.divider()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Toplam Varlık", f"{toplam_varlik:,.2f} TL")
c2.metric("Nakit Bakiye", f"{st.session_state.virtual_cash:,.2f} TL")
c3.metric("Hisse Senedi Değeri", f"{toplam_hisse_degeri:,.2f} TL")

# Kâr/Zarar rengi
kz_color = "normal" if toplam_kz >= 0 else "inverse"
c4.metric("Açık PnL", f"{toplam_kz:,.2f} TL", delta_color=kz_color)

# ---------------------------------------------------------------------------
# Tablo ve Dağılım Grafiği
# ---------------------------------------------------------------------------
st.divider()

if not df_port.empty:
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("📊 Açık Pozisyonlar")
        # DataFrame formatlama
        format_dict = {
            "Maliyet": "{:.2f} ₺",
            "Guncel_Fiyat": "{:.2f} ₺",
            "Toplam_Maliyet": "{:,.2f} ₺",
            "Guncel_Deger": "{:,.2f} ₺",
            "Kâr_Zarar": "{:+,.2f} ₺",
            "Kâr_Zarar_%": "{:+.2f}%"
        }
        
        # PnL kolonunu renklendirmek için Pandas Styler
        styler = df_port.style.format(format_dict)
        styler = styler.map(lambda x: 'color: green' if x > 0 else 'color: red' if x < 0 else '', subset=['Kâr_Zarar', 'Kâr_Zarar_%'])
        
        st.dataframe(styler, use_container_width=True, hide_index=True)
        
    with col2:
        st.subheader("Varlık Dağılımı")
        
        # Nakit + Hisseler için pasta grafik verisi
        pie_data = [{"Varlık": "Nakit", "Değer": st.session_state.virtual_cash}]
        for idx, row in df_port.iterrows():
            pie_data.append({"Varlık": row["Sembol"], "Değer": row["Guncel_Deger"]})
            
        df_pie = pd.DataFrame(pie_data)
        
        fig = px.pie(
            df_pie, 
            values='Değer', 
            names='Varlık', 
            hole=0.4,
            template="plotly_dark" if st.session_state.get("theme") == "Karanlık (Dark)" else "plotly_white"
        )
        fig.update_layout(margin=dict(l=20, r=20, t=20, b=20), height=300)
        st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Henüz portföyünüzde açık pozisyon bulunmuyor. 'Borsa' sekmesinden alım yapabilirsiniz.")

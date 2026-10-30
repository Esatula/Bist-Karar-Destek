"""
ui/dashboard.py
---------------
Borsa Bot 2 için ana Streamlit giriş noktası (Yönlendirici).
Alt sayfalar `pages/` klasöründe yer almaktadır.
"""

import sys
import os
import streamlit as st

# Proje kök dizinini sys.path'e ekle
# NOT: `pip install -e .` ile paket kurulursa bu satıra gerek kalmaz.
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Sayfa genel ayarları (Tüm sayfalara yansır)
st.set_page_config(
    page_title="BIST Bot 2 Dashboard",
    page_icon="📈",
    layout="wide"
)

st.title("BIST Karar Destek Sistemi'ne Hoş Geldiniz! 🚀")
st.markdown("""
Sol taraftaki menüyü kullanarak paneller arası geçiş yapabilirsiniz:

* **🔍 Tarama:** BIST-100 evren tarayıcı — tüm hisseleri tek tabloda görün.
* **📈 Borsa:** Piyasa taraması, teknik skorlu sinyal tablosu ve hisse detayları.
* **💼 Hisselerim:** Portföy durumu ve sanal bakiye yönetimi.
* **🔬 Simülasyon:** Geçmiş verilere dayalı backtest simülasyonu.

*(İpucu: Tema değiştirmek için sağ üst köşedeki `⋮` → Settings → Theme bölümünü kullanabilirsiniz.)*
""")

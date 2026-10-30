"""
portfolio_manager.py
--------------------
Portföy Seviyesi Risk Yönetimi Modülü

Bu modül, sinyal motorundan gelen ham "AL" kararlarını portföyün genel
durumuna (açık pozisyon sayısı, sektör konsantrasyonu, portföy MDD'si) göre filtreler.
Sinyalleri onaylayabilir veya "Sektör Limiti", "Drawdown" gibi sebeplerle reddedebilir.
"""

import logging
import yaml
import os
from pathlib import Path
from data.bist_universe import get_sector_map

logger = logging.getLogger(__name__)

class PortfolioManager:
    def __init__(self, config_path: str = "config/settings.yaml"):
        self.config_path = config_path
        self._load_config()
        # Sembol -> Sektor haritasi
        self.sector_map = get_sector_map("all")
        
    def _load_config(self):
        from config.manager import config as app_cfg
        cfg = app_cfg.get_all()
        pcfg = cfg.get("portfolio", {})
        self.max_positions = pcfg.get("max_open_positions", 5)
        self.max_sector_weight_pct = pcfg.get("max_sector_weight_pct", 30.0)
        self.max_drawdown_pct = pcfg.get("max_drawdown_pct", 20.0)
            
    def approve_signal(self, symbol: str, current_open_positions: list[str], portfolio_drawdown: float) -> tuple[bool, str]:
        """
        Sinyali portfoy risk kriterlerine gore denetler.
        Returns: (Approved: bool, Reason: str)
        """
        # Eger zaten portfoydeyse satmasi/tutmasi icin engel yok, biz sadece YENI alimlari engelliyoruz.
        if symbol in current_open_positions:
            return True, "Zaten portföyde"
            
        # 1. MDD (Maksimum Drawdown) Kontrolu
        if portfolio_drawdown > self.max_drawdown_pct:
            return False, f"Portföy Drawdown ({portfolio_drawdown:.1f}%) limiti aşıldı! Alım durduruldu."
            
        # 2. Maksimum Pozisyon Kontrolu
        if len(current_open_positions) >= self.max_positions:
            return False, f"Maksimum açık pozisyon limitine ({self.max_positions}) ulaşıldı."
            
        # 3. Sektor Konsantrasyonu Kontrolu
        target_sector = self.sector_map.get(symbol, "Diğer")
        sector_counts = {}
        for pos in current_open_positions:
            sec = self.sector_map.get(pos, "Diğer")
            sector_counts[sec] = sector_counts.get(sec, 0) + 1
            
        current_sector_count = sector_counts.get(target_sector, 0)
        # Portfoy limitine gore kac hisse bu sektorde olabilir?
        # Ornek: 5 hisse x %30 limit = 1.5 -> maks 1 hisse.
        # Formul: (mevcut + 1) / (toplam acik + 1 veya max_positions)
        # Gercekte portfoy agirligi sermaye uzerinden yapilir ama hisse sayisi ile priblizik yapacagiz.
        # Varsayim: Esit agirlikli (Equal Weight)
        
        # Gelecekteki oran (Eger bu hisseyi de alirsak)
        projected_total = max(len(current_open_positions) + 1, self.max_positions)
        projected_sector_weight = ((current_sector_count + 1) / projected_total) * 100.0
        
        if projected_sector_weight > self.max_sector_weight_pct:
            return False, f"Sektör limiti aşıldı ({target_sector}: %{projected_sector_weight:.1f} > %{self.max_sector_weight_pct})."
            
        return True, "Onaylandı"

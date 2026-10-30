"""
sensitivity_tester.py
---------------------
Overfitting (Curve-fitting) kalkanı.
Sistemin kalbindeki eşik değerlerini (RSI, MACD tavanı vb.) %20 oranında
değiştirerek sonuçların (skorlama dağılımı vb.) ne kadar hassas olduğunu ölçer.
Keskin tepelerden kaçınarak, düz platolar bulmak için tasarlanmıştır.

Örnek Kullanım:
    python -m tools.sensitivity_tester
"""

import yaml
import os
import copy
import logging

logger = logging.getLogger(__name__)

class SensitivityTester:
    def __init__(self, config_path="config/settings.yaml"):
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.cpath = os.path.join(project_root, config_path)
        if not os.path.exists(self.cpath):
            self.cpath = os.path.join(project_root, "config", "settings.example.yaml")
            
        with open(self.cpath, "r", encoding="utf-8") as f:
            self.original_config = yaml.safe_load(f) or {}

    def test_parameter(self, param_name: str, values: list):
        """
        Belirtilen parametreyi degistirerek basit bir robustness kontrolu yapar.
        Canli veride tam backtest yapmak cok uzun surecegi icin bu bir ornek scripttir.
        Asil kullanimda 'backtester' modulune config enjekte edilir.
        """
        print(f"\n[DUYARLILIK TESTI] Parametre: {param_name}")
        print("-" * 50)
        
        tech_params = self.original_config.get("technical_params", {})
        original_val = tech_params.get(param_name)
        
        if original_val is None:
            print(f"Hata: {param_name} bulunamadi.")
            return

        for val in values:
            test_config = copy.deepcopy(self.original_config)
            test_config["technical_params"][param_name] = val
            
            # Burada normalde gercek bir Walk-Forward backtest cagrilir.
            # backtest_results = run_backtest(config=test_config, start="2018-01-01", end="2018-12-31")
            # Biz mock sonuc uretecegiz, gercekte backtester modulune entegre edilmelidir.
            
            # Simulated outcome
            print(f"Test Degeri: {val} (Orijinal: {original_val}) -> Simülasyon bekleniyor...")
            
        print("Not: Bu script, ayarlar uzerinde (Örn: RSI 65, 70, 75) ±%20 degisiklik yapip")
        print("sistemin cokup cokmedigini gormek uzere backtester tarafindan cagrilmalidir.")

if __name__ == "__main__":
    tester = SensitivityTester()
    tester.test_parameter("rsi_overbought", [65, 70, 75, 80])
    tester.test_parameter("macd_buy_cap", [45, 50, 55, 60])

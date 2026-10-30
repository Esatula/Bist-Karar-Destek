import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

def run_portfolio_backtest(
    dfs: dict[str, pd.DataFrame],
    signal_scores: dict[str, pd.Series],
    initial_capital: float = 100000.0,
    commission_pct: float = 0.1,
    slippage_pct: float = 0.2,            # Kapanışta emir kayması (varsayılan binde 2)
    use_atr_dynamic: bool = True,         # ATR hedefleme kullan?
    atr_tp_multiplier: float = 2.0,       # ATR Kâr-Al çarpanı
    atr_sl_multiplier: float = 1.0,       # ATR Zarar-Kes çarpanı
    take_profit_pct: float = 0.05,        # Sabit sistem için
    stop_loss_pct: float = 0.025,         # Sabit sistem için
    score_buy_threshold: float = 70.0,
    score_sell_threshold: float = 40.0,
) -> dict:
    """
    Portföy bazlı (ortak bütçe) Vur-Kaç backtest motoru.
    Aynı anda birçok hisseyi zaman serisi boyunca simüle eder.
    Sinyal skoru yüksek olana (daha çok güvenilen) daha fazla bütçe ayırır.
    """
    commission = commission_pct / 100.0
    capital = initial_capital
    positions = {}  # sym -> {"shares": x, "average_cost": y, "last_date": z}
    trades = []
    daily_returns = []
    
    # 1. Ortak tarihleri topla ve sirala
    all_dates = set()
    for sym, df in dfs.items():
        if df is not None and not df.empty:
            all_dates.update(df.index)
    sorted_dates = sorted(list(all_dates))
    
    if not sorted_dates:
        return _empty_result()
        
    prev_portfolio_value = initial_capital
    daily_equity = []  # Equity curve verisi (grafik için)
    
    for date in sorted_dates:
        # A. Satis Kontrolleri (Zarar Kes, Kar Al veya Trend Bitti)
        symbols_to_sell = []
        for sym, pos in positions.items():
            df = dfs[sym]
            if date not in df.index: 
                continue
                
            row = df.loc[date]
            price = row["Close"]
            high_price = row.get("High", price)
            low_price = row.get("Low", price)
            
            average_cost = pos["average_cost"]
            
            if use_atr_dynamic and pos.get("entry_atr", 0) > 0:
                atr_val = pos["entry_atr"]
                tp_price = average_cost + (atr_val * atr_tp_multiplier)
                sl_price = average_cost - (atr_val * atr_sl_multiplier)
                tp_label = f"ATR TP (+{atr_tp_multiplier}x)"
                sl_label = f"ATR SL (-{atr_sl_multiplier}x)"
            else:
                tp_price = average_cost * (1 + take_profit_pct)
                sl_price = average_cost * (1 - stop_loss_pct)
                tp_label = f"Kâr-Al (+%{take_profit_pct*100})"
                sl_label = f"Zarar-Kes (-%{stop_loss_pct*100})"
            
            force_sell = False
            sell_price = price
            reason = ""
            
            if high_price >= tp_price:
                force_sell = True
                sell_price = tp_price
                reason = tp_label
            elif low_price <= sl_price:
                force_sell = True
                sell_price = sl_price
                reason = sl_label
            else:
                score = signal_scores[sym].get(date, 50) if sym in signal_scores else 50
                if score <= score_sell_threshold:
                    force_sell = True
                    reason = "Trend Zayıfladı"
                    
            if force_sell:
                symbols_to_sell.append((sym, sell_price, reason))
                
        # Satis islemlerini gerceklestir ve nakde gec
        for sym, sell_price, reason in symbols_to_sell:
            pos = positions.pop(sym)
            shares = pos["shares"]
            # Satarken slippage (kayma) bedelini duş ve komisyonu kes
            effective_sell_price = sell_price * (1 - slippage_pct / 100.0)
            revenue = shares * effective_sell_price * (1 - commission)
            
            net_sell_price = revenue / shares if shares > 0 else 0
            pnl = revenue - (shares * pos["average_cost"])
            
            trades.append({
                "symbol": sym,
                "buy_date": pos["last_date"],
                "sell_date": date,
                "buy_price": pos["average_cost"],
                "sell_price": net_sell_price,
                "pnl": pnl,
                "pnl_pct": (net_sell_price / pos["average_cost"] - 1) * 100,
                "win": pnl > 0,
                "type": reason
            })
            capital += revenue
            
        # B. Alim Adaylarini Belirle (Score > Buy Threshold)
        buy_candidates = []
        for sym, df in dfs.items():
            if sym in positions: 
                continue
            if date not in df.index: 
                continue
                
            score = signal_scores[sym].get(date, 50) if sym in signal_scores else 50
            if score >= score_buy_threshold:
                price = df.loc[date]["Close"]
                atr_val = df.loc[date].get("ATR_14", 0)
                buy_candidates.append({"sym": sym, "score": score, "price": price, "atr": atr_val})
                
        # C. Bütçe Tahsisi (Allocation)
        if buy_candidates and capital > 100:
            # En yuksek skordan baslayarak gven derecesine gore tahsis yap
            buy_candidates.sort(key=lambda x: x["score"], reverse=True)
            
            # Portfoyun o anki toplam degerini (Nakit + Hisseler) hesapla
            portfolio_value = capital
            for s, p in positions.items():
                if date in dfs[s].index:
                    portfolio_value += p["shares"] * dfs[s].loc[date]["Close"]
                else:
                    portfolio_value += p["shares"] * p["average_cost"]
                    
            for cand in buy_candidates:
                if capital <= 100: 
                    break # Alinabilecek minimum tutar kalmadi
                    
                score = cand["score"]
                # Ne kadar yuksek skor, o kadar cok sermaye yuzdesi (max %40)
                if score >= 90: weight = 0.40
                elif score >= 80: weight = 0.30
                else: weight = 0.20
                
                target_invest = portfolio_value * weight
                invest_amount = min(target_invest, capital)
                
                if invest_amount > 100:
                    # Alırken slippage (kayma) maliyetini fiyata ekle
                    effective_buy_price = cand["price"] * (1 + slippage_pct / 100.0)
                    cost = invest_amount * (1 - commission)
                    shares = cost / effective_buy_price
                    
                    capital -= invest_amount
                    positions[cand["sym"]] = {
                        "shares": shares,
                        "average_cost": effective_buy_price,
                        "last_date": date,
                        "entry_atr": cand["atr"]
                    }
                    
        # D. Gunluk Portfoy Getirisi Hesabi
        current_portfolio_value = capital
        for sym, pos in positions.items():
            if date in dfs[sym].index:
                current_portfolio_value += pos["shares"] * dfs[sym].loc[date]["Close"]
            else:
                current_portfolio_value += pos["shares"] * pos["average_cost"]
                
        daily_ret = (current_portfolio_value - prev_portfolio_value) / prev_portfolio_value if prev_portfolio_value > 0 else 0
        daily_returns.append(daily_ret)
        prev_portfolio_value = current_portfolio_value
        
    # Acik pozisyonlari son gun fiyatiyla kapat
    last_date = sorted_dates[-1] if sorted_dates else None
    for sym, pos in list(positions.items()):
        price = dfs[sym].iloc[-1]["Close"]
        effective_sell_price = price * (1 - slippage_pct / 100.0)
        revenue = pos["shares"] * effective_sell_price * (1 - commission)
        
        net_sell_price = revenue / pos["shares"] if pos["shares"] > 0 else 0
        pnl = revenue - (pos["shares"] * pos["average_cost"])
        
        trades.append({
            "symbol": sym,
            "buy_date": pos["last_date"],
            "sell_date": last_date,
            "buy_price": pos["average_cost"],
            "sell_price": net_sell_price,
            "pnl": pnl,
            "pnl_pct": (net_sell_price / pos["average_cost"] - 1) * 100,
            "win": pnl > 0,
            "type": "SİM. BİTİŞ"
        })
        capital += revenue
        
    # Metrikleri Hesapla
    final_capital = capital
    total_return = (final_capital - initial_capital) / initial_capital * 100
    num_trades = len(trades)
    win_rate = sum(t["win"] for t in trades) / num_trades if num_trades > 0 else 0.0
    
    returns_series = pd.Series(daily_returns)
    cumulative = (1 + returns_series).cumprod()
    rolling_max = cumulative.cummax()
    drawdown = (cumulative - rolling_max) / rolling_max
    max_drawdown = float(drawdown.min() * 100) if not drawdown.empty else 0.0
    
    mean_ret = returns_series.mean()
    std_ret = returns_series.std()
    sharpe = (mean_ret / std_ret * np.sqrt(252)) if std_ret > 0 else 0.0
    
    wins = [t["pnl"] for t in trades if t["win"]]
    losses = [abs(t["pnl"]) for t in trades if not t["win"]]
    avg_win = np.mean(wins) if wins else 0.0
    avg_loss = np.mean(losses) if losses else 0.0
    avg_win_loss = (avg_win / avg_loss) if avg_loss > 0 else float("inf")
    
    return {
        "total_return": round(total_return, 2),
        "num_trades": num_trades,
        "win_rate": round(win_rate, 4),
        "max_drawdown": round(max_drawdown, 2),
        "sharpe_ratio": round(float(sharpe), 4),
        "avg_win_loss": round(avg_win_loss, 4),
        "final_capital": round(final_capital, 2),
        "trades": trades,
    }

def _empty_result() -> dict:
    return {
        "total_return": 0.0, "num_trades": 0, "win_rate": 0.0,
        "max_drawdown": 0.0, "sharpe_ratio": 0.0, "avg_win_loss": 0.0,
        "final_capital": 0.0, "trades": [],
    }

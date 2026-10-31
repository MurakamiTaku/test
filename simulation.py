"""
日本株 投資シミュレーション（教育用・標準ライブラリのみ）

株価は「幾何ブラウン運動」で作った架空の月次データです。
実際の日経平均・TOPIX のデータではなく、将来の成績を保証するものでもありません。

比較する戦略:
  1. 一括投資（最初に全額買って保有）
  2. 積立投資（毎月同じ金額を買う＝ドルコスト平均法）
  3. 移動平均トレンドフォロー（株価が12か月平均より上なら保有、下なら現金）

さらに、積立投資を何千通りもの将来シナリオで試す「モンテカルロ」も行います。

使い方:
  python3 simulation.py
  python3 simulation.py --years 30 --monthly 50000 --return 0.06 --vol 0.20 --seed 1
"""

import argparse
import math
import random
import statistics
import unicodedata

TAX_RATE = 0.20315  # 日本の上場株式の譲渡益・配当課税（所得税+住民税+復興特別所得税）


def generate_prices(months, annual_return, annual_vol, rng, start=100.0):
    """幾何ブラウン運動で月次の株価（配当込みではない）を生成する。"""
    mu = annual_return / 12
    sigma = annual_vol / math.sqrt(12)
    prices = [start]
    for _ in range(months):
        shock = rng.gauss(0, 1)
        prices.append(prices[-1] * math.exp(mu - 0.5 * sigma**2 + sigma * shock))
    return prices


def apply_tax(final_value, invested, nisa):
    """利益に課税（NISA なら非課税）。"""
    gain = final_value - invested
    if nisa or gain <= 0:
        return final_value
    return final_value - gain * TAX_RATE


def lump_sum(prices, total, div_yield, fee):
    shares = total * (1 - fee) / prices[0]
    for _ in prices[1:]:
        shares += shares * div_yield / 12 * (1 - TAX_RATE)  # 配当（課税後）を再投資
    return shares * prices[-1]


def dollar_cost_average(prices, monthly, div_yield, fee):
    shares = 0.0
    for p in prices[:-1]:
        shares += shares * div_yield / 12 * (1 - TAX_RATE)  # 配当再投資
        shares += monthly * (1 - fee) / p
    return shares * prices[-1]


def trend_follow(prices, total, div_yield, fee, window=12):
    cash, shares = total, 0.0
    for i in range(1, len(prices)):
        p = prices[i - 1]
        shares += shares * div_yield / 12 * (1 - TAX_RATE)
        if i >= window:
            ma = sum(prices[i - window:i]) / window
            if p > ma and cash > 0:          # 上昇トレンド → 買う
                shares += cash * (1 - fee) / p
                cash = 0.0
            elif p < ma and shares > 0:      # 下降トレンド → 売る（途中の売却益課税は簡略化のため省略）
                proceeds = shares * p * (1 - fee)
                cash += proceeds
                shares = 0.0
    return cash + shares * prices[-1]


def max_drawdown(prices):
    peak, mdd = prices[0], 0.0
    for p in prices:
        peak = max(peak, p)
        mdd = min(mdd, p / peak - 1)
    return mdd


def pad(text, width):
    """全角文字を2桁として左寄せする。"""
    w = sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)
    return text + " " * max(0, width - w)


def yen(x):
    return f"{x:>14,.0f} 円"


def main():
    ap = argparse.ArgumentParser(description="日本株 投資シミュレーション")
    ap.add_argument("--years", type=int, default=20)
    ap.add_argument("--monthly", type=float, default=30000, help="毎月の積立額（円）")
    ap.add_argument("--return", dest="ret", type=float, default=0.05, help="期待値上がり率（年率、配当除く）")
    ap.add_argument("--dividend", type=float, default=0.02, help="配当利回り（年率）")
    ap.add_argument("--vol", type=float, default=0.18, help="ボラティリティ（年率）")
    ap.add_argument("--fee", type=float, default=0.001, help="売買コスト（片道）")
    ap.add_argument("--trials", type=int, default=5000, help="モンテカルロの試行回数")
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()

    rng = random.Random(a.seed)
    months = a.years * 12
    total = a.monthly * months

    # ---- 1本のシナリオで戦略比較 ----
    prices = generate_prices(months, a.ret, a.vol, rng)
    print("=" * 60)
    print(f" 架空の日本株指数 {a.years}年  (期待リターン {a.ret:.0%} + 配当 {a.dividend:.0%}, 変動率 {a.vol:.0%})")
    print("=" * 60)
    print(f" 指数: {prices[0]:.0f} → {prices[-1]:.0f}   最大下落率: {max_drawdown(prices):.0%}")
    print(f" 投資総額: {yen(total)}\n")

    results = {
        "一括投資": (lump_sum(prices, total, a.dividend, a.fee), total),
        "積立投資": (dollar_cost_average(prices, a.monthly, a.dividend, a.fee), total),
        "トレンドフォロー": (trend_follow(prices, total, a.dividend, a.fee), total),
    }
    print(f" {pad('戦略', 18)}{pad('  最終資産(課税口座)', 20)}{'  NISA(非課税)'}")
    for name, (val, inv) in results.items():
        print(f" {pad(name, 18)}{yen(apply_tax(val, inv, False))}{yen(apply_tax(val, inv, True))}")
    print("  ※一括投資は初月に総額を投入するため、積立とは単純比較できません。\n")

    # ---- モンテカルロ（積立投資）----
    finals = []
    for _ in range(a.trials):
        p = generate_prices(months, a.ret, a.vol, rng)
        finals.append(apply_tax(dollar_cost_average(p, a.monthly, a.dividend, a.fee), total, True))
    finals.sort()
    q = lambda r: finals[int(r * (len(finals) - 1))]
    loss = sum(1 for f in finals if f < total) / len(finals)

    print("=" * 60)
    print(f" 積立投資（NISA）を {a.trials:,} 通りの未来で試した結果")
    print("=" * 60)
    print(f" 元本            : {yen(total)}")
    print(f" 悪いケース(5%) : {yen(q(0.05))}")
    print(f" 下位25%        : {yen(q(0.25))}")
    print(f" 中央値          : {yen(statistics.median(finals))}")
    print(f" 上位25%        : {yen(q(0.75))}")
    print(f" 良いケース(95%): {yen(q(0.95))}")
    print(f" 元本割れの確率  : {loss:.1%}")

    # 期間別の元本割れ確率（長期ほど下がることの確認）
    print("\n 積立期間ごとの元本割れ確率:")
    for y in (1, 3, 5, 10, 20, 30):
        m = y * 12
        n = 2000
        cnt = 0
        for _ in range(n):
            p = generate_prices(m, a.ret, a.vol, rng)
            if dollar_cost_average(p, a.monthly, a.dividend, a.fee) < a.monthly * m:
                cnt += 1
        bar = "#" * int(cnt / n * 50)
        print(f"  {y:>2}年: {cnt / n:6.1%} {bar}")


if __name__ == "__main__":
    main()

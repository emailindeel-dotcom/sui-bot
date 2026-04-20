import requests
import hmac
import hashlib
import json
import time
import os

# ── API Keys ──
API_KEY    = os.environ.get("API_KEY", "your_api_key_here")
API_SECRET = os.environ.get("API_SECRET", "your_secret_here").encode()

# ── Settings ──
PAIR          = "B-SUI_USDT"
TRADE_QTY     = 10
LEVERAGE      = 5
INTERVAL      = 300        # Check every 5 minutes
STOP_LOSS_PCT = 1.5
TP_PCT        = 4.5
CANDLE_LIMIT  = 100

CANDLE_URL  = f"https://public.coindcx.com/market_data/candles?pair={PAIR}&interval=15m&limit={CANDLE_LIMIT}"
FUTURES_URL = "https://api.coindcx.com/exchange/v1/derivatives/futures/orders/create"

in_position   = False
buy_price     = 0.0
trade_count   = 0
win_count     = 0

# Track previous EMA state for crossover detection
prev_ema20    = None
prev_ema50    = None

def get_signature(json_body):
    return hmac.new(
        API_SECRET,
        json_body.encode(),
        hashlib.sha256
    ).hexdigest()

def calculate_ema(data, period):
    k       = 2 / (period + 1)
    ema_val = sum(data[:period]) / period
    for price in data[period:]:
        ema_val = price * k + ema_val * (1 - k)
    return round(ema_val, 6)

def calculate_rsi(closes, period=14):
    gains  = [max(closes[i]-closes[i-1], 0) for i in range(1, len(closes))]
    losses = [max(closes[i-1]-closes[i], 0) for i in range(1, len(closes))]
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100
    rs  = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)

def get_candles():
    try:
        r = requests.get(CANDLE_URL, timeout=10)
        if r.status_code == 200:
            data    = r.json()
            closes  = [float(c['close'])  for c in data]
            volumes = [float(c['volume']) for c in data]
            return closes, volumes
        else:
            print(f"Candle Error: {r.status_code}")
            return None, None
    except Exception as e:
        print(f"Fetch Error: {e}")
        return None, None

def check_signal():
    global prev_ema20, prev_ema50

    closes, volumes = get_candles()
    if closes is None:
        return "ERROR", 0

    price   = closes[-1]
    ema20   = calculate_ema(closes, 20)
    ema50   = calculate_ema(closes, 50)
    rsi     = calculate_rsi(closes)
    avg_vol = sum(volumes[-20:]) / 20
    vol_ratio = round(volumes[-1] / avg_vol, 2)

    # Gap between EMAs as percentage
    gap_pct = round(((ema20 - ema50) / ema50) * 100, 4)

    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  Price      : {price}")
    print(f"  EMA20      : {ema20}")
    print(f"  EMA50      : {ema50}")
    print(f"  EMA Gap    : {gap_pct}%")
    print(f"  RSI        : {rsi}")
    print(f"  Volume     : {vol_ratio}x avg")

    # Determine current trend
    if ema20 > ema50:
        trend = "BULLISH"
    else:
        trend = "BEARISH"

    print(f"  Trend      : {trend}")

    # ── Crossover Detection ──
    signal = "HOLD"

    if prev_ema20 is not None and prev_ema50 is not None:

        was_below = prev_ema20 <= prev_ema50   # EMA20 was below EMA50
        now_above = ema20 > ema50              # EMA20 now above EMA50
        was_above = prev_ema20 >= prev_ema50   # EMA20 was above EMA50
        now_below = ema20 < ema50              # EMA20 now below EMA50

        # Golden Cross → BUY
        if was_below and now_above:
            if rsi < 75:                       # Not overbought
                signal = "BUY"
                print(f"  🟢 GOLDEN CROSS DETECTED!")

        # Death Cross → SELL
        elif was_above and now_below:
            if rsi > 25:                       # Not oversold
                signal = "SELL"
                print(f"  🔴 DEATH CROSS DETECTED!")

        # Already in trend — ride it
        else:
            if trend == "BULLISH" and gap_pct > 0.05 and rsi < 70:
                signal = "BUY"
            elif trend == "BEARISH" and gap_pct < -0.05 and rsi > 30:
                signal = "SELL"

    else:
        # First run — check current trend
        if trend == "BULLISH" and gap_pct > 0.05 and rsi < 70:
            signal = "BUY"
        elif trend == "BEARISH" and gap_pct < -0.05 and rsi > 30:
            signal = "SELL"

    # Update previous values
    prev_ema20 = ema20
    prev_ema50 = ema50

    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    return signal, price

def check_sl_tp(price):
    global in_position, buy_price, trade_count, win_count
    if not in_position:
        return None

    sl  = buy_price * (1 - STOP_LOSS_PCT / 100)
    tp  = buy_price * (1 + TP_PCT / 100)
    pnl = round((price - buy_price) / buy_price * 100, 2)

    print(f"  Entry      : {round(buy_price, 4)}")
    print(f"  Stop Loss  : {round(sl, 4)}")
    print(f"  Take Profit: {round(tp, 4)}")
    print(f"  Current PnL: {pnl}%")

    if price <= sl:
        print("  🔴 STOP LOSS HIT")
        trade_count += 1
        return "EXIT_LOSS"
    if price >= tp:
        print("  🟢 TAKE PROFIT HIT")
        trade_count += 1
        win_count   += 1
        return "EXIT_WIN"
    return None

def place_order(side, price):
    timestamp = int(round(time.time() * 1000))
    body = {
        "timestamp":      timestamp,
        "side":           side,
        "pair":           PAIR,
        "order_type":     "limit",
        "price":          round(price, 4),
        "total_quantity": TRADE_QTY,
        "leverage":       LEVERAGE
    }
    json_body = json.dumps(body, separators=(',', ':'))
    signature = get_signature(json_body)
    headers = {
        'Content-Type': 'application/json',
        'X-AUTH-APIKEY': API_KEY,
        'X-AUTH-SIGNATURE': signature
    }
    r = requests.post(FUTURES_URL, data=json_body, headers=headers)
    print(f"  Order      : {r.json()}")

def print_stats():
    print(f"  ── Stats ──────────────────────────")
    if trade_count > 0:
        win_rate = round((win_count / trade_count) * 100, 1)
        print(f"  Trades     : {trade_count}")
        print(f"  Wins       : {win_count}")
        print(f"  Win Rate   : {win_rate}%")
    else:
        print(f"  No trades yet — monitoring...")

# ── Main Loop ──
print("═" * 35)
print("  SUI EMA 20/50 CROSSOVER BOT")
print("═" * 35)
print(f"  Pair       : {PAIR}")
print(f"  Candles    : 15min x {CANDLE_LIMIT}")
print(f"  EMA Fast   : 20")
print(f"  EMA Slow   : 50")
print(f"  Stop Loss  : {STOP_LOSS_PCT}%")
print(f"  Take Profit: {TP_PCT}%")
print(f"  R:R Ratio  : 1:3")
print(f"  Leverage   : {LEVERAGE}x")
print("═" * 35)
print("  Orders COMMENTED — Safe Test!")
print("═" * 35)

while True:
    try:
        print(f"\n  Time: {time.ctime()}")

        signal, price = check_signal()
        print(f"\n  >>>  SIGNAL : {signal}  <<<\n")

        exit_signal = check_sl_tp(price)
        print_stats()

        # ── Uncomment ONLY after 5-7 days testing ──
        # if exit_signal in ["EXIT_LOSS", "EXIT_WIN"]:
        #     place_order("sell", price)
        #     in_position = False
        #     buy_price   = 0.0
        #
        # elif signal == "BUY" and not in_position:
        #     place_order("buy", price)
        #     in_position = True
        #     buy_price   = price
        #     print(f"  Bought at {price}")
        #
        # elif signal == "SELL" and in_position:
        #     place_order("sell", price)
        #     in_position = False
        #     buy_price   = 0.0
        #     print(f"  Sold at {price}")

        time.sleep(INTERVAL)

    except Exception as e:
        print(f"  Error: {e}")
        time.sleep(30)

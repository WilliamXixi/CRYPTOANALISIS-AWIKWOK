import requests
import time
import ccxt
import pandas as pd
import numpy as np
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Token dari BotFather
TOKEN = "7567730596:AAFcE_nUpKKPrlU893Sbgu7mqNAMRRhtyU4"

# Ganti dengan chat_id kamu (dapat dari @userinfobot atau logging update.message.chat_id)
CHAT_ID = "7284106078"  # Contoh, ganti dengan chat ID asli

# Inisialisasi ccxt untuk ambil data candlestick (pake Binance)
exchange = ccxt.binance()

# Fungsi buat ambil harga koin dengan format yang lebih detail
def get_price(coin_id):
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd"
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for HTTP errors
        data = response.json()
        return data[coin_id]["usd"]
    except requests.exceptions.RequestException as e:
        print(f"Error fetching price for {coin_id}: {e}")
        return None
    except (KeyError, TypeError) as e:
        print(f"Error parsing price for {coin_id}: {e}")
        return None

# Fungsi buat ambil data candlestick
def get_candlestick(symbol, timeframe, limit=50):  # Ambil lebih banyak data untuk MA dan RSI
    try:
        candles = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        return candles
    except ccxt.NetworkError as e:
        print(f"Binance Network error for {symbol} {timeframe}: {e}")
        return None
    except ccxt.ExchangeError as e:
        print(f"Binance Exchange error for {symbol} {timeframe}: {e}")
        return None

# Fungsi buat hitung MA
def calculate_ma(prices, period):
    df = pd.Series(prices)
    return df.rolling(window=period).mean().iloc[-1]

# Fungsi buat hitung RSI
def calculate_rsi(prices, period=14):
    df = pd.Series(prices)
    delta = df.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]

# Fungsi buat analisis candlestick, MA, RSI, dan simpulkan sinyal
def analyze_candle(candles, timeframe, current_price):
    if not candles or len(candles) < 27:  # Butuh minimal 27 candle untuk MA dan analisis
        return "Neutral ⚖️", None, None, None, None, None, None

    latest_candle = candles[-1]
    previous_candle = candles[-2]
    open_price, high, low, close = latest_candle[1], latest_candle[2], latest_candle[3], latest_candle[4]
    body = abs(close - open_price)
    upper_wick = high - max(open_price, close)
    lower_wick = min(open_price, close) - low

    # Analisis Candlestick
    candle_signal = "Neutral"
    if close > open_price and body > (high - low) * 0.6:
        candle_signal = "Bullish"
    elif close < open_price and body > (high - low) * 0.6:
        candle_signal = "Bearish"
    elif upper_wick > 2 * body:
        candle_signal = "Bearish"
    elif lower_wick > 2 * body:
        candle_signal = "Bullish"

    # Hitung MA 12 dan MA 26
    closes = [candle[4] for candle in candles]
    ma_12 = calculate_ma(closes, 12)
    ma_26 = calculate_ma(closes, 26)
    ma_12_prev = calculate_ma(closes[:-1], 12)
    ma_26_prev = calculate_ma(closes[:-1], 26)

    # Analisis MA
    ma_signal = "Neutral"
    if ma_12 > ma_26 and ma_12_prev <= ma_26_prev:
        ma_signal = "Bullish"
    elif ma_12 < ma_26 and ma_12_prev >= ma_26_prev:
        ma_signal = "Bearish"

    # Hitung RSI
    rsi = calculate_rsi(closes, 14)
    rsi_signal = "Neutral"
    if rsi > 70:
        rsi_signal = "Bearish"  # Overbought
    elif rsi < 30:
        rsi_signal = "Bullish"  # Oversold
    elif 50 < rsi <= 70:
        rsi_signal = "Bullish"  # Tren naik
    elif 30 <= rsi < 50:
        rsi_signal = "Bearish"  # Tren turun

    # Simpulkan sinyal
    signals = [candle_signal, ma_signal, rsi_signal]
    bullish_count = signals.count("Bullish")
    bearish_count = signals.count("Bearish")

    if bullish_count >= 2:
        final_signal = "Bullish 🚀"
    elif bearish_count >= 2:
        final_signal = "Bearish 🐻"
    else:
        final_signal = "Neutral 🧘"

    # Tentukan target harga, entry, TP, dan SL berdasarkan analisis yang lebih sederhana
    entry = close
    trade_action = None
    # Untuk bullish, target sedikit di atas harga saat ini, SL sedikit di bawah
    if "Bullish" in final_signal:
        target = high + abs(high - low) * 0.5  # Contoh target sedikit di atas high
        tp = target
        sl = low - abs(high - low) * 0.5      # Contoh SL sedikit di bawah low
        trade_action = "Long Entry"
    # Untuk bearish, target sedikit di bawah harga saat ini, SL sedikit di atas
    elif "Bearish" in final_signal:
        target = low - abs(high - low) * 0.5   # Contoh target sedikit di bawah low
        tp = target
        sl = high + abs(high - low) * 0.5      # Contoh SL sedikit di atas high
        trade_action = "Short Entry"
    else:
        target = None
        tp = None
        sl = None

    tp_usd = abs(tp - entry) if tp is not None and entry is not None else None
    sl_usd = abs(entry - sl) if sl is not None and entry is not None else None

    return final_signal, entry, target, tp, sl, tp_usd, sl_usd, trade_action

# Fungsi start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text(f"DexBot Pantauan Brutal Aktif! Notifikasi akan dikirim ke chat ID: {chat_id}")
    context.chat_data["chat_id"] = chat_id
    print(f"Bot started. Chat ID: {chat_id}")

# Fungsi buat cek harga, candle, dan kirim notifikasi (DIUBAH)
async def check_alerts(context: ContextTypes.DEFAULT_TYPE):
    chat_id = CHAT_ID
    coins = {
        "bitcoin": "BTC/USDT",
        "ethereum": "ETH/USDT",
        "dogecoin": "DOGE/USDT",
        "pepe": "PEPE/USDT"
    }
    timeframes = ["15m", "4h", "1d"]
    output_message = "📊 **Pantauan Pasar Kripto Brutal:** 📊\n\n"

    for coin_id, symbol in coins.items():
        try:
            live_price = get_price(coin_id)
            if live_price is None:
                output_message += f"⚠️ Gagal mendapatkan harga live untuk {coin_id.upper()}\n"
                continue

            coin_name = coin_id.upper() if coin_id != "pepe" else "PEPE"
            coin_output = f"**{coin_name}:** Harga Saat Ini: ${live_price:.8f}" if coin_id in ["dogecoin", "pepe"] else f"**{coin_name}:** Harga Saat Ini: ${live_price:.2f}\n"

            for tf in timeframes:
                candles = get_candlestick(symbol, tf)
                if candles is None or len(candles) < 27:
                    coin_output += f"  ⏳ TF {tf}: Data candlestick belum mencukupi.\n"
                    continue

                signal, entry, target, tp, sl, tp_usd, sl_usd, trade_action = analyze_candle(candles, tf, live_price)

                price_format = f"{live_price:.8f}" if coin_id in ["dogecoin", "pepe"] else f"{live_price:.2f}"
                entry_format = f"{entry:.8f}" if coin_id in ["dogecoin", "pepe"] else f"{entry:.2f}"
                target_format = f"{target:.8f}" if coin_id in ["dogecoin", "pepe"] and target is not None else f"{target:.2f}" if target is not None else "N/A"
                tp_format = f"{tp:.8f}" if coin_id in ["dogecoin", "pepe"] and tp is not None else f"{tp:.2f}" if tp is not None else "N/A"
                sl_format = f"{sl:.8f}" if coin_id in ["dogecoin", "pepe"] and sl is not None else f"{sl:.2f}" if sl is not None else "N/A"

                profit_loss_str = ""
                if tp_usd is not None and sl_usd is not None and entry is not None:
                    profit_loss_percentage = (tp_usd / entry) * 100 if entry != 0 else 0
                    loss_loss_percentage = (sl_usd / entry) * 100 if entry != 0 else 0
                    profit_loss_str = f"(TP: +{profit_loss_percentage:.2f}% | SL: -{loss_loss_percentage:.2f}%)"

                coin_output += f"  ⏱️ TF {tf}: {signal}\n"
                if trade_action == "Long Entry":
                    coin_output += f"    🚀 **Sinyal:** Long Entry di Harga: {price_format}\n"
                    coin_output += f"       🎯 Target: {target_format} | 🛑 Stop Loss: {sl_format} {profit_loss_str}\n"
                elif trade_action == "Short Entry":
                    coin_output += f"    🐻 **Sinyal:** Short Entry di Harga: {price_format}\n"
                    coin_output += f"       🎯 Target: {target_format} | 🛑 Stop Loss: {sl_format} {profit_loss_str}\n"
                elif entry is not None:
                    coin_output += f"    ➡️ Entry: {entry_format} | Target: {target_format} | SL: {sl_format} {profit_loss_str}\n"

            output_message += coin_output + "\n"

        except Exception as e:
            output_message += f"🚨 Terjadi kesalahan saat memproses {coin_id.upper()}: {e}\n\n"

    if output_message != "📊 **Pantauan Pasar Kripto Brutal:** 📊\n\n":
        await context.bot.send_message(chat_id=chat_id, text=output_message)
        print("Pesan pantauan pasar terkirim!")
    else:
        print("Tidak ada informasi pantauan untuk dikirim.")

# Main function
def main():
    app = Application.builder().token(TOKEN).build()

    # Tambah command /start
    app.add_handler(CommandHandler("start", start))

    # Jadwal cek tiap 15 menit
    app.job_queue.run_repeating(check_alerts, interval=900, first=10)

    # Start bot
    app.run_polling()

if __name__ == "__main__":
    main()
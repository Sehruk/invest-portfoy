import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import yfinance as yf
import requests
import json
import hashlib
import time
from datetime import datetime

# ==========================================
# SAYFA VE TEMA KONFİGÜRASYONU
# ==========================================
st.set_page_config(
    page_title="Finvest - Portföy & Varlık Yönetimi",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Özel CSS ile Modern Koyu Arayüz
st.markdown("""
<style>
    .stApp {
        background-color: #030712;
        color: #f3f4f6;
    }
    .metric-card {
        background: linear-gradient(135deg, #111827 0%, #1f2937 100%);
        border: 1px solid #374151;
        border-radius: 12px;
        padding: 16px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
    }
    .rebalance-card-buy {
        border-left: 4px solid #10b981;
        background: #064e3b22;
        padding: 12px;
        border-radius: 8px;
        margin-bottom: 8px;
    }
    .rebalance-card-sell {
        border-left: 4px solid #ef4444;
        background: #7f1d1d22;
        padding: 12px;
        border-radius: 8px;
        margin-bottom: 8px;
    }
    .stButton>button {
        border-radius: 8px;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# YARDIMCI VE GÜVENLİK FONKSİYONLARI
# ==========================================
def hash_password(password: str) -> str:
    return hashlib.sha256(password.strip().encode()).hexdigest()

def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed

# Canlı Döviz Kuru Çekme (TCMB / Serbest Piyasa fallback)
@st.cache_data(ttl=300)
def get_exchange_rates():
    try:
        usd_try = 34.20
        eur_try = 37.10
        try:
            tickers = yf.Tickers('TRY=X EURTRY=X')
            usd_data = tickers.tickers['TRY=X'].fast_info.last_price
            eur_data = tickers.tickers['EURTRY=X'].fast_info.last_price
            if usd_data and usd_data > 0:
                usd_try = float(usd_data)
            if eur_data and eur_data > 0:
                eur_try = float(eur_data)
        except Exception:
            pass
        
        eur_usd = eur_try / usd_try if usd_try > 0 else 1.08
        return {"USD_TRY": usd_try, "EUR_TRY": eur_try, "EUR_USD": eur_usd}
    except Exception:
        return {"USD_TRY": 34.20, "EUR_TRY": 37.10, "EUR_USD": 1.08}

def convert_currency(amount: float, from_curr: str, to_curr: str, rates: dict) -> float:
    if from_curr == to_curr or amount == 0:
        return amount
    
    # Önce TRY'ye çevir
    val_in_try = amount
    if from_curr == 'USD':
        val_in_try = amount * rates['USD_TRY']
    elif from_curr == 'EUR':
        val_in_try = amount * rates['EUR_TRY']
    
    # TRY'den hedef para birimine çevir
    if to_curr == 'TRY':
        return val_in_try
    elif to_curr == 'USD':
        return val_in_try / rates['USD_TRY']
    elif to_curr == 'EUR':
        return val_in_try / rates['EUR_TRY']
    return val_in_try

def format_money(val: float, curr: str) -> str:
    symbols = {"TRY": "₺", "USD": "$", "EUR": "€"}
    sym = symbols.get(curr, "₺")
    return f"{sym}{val:,.2f}"

# Canlı Fiyat Çekme Motoru (Yahoo Finance)
@st.cache_data(ttl=120)
def fetch_live_prices(symbols_tuple):
    prices = {}
    if not symbols_tuple:
        return prices
    
    for sym in symbols_tuple:
        try:
            lookup_sym = sym
            if sym.startswith("BIST:") or (not "." in sym and len(sym) <= 5 and not sym in ["USD", "EUR", "GLD"]):
                if not sym.endswith(".IS") and not sym in ["BTC-USD", "ETH-USD", "GC=F"]:
                    lookup_sym = f"{sym.replace('BIST:', '')}.IS"
            
            ticker = yf.Ticker(lookup_sym)
            info = ticker.fast_info
            price = info.last_price
            if price and price > 0:
                prices[sym] = float(price)
        except Exception:
            continue
    return prices

# ==========================================
# SESSION STATE VE VERİTABANI İLKLENDİRME
# ==========================================
DEFAULT_CATEGORIES = [
    {"id": "BIST", "name": "Borsa İstanbul", "targetPercent": 25.0, "color": "#3b82f6"},
    {"id": "US_EQUITY", "name": "ABD & Yabancı Hisse", "targetPercent": 30.0, "color": "#10b981"},
    {"id": "GOLD", "name": "Altın & Kıymetli Maden", "targetPercent": 15.0, "color": "#f59e0b"},
    {"id": "CRYPTO", "name": "Kripto Varlıklar", "targetPercent": 10.0, "color": "#8b5cf6"},
    {"id": "EUROBOND", "name": "Eurobond & Tahvil", "targetPercent": 10.0, "color": "#06b6d4"},
    {"id": "CASH", "name": "Nakit & Para Piyasası", "targetPercent": 10.0, "color": "#64748b"},
]

if "users" not in st.session_state:
    st.session_state.users = {
        "admin@invest.local": {
            "name": "Şehruk (Yönetici)",
            "password": hash_password("123456"),
            "role": "ADMIN"
        }
    }

if "current_user" not in st.session_state:
    st.session_state.current_user = None

if "db" not in st.session_state:
    st.session_state.db = {}

# Aktif kullanıcı veritabanı alanı oluştur
def get_user_db():
    email = st.session_state.current_user["email"]
    if email not in st.session_state.db:
        st.session_state.db[email] = {
            "categories": [c.copy() for c in DEFAULT_CATEGORIES],
            "transactions": [],
            "wallet": [],
            "dividends": [],
            "realized_gains": [],
            "manual_valuations": {},
            "base_currency": "TRY"
        }
    return st.session_state.db[email]

# ==========================================
# GİRİŞ & KAYIT EKRANI (AUTH)
# ==========================================
if not st.session_state.current_user:
    st.title("💼 Finvest Portföy & Varlık Yönetimi")
    st.caption("Güvenli, Çoklu Para Birimli ve Dinamik Yeniden Dengelemeli Varlık Takip Sistemi")
    
    tab_login, tab_register = st.tabs(["🔒 Giriş Yap", "📝 Yeni Hesap Oluştur"])
    
    with tab_login:
        st.subheader("Hesabınıza Giriş Yapın")
        login_email = st.text_input("E-Posta Adresi", key="log_email")
        login_password = st.text_input("Şifre", type="password", key="log_pwd")
        
        if st.button("Giriş Yap", use_container_width=True, type="primary"):
            clean_email = login_email.strip().lower()
            if clean_email in st.session_state.users:
                user_data = st.session_state.users[clean_email]
                if verify_password(login_password, user_data["password"]):
                    st.session_state.current_user = {
                        "email": clean_email,
                        "name": user_data["name"],
                        "role": user_data["role"]
                    }
                    st.success(f"Hoş geldiniz, {user_data['name']}!")
                    st.rerun()
                else:
                    st.error("Girdiğiniz şifre hatalı.")
            else:
                st.error("Bu e-posta adresine ait kayıtlı kullanıcı bulunamadı.")
        
        st.info("💡 **Demo Giriş Bilgileri:** E-Posta: `admin@invest.local` | Şifre: `123456`")

    with tab_register:
        st.subheader("Yeni Portföy Hesabı Aç")
        reg_name = st.text_input("Ad Soyad", key="reg_name")
        reg_email = st.text_input("E-Posta Adresi", key="reg_email")
        reg_pwd = st.text_input("Şifre Belirleyin (En az 6 karakter)", type="password", key="reg_pwd")
        reg_pwd_confirm = st.text_input("Şifre Onayı", type="password", key="reg_pwd_c")
        
        if st.button("Kayıt Ol & Başla", use_container_width=True):
            clean_email = reg_email.strip().lower()
            if not reg_name or not clean_email or not reg_pwd:
                st.error("Lütfen tüm alanları eksiksiz doldurunuz.")
            elif len(reg_pwd) < 6:
                st.error("Şifre en az 6 karakter uzunluğunda olmalıdır.")
            elif reg_pwd != reg_pwd_confirm:
                st.error("Şifreler birbiriyle uyuşmuyor.")
            elif clean_email in st.session_state.users:
                st.error("Bu e-posta adresi zaten kayıtlı.")
            else:
                st.session_state.users[clean_email] = {
                    "name": reg_name.strip(),
                    "password": hash_password(reg_pwd),
                    "role": "USER"
                }
                st.session_state.current_user = {
                    "email": clean_email,
                    "name": reg_name.strip(),
                    "role": "USER"
                }
                st.success("Hesabınız başarıyla oluşturuldu! Temiz portföyünüz yükleniyor...")
                st.rerun()
    st.stop()

# ==========================================
# ANA UYGULAMA (GİRİŞ YAPILDIKTAN SONRA)
# ==========================================
user_db = get_user_db()
rates = get_exchange_rates()

# ------------------------------------------
# YAN MENÜ (SIDEBAR) & AYARLAR
# ------------------------------------------
with st.sidebar:
    st.markdown(f"### 👤 {st.session_state.current_user['name']}")
    st.caption(f"Rol: **{st.session_state.current_user['role']}** | {st.session_state.current_user['email']}")
    
    # Para Birimi Seçimi
    base_curr = st.selectbox(
        "💱 Ana Para Birimi",
        ["TRY", "USD", "EUR"],
        index=["TRY", "USD", "EUR"].index(user_db.get("base_currency", "TRY"))
    )
    user_db["base_currency"] = base_curr
    
    st.markdown("---")
    st.markdown("#### 📊 Canlı Kurlar")
    st.write(f"💵 **USD/TRY:** {rates['USD_TRY']:.2f} ₺")
    st.write(f"💶 **EUR/TRY:** {rates['EUR_TRY']:.2f} ₺")
    
    st.markdown("---")
    # Menü Navigasyonu
    menu_choice = st.radio(
        "Menü",
        ["📈 Portföy Özeti & Tablo", "➕ Yeni İşlem Ekle", "⚖️ Yeniden Dengeleme (Rebalance)", "💵 Nakit Cüzdanı", "🎯 Kategori & Hedef Ayarları", "📜 İşlem Geçmişi"],
        index=0
    )
    
    st.markdown("---")
    if st.button("🚪 Güvenli Çıkış Yap", use_container_width=True):
        st.session_state.current_user = None
        st.rerun()

# ==========================================
# HESAPLAMA MOTORU (PORTFOLIO CALCULATOR)
# ==========================================
transactions = user_db["transactions"]
categories = user_db["categories"]
manual_vals = user_db["manual_valuations"]

# Canlı Fiyatları Çek
live_symbols = tuple(set(t["symbol"] for t in transactions if t.get("pricingMode") != "MANUAL"))
live_quotes = fetch_live_prices(live_symbols)

# Varlıkları Gruplama
holdings_dict = {}
for tx in sorted(transactions, key=lambda x: x["date"]):
    sym = tx["symbol"].upper()
    if sym not in holdings_dict:
        holdings_dict[sym] = {
            "symbol": sym,
            "name": tx.get("name", sym),
            "category": tx["category"],
            "currency": tx["currency"],
            "pricingMode": tx.get("pricingMode", "LIVE"),
            "quantity": 0.0,
            "totalCostNative": 0.0
        }
    
    if tx["type"] == "BUY":
        holdings_dict[sym]["quantity"] += tx["quantity"]
        holdings_dict[sym]["totalCostNative"] += tx["quantity"] * tx["price"]
    elif tx["type"] == "SELL":
        if holdings_dict[sym]["quantity"] > 0:
            avg_cost = holdings_dict[sym]["totalCostNative"] / holdings_dict[sym]["quantity"]
            deduct_qty = min(tx["quantity"], holdings_dict[sym]["quantity"])
            holdings_dict[sym]["quantity"] -= deduct_qty
            holdings_dict[sym]["totalCostNative"] -= avg_cost * deduct_qty

# Pozisyon Listesi Oluşturma
holdings_list = []
total_portfolio_value_base = 0.0
total_portfolio_cost_base = 0.0

for sym, h in holdings_dict.items():
    if h["quantity"] <= 0.00001:
        continue
    
    avg_price = h["totalCostNative"] / h["quantity"] if h["quantity"] > 0 else 0.0
    
    # Fiyat Belirleme
    if h["pricingMode"] == "MANUAL":
        curr_price = manual_vals.get(sym, avg_price)
    else:
        curr_price = live_quotes.get(sym, avg_price)
    
    val_native = h["quantity"] * curr_price
    cost_native = h["totalCostNative"]
    
    val_base = convert_currency(val_native, h["currency"], base_curr, rates)
    cost_base = convert_currency(cost_native, h["currency"], base_curr, rates)
    pnl_base = val_base - cost_base
    pnl_pct = ((curr_price - avg_price) / avg_price * 100) if avg_price > 0 else 0.0
    
    total_portfolio_value_base += val_base
    total_portfolio_cost_base += cost_base
    
    cat_name = next((c["name"] for c in categories if c["id"] == h["category"]), h["category"])
    
    holdings_list.append({
        "Sembol": sym,
        "Varlık Adı": h["name"],
        "Kategori": cat_name,
        "Kategori_ID": h["category"],
        "Adet": h["quantity"],
        "Ortalama Maliyet": avg_price,
        "Güncel Fiyat": curr_price,
        "Para Birimi": h["currency"],
        "Toplam Değer": val_base,
        "Toplam Maliyet": cost_base,
        "Kâr/Zarar": pnl_base,
        "Getiri %": pnl_pct
    })

df_holdings = pd.DataFrame(holdings_list)
if not df_holdings.empty:
    df_holdings["Ağırlık %"] = (df_holdings["Toplam Değer"] / total_portfolio_value_base) * 100
else:
    df_holdings = pd.DataFrame(columns=["Sembol", "Varlık Adı", "Kategori", "Adet", "Ortalama Maliyet", "Güncel Fiyat", "Para Birimi", "Toplam Değer", "Kâr/Zarar", "Getiri %", "Ağırlık %"])

# ==========================================
# SAYFA: PORTFÖY ÖZETİ & VARLIK TABLOSU
# ==========================================
if menu_choice == "📈 Portföy Özeti & Tablo":
    st.header("💼 Portföy Performans Göstergesi")
    
    # 1. Metrik Kartları
    total_pnl = total_portfolio_value_base - total_portfolio_cost_base
    total_pnl_pct = (total_pnl / total_portfolio_cost_base * 100) if total_portfolio_cost_base > 0 else 0.0
    
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("Toplam Portföy Değeri", format_money(total_portfolio_value_base, base_curr))
        st.markdown('</div>', unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("Toplam Yatırılan Tutar", format_money(total_portfolio_cost_base, base_curr))
        st.markdown('</div>', unsafe_allow_html=True)
    with c3:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("Toplam Kâr / Zarar", format_money(total_pnl, base_curr), delta=f"{total_pnl_pct:+.2f}%")
        st.markdown('</div>', unsafe_allow_html=True)
    with c4:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("Açık Pozisyon Sayısı", f"{len(df_holdings)} Varlık")
        st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown("---")
    
    # 2. Pasta Grafiği & Kategori Dağılımı
    col_chart1, col_chart2 = st.columns(2)
    with col_chart1:
        st.subheader("🎯 Mevcut Dağılım (Kategori Bazında)")
        if not df_holdings.empty:
            cat_summary = df_holdings.groupby("Kategori")["Toplam Değer"].sum().reset_index()
            fig_pie = px.pie(
                cat_summary,
                values="Toplam Değer",
                names="Kategori",
                hole=0.45,
                color_discrete_sequence=px.colors.qualitative.Plotly
            )
            fig_pie.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#f3f4f6")
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("Henüz portföyünüzde işlem bulunmuyor.")

    with col_chart2:
        st.subheader("📊 Hedef vs Mevcut Dağılım (%)")
        if not df_holdings.empty and total_portfolio_value_base > 0:
            comp_data = []
            for c in categories:
                c_val = df_holdings[df_holdings["Kategori_ID"] == c["id"]]["Toplam Değer"].sum() if "Kategori_ID" in df_holdings else 0
                c_pct = (c_val / total_portfolio_value_base) * 100
                comp_data.append({
                    "Kategori": c["name"],
                    "Mevcut %": c_pct,
                    "Hedef %": c["targetPercent"]
                })
            df_comp = pd.DataFrame(comp_data)
            fig_bar = go.Figure(data=[
                go.Bar(name='Mevcut %', x=df_comp['Kategori'], y=df_comp['Mevcut %'], marker_color='#3b82f6'),
                go.Bar(name='Hedef %', x=df_comp['Kategori'], y=df_comp['Hedef %'], marker_color='#10b981')
            ])
            fig_bar.update_layout(barmode='group', paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#f3f4f6")
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.info("Karşılaştırma için varlık ekleyiniz.")

    # 3. Varlık Tablosu
    st.subheader("📋 Açık Pozisyonlar ve Varlık Tablosu")
    if not df_holdings.empty:
        display_df = df_holdings.copy()
        display_df["Ortalama Maliyet"] = display_df.apply(lambda r: format_money(r["Ortalama Maliyet"], r["Para Birimi"]), axis=1)
        display_df["Güncel Fiyat"] = display_df.apply(lambda r: format_money(r["Güncel Fiyat"], r["Para Birimi"]), axis=1)
        display_df["Toplam Değer"] = display_df["Toplam Değer"].apply(lambda v: format_money(v, base_curr))
        display_df["Toplam Maliyet"] = display_df["Toplam Maliyet"].apply(lambda v: format_money(v, base_curr))
        display_df["Kâr/Zarar"] = display_df["Kâr/Zarar"].apply(lambda v: format_money(v, base_curr))
        display_df["Getiri %"] = display_df["Getiri %"].apply(lambda v: f"{v:+.2f}%")
        display_df["Ağırlık %"] = display_df["Ağırlık %"].apply(lambda v: f"%{v:.2f}")
        
        st.dataframe(display_df[["Sembol", "Varlık Adı", "Kategori", "Adet", "Ortalama Maliyet", "Güncel Fiyat", "Toplam Değer", "Kâr/Zarar", "Getiri %", "Ağırlık %"]], use_container_width=True)
        
        # CSV Dışa Aktarma
        csv_data = df_holdings.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            "📥 Portföy Raporunu CSV Olarak İndir (Excel Uyumlu)",
            data=csv_data,
            file_name=f"Finvest_Portfoy_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
    else:
        st.warning("Henüz açık pozisyonunuz yok. Sol menüden 'Yeni İşlem Ekle' adımını kullanarak ilk varlığınızı ekleyin.")

# ==========================================
# SAYFA: YENİ İŞLEM EKLE (ALIM / SATIM)
# ==========================================
elif menu_choice == "➕ Yeni İşlem Ekle":
    st.header("➕ Yeni Portföy İşlemi Girişi")
    
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        tx_type = st.radio("İşlem Türü", ["BUY (Alım)", "SELL (Satım)"], horizontal=True)
        tx_type = "BUY" if "BUY" in tx_type else "SELL"
        
        cat_options = {c["id"]: c["name"] for c in categories}
        tx_cat = st.selectbox("Varlık Kategorisi", options=list(cat_options.keys()), format_func=lambda x: cat_options[x])
        
        tx_symbol = st.text_input("Varlık Sembolü / Kodu", placeholder="Örn: THYAO, AAPL, BTC-USD, ALTIN").upper().strip()
        tx_name = st.text_input("Varlık Açıklaması / Adı", placeholder="Örn: Türk Hava Yolları, Apple Inc.")
        
    with col_t2:
        tx_currency = st.selectbox("İşlem Para Birimi", ["TRY", "USD", "EUR"])
        tx_qty = st.number_input("Adet / Miktar", min_value=0.0001, value=1.0, step=1.0)
        tx_price = st.number_input(f"Birim Fiyat ({tx_currency})", min_value=0.0001, value=100.0, step=1.0)
        tx_date = st.date_input("İşlem Tarihi", value=datetime.now())
        
        tx_mode = st.radio("Fiyat Güncelleme Modu", ["Canlı Piyasa (Yahoo Finance)", "Manuel Değerleme"])
        pricing_mode = "MANUAL" if "Manuel" in tx_mode else "LIVE"

    total_cost_calc = tx_qty * tx_price
    st.info(f"💵 Toplam İşlem Tutarı: **{format_money(total_cost_calc, tx_currency)}**")
    
    deduct_wallet = False
    if tx_type == "BUY":
        deduct_wallet = st.checkbox("Bu tutarı Nakit Cüzdanımdan (Dry Powder) düş", value=False)
        
    if st.button("İşlemi Kaydet & Portföye Ekle", type="primary", use_container_width=True):
        if not tx_symbol:
            st.error("Lütfen varlık sembolünü giriniz.")
        else:
            new_tx = {
                "id": f"tx_{int(time.time()*1000)}",
                "symbol": tx_symbol,
                "name": tx_name or tx_symbol,
                "category": tx_cat,
                "type": tx_type,
                "quantity": float(tx_qty),
                "price": float(tx_price),
                "currency": tx_currency,
                "date": tx_date.strftime("%Y-%m-%d"),
                "pricingMode": pricing_mode
            }
            user_db["transactions"].append(new_tx)
            
            # Cüzdan Hareketi
            if tx_type == "BUY" and deduct_wallet:
                user_db["wallet"].append({
                    "id": f"wtx_{int(time.time()*1000)}",
                    "type": "BUY_DEDUCT",
                    "amount": total_cost_calc,
                    "currency": tx_currency,
                    "date": tx_date.strftime("%Y-%m-%d"),
                    "description": f"{tx_symbol} Alımı"
                })
            elif tx_type == "SELL":
                # Satış hasılatını otomatik cüzdana aktar
                user_db["wallet"].append({
                    "id": f"wtx_{int(time.time()*1000)}",
                    "type": "SELL_CREDIT",
                    "amount": total_cost_calc,
                    "currency": tx_currency,
                    "date": tx_date.strftime("%Y-%m-%d"),
                    "description": f"{tx_symbol} Satış Geliri"
                })
                
            st.success(f"✅ {tx_symbol} işlemi başarıyla kaydedildi!")
            st.cache_data.clear()
            time.sleep(1)
            st.rerun()

# ==========================================
# SAYFA: DİNAMİK YENİDEN DENGELEME (REBALANCE)
# ==========================================
elif menu_choice == "⚖️ Yeniden Dengeleme (Rebalance)":
    st.header("⚖️ Dinamik Portföy Yeniden Dengeleme Motoru")
    st.caption("Hedeflediğiniz varlık dağılımına ulaşmak için matematiksel alım ve satım önerileri")
    
    if total_portfolio_value_base <= 0:
        st.warning("Yeniden dengeleme analizi için önce portföyünüze varlık eklemelisiniz.")
    else:
        st.markdown(f"#### Toplam Portföy Büyüklüğü: **{format_money(total_portfolio_value_base, base_curr)}**")
        
        rebalance_data = []
        for c in categories:
            c_val = df_holdings[df_holdings["Kategori_ID"] == c["id"]]["Toplam Değer"].sum() if not df_holdings.empty else 0
            curr_pct = (c_val / total_portfolio_value_base) * 100
            target_pct = c["targetPercent"]
            target_val = (target_pct / 100.0) * total_portfolio_value_base
            diff_val = target_val - c_val  # Pozitif ise ALIM lazım, Negatif ise SATIM lazım
            diff_pct = target_pct - curr_pct
            
            rebalance_data.append({
                "Kategori": c["name"],
                "Mevcut Tutar": c_val,
                "Mevcut %": curr_pct,
                "Hedef %": target_pct,
                "Hedef Tutar": target_val,
                "Fark Tutar": diff_val,
                "Fark %": diff_pct,
                "Eylem": "AL" if diff_val > 50 else ("SAT" if diff_val < -50 else "DENGEDE")
            })
            
        df_reb = pd.DataFrame(rebalance_data)
        
        # Öneri Kartları
        for _, r in df_reb.iterrows():
            if r["Eylem"] == "AL":
                st.markdown(f"""
                <div class="rebalance-card-buy">
                    <h4 style="color:#10b981; margin:0;">🟢 {r['Kategori']} - HEDEFİN ALTINDA (ALIM GEREKİYOR)</h4>
                    <p style="margin:4px 0 0 0;">Mevcut Dağılım: <b>%{r['Mevcut %']:.1f}</b> → Hedef: <b>%{r['Hedef %']:.1f}</b><br>
                    Hedefe Ulaşmak İçin Eklenecek Tutar: <b>+{format_money(abs(r['Fark Tutar']), base_curr)}</b></p>
                </div>
                """, unsafe_allow_html=True)
            elif r["Eylem"] == "SAT":
                st.markdown(f"""
                <div class="rebalance-card-sell">
                    <h4 style="color:#ef4444; margin:0;">🔴 {r['Kategori']} - HEDEFİN ÜSTÜNDE (KÂR REALİZASYONU / SATIM)</h4>
                    <p style="margin:4px 0 0 0;">Mevcut Dağılım: <b>%{r['Mevcut %']:.1f}</b> → Hedef: <b>%{r['Hedef %']:.1f}</b><br>
                    Dengeye Ulaşmak İçin Azaltılacak Tutar: <b>-{format_money(abs(r['Fark Tutar']), base_curr)}</b></p>
                </div>
                """, unsafe_allow_html=True)

# ==========================================
# SAYFA: NAKİT CÜZDANI (DRY POWDER)
# ==========================================
elif menu_choice == "💵 Nakit Cüzdanı":
    st.header("💵 Nakit Cüzdanı & Likit Rezerv (Dry Powder)")
    st.caption("Fırsat alımları için kenarda bekleyen nakit varlıklarınızı yönetin")
    
    wallet_txs = user_db["wallet"]
    
    # Bakiyeleri Hesapla
    balances = {"TRY": 0.0, "USD": 0.0, "EUR": 0.0}
    for w in wallet_txs:
        curr = w.get("currency", "TRY")
        w_type = w.get("type", "DEPOSIT")
        if w_type in ["DEPOSIT", "SELL_CREDIT", "DIVIDEND"]:
            balances[curr] += w["amount"]
        elif w_type in ["WITHDRAW", "BUY_DEDUCT"]:
            balances[curr] -= w["amount"]
            
    wc1, wc2, wc3 = st.columns(3)
    with wc1:
        st.metric("₺ Türk Lirası Bakiyesi", format_money(balances["TRY"], "TRY"))
    with wc2:
        st.metric("$ Amerikan Doları Bakiyesi", format_money(balances["USD"], "USD"))
    with wc3:
        st.metric("€ Euro Bakiyesi", format_money(balances["EUR"], "EUR"))
        
    st.markdown("---")
    st.subheader("Nakit Yatır / Çek")
    col_w1, col_w2, col_w3 = st.columns(3)
    with col_w1:
        w_action = st.selectbox("İşlem", ["Para Yatır (Deposit)", "Para Çek (Withdraw)"])
    with col_w2:
        w_curr = st.selectbox("Para Birimi", ["TRY", "USD", "EUR"], key="w_curr")
    with col_w3:
        w_amount = st.number_input("Tutar", min_value=1.0, value=1000.0, step=100.0)
        
    if st.button("Cüzdan İşlemini Kaydet", type="primary"):
        act_type = "DEPOSIT" if "Yatır" in w_action else "WITHDRAW"
        user_db["wallet"].append({
            "id": f"wtx_{int(time.time()*1000)}",
            "type": act_type,
            "amount": float(w_amount),
            "currency": w_curr,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "description": "Manuel Cüzdan Hareketi"
        })
        st.success("Cüzdan işlemi başarıyla kaydedildi!")
        st.rerun()

# ==========================================
# SAYFA: KATEGORİ & HEDEF AYARLARI (%100 KONTROLÜ)
# ==========================================
elif menu_choice == "🎯 Kategori & Hedef Ayarları":
    st.header("🎯 Portföy Kategori ve Hedef Oran Ayarları")
    st.caption("Hedef oranların toplamı **kesinlikle tam olarak %100** olmalıdır.")
    
    temp_categories = []
    total_target = 0.0
    
    for i, cat in enumerate(categories):
        col_c1, col_c2 = st.columns([3, 2])
        with col_c1:
            c_name = st.text_input(f"Kategori Adı #{i+1}", value=cat["name"], key=f"cname_{cat['id']}")
        with col_c2:
            c_target = st.number_input(f"Hedef Yüzde %", min_value=0.0, max_value=100.0, value=float(cat["targetPercent"]), step=1.0, key=f"ctarget_{cat['id']}")
            total_target += c_target
            
        temp_categories.append({
            "id": cat["id"],
            "name": c_name,
            "targetPercent": c_target,
            "color": cat.get("color", "#3b82f6")
        })
        
    st.markdown("---")
    
    # %100 Kesin Doğrulama
    is_valid = round(total_target) == 100
    if is_valid:
        st.success(f"✅ Hedef Yüzdelerin Toplamı: **%{total_target:.1f}** (Geçerli)")
        if st.button("💾 Ayarları Kaydet & Uygula", type="primary", use_container_width=True):
            user_db["categories"] = temp_categories
            st.success("Kategori hedefleriniz başarıyla güncellendi!")
            st.rerun()
    else:
        st.error(f"❌ Hedef Yüzdelerin Toplamı: **%{total_target:.1f}**. Kaydetmek için toplam tam olarak %100 olmalıdır!")
        st.button("💾 Ayarları Kaydet & Uygula", disabled=True, use_container_width=True)

# ==========================================
# SAYFA: İŞLEM GEÇMİŞİ (TRANSACTION LOGS)
# ==========================================
elif menu_choice == "📜 İşlem Geçmişi":
    st.header("📜 Tüm İşlem Geçmişi")
    
    if not transactions:
        st.info("Kayıtlı herhangi bir işlem geçmişiniz bulunmamaktadır.")
    else:
        df_tx = pd.DataFrame(transactions)
        st.dataframe(df_tx[["date", "type", "symbol", "name", "category", "quantity", "price", "currency"]], use_container_width=True)
        
        if st.button("🗑️ Tüm İşlem Geçmişini Temizle (Sıfırla)"):
            user_db["transactions"] = []
            user_db["wallet"] = []
            st.success("Tüm işlem geçmişi sıfırlandı.")
            st.rerun()

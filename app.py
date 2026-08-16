import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import yfinance as yf
import hashlib
import time
from datetime import datetime

# ==============================================================================
# 1. SAYFA & MODERN KOYU LÜKS TEMA (ÖZEL CSS İLE ÜST MENÜ & KART TASARIMI)
# ==============================================================================
st.set_page_config(
    page_title="Zettaishi Finvest - Premium Portföy & Varlık Yönetimi",
    page_icon="💎",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Sol menüyü tamamen gizleyip modern üst navigasyon ve dashboard tasarımı enjekte eden CSS
st.markdown("""
<style>
    /* Streamlit varsayılan sidebar ve boşlukları gizleme */
    [data-testid="collapsedControl"] { display: none !important; }
    section[data-testid="stSidebar"] { display: none !important; }
    .block-container {
        padding-top: 1.5rem !important;
        padding-bottom: 3rem !important;
        max-width: 1300px !important;
    }
    .stApp {
        background-color: #0b0f19;
        color: #f8fafc;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }

    /* Üst Header Kartı */
    .top-navbar {
        background: linear-gradient(180deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.8) 100%);
        border: 1px solid rgba(51, 65, 85, 0.6);
        border-radius: 16px;
        padding: 18px 24px;
        margin-bottom: 24px;
        backdrop-filter: blur(12px);
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
    }

    /* Metrik Kartları */
    .glass-card {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.5) 0%, rgba(15, 23, 42, 0.7) 100%);
        border: 1px solid rgba(51, 65, 85, 0.5);
        border-radius: 16px;
        padding: 20px;
        backdrop-filter: blur(10px);
        box-shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.4);
        transition: transform 0.2s ease, border-color 0.2s ease;
    }
    .glass-card:hover {
        border-color: rgba(59, 130, 246, 0.5);
        transform: translateY(-2px);
    }

    /* Yeniden Dengeleme Rozetleri */
    .reb-badge-buy {
        background: rgba(16, 185, 129, 0.12);
        border: 1px solid rgba(16, 185, 129, 0.4);
        border-left: 4px solid #10b981;
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 12px;
    }
    .reb-badge-sell {
        background: rgba(239, 68, 68, 0.12);
        border: 1px solid rgba(239, 68, 68, 0.4);
        border-left: 4px solid #ef4444;
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 12px;
    }

    /* Form Girişleri & Butonlar */
    .stTextInput>div>div>input, .stNumberInput>div>div>input, .stSelectbox>div>div {
        background-color: #1e293b !important;
        color: #f8fafc !important;
        border: 1px solid #334155 !important;
        border-radius: 10px !important;
    }
    .stButton>button {
        border-radius: 10px !important;
        padding: 8px 18px !important;
        font-weight: 600 !important;
        transition: all 0.2s ease !important;
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. ŞİFRE GÜVENLİĞİ & YARDIMCI HESAPLAMA MOTORU
# ==============================================================================
def hash_password(password: str) -> str:
    return hashlib.sha256(password.strip().encode()).hexdigest()

def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed

@st.cache_data(ttl=300)
def get_exchange_rates():
    rates = {"USD_TRY": 34.20, "EUR_TRY": 37.10, "EUR_USD": 1.08}
    try:
        tickers = yf.Tickers('TRY=X EURTRY=X')
        usd_data = tickers.tickers['TRY=X'].fast_info.last_price
        eur_data = tickers.tickers['EURTRY=X'].fast_info.last_price
        if usd_data and usd_data > 0:
            rates["USD_TRY"] = float(usd_data)
        if eur_data and eur_data > 0:
            rates["EUR_TRY"] = float(eur_data)
        rates["EUR_USD"] = rates["EUR_TRY"] / rates["USD_TRY"] if rates["USD_TRY"] > 0 else 1.08
    except Exception:
        pass
    return rates

def convert_currency(amount: float, from_curr: str, to_curr: str, rates: dict) -> float:
    if from_curr == to_curr or amount == 0:
        return amount
    val_in_try = amount
    if from_curr == 'USD':
        val_in_try = amount * rates['USD_TRY']
    elif from_curr == 'EUR':
        val_in_try = amount * rates['EUR_TRY']
    
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
            price = ticker.fast_info.last_price
            if price and price > 0:
                prices[sym] = float(price)
        except Exception:
            continue
    return prices

# ==============================================================================
# 3. VERİTABANI İLKLENDİRME (SIFIR MOCK VERİ)
# ==============================================================================
DEFAULT_CATEGORIES = [
    {"id": "BIST", "name": "Borsa İstanbul", "targetPercent": 25.0, "color": "#3b82f6"},
    {"id": "US_EQUITY", "name": "ABD & Global Hisse", "targetPercent": 30.0, "color": "#10b981"},
    {"id": "GOLD", "name": "Altın & Değerli Maden", "targetPercent": 15.0, "color": "#f59e0b"},
    {"id": "CRYPTO", "name": "Kripto Varlıklar", "targetPercent": 10.0, "color": "#8b5cf6"},
    {"id": "EUROBOND", "name": "Eurobond & Tahvil", "targetPercent": 10.0, "color": "#06b6d4"},
    {"id": "CASH", "name": "Nakit Rezerv (Dry Powder)", "targetPercent": 10.0, "color": "#64748b"},
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

def get_user_db():
    email = st.session_state.current_user["email"]
    if email not in st.session_state.db:
        st.session_state.db[email] = {
            "categories": [c.copy() for c in DEFAULT_CATEGORIES],
            "transactions": [],
            "wallet": [],
            "manual_valuations": {},
            "base_currency": "TRY"
        }
    return st.session_state.db[email]

# ==============================================================================
# 4. ŞIK KİMLİK DOĞRULAMA (LOGIN / REGISTER MODALI)
# ==============================================================================
if not st.session_state.current_user:
    st.markdown("<div style='height:40px;'></div>", unsafe_allow_html=True)
    c_center = st.columns([1, 2, 1])[1]
    
    with c_center:
        st.markdown("""
        <div class="top-navbar" style="text-align: center;">
            <h1 style="color: #60a5fa; margin: 0; font-size: 28px;">💎 Zettaishi Finvest</h1>
            <p style="color: #94a3b8; margin-top: 6px; font-size: 14px;">Güvenli, Şifreli & Profesyonel Portföy Yönetim Platformu</p>
        </div>
        """, unsafe_allow_html=True)
        
        tab_login, tab_register = st.tabs(["🔒 Güvenli Giriş", "📝 Yeni Hesap Oluştur"])
        
        with tab_login:
            st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
            log_email = st.text_input("E-Posta Adresi", placeholder="ornek@hesap.com", key="auth_l_email")
            log_pwd = st.text_input("Şifre", type="password", placeholder="••••••••", key="auth_l_pwd")
            
            if st.button("Sisteme Giriş Yap", use_container_width=True, type="primary"):
                c_email = log_email.strip().lower()
                if c_email in st.session_state.users:
                    u_data = st.session_state.users[c_email]
                    if verify_password(log_pwd, u_data["password"]):
                        st.session_state.current_user = {"email": c_email, "name": u_data["name"], "role": u_data["role"]}
                        st.success(f"Hoş geldiniz, {u_data['name']}!")
                        st.rerun()
                    else:
                        st.error("Girdiğiniz şifre hatalı. Lütfen kontrol ediniz.")
                else:
                    st.error("Bu e-posta adresine kayıtlı kullanıcı bulunamadı.")
            
            st.info("💡 **Yönetici Girişi:** `admin@invest.local` | Şifre: `123456`")
            
        with tab_register:
            st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
            r_name = st.text_input("Adınız & Soyadınız", placeholder="Örn: Ahmet Yılmaz", key="auth_r_name")
            r_email = st.text_input("E-Posta Adresi", placeholder="ahmet@ornek.com", key="auth_r_email")
            r_pwd = st.text_input("Şifre (En az 6 karakter)", type="password", placeholder="••••••••", key="auth_r_pwd")
            r_pwd_c = st.text_input("Şifre Onayı", type="password", placeholder="••••••••", key="auth_r_pwd_c")
            
            if st.button("Hesabı Oluştur & Başla", use_container_width=True):
                c_email = r_email.strip().lower()
                if not r_name or not c_email or not r_pwd:
                    st.error("Lütfen tüm zorunlu alanları doldurunuz.")
                elif len(r_pwd) < 6:
                    st.error("Şifreniz en az 6 karakter olmalıdır.")
                elif r_pwd != r_pwd_c:
                    st.error("Girdiğiniz şifreler uyuşmuyor.")
                elif c_email in st.session_state.users:
                    st.error("Bu e-posta adresi zaten sisteme kayıtlı.")
                else:
                    st.session_state.users[c_email] = {
                        "name": r_name.strip(),
                        "password": hash_password(r_pwd),
                        "role": "USER"
                    }
                    st.session_state.current_user = {
                        "email": c_email,
                        "name": r_name.strip(),
                        "role": "USER"
                    }
                    st.success("Hesabınız sıfır portföy bakiyesi ile açıldı! Yönlendiriliyorsunuz...")
                    st.rerun()
    st.stop()

# ==============================================================================
# 5. ANA PANEL: MODERN ÜST NAVİGASYON (HEADER & NAVBAR)
# ==============================================================================
user_db = get_user_db()
rates = get_exchange_rates()

# Üst Bar Tasarımı
head_col1, head_col2, head_col3 = st.columns([4, 3, 3])
with head_col1:
    st.markdown(f"""
    <div style="display:flex; align-items:center; gap:12px;">
        <div style="background:#2563eb; width:42px; height:42px; border-radius:12px; display:flex; align-items:center; justify-content:center; font-size:22px;">💎</div>
        <div>
            <h2 style="margin:0; font-size:20px; color:#fff; font-weight:700;">Zettaishi Finvest</h2>
            <p style="margin:0; font-size:12px; color:#94a3b8;">Portföy & Varlık Yönetim Konsolu</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

with head_col2:
    st.markdown(f"""
    <div style="background:rgba(30,41,59,0.6); padding:8px 14px; border-radius:10px; border:1px solid #334155; font-size:12px; display:flex; justify-content:space-around;">
        <span>💵 USD/TRY: <b style="color:#60a5fa;">{rates['USD_TRY']:.2f} ₺</b></span>
        <span>💶 EUR/TRY: <b style="color:#60a5fa;">{rates['EUR_TRY']:.2f} ₺</b></span>
    </div>
    """, unsafe_allow_html=True)

with head_col3:
    u_col1, u_col2 = st.columns([2, 1])
    with u_col1:
        base_curr = st.selectbox(
            "Para Birimi",
            ["TRY", "USD", "EUR"],
            index=["TRY", "USD", "EUR"].index(user_db.get("base_currency", "TRY")),
            label_visibility="collapsed"
        )
        user_db["base_currency"] = base_curr
    with u_col2:
        if st.button("Çıkış", use_container_width=True):
            st.session_state.current_user = None
            st.rerun()

st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

# ÜST MENÜ TABLARI (TOP NAVIGATION BAR)
active_tab = st.radio(
    "Navigasyon",
    ["📊 Portföy Dashboard", "➕ İşlem Ekle", "⚖️ Yeniden Dengeleme (Rebalance)", "💵 Nakit Cüzdanı", "🎯 Hedef & Kategori Ayarları", "📜 İşlem Geçmişi"],
    horizontal=True,
    label_visibility="collapsed"
)

st.markdown("<hr style='border-color:#1e293b; margin: 12px 0 24px 0;'>", unsafe_allow_html=True)

# ==============================================================================
# 6. HESAPLAMA MOTORU (PORTFOLIO ANALYTICS)
# ==============================================================================
transactions = user_db["transactions"]
categories = user_db["categories"]
manual_vals = user_db["manual_valuations"]

# Canlı Fiyatları Çekme
live_symbols = tuple(set(t["symbol"] for t in transactions if t.get("pricingMode") != "MANUAL"))
live_quotes = fetch_live_prices(live_symbols)

# Pozisyonları Hesapla
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
            avg_c = holdings_dict[sym]["totalCostNative"] / holdings_dict[sym]["quantity"]
            deduct_q = min(tx["quantity"], holdings_dict[sym]["quantity"])
            holdings_dict[sym]["quantity"] -= deduct_q
            holdings_dict[sym]["totalCostNative"] -= avg_c * deduct_q

holdings_list = []
total_portfolio_value_base = 0.0
total_portfolio_cost_base = 0.0

for sym, h in holdings_dict.items():
    if h["quantity"] <= 0.00001:
        continue
    avg_price = h["totalCostNative"] / h["quantity"] if h["quantity"] > 0 else 0.0
    curr_price = manual_vals.get(sym, avg_price) if h["pricingMode"] == "MANUAL" else live_quotes.get(sym, avg_price)
    
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

# ==============================================================================
# 7. SAYFA: PORTFÖY DASHBOARD
# ==============================================================================
if active_tab == "📊 Portföy Dashboard":
    total_pnl = total_portfolio_value_base - total_portfolio_cost_base
    total_pnl_pct = (total_pnl / total_portfolio_cost_base * 100) if total_portfolio_cost_base > 0 else 0.0
    
    # 4'lü Metrik Kartları
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown(f"""
        <div class="glass-card">
            <p style="color:#94a3b8; font-size:12px; margin:0; text-transform:uppercase; font-weight:600;">Toplam Portföy Değeri</p>
            <h2 style="color:#fff; font-size:26px; margin:8px 0 0 0; font-weight:700;">{format_money(total_portfolio_value_base, base_curr)}</h2>
        </div>
        """, unsafe_allow_html=True)
    with m2:
        st.markdown(f"""
        <div class="glass-card">
            <p style="color:#94a3b8; font-size:12px; margin:0; text-transform:uppercase; font-weight:600;">Yatırılan Ana Para</p>
            <h2 style="color:#e2e8f0; font-size:26px; margin:8px 0 0 0; font-weight:700;">{format_money(total_portfolio_cost_base, base_curr)}</h2>
        </div>
        """, unsafe_allow_html=True)
    with m3:
        pnl_color = "#10b981" if total_pnl >= 0 else "#ef4444"
        st.markdown(f"""
        <div class="glass-card">
            <p style="color:#94a3b8; font-size:12px; margin:0; text-transform:uppercase; font-weight:600;">Net Kâr / Zarar</p>
            <h2 style="color:{pnl_color}; font-size:26px; margin:8px 0 0 0; font-weight:700;">{format_money(total_pnl, base_curr)} <span style="font-size:15px; font-weight:500;">({total_pnl_pct:+.2f}%)</span></h2>
        </div>
        """, unsafe_allow_html=True)
    with m4:
        st.markdown(f"""
        <div class="glass-card">
            <p style="color:#94a3b8; font-size:12px; margin:0; text-transform:uppercase; font-weight:600;">Açık Pozisyon Sayısı</p>
            <h2 style="color:#60a5fa; font-size:26px; margin:8px 0 0 0; font-weight:700;">{len(df_holdings)} Varlık</h2>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)
    
    # Grafikler
    c_g1, c_g2 = st.columns(2)
    with c_g1:
        st.markdown("#### 🎯 Kategori Dağılımı")
        if not df_holdings.empty:
            cat_sum = df_holdings.groupby("Kategori")["Toplam Değer"].sum().reset_index()
            fig_p = px.pie(cat_sum, values="Toplam Değer", names="Kategori", hole=0.5, color_discrete_sequence=px.colors.qualitative.Plotly)
            fig_p.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#cbd5e1", margin=dict(t=10, b=10, l=10, r=10))
            st.plotly_chart(fig_p, use_container_width=True)
        else:
            st.info("Henüz portföyünüzde aktif varlık bulunmuyor.")

    with c_g2:
        st.markdown("#### 📊 Mevcut vs Hedef Ağırlık (%)")
        if not df_holdings.empty and total_portfolio_value_base > 0:
            c_comp = []
            for c in categories:
                c_val = df_holdings[df_holdings["Kategori_ID"] == c["id"]]["Toplam Değer"].sum()
                c_comp.append({"Kategori": c["name"], "Mevcut %": (c_val / total_portfolio_value_base) * 100, "Hedef %": c["targetPercent"]})
            df_c = pd.DataFrame(c_comp)
            fig_b = go.Figure([
                go.Bar(name='Mevcut %', x=df_c['Kategori'], y=df_c['Mevcut %'], marker_color='#3b82f6'),
                go.Bar(name='Hedef %', x=df_c['Kategori'], y=df_c['Hedef %'], marker_color='#10b981')
            ])
            fig_b.update_layout(barmode='group', paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#cbd5e1", margin=dict(t=10, b=10, l=10, r=10))
            st.plotly_chart(fig_b, use_container_width=True)
        else:
            st.info("Karşılaştırma için pozisyon ekleyin.")

    # Varlık Tablosu
    st.markdown("#### 📋 Varlık Pozisyon Listesi")
    if not df_holdings.empty:
        disp_df = df_holdings.copy()
        disp_df["Ortalama Maliyet"] = disp_df.apply(lambda r: format_money(r["Ortalama Maliyet"], r["Para Birimi"]), axis=1)
        disp_df["Güncel Fiyat"] = disp_df.apply(lambda r: format_money(r["Güncel Fiyat"], r["Para Birimi"]), axis=1)
        disp_df["Toplam Değer"] = disp_df["Toplam Değer"].apply(lambda v: format_money(v, base_curr))
        disp_df["Toplam Maliyet"] = disp_df["Toplam Maliyet"].apply(lambda v: format_money(v, base_curr))
        disp_df["Kâr/Zarar"] = disp_df["Kâr/Zarar"].apply(lambda v: format_money(v, base_curr))
        disp_df["Getiri %"] = disp_df["Getiri %"].apply(lambda v: f"{v:+.2f}%")
        disp_df["Ağırlık %"] = disp_df["Ağırlık %"].apply(lambda v: f"%{v:.2f}")
        
        st.dataframe(disp_df[["Sembol", "Varlık Adı", "Kategori", "Adet", "Ortalama Maliyet", "Güncel Fiyat", "Toplam Değer", "Kâr/Zarar", "Getiri %", "Ağırlık %"]], use_container_width=True)
        
        st.download_button(
            "📥 Portföyü Excel Uyumlu CSV Olarak İndir",
            data=df_holdings.to_csv(index=False).encode('utf-8-sig'),
            file_name=f"Zettaishi_Portfoy_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
    else:
        st.warning("Portföyünüz temiz ve boş durumda. Yukarıdaki **'➕ İşlem Ekle'** sekmesinden ilk işleminizi girin.")

# ==============================================================================
# 8. SAYFA: İŞLEM EKLE (ALIM / SATIM)
# ==============================================================================
elif active_tab == "➕ İşlem Ekle":
    st.markdown("### ➕ Yeni Portföy İşlemi")
    st.caption("Alım veya satım işlemlerinizi girerek anında portföyünüzü güncelleyin.")
    
    col_a, col_b = st.columns(2)
    with col_a:
        t_type = st.radio("İşlem Tipi", ["BUY (Alım)", "SELL (Satım)"], horizontal=True)
        t_type = "BUY" if "BUY" in t_type else "SELL"
        cat_map = {c["id"]: c["name"] for c in categories}
        t_cat = st.selectbox("Kategori", options=list(cat_map.keys()), format_func=lambda x: cat_map[x])
        t_sym = st.text_input("Varlık Sembolü", placeholder="Örn: THYAO, AAPL, BTC-USD, ALTIN").upper().strip()
        t_name = st.text_input("Varlık Adı / Açıklama", placeholder="Örn: Türk Hava Yolları")
        
    with col_b:
        t_curr = st.selectbox("Para Birimi", ["TRY", "USD", "EUR"])
        t_qty = st.number_input("Adet / Miktar", min_value=0.0001, value=10.0, step=1.0)
        t_price = st.number_input(f"Birim Fiyat ({t_curr})", min_value=0.0001, value=100.0, step=1.0)
        t_date = st.date_input("İşlem Tarihi", value=datetime.now())
        t_pmode = st.radio("Fiyatlama Modu", ["Canlı Piyasa (Yahoo Finance)", "Manuel Değerleme"])
        pricing_mode = "MANUAL" if "Manuel" in t_pmode else "LIVE"

    total_val = t_qty * t_price
    st.info(f"💵 Toplam İşlem Tutarı: **{format_money(total_val, t_curr)}**")
    
    deduct_wallet = False
    if t_type == "BUY":
        deduct_wallet = st.checkbox("Bu tutarı Nakit Cüzdanımdan düş", value=False)
        
    if st.button("İşlemi Onayla & Portföye Kaydet", type="primary", use_container_width=True):
        if not t_sym:
            st.error("Lütfen varlık sembolünü giriniz.")
        else:
            user_db["transactions"].append({
                "id": f"tx_{int(time.time()*1000)}",
                "symbol": t_sym,
                "name": t_name or t_sym,
                "category": t_cat,
                "type": t_type,
                "quantity": float(t_qty),
                "price": float(t_price),
                "currency": t_curr,
                "date": t_date.strftime("%Y-%m-%d"),
                "pricingMode": pricing_mode
            })
            if t_type == "BUY" and deduct_wallet:
                user_db["wallet"].append({"id": f"w_{int(time.time()*1000)}", "type": "BUY_DEDUCT", "amount": total_val, "currency": t_curr, "date": t_date.strftime("%Y-%m-%d"), "description": f"{t_sym} Alımı"})
            elif t_type == "SELL":
                user_db["wallet"].append({"id": f"w_{int(time.time()*1000)}", "type": "SELL_CREDIT", "amount": total_val, "currency": t_curr, "date": t_date.strftime("%Y-%m-%d"), "description": f"{t_sym} Satışı"})
            
            st.success(f"{t_sym} işlemi başarıyla kaydedildi!")
            st.cache_data.clear()
            time.sleep(0.5)
            st.rerun()

# ==============================================================================
# 9. SAYFA: YENİDEN DENGELEME MOTORU (REBALANCE)
# ==============================================================================
elif active_tab == "⚖️ Yeniden Dengeleme (Rebalance)":
    st.markdown("### ⚖️ Akıllı Yeniden Dengeleme (Rebalance) Önerileri")
    st.caption("Hedef dağılımınıza göre matematiksel olarak almanız veya satmanız gereken tutarlar.")
    
    if total_portfolio_value_base <= 0:
        st.warning("Yeniden dengeleme için portföyünüzde en az bir varlık bulunmalıdır.")
    else:
        st.markdown(f"#### Toplam Portföy Büyüklüğü: **{format_money(total_portfolio_value_base, base_curr)}**")
        
        for c in categories:
            c_val = df_holdings[df_holdings["Kategori_ID"] == c["id"]]["Toplam Değer"].sum() if not df_holdings.empty else 0
            curr_pct = (c_val / total_portfolio_value_base) * 100
            target_pct = c["targetPercent"]
            target_val = (target_pct / 100.0) * total_portfolio_value_base
            diff_val = target_val - c_val
            
            if diff_val > 50:
                st.markdown(f"""
                <div class="reb-badge-buy">
                    <h4 style="color:#10b981; margin:0;">🟢 {c['name']} - ALIM ÖNERİSİ</h4>
                    <p style="margin:4px 0 0 0; color:#e2e8f0;">Mevcut Dağılım: <b>%{curr_pct:.1f}</b> → Hedef: <b>%{target_pct:.1f}</b> | Hedefe Ulaşmak İçin Eklenecek Tutar: <b style="color:#10b981;">+{format_money(abs(diff_val), base_curr)}</b></p>
                </div>
                """, unsafe_allow_html=True)
            elif diff_val < -50:
                st.markdown(f"""
                <div class="reb-badge-sell">
                    <h4 style="color:#ef4444; margin:0;">🔴 {c['name']} - KÂR REALİZASYONU / SATIM</h4>
                    <p style="margin:4px 0 0 0; color:#e2e8f0;">Mevcut Dağılım: <b>%{curr_pct:.1f}</b> → Hedef: <b>%{target_pct:.1f}</b> | Dengeye Ulaşmak İçin Azaltılacak Tutar: <b style="color:#ef4444;">-{format_money(abs(diff_val), base_curr)}</b></p>
                </div>
                """, unsafe_allow_html=True)

# ==============================================================================
# 10. SAYFA: NAKİT CÜZDANI (DRY POWDER)
# ==============================================================================
elif active_tab == "💵 Nakit Cüzdanı":
    st.markdown("### 💵 Likit Rezerv & Nakit Cüzdanı (Dry Powder)")
    
    wallet_txs = user_db["wallet"]
    bals = {"TRY": 0.0, "USD": 0.0, "EUR": 0.0}
    for w in wallet_txs:
        curr = w.get("currency", "TRY")
        w_t = w.get("type", "DEPOSIT")
        if w_t in ["DEPOSIT", "SELL_CREDIT", "DIVIDEND"]:
            bals[curr] += w["amount"]
        elif w_t in ["WITHDRAW", "BUY_DEDUCT"]:
            bals[curr] -= w["amount"]
            
    w1, w2, w3 = st.columns(3)
    with w1:
        st.markdown(f'<div class="glass-card"><p style="color:#94a3b8; font-size:12px; margin:0;">TRY Nakit</p><h2 style="color:#fff; margin:4px 0 0 0;">{format_money(bals["TRY"], "TRY")}</h2></div>', unsafe_allow_html=True)
    with w2:
        st.markdown(f'<div class="glass-card"><p style="color:#94a3b8; font-size:12px; margin:0;">USD Nakit</p><h2 style="color:#fff; margin:4px 0 0 0;">{format_money(bals["USD"], "USD")}</h2></div>', unsafe_allow_html=True)
    with w3:
        st.markdown(f'<div class="glass-card"><p style="color:#94a3b8; font-size:12px; margin:0;">EUR Nakit</p><h2 style="color:#fff; margin:4px 0 0 0;">{format_money(bals["EUR"], "EUR")}</h2></div>', unsafe_allow_html=True)
        
    st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)
    st.markdown("#### Nakit Para Yatır / Çek")
    cw1, cw2, cw3 = st.columns(3)
    with cw1:
        w_act = st.selectbox("İşlem Türü", ["Para Yatır (Deposit)", "Para Çek (Withdraw)"])
    with cw2:
        w_c = st.selectbox("Para Birimi", ["TRY", "USD", "EUR"], key="cw_c")
    with cw3:
        w_amt = st.number_input("Tutar", min_value=1.0, value=5000.0, step=500.0)
        
    if st.button("Cüzdan İşlemini Uygula", type="primary"):
        act_t = "DEPOSIT" if "Yatır" in w_act else "WITHDRAW"
        user_db["wallet"].append({
            "id": f"w_{int(time.time()*1000)}",
            "type": act_t,
            "amount": float(w_amt),
            "currency": w_c,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "description": "Manuel Cüzdan Hareketi"
        })
        st.success("Nakit cüzdanı güncellendi!")
        st.rerun()

# ==============================================================================
# 11. SAYFA: KATEGORİ & HEDEF AYARLARI (%100 KESİN DOĞRULAMASI)
# ==============================================================================
elif active_tab == "🎯 Hedef & Kategori Ayarları":
    st.markdown("### 🎯 Hedef Varlık Dağılımı Ayarları")
    st.caption("Hedef oranların toplamı **tam olarak %100** olmalıdır. Aksi halde kaydetme butonu kilitli kalır.")
    
    temp_cats = []
    tot_t = 0.0
    
    for i, cat in enumerate(categories):
        cx1, cx2 = st.columns([3, 2])
        with cx1:
            cn = st.text_input(f"Kategori Adı #{i+1}", value=cat["name"], key=f"cn_{cat['id']}")
        with cx2:
            ct = st.number_input(f"Hedef Yüzde %", min_value=0.0, max_value=100.0, value=float(cat["targetPercent"]), step=1.0, key=f"ct_{cat['id']}")
            tot_t += ct
        temp_cats.append({"id": cat["id"], "name": cn, "targetPercent": ct, "color": cat.get("color", "#3b82f6")})
        
    st.markdown("<hr style='border-color:#334155;'>", unsafe_allow_html=True)
    
    is_valid = round(tot_t) == 100
    if is_valid:
        st.success(f"✅ Toplam Hedef: **%{tot_t:.1f}** (Doğrulandı - Kaydedilebilir)")
        if st.button("💾 Ayarları Kaydet & Uygula", type="primary", use_container_width=True):
            user_db["categories"] = temp_cats
            st.success("Hedef oranlarınız başarıyla güncellendi!")
            st.rerun()
    else:
        st.error(f"❌ Toplam Hedef: **%{tot_t:.1f}**. Kaydedebilmek için toplam tam olarak %100 olmalıdır!")
        st.button("💾 Ayarları Kaydet & Uygula (Kilitli - Toplam %100 Olmalı)", disabled=True, use_container_width=True)

# ==============================================================================
# 12. SAYFA: İŞLEM GEÇMİŞİ
# ==============================================================================
elif active_tab == "📜 İşlem Geçmişi":
    st.markdown("### 📜 İşlem Geçmişi ve Hareketler")
    
    if not transactions:
        st.info("Kayıtlı herhangi bir işlem geçmişiniz bulunmamaktadır (Temiz Başlangıç).")
    else:
        df_t = pd.DataFrame(transactions)
        st.dataframe(df_t[["date", "type", "symbol", "name", "category", "quantity", "price", "currency"]], use_container_width=True)
        
        if st.button("🗑️ Tüm İşlem Geçmişini Sıfırla (Portföyü Temizle)"):
            user_db["transactions"] = []
            user_db["wallet"] = []
            st.success("Tüm veriler başarıyla sıfırlandı.")
            st.rerun()

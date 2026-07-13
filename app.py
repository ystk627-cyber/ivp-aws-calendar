import streamlit as st
import datetime
import pandas as pd
import json
import urllib.parse
import requests
from scraper import scrape_aws_seminars, login_ivp, scrape_ivp_schedule, extract_ivp_diagnostic_info

# ==========================================
# Event Splitting Utility
# ==========================================
def split_multiday_events(events):
    """
    Splits multi-day events into multiple individual 1-day events
    so they display as separate daily boxes in FullCalendar.
    """
    processed = []
    for ev in events:
        start_str = ev.get("start", "")
        end_str = ev.get("end", "")
        
        # Get date part
        start_date_str = start_str.split("T")[0]
        end_date_str = end_str.split("T")[0] if end_str else start_date_str
        
        if not start_date_str:
            continue
            
        try:
            start_date = datetime.date.fromisoformat(start_date_str)
            end_date = datetime.date.fromisoformat(end_date_str)
        except ValueError:
            processed.append(ev)
            continue
            
        if start_date == end_date:
            processed.append(ev)
        else:
            curr = start_date
            while curr <= end_date:
                new_ev = ev.copy()
                if "T" in start_str:
                    new_ev["start"] = f"{curr.isoformat()}T{start_str.split('T')[1]}"
                else:
                    new_ev["start"] = curr.isoformat()
                    
                if "T" in end_str:
                    new_ev["end"] = f"{curr.isoformat()}T{end_str.split('T')[1]}"
                else:
                    new_ev["end"] = curr.isoformat()
                    
                new_ev["id"] = f"{ev['id']}_{curr.isoformat()}"
                processed.append(new_ev)
                curr += datetime.timedelta(days=1)
    return processed


# ==========================================


# ==========================================
# Page Configuration
# ==========================================
st.set_page_config(
    page_title="IVP・AWS 統合イベントスケジュールカレンダー",
    page_icon="📅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom premium styling
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&family=Noto+Sans+JP:wght@300;400;500;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Noto Sans JP', 'Outfit', sans-serif;
    }
    
    .main-title {
        font-family: 'Outfit', 'Noto Sans JP', sans-serif;
        font-weight: 700;
        font-size: 2.8rem;
        background: linear-gradient(135deg, #1f77b4 0%, #ff7f0e 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    
    .sub-title {
        font-size: 1.1rem;
        color: #666;
        margin-bottom: 2rem;
    }
    
    /* Stat Cards */
    .stat-card {
        background-color: #f8f9fa;
        border-left: 5px solid #1f77b4;
        border-radius: 6px;
        padding: 1rem;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        margin-bottom: 1rem;
    }
    .stat-card.ivp {
        border-left-color: #ff7f0e;
    }
    .stat-card.total {
        border-left-color: #2ca02c;
    }
    .stat-title {
        font-size: 0.85rem;
        color: #6c757d;
        text-transform: uppercase;
        font-weight: 600;
    }
    .stat-value {
        font-size: 1.8rem;
        font-weight: 700;
        color: #212529;
    }
    
    /* Custom Badges */
    .badge {
        padding: 0.25em 0.6em;
        font-size: 75%;
        font-weight: 700;
        border-radius: 10rem;
        display: inline-block;
        margin-right: 0.5rem;
    }
    .badge-aws {
        background-color: #e1f5fe;
        color: #0288d1;
    }
    .badge-ivp {
        background-color: #fff3e0;
        color: #f57c00;
    }
    
    /* Event Cards */
    .event-card {
        background: #ffffff;
        border: 1px solid #e9ecef;
        border-radius: 10px;
        padding: 1.25rem;
        margin-bottom: 1rem;
        transition: transform 0.2s, box-shadow 0.2s;
        box-shadow: 0 4px 6px rgba(0,0,0,0.02);
    }
    .event-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 12px rgba(0,0,0,0.08);
    }
</style>
""", unsafe_allow_html=True)


# ==========================================
# Google Calendar URL Generator
# ==========================================
def make_gcal_link(title, start_str, end_str, place="", details_url=""):
    try:
        clean_title = urllib.parse.quote(title)
        clean_place = urllib.parse.quote(place)
        
        details_text = f"統合スケジュールより登録\n詳細URL: {details_url}"
        clean_details = urllib.parse.quote(details_text)
        
        if "T" in start_str:
            st_dt = datetime.datetime.fromisoformat(start_str)
            en_dt = datetime.datetime.fromisoformat(end_str)
            dates_str = f"{st_dt.strftime('%Y%m%dT%H%M%S')}/{en_dt.strftime('%Y%m%dT%H%M%S')}"
        else:
            st_d = datetime.date.fromisoformat(start_str)
            en_d = datetime.date.fromisoformat(end_str)
            # Google Calendar requires end date of all-day event to be exclusive
            exclusive_end = en_d + datetime.timedelta(days=1)
            dates_str = f"{st_d.strftime('%Y%m%d')}/{exclusive_end.strftime('%Y%m%d')}"
            
        return f"https://www.google.com/calendar/render?action=TEMPLATE&text={clean_title}&dates={dates_str}&details={clean_details}&location={clean_place}"
    except Exception as e:
        return "#"


# ==========================================
# Session State Initialization
# ==========================================
if 'ivp_id' not in st.session_state:
    st.session_state['ivp_id'] = ""
if 'ivp_pw' not in st.session_state:
    st.session_state['ivp_pw'] = ""
if 'ivp_session' not in st.session_state:
    st.session_state['ivp_session'] = None
if 'ivp_login_error' not in st.session_state:
    st.session_state['ivp_login_error'] = None
if 'refresh_trigger' not in st.session_state:
    st.session_state['refresh_trigger'] = False
if 'last_login_html' not in st.session_state:
    st.session_state['last_login_html'] = None


# ==========================================
# Sidebar UI & Controls
# ==========================================
st.sidebar.markdown("### 📅 統合カレンダー")

# AWS Pages Config (Fixed to 5 pages / 5 months)
max_aws_pages = 5
st.sidebar.markdown("#### ☁️ AWSカレンダー")
st.sidebar.caption("📅 自動取得 (5ヶ月分)")
fetch_details = st.sidebar.checkbox("AWSの詳細時間も取得する", value=False, help="チェックを入れると各セミナーの詳細ページから開始・終了時間（例：13:00〜16:00）を並列処理で取得します。チェックを外すと終日イベントとして非常に高速に読み込みます。")

# IVP Credentials Section
st.sidebar.markdown("---")
st.sidebar.markdown("#### 🍊 IVPカレンダー")
st.sidebar.subheader("🔒 IVP ログイン設定")
st.sidebar.caption("IVP会員スケジュールを取得するために入力してください (5ヶ月分同期中)")

input_id = st.sidebar.text_input("IVP ID (Partner No.)", value=st.session_state['ivp_id'], max_chars=6, help="数字6桁 of Partner ID")
input_pw = st.sidebar.text_input("パスワード", value=st.session_state['ivp_pw'], type="password")

# Success indicator if logged in
if st.session_state['ivp_session']:
    st.sidebar.success("🟢 IVPログイン成功")

# Login action
if input_id != st.session_state['ivp_id'] or input_pw != st.session_state['ivp_pw']:
    # Credentials changed, reset session
    st.session_state['ivp_id'] = input_id
    st.session_state['ivp_pw'] = input_pw
    st.session_state['ivp_session'] = None
    st.session_state['ivp_login_error'] = None
    st.session_state['last_login_html'] = None

if input_id and input_pw and st.session_state['ivp_session'] is None and not st.session_state['ivp_login_error']:
    with st.sidebar.spinner("IVPログイン試行中..."):
        session, error, debug_html = login_ivp(input_id, input_pw)
        st.session_state['last_login_html'] = debug_html
        if session:
            st.session_state['ivp_session'] = session
            st.cache_data.clear()
            st.rerun()
        else:
            st.session_state['ivp_login_error'] = error

if st.session_state['ivp_login_error']:
    st.sidebar.error(st.session_state['ivp_login_error'])
    if st.sidebar.button("ログインを再試行"):
        st.session_state['ivp_login_error'] = None
        st.session_state['ivp_session'] = None
        st.rerun()

# Refresh button
st.sidebar.markdown("---")
if st.sidebar.button("🔄 カレンダーデータを更新", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

# Diagnostics tool (visible only to developers/ad-hoc users)
show_debug = st.sidebar.checkbox("🔧 IVP 解析デバッガを表示", value=False)


# ==========================================
# Data Fetching Logic (Cached in Memory)
# ==========================================
@st.cache_data(ttl=600)  # Cache in memory for 10 minutes
def get_all_events(aws_pages, fetch_details, ivp_session_cookie_dict=None):
    all_events = []
    
    # 1. Fetch AWS Seminars
    aws_events = scrape_aws_seminars(max_pages=aws_pages, fetch_details=fetch_details)
    all_events.extend(aws_events)
    
    # 2. Fetch IVP Seminars (if session available)
    if ivp_session_cookie_dict:
        # Reconstruct session
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, http/1.1) Chrome/120.0.0.0 Safari/537.36"
        })
        requests.utils.cookiejar_from_dict(ivp_session_cookie_dict, session.cookies)
        
        ivp_events = scrape_ivp_schedule(session)
        all_events.extend(ivp_events)
        
    return all_events

# Always do live fetch from memory cache (no local file caching)
session_cookies = None
if st.session_state['ivp_session']:
    session_cookies = requests.utils.dict_from_cookiejar(st.session_state['ivp_session'].cookies)

events = split_multiday_events(get_all_events(max_aws_pages, fetch_details, session_cookies))


# ==========================================
# Main Header & Stat Indicators
# ==========================================
st.markdown('<h1 class="main-title">📅 IVP・AWS 統合スケジュールカレンダー</h1>', unsafe_allow_html=True)
st.markdown('<p class="sub-title">AWARENESS（AWS）と IVP（WEB会員専用）のスケジュールを同期・統合して表示します 🔄✨</p>', unsafe_allow_html=True)

# Count stats
aws_count = sum(1 for e in events if e['source'] == 'AWS')
ivp_count = sum(1 for e in events if e['source'] == 'IVP')
total_count = len(events)

col1, col2, col3 = st.columns(3)
with col1:
    st.markdown(f"""
    <div class="stat-card total">
        <div class="stat-title">全イベント数</div>
        <div class="stat-value">{total_count}</div>
    </div>
    """, unsafe_allow_html=True)
with col2:
    st.markdown(f"""
    <div class="stat-card">
        <div class="stat-title">AWSセミナー数</div>
        <div class="stat-value">{aws_count}</div>
    </div>
    """, unsafe_allow_html=True)
with col3:
    st.markdown(f"""
    <div class="stat-card ivp">
        <div class="stat-title">IVPイベント数（同期中）</div>
        <div class="stat-value">{ivp_count if st.session_state['ivp_session'] else '未接続'}</div>
    </div>
    """, unsafe_allow_html=True)


# ==========================================
# Interactive Tabs
# ==========================================
tab_calendar, tab_table, tab_upcoming = st.tabs(["📅 統合カレンダー", "🔍 一覧検索・ダウンロード", "🚀 近日開催の注目イベント"])

# --- Tab 1: Calendar ---
with tab_calendar:
    # FullCalendar.js Integration HTML code
    # Injecting events as JSON
    events_json = json.dumps(events)
    
    calendar_html = f"""
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <link href="https://cdn.jsdelivr.net/npm/fullcalendar@6.1.11/index.global.min.css" rel="stylesheet">
        <script src="https://cdn.jsdelivr.net/npm/fullcalendar@6.1.11/index.global.min.js"></script>
        <style>
            html, body {{
                margin: 0;
                padding: 0;
                font-family: 'Noto Sans JP', sans-serif;
                font-size: 14px;
                background-color: #ffffff;
            }}
            #calendar {{
                max-width: 100%;
                margin: 10px auto;
                padding: 0 10px;
            }}
            .fc-event {{
                cursor: pointer;
                transition: transform 0.1s ease;
            }}
            .fc-event:hover {{
                transform: scale(1.02);
            }}
        </style>
    </head>
    <body>
        <div id="calendar"></div>
        <script>
            document.addEventListener('DOMContentLoaded', function() {{
                var calendarEl = document.getElementById('calendar');
                var eventsData = {events_json};
                
                var calendar = new FullCalendar.Calendar(calendarEl, {{
                    initialView: 'dayGridMonth',
                    locale: 'ja',
                    headerToolbar: {{
                        left: 'prev,next today',
                        center: 'title',
                        right: 'dayGridMonth,timeGridWeek,listMonth'
                    }},
                    buttonText: {{
                        today: '今日',
                        month: '月',
                        week: '週',
                        list: 'リスト'
                    }},
                    events: eventsData,
                    eventClick: function(info) {{
                        if (info.event.url) {{
                            window.open(info.event.url, '_blank');
                            info.jsEvent.preventDefault(); // Don't let default iframe navigate
                        }}
                    }},
                    eventMouseEnter: function(info) {{
                        info.el.style.opacity = 0.85;
                    }},
                    eventMouseLeave: function(info) {{
                        info.el.style.opacity = 1.0;
                    }}
                }});
                calendar.render();
            }});
        </script>
    </body>
    </html>
    """
    
    st.components.v1.html(calendar_html, height=750, scrolling=True)


# --- Tab 2: Table & Search ---
with tab_table:
    st.markdown("### 🔍 スケジュール一覧検索・CSV出力")
    
    if events:
        # Construct DataFrame
        df_data = []
        for e in events:
            df_data.append({
                "ソース": e["source"],
                "セミナー名": e["title"],
                "開催日時（開始）": e["start"],
                "開催日時（終了）": e["end"],
                "会場": e["place"],
                "URL": e["url"]
            })
        df = pd.DataFrame(df_data)
        
        # Filters
        col_search, col_source, col_place = st.columns([2, 1, 1])
        with col_search:
            search_query = st.text_input("🔍 セミナー名・キーワードで検索", "")
        with col_source:
            source_filter = st.multiselect("ソースで絞り込み", options=["AWS", "IVP"], default=["AWS", "IVP"])
        with col_place:
            all_places = list(df["会場"].unique())
            place_filter = st.multiselect("会場で絞り込み", options=all_places, default=all_places)
            
        # Apply filters
        filtered_df = df[
            (df["ソース"].isin(source_filter)) &
            (df["会場"].isin(place_filter))
        ]
        if search_query:
            filtered_df = filtered_df[filtered_df["セミナー名"].str.contains(search_query, case=False, na=False)]
            
        # Render Table
        st.dataframe(
            filtered_df,
            use_container_width=True,
            column_config={
                "URL": st.column_config.LinkColumn("詳細リンク")
            }
        )
        
        # Download button
        csv = filtered_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 絞り込んだ一覧をCSVとしてダウンロード",
            data=csv,
            file_name=f"integrated_schedule_{datetime.date.today().isoformat()}.csv",
            mime="text/csv"
        )
    else:
        st.info("表示するイベントはありません。")


# --- Tab 3: Upcoming Featured Events ---
with tab_upcoming:
    st.markdown("### 🚀 近日開催の注目イベント（直近10件）")
    
    # Filter upcoming events from today onwards
    now = datetime.datetime.now().date().isoformat()
    upcoming_events = [e for e in events if e["start"] >= now]
    upcoming_events = sorted(upcoming_events, key=lambda x: x["start"])[:10]
    
    if upcoming_events:
        for idx, e in enumerate(upcoming_events):
            # Parse time format
            date_display = e["start"].replace("T", " ")
            
            badge_class = "badge-aws" if e["source"] == "AWS" else "badge-ivp"
            
            col_img, col_info = st.columns([1, 4])
            
            with col_img:
                if e["image"]:
                    st.image(e["image"], use_container_width=True)
                else:
                    # Generic placeholder based on source
                    placeholder_img = "https://images.unsplash.com/photo-1506784983877-45594efa4cbe?w=500"
                    st.image(placeholder_img, use_container_width=True)
                    
            with col_info:
                st.markdown(f"""
                <div class="event-card">
                    <span class="badge {badge_class}">{e['source']}</span>
                    <strong style="font-size: 1.25rem;">{e['title']}</strong><br>
                    <div style="margin-top: 0.5rem; color: #555;">
                        📅 <strong>日時:</strong> {e['raw_date']} ({date_display})<br>
                        📍 <strong>会場:</strong> {e['place']}
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                # Action buttons
                gcal_link = make_gcal_link(e["title"], e["start"], e["end"], e["place"], e["url"])
                
                btn_col1, btn_col2 = st.columns(2)
                with btn_col1:
                    st.link_button("🌐 公式詳細ページを開く", e["url"], use_container_width=True)
                with btn_col2:
                    st.link_button("📅 Googleカレンダーに追加", gcal_link, use_container_width=True)
                st.markdown("<br>", unsafe_allow_html=True)
    else:
        st.info("近日開催予定のイベントは見つかりませんでした。")


# ==========================================
# Diagnostics / HTML Debugger (Expanded View)
# ==========================================
if show_debug:
    st.markdown("---")
    st.markdown("### 🔧 IVP 解析デバッガ")
    st.caption("IVPのレイアウトが変更されてスケジュールが読み込めない場合、ここからHTML構造を確認できます。")
    
    if st.session_state['ivp_session']:
        with st.spinner("IVP構造の解析中..."):
            diag_info = extract_ivp_diagnostic_info(st.session_state['ivp_session'])
            
            st.text(f"ページタイトル: {diag_info['title']}")
            
            tab_diag_tables, tab_diag_links, tab_diag_html = st.tabs(["📊 検出されたテーブル", "🔗 リンク一覧", "📄 生HTML"])
            
            with tab_diag_tables:
                if diag_info["tables_summary"]:
                    st.json(diag_info["tables_summary"])
                else:
                    st.info("テーブルは検出されませんでした。")
                    
            with tab_diag_links:
                if diag_info["links"]:
                    st.dataframe(pd.DataFrame(diag_info["links"]))
                else:
                    st.info("リンクは検出されませんでした。")
                    
            with tab_diag_html:
                st.text_area("HTMLソース (一部)", diag_info["html_snippet"], height=400)
    else:
        st.warning("デバッガを使用するには、まず左側のサイドバーからIVPにログインしてください。")
        if st.session_state.get('last_login_html'):
            st.markdown("#### ⚠️ 直近のログイン試行時のレスポンスHTML:")
            st.caption("ID/PW送信後に返された生のHTMLです。エラーメッセージや変更点を確認できます。")
            st.text_area("ログイン試行レスポンスHTML", st.session_state['last_login_html'], height=400)

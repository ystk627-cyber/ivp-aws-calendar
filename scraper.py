import requests
from bs4 import BeautifulSoup, Comment
import re
import datetime
import urllib.parse
import streamlit as st

AWS_BASE_URL = "https://www.awareness.co.jp"
AWS_LIST_URL = f"{AWS_BASE_URL}/seminar2/seminarlist"
AWS_CALENDAR_URL = f"{AWS_BASE_URL}/seminar2/calendar"

IVP_BASE_URL = "https://valuable-style.co.jp"
IVP_LOGIN_URL = f"{IVP_BASE_URL}/ivp-web/schedule/index.php"

# ==========================================
# Common Date Parsing Utility
# ==========================================
def parse_date_with_year(date_str, ref_date=None):
    """
    Parses dates like '07月12日(日)' or '2026/07/12' or '7月12日'.
    Handles year rollover logic based on ref_date (default to today).
    """
    if not ref_date:
        ref_date = datetime.date.today()
        
    date_str = date_str.strip()
    
    # Check for YYYY/MM/DD or YYYY-MM-DD
    match_ymd = re.search(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', date_str)
    if match_ymd:
        return datetime.date(int(match_ymd.group(1)), int(match_ymd.group(2)), int(match_ymd.group(3)))
        
    # Check for MM/DD or MM-DD
    match_md = re.search(r'(\d{1,2})[-/](\d{1,2})', date_str)
    if match_md:
        month = int(match_md.group(1))
        day = int(match_md.group(2))
        year = ref_date.year
        if month < ref_date.month - 2:
            year += 1
        elif month > ref_date.month + 9:
            year -= 1
        return datetime.date(year, month, day)

    # Check for X月Y日
    match_jp = re.search(r'(\d{1,2})月(\d{1,2})日', date_str)
    if match_jp:
        month = int(match_jp.group(1))
        day = int(match_jp.group(2))
        year = ref_date.year
        if month < ref_date.month - 2:
            year += 1
        elif month > ref_date.month + 9:
            year -= 1
        return datetime.date(year, month, day)
        
    return None


def parse_ivp_list_date_range(day_text):
    """
    Parses date ranges or single dates from IVP list items, e.g.
    '2026年9月12日(土)～9月13日(日)' -> (2026-09-12, 2026-09-13)
    '2026年8月4日(火)' -> (2026-08-04, 2026-08-04)
    '2026年3月20日(金)～7月31日(金)' -> (2026-03-20, 2026-07-31)
    """
    # Split by ~ or ～
    parts = re.split(r'[~～]', day_text)
    
    start_str = parts[0].strip()
    match_start = re.search(r'(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日', start_str)
    if not match_start:
        match_start = re.search(r'(\d{1,2})月\s*(\d{1,2})日', start_str)
        if not match_start:
            return None, None
        year = datetime.date.today().year
        month = int(match_start.group(1))
        day = int(match_start.group(2))
    else:
        year = int(match_start.group(1))
        month = int(match_start.group(2))
        day = int(match_start.group(3))
        
    try:
        start_date = datetime.date(year, month, day)
    except ValueError:
        return None, None
        
    end_date = start_date
    
    if len(parts) > 1:
        end_str = parts[1].strip()
        match_end_full = re.search(r'(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日', end_str)
        if match_end_full:
            try:
                end_date = datetime.date(int(match_end_full.group(1)), int(match_end_full.group(2)), int(match_end_full.group(3)))
            except ValueError:
                pass
        else:
            match_end_md = re.search(r'(\d{1,2})月\s*(\d{1,2})日', end_str)
            if match_end_md:
                try:
                    end_date = datetime.date(year, int(match_end_md.group(1)), int(match_end_md.group(2)))
                except ValueError:
                    pass
            else:
                match_end_d = re.search(r'(\d{1,2})日', end_str)
                if match_end_d:
                    try:
                        end_date = datetime.date(year, month, int(match_end_d.group(1)))
                    except ValueError:
                        pass
                        
    return start_date, end_date


# ==========================================
# AWS (AWARENESS) Scraper
# ==========================================
@st.cache_data(ttl=3600)  # Cache detailed times for 1 hour to prevent redundant requests
def scrape_aws_detail_time(detail_url):
    """
    Fetches the detail page for an AWS seminar and extracts the time range (e.g. '13:00～16:00').
    """
    url = detail_url if detail_url.startswith("http") else AWS_BASE_URL + detail_url
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        
        # Search table rows for "日時"
        table = soup.find("table", class_="seminar-table")
        if table:
            for tr in table.find_all("tr"):
                th = tr.find("th")
                td = tr.find("td")
                if th and td and "日時" in th.get_text():
                    td_text = td.get_text()
                    # Find HH:MM～HH:MM pattern
                    match = re.search(r'(\d{1,2}):(\d{2})\s*～\s*(\d{1,2}):(\d{2})', td_text)
                    if match:
                        start_time = f"{int(match.group(1)):02d}:{match.group(2)}"
                        end_time = f"{int(match.group(3)):02d}:{match.group(4)}"
                        return start_time, end_time
    except Exception as e:
        pass
    return None, None

def _infer_aws_place(title):
    t_lower = title.lower()
    if "zoom" in t_lower:
        return "オンライン (Zoom)"
    if any(k in title for k in ["動画販売", "収録配信", "収録販売"]):
        return "オンライン (動画・収録配信)"
    if "東京" in title:
        return "東京"
    if "大阪" in title:
        return "大阪"
    if "名古屋" in title:
        return "名古屋"
    if "対面" in title:
        return "対面会場"
    return "AWARENESS"

def scrape_aws_seminars(max_pages=5, fetch_details=False):
    """
    Scrapes AWS seminars from the official monthly calendar pages (/seminar2/calendar/YYYYMM).
    Fetches `max_pages` months starting from the current month in parallel.
    """
    events = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    today = datetime.date.today()
    target_months = []
    for i in range(max_pages):
        m_year = today.year
        m_month = today.month + i
        while m_month > 12:
            m_month -= 12
            m_year += 1
        target_months.append((m_year, m_month))

    # 1. Collect monthly calendar items in parallel
    from concurrent.futures import ThreadPoolExecutor
    raw_items = []

    def fetch_calendar_month(ym_tuple):
        m_year, m_month = ym_tuple
        ym_str = f"{m_year}{m_month:02d}"
        url = f"{AWS_CALENDAR_URL}/{ym_str}"
        try:
            res = requests.get(url, headers=headers, timeout=15)
            res.raise_for_status()
            soup = BeautifulSoup(res.text, "html.parser")

            year, month = m_year, m_month
            header_el = soup.find("span", class_="header-title-date")
            if header_el:
                m = re.search(r'(\d{4})年\s*(\d{1,2})月', header_el.get_text())
                if m:
                    year = int(m.group(1))
                    month = int(m.group(2))

            month_items = []
            for dd in soup.find_all("dd", class_="day"):
                num_el = dd.find("span", class_="number")
                if not num_el:
                    continue
                day_text = num_el.get_text(strip=True)
                if not day_text.isdigit():
                    continue
                try:
                    event_date = datetime.date(year, month, int(day_text))
                except ValueError:
                    continue

                for ttl_div in dd.find_all("div", class_="event-ttl"):
                    link_el = ttl_div.find("a", href=True)
                    if not link_el:
                        continue
                    href = link_el.get("href", "").strip()
                    title = link_el.get_text(strip=True) or "無題のセミナー"
                    month_items.append({
                        "href": href,
                        "title": title,
                        "event_date": event_date,
                        "place": _infer_aws_place(title)
                    })
            return month_items
        except Exception as e:
            st.error(f"AWSカレンダースクレイピングエラー（{m_year}年{m_month}月）: {e}")
            return []

    with ThreadPoolExecutor(max_workers=max(1, min(max_pages, 6))) as executor:
        results = executor.map(fetch_calendar_month, target_months)
        for res_items in results:
            raw_items.extend(res_items)

    # 2. Fetch details in parallel if requested
    detail_times = {}
    if fetch_details and raw_items:
        urls_to_scrape = list(set(item["href"] for item in raw_items if item["href"]))

        def worker(url):
            try:
                st_time, en_time = scrape_aws_detail_time(url)
                return url, (st_time, en_time)
            except Exception:
                return url, (None, None)

        with ThreadPoolExecutor(max_workers=24) as executor:
            results = executor.map(worker, urls_to_scrape)
            for url, times in results:
                detail_times[url] = times

    # 3. Build events list (deduplicated by href + date)
    seen = set()
    for item in raw_items:
        href = item["href"]
        event_date = item["event_date"]
        date_iso = event_date.isoformat()
        dedup_key = (href, date_iso, item["title"])
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        detail_url = href if href.startswith("http") else AWS_BASE_URL + href
        title = item["title"]
        place = item["place"]

        start_time, end_time = None, None
        if fetch_details and href:
            start_time, end_time = detail_times.get(href, (None, None))

        start_dt = f"{date_iso}T{start_time}:00" if start_time else date_iso
        end_dt = f"{date_iso}T{end_time}:00" if end_time else date_iso
        slug = href.rstrip("/").split("/")[-1] if href else str(abs(hash(title)) % 100000)

        events.append({
            "id": f"aws_{slug}_{date_iso}",
            "title": title,
            "start": start_dt,
            "end": end_dt,
            "allDay": start_time is None,
            "url": detail_url,
            "color": "#1f77b4",  # AWS: Corporate blue
            "place": place,
            "image": "",
            "raw_date": f"{event_date.month}月{event_date.day}日",
            "source": "AWS"
        })
    return events


# ==========================================
# IVP Scraper
# ==========================================
def login_ivp(id_str, password_str):
    """
    Attempts to log in to IVP. Returns a requests.Session object if successful, or None.
    """
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    session.headers.update(headers)
    
    payload = {
        "ivp_ivp_id": id_str,
        "ivp_password": password_str,
        "login": "1"
    }
    
    try:
        # 1. GET request to obtain session cookies and find the actual login page (index.php?return_url=...)
        res_init = session.get(IVP_LOGIN_URL, timeout=15)
        res_init.raise_for_status()
        actual_login_url = res_init.url
        
        # 2. POST login request to the actual login page
        res = session.post(actual_login_url, data=payload, timeout=15)
        res.raise_for_status()
        
        # Check if the login form is still present on the final page
        if 'name="ivp_ivp_id"' in res.text or 'placeholder="Password"' in res.text:
            return None, "IDまたはパスワードが正しくありません。", res.text
            
        return session, None, res.text
    except Exception as e:
        return None, f"IVPログイン通信エラー: {e}", getattr(locals().get('res', None), 'text', None)

def scrape_ivp_schedule(session):
    """
    Scrapes the IVP schedule page using an authenticated session.
    Parses events dynamically based on table elements, calendar labels, and commented-out links.
    Fetches the current month and the next month in parallel.
    """
    events = []
    
    # Calculate 5 months of URLs
    today = datetime.date.today()
    urls = []
    for i in range(5):
        m_year = today.year
        m_month = today.month + i
        while m_month > 12:
            m_month -= 12
            m_year += 1
        ym_str = f"{m_year}-{m_month:02d}"
        if i == 0:
            urls.append((IVP_LOGIN_URL, m_year, m_month))
        else:
            urls.append((f"{IVP_LOGIN_URL}?ym={ym_str}", m_year, m_month))
    
    from concurrent.futures import ThreadPoolExecutor
    
    def fetch_and_parse_ivp(url, default_year, default_month):
        # Create a thread-safe session copy
        thread_session = requests.Session()
        thread_session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, http/1.1) Chrome/120.0.0.0 Safari/537.36"
        })
        thread_session.cookies.update(session.cookies)
        
        try:
            res = thread_session.get(url, timeout=15)
            res.raise_for_status()
            
            # Save the page to local file for debug
            try:
                with open(f"g:\\マイドライブ\\04_名古屋会\\ivp_page_{default_month}.html", "w", encoding="utf-8") as f:
                    f.write(res.text)
            except Exception:
                pass
            
            soup = BeautifulSoup(res.text, "html.parser")
            
            # Parse Year and Month from page context
            year = default_year
            month = default_month
            title_context = soup.find(class_="calendar-year-month")
            if title_context:
                month_match = re.search(r'(\d{4})[年/-](\d{1,2})', title_context.get_text())
                if month_match:
                    year = int(month_match.group(1))
                    month = int(month_match.group(2))
            
            # Diagnostic Log to file
            try:
                with open("g:\\マイドライブ\\04_名古屋会\\debug_ivp_scrape.log", "a", encoding="utf-8") as debug_file:
                    debug_file.write(f"[{datetime.datetime.now().isoformat()}] URL: {url}, Status: {res.status_code}, Length: {len(res.text)}, Default Month: {default_month}, Parsed Year/Month: {year}/{month}\n")
            except Exception:
                pass
                
            page_events = []
            tables = soup.find_all("table")
            for table in tables:
                headers = [th.get_text(strip=True) for th in table.find_all("th")]
                is_calendar = any(h in ["日", "月", "火", "水", "木", "金", "土"] for h in headers) or "calendar" in table.get("class", [])
                
                if is_calendar or len(table.find_all("td")) >= 28:
                    cells = table.find_all("td")
                    for cell in cells:
                        # 1. Look for date number
                        day_elem = cell.find(class_=re.compile("calendar-day-number"))
                        if not day_elem:
                            continue
                        day_text = day_elem.get_text(strip=True)
                        if not day_text.isdigit():
                            continue
                        day_num = int(day_text)
                        
                        # 2. Look for events inside the cell
                        labels = cell.find_all("span", class_=re.compile("calend[ae]r-label"))
                        for label in labels:
                            link_text = label.get_text(strip=True)
                            if not link_text or link_text.isdigit():
                                continue
                                
                            # Try to extract href from commented-out <a> tags
                            href = ""
                            for child in label.children:
                                if isinstance(child, Comment):
                                    match = re.search(r'href=["\']([^"\']+)["\']', child.string)
                                    if match:
                                        href = match.group(1)
                                        break
                                        
                            detail_url = urllib.parse.urljoin(url, href) if href else url
                            
                            color = "#ff7f0e"
                            label_class = "".join(label.get("class", []))
                            if "red" in label_class:
                                color = "#d62728"  # Soft red for main study sessions
                            elif "green" in label_class:
                                color = "#2ca02c"  # Emerald green for rookie programs
                            elif "blue" in label_class:
                                color = "#17becf"  # Soft cyan/blue for archives/recordings
                                
                            try:
                                event_date = datetime.date(year, month, day_num)
                            except ValueError:
                                continue
                                
                            page_events.append({
                                "id": f"ivp_cal_{year}_{month}_{day_num}_{hash(link_text) % 10000}",
                                "title": link_text,
                                "start": event_date.isoformat(),
                                "end": event_date.isoformat(),
                                "allDay": True,
                                "url": detail_url,
                                "color": color,
                                "place": "IVP-WEB (ログイン要)",
                                "source": "IVP",
                                "image": "",
                                "raw_date": f"{month}月{day_num}日"
                            })
            return page_events
        except Exception as e:
            try:
                with open("g:\\マイドライブ\\04_名古屋会\\debug_ivp_scrape.log", "a", encoding="utf-8") as debug_file:
                    debug_file.write(f"[{datetime.datetime.now().isoformat()}] URL: {url} ERROR: {e}\n")
            except Exception:
                pass
            st.error(f"IVPスクレイピングエラー（{url}）: {e}")
            return []

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = executor.map(lambda item: fetch_and_parse_ivp(*item), urls)
        for res_events in results:
            events.extend(res_events)
            
    return events


# ==========================================
# IVP HTML Diagnostic Helper
# ==========================================
def extract_ivp_diagnostic_info(session):
    """
    Extracts high-level structures from the logged-in IVP page for debugging.
    """
    info = {
        "title": "取得失敗",
        "links": [],
        "tables_summary": [],
        "html_snippet": "取得できませんでした"
    }
    try:
        res = session.get(IVP_LOGIN_URL, timeout=15)
        res.raise_for_status()
        
        soup = BeautifulSoup(res.text, "html.parser")
        info["title"] = soup.title.string if soup.title else "タイトルなし"
        
        # Extract links
        for a in soup.find_all("a"):
            text = a.get_text(strip=True)
            href = a.get("href", "")
            if text and href:
                info["links"].append({"text": text, "href": href})
                
        # Extract table structures
        for idx, table in enumerate(soup.find_all("table")):
            rows = table.find_all("tr")
            info["tables_summary"].append({
                "index": idx,
                "class": table.get("class", []),
                "rows_count": len(rows),
                "preview_text": table.get_text()[:200].strip() + "..."
            })
            
        # Get raw snippet
        info["html_snippet"] = res.text[:20000] # Limit to 20k chars
    except Exception as e:
        info["html_snippet"] = f"エラーが発生しました: {e}"
        
    return info

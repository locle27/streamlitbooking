"""
🏨 HOTEL ROOM MANAGEMENT SYSTEM
=====================================
Hệ thống quản lý phòng khách sạn hiện đại với giao diện thân thiện

INSTALLATION REQUIREMENTS:
pip install streamlit pandas numpy plotly openpyxl xlrd pypdf2 beautifulsoup4 Pillow pytesseract python-dateutil google-generativeai toml

Author: Optimized Version (Reviewed and Enhanced by Gemini)
Version: 3.2.6 (Final GSheet Integration for Messages)
"""

import streamlit as st
import pandas as pd
import numpy as np
import datetime
import plotly.graph_objects as go
import plotly.express as px
import io
import calendar
from datetime import timedelta
import re
import xlrd # Cần thiết cho file .xls cũ
import openpyxl # Cần thiết cho file .xlsx hiện đại
import csv
from typing import Dict, List, Optional, Tuple, Any
import asyncio # Added for running async Telegram function
import base64
import os # Import the os library
import streamlit.components.v1 as components # Import for custom components

# Google Sheets API imports
import gspread
from google.oauth2.service_account import Credentials

import telegram # Added for Telegram bot functionality

# --- New imports for Image Processing ---
from PIL import Image
import pytesseract
from dateutil import parser as date_parser
# --- End New imports ---

import json
import google.generativeai as genai
import toml # Import the toml library


# --- TELEGRAM BOT CONFIGURATION ---
TELEGRAM_BOT_TOKEN = "7998311603:AAGFoxqsbBe5nhocp9Tco635o9tbdT4DTDI" # User provided test token
TELEGRAM_CHAT_ID = "1189687917" # Corrected Chat ID based on user's getUpdates output

# --- TELEGRAM BOT FUNCTION ---
async def send_telegram_message(bot_token: str, chat_id: str, message: str) -> bool:
    try:
        bot = telegram.Bot(token=bot_token)
        await bot.send_message(chat_id=chat_id, text=message)
        print(f"Telegram message sent to chat ID {chat_id[:4]}****.")
        return True
    except telegram.error.TelegramError as e:
        print(f"TelegramError sending message: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error sending Telegram message: {e}")
        return False

async def send_daily_status_telegram():
    today_dt = datetime.date.today()
    message_parts = [f"📢 Cập nhật Khách sạn - {today_dt.strftime('%d/%m/%Y')} 📢\n"]
    active_bookings_df = st.session_state.get('active_bookings')
    if active_bookings_df is None or active_bookings_df.empty:
        message_parts.append("Không có dữ liệu đặt phòng để tạo báo cáo.")
    else:
        overall_info = get_overall_calendar_day_info(today_dt, active_bookings_df, TOTAL_HOTEL_CAPACITY)
        message_parts.append("🏨 Tình trạng Phòng Tổng quan:")
        message_parts.append(f"- Tổng số phòng có khách: {overall_info['occupied_units']} / {TOTAL_HOTEL_CAPACITY}")
        message_parts.append(f"- Phòng trống: {overall_info['available_units']}\n")
        daily_activity = get_daily_activity(today_dt, active_bookings_df)
        message_parts.append("➡️ Khách Check-in Hôm Nay:")
        if daily_activity['check_in']:
            for guest_ci in daily_activity['check_in']:
                message_parts.append(f"- {guest_ci.get('name', 'N/A')} ({guest_ci.get('room_type', 'N/A')}) - Mã ĐP: {guest_ci.get('booking_id','N/A')}")
        else:
            message_parts.append("Không có khách check-in hôm nay.")
        message_parts.append("")
        message_parts.append("⬅️ Khách Check-out Hôm Nay:")
        if daily_activity['check_out']:
            for guest_co in daily_activity['check_out']:
                message_parts.append(f"- {guest_co.get('name', 'N/A')} ({guest_co.get('room_type', 'N/A')}) - Mã ĐP: {guest_co.get('booking_id','N/A')}")
        else:
            message_parts.append("Không có khách check-out hôm nay.")
    full_message = "\n".join(message_parts)
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        success = await send_telegram_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, full_message)
        if success:
            st.sidebar.success("Đã gửi cập nhật hàng ngày qua Telegram!")
    else:
        st.sidebar.warning("Thiếu Token hoặc Chat ID của Telegram để gửi tin nhắn.")

async def send_room_type_details_telegram():
    today_dt = datetime.date.today()
    message_parts = [f"🏡 Chi Tiết Tình Trạng Loại Phòng - {today_dt.strftime('%d/%m/%Y')} 🏡\n"]
    active_bookings_df = st.session_state.get('active_bookings')
    all_room_types_list = st.session_state.get('room_types', [])
    if active_bookings_df is None or active_bookings_df.empty or not all_room_types_list:
        message_parts.append("Không có dữ liệu đặt phòng hoặc loại phòng để tạo báo cáo chi tiết.")
    else:
        availability_per_type = get_room_availability(today_dt, active_bookings_df, all_room_types_list, ROOM_UNIT_PER_ROOM_TYPE)
        if not availability_per_type:
            message_parts.append("Không thể lấy thông tin phòng trống chi tiết.")
        else:
            for room_type, available_units in availability_per_type.items():
                total_units_for_type = ROOM_UNIT_PER_ROOM_TYPE
                message_parts.append(f"- {room_type}: {available_units}/{total_units_for_type} trống")
    full_message = "\n".join(message_parts)
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        success = await send_telegram_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, full_message)
        if success:
            st.sidebar.success("Đã gửi chi tiết loại phòng qua Telegram!")
    else:
        st.sidebar.warning("Thiếu Token hoặc Chat ID của Telegram để gửi chi tiết loại phòng.")

# Hằng số toàn cục
ROOM_UNIT_PER_ROOM_TYPE = 4
TOTAL_HOTEL_CAPACITY = 4

# Định nghĩa các cột
REQUIRED_APP_COLS_BASE = [
    'Tên chỗ nghỉ', 'Vị trí', 'Tên người đặt', 'Thành viên Genius',
    'Ngày đến', 'Ngày đi', 'Được đặt vào',
    'Tình trạng', 'Tổng thanh toán', 'Hoa hồng', 'Tiền tệ', 'Số đặt phòng',
    'Check-in Date', 'Check-out Date', 'Booking Date', 'Stay Duration'
]
REQUIRED_APP_COLS_DERIVED = ['Giá mỗi đêm']
ALL_REQUIRED_COLS = REQUIRED_APP_COLS_BASE + REQUIRED_APP_COLS_DERIVED + ['Người thu tiền']

# Kiểm tra thư viện tùy chọn
try:
    from PyPDF2 import PdfReader
    PYPDF2_AVAILABLE = True
except ImportError:
    PYPDF2_AVAILABLE = False
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

# Cấu hình trang
st.set_page_config(
    page_title="🏨 Hotel Management Pro",
    page_icon="🏨",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': 'https://www.example.com/help',
        'Report a bug': "https://www.example.com/bugs",
        'About': "# Hotel Management System v3.2.6\nĐã tích hợp Google Sheets cho Mẫu tin nhắn."
    }
)

# CSS tùy chỉnh
st.markdown("""
<style>
    :root {
        --primary-color: #1f77b4; --secondary-color: #ff7f0e; --success-color: #2ca02c;
        --warning-color: #ffbb00; --danger-color: #d62728; --info-color: #17a2b8;
        --light-bg: #f8f9fa; --dark-bg: #343a40;
    }
    .css-1d391kg { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
    .metric-card { background: white; padding: 1.5rem; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); border-left: 5px solid var(--primary-color); margin-bottom: 1rem; transition: transform 0.2s ease, box-shadow 0.2s ease; }
    .metric-card:hover { transform: translateY(-3px); box-shadow: 0 4px 20px rgba(0,0,0,0.15); }
    .stButton > button { border-radius: 20px; border: none; padding: 0.6rem 1.2rem; font-weight: 600; transition: all 0.3s ease; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
    .stButton > button:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.2); }
    .calendar-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 5px; text-align: center; font-family: 'Segoe UI', sans-serif; } .day-header { font-weight: bold; padding: 8px 0; background-color: #e9ecef; color: #495057; border-radius: 5px; font-size: 0.9em; } .day-cell { border: 1px solid #dee2e6; padding: 8px 2px; min-height: 75px; display: flex; flex-direction: column; justify-content: space-between; align-items: center; border-radius: 5px; cursor: pointer; transition: background-color 0.2s, box-shadow 0.2s ease; position: relative; background-color: #fff; } .day-cell:hover { background-color: #f8f9fa; box-shadow: 0 0 5px rgba(0,0,0,0.1); } .day-number { font-size: 1.1em; font-weight: bold; margin-bottom: 3px; color: #343a40; } .day-status { font-size: 0.75em; color: #6c757d; padding: 0 2px; word-break: break-word; } .dot-indicator { font-size: 1.8em; line-height: 0.5; margin-top: -2px; margin-bottom: 2px; } .dot-green { color: var(--success-color); } .dot-orange { color: var(--warning-color); } .day-disabled { color: #adb5bd; background-color: #f1f3f5; cursor: not-allowed; } .day-today { border: 2px solid var(--primary-color); background-color: #e7f3ff; } .day-selected { background-color: #cfe2ff; border: 2px solid #0a58ca; } .guest-separator { border-bottom: 1px dashed #ced4da; margin: 4px 0; width: 90%; align-self: center; }
</style>
""", unsafe_allow_html=True)

# --- HÀM HỖ TRỢ ---
def parse_app_standard_date(date_input: Any) -> Optional[datetime.date]:
    if pd.isna(date_input): return None
    if isinstance(date_input, datetime.datetime): return date_input.date()
    if isinstance(date_input, datetime.date): return date_input
    if isinstance(date_input, pd.Timestamp): return date_input.date()
    date_str = str(date_input).strip().lower()
    try:
        if re.match(r"ngày\s*\d{1,2}\s*tháng\s*\d{1,2}\s*năm\s*\d{4}", date_str):
            m = re.search(r"ngày\s*(\d{1,2})\s*tháng\s*(\d{1,2})\s*năm\s*(\d{4})", date_str)
            if m: return datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        parsed_date = pd.to_datetime(date_str, errors='coerce', dayfirst=True).date()
        if parsed_date: return parsed_date
        parsed_date = pd.to_datetime(date_str, errors='coerce', dayfirst=False).date()
        if parsed_date: return parsed_date
    except Exception: pass
    return None

def convert_display_date_to_app_format(display_date_input: Any) -> Optional[str]:
    if pd.isna(display_date_input): return None
    if isinstance(display_date_input, (datetime.datetime, datetime.date, pd.Timestamp)):
        return f"ngày {display_date_input.day} tháng {display_date_input.month} năm {display_date_input.year}"
    cleaned_date_str = str(display_date_input).replace(',', '').strip().lower()
    m_vietnamese = re.search(r"(\d{1,2})\s*tháng\s*(\d{1,2})\s*(\d{4})", cleaned_date_str)
    if m_vietnamese:
        return f"ngày {m_vietnamese.group(1)} tháng {m_vietnamese.group(2)} năm {m_vietnamese.group(3)}"
    try:
        parsed = pd.to_datetime(cleaned_date_str, errors='coerce', dayfirst=True)
        if pd.notna(parsed): return f"ngày {parsed.day} tháng {parsed.month} năm {parsed.year}"
        parsed = pd.to_datetime(cleaned_date_str, errors='coerce', dayfirst=False)
        if pd.notna(parsed): return f"ngày {parsed.day} tháng {parsed.month} năm {parsed.year}"
    except Exception: pass
    return None

def clean_currency_value(value_input: Any) -> float:
    if pd.isna(value_input): return 0.0
    cleaned_str = str(value_input).strip()
    cleaned_str = re.sub(r'(?i)VND\s*', '', cleaned_str)
    cleaned_str = re.sub(r'[^\d,.-]', '', cleaned_str)
    if not cleaned_str: return 0.0
    has_dot, has_comma = '.' in cleaned_str, ',' in cleaned_str
    if has_dot and has_comma:
        last_dot_pos, last_comma_pos = cleaned_str.rfind('.'), cleaned_str.rfind(',')
        if last_comma_pos > last_dot_pos:
            cleaned_str = cleaned_str.replace('.', '').replace(',', '.')
        else:
            cleaned_str = cleaned_str.replace(',', '')
    elif has_comma:
        if cleaned_str.count(',') > 1 or (cleaned_str.count(',') == 1 and len(cleaned_str.split(',')[-1]) == 3 and len(cleaned_str.split(',')[0]) > 0):
            cleaned_str = cleaned_str.replace(',', '')
        else: cleaned_str = cleaned_str.replace(',', '.')
    elif has_dot:
        if cleaned_str.count('.') > 1 or (cleaned_str.count('.') == 1 and len(cleaned_str.split('.')[-1]) == 3 and len(cleaned_str.split('.')[0]) > 0):
            cleaned_str = cleaned_str.replace('.', '')
    numeric_val = pd.to_numeric(cleaned_str, errors='coerce')
    return numeric_val if pd.notna(numeric_val) else 0.0

def get_cleaned_room_types(df_source: Optional[pd.DataFrame]) -> List[str]:
    if df_source is None or df_source.empty or 'Tên chỗ nghỉ' not in df_source.columns:
        return []
    try:
        unique_values = df_source['Tên chỗ nghỉ'].dropna().unique()
    except Exception:
        return []
    cleaned_types = []
    seen_types = set()
    for val in unique_values:
        s_val = str(val).strip()
        if s_val and s_val not in seen_types:
            cleaned_types.append(s_val)
            seen_types.add(s_val)
    return sorted(cleaned_types)

# --- SỬA LỖI: Sử dụng credentials từ st.secrets thay vì đường dẫn tệp ---
def import_from_gsheet(sheet_id, gcp_creds_dict, worksheet_name=None):
    """
    Imports data from a Google Sheet using service account credentials
    provided as a dictionary (from st.secrets).
    """
    scope = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive',
    ]
    creds = Credentials.from_service_account_info(gcp_creds_dict, scopes=scope)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(sheet_id)
    if worksheet_name:
        worksheet = sh.worksheet(worksheet_name)
    else:
        worksheet = sh.sheet1
    data = worksheet.get_all_values()
    if not data or len(data) < 2:
        return pd.DataFrame()
    df = pd.DataFrame(data[1:], columns=data[0])
    return df

# --- SỬA LỖI: Sử dụng credentials từ st.secrets thay vì đường dẫn tệp ---
def upload_to_gsheet(df, sheet_id, gcp_creds_dict, worksheet_name=None):
    """
    Uploads a DataFrame to a Google Sheet using service account credentials
    provided as a dictionary (from st.secrets).
    """
    scope = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive',
    ]
    creds = Credentials.from_service_account_info(gcp_creds_dict, scopes=scope)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(sheet_id)
    if worksheet_name:
        try:
            worksheet = sh.worksheet(worksheet_name)
        except gspread.WorksheetNotFound:
            worksheet = sh.add_worksheet(title=worksheet_name, rows="100", cols="20")
    else:
        worksheet = sh.sheet1
    worksheet.clear()
    df_str = df.astype(str)
    worksheet.update([df_str.columns.values.tolist()] + df_str.values.tolist())
    return sh.url

@st.cache_data
def load_data_from_file(uploaded_file_obj) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    filename = uploaded_file_obj.name
    df_loaded = pd.DataFrame()
    try:
        if filename.endswith(('.xls', '.xlsx')):
            st.info(f"Đang xử lý file Excel: {filename}...")
            engine = 'xlrd' if filename.endswith('.xls') else 'openpyxl'
            df_loaded = pd.read_excel(uploaded_file_obj, engine=engine)
            excel_to_app_map = {
                'Ngày đến': 'Ngày đến_str_original', 'Ngày đi': 'Ngày đi_str_original',
                'Được đặt vào': 'Được đặt vào_str_original', 'Tên chỗ nghỉ': 'Tên chỗ nghỉ',
                'Vị trí': 'Vị trí', 'Tên người đặt': 'Tên người đặt',
                'Thành viên Genius': 'Thành viên Genius', 'Tình trạng': 'Tình trạng',
                'Tổng thanh toán': 'Tổng thanh toán', 'Hoa hồng': 'Hoa hồng',
                'Tiền tệ': 'Tiền tệ', 'Số đặt phòng': 'Số đặt phòng'
            }
            df_loaded = df_loaded.rename(columns={k: v for k, v in excel_to_app_map.items() if k in df_loaded.columns})
            if 'Ngày đến_str_original' in df_loaded.columns:
                df_loaded['Check-in Date'] = df_loaded['Ngày đến_str_original'].apply(parse_app_standard_date)
            if 'Ngày đi_str_original' in df_loaded.columns:
                df_loaded['Check-out Date'] = df_loaded['Ngày đi_str_original'].apply(parse_app_standard_date)
            if 'Được đặt vào_str_original' in df_loaded.columns:
                df_loaded['Booking Date'] = df_loaded['Được đặt vào_str_original'].apply(parse_app_standard_date)
        elif filename.endswith('.pdf'):
            st.info(f"Đang xử lý file PDF: {filename}...")
            if not PYPDF2_AVAILABLE:
                st.error("Không thể xử lý file PDF do thiếu thư viện PyPDF2. Vui lòng cài đặt: pip install pypdf2")
                return None, None
            st.warning("Chức năng xử lý file PDF đang trong giai đoạn thử nghiệm.")
            reader = PdfReader(uploaded_file_obj)
            text_data = ""
            for page_num, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text: text_data += page_text + "\n"
                else: st.warning(f"Không thể trích xuất văn bản từ trang {page_num + 1} của file PDF.")
            if not text_data.strip():
                st.error("File PDF không chứa văn bản hoặc không thể trích xuất văn bản.")
                return None, None
            lines = text_data.splitlines()
            parsed_rows = []
            pdf_headers_assumed_order = [
                "ID chỗ nghỉ", "Tên chỗ nghỉ", "Tên khách", "Nhận phòng", "Ngày đi",
                "Tình trạng", "Tổng thanh toán", "Hoa hồng", "Số đặt phòng", "Được đặt vào"
            ]
            for line in lines:
                cleaned_line = line.replace('\r', '').strip()
                if cleaned_line.startswith('"') and cleaned_line.count('","') >= (len(pdf_headers_assumed_order) - 5):
                    try:
                        csv_reader_obj = csv.reader(io.StringIO(cleaned_line))
                        fields = next(csv_reader_obj)
                        if len(fields) >= (len(pdf_headers_assumed_order) - 3) and len(fields) <= len(pdf_headers_assumed_order) + 2:
                            processed_fields = [field.replace('\n', ' ').strip() for field in fields]
                            row_dict = {header: (processed_fields[i] if i < len(processed_fields) else None)
                                        for i, header in enumerate(pdf_headers_assumed_order)}
                            parsed_rows.append(row_dict)
                    except csv.Error:
                        st.caption(f"Bỏ qua dòng không hợp lệ trong PDF: {cleaned_line[:50]}...")
                        continue
            if not parsed_rows:
                st.error("Không trích xuất được dữ liệu có cấu trúc từ file PDF.")
                return None, None
            df_loaded = pd.DataFrame(parsed_rows)
            if 'Nhận phòng' in df_loaded.columns: df_loaded['Ngày đến_str_original'] = df_loaded['Nhận phòng'].apply(convert_display_date_to_app_format)
            if 'Ngày đi' in df_loaded.columns: df_loaded['Ngày đi_str_original'] = df_loaded['Ngày đi'].apply(convert_display_date_to_app_format)
            if 'Được đặt vào' in df_loaded.columns: df_loaded['Được đặt vào_str_original'] = df_loaded['Được đặt vào'].apply(convert_display_date_to_app_format)
            if 'Ngày đến_str_original' in df_loaded.columns: df_loaded['Check-in Date'] = df_loaded['Ngày đến_str_original'].apply(parse_app_standard_date)
            if 'Ngày đi_str_original' in df_loaded.columns: df_loaded['Check-out Date'] = df_loaded['Ngày đi_str_original'].apply(parse_app_standard_date)
            if 'Được đặt vào_str_original' in df_loaded.columns: df_loaded['Booking Date'] = df_loaded['Được đặt vào_str_original'].apply(parse_app_standard_date)
            if "Tên khách" in df_loaded.columns:
                df_loaded["Tên người đặt"] = df_loaded["Tên khách"].apply(lambda x: str(x).split("Genius")[0].replace("1 khách", "").replace("2 khách", "").replace("2 người lớn","").strip() if pd.notna(x) else "N/A")
                df_loaded["Thành viên Genius"] = df_loaded["Tên khách"].apply(lambda x: "Có" if pd.notna(x) and "Genius" in str(x) else "Không")
            if "Vị trí" not in df_loaded.columns: df_loaded["Vị trí"] = "N/A (từ PDF)"
            if "Tiền tệ" not in df_loaded.columns: df_loaded["Tiền tệ"] = "VND"
        elif filename.endswith('.html'):
            st.info(f"Đang xử lý file HTML: {filename}...")
            if not BS4_AVAILABLE:
                st.error("Không thể xử lý file HTML do thiếu thư viện BeautifulSoup4.")
                return None, None
            
            soup = BeautifulSoup(uploaded_file_obj.read(), 'html.parser')
            parsed_rows_html = []
            
            table_format1 = soup.find('table', class_='cdd0659f86')
            if table_format1:
                st.info("Đang phân tích HTML theo định dạng 1 (class 'cdd0659f86').")
                table_to_parse = table_format1
                
                headers_from_html = []
                header_row_element = table_to_parse.find('thead')
                if header_row_element: header_row_element = header_row_element.find('tr')
                if not header_row_element:
                    tbody_for_header = table_to_parse.find('tbody')
                    if tbody_for_header: header_row_element = tbody_for_header.find('tr')
                if not header_row_element:
                    header_row_element = table_to_parse.find('tr')
                if header_row_element:
                    headers_from_html = [th.get_text(separator=" ", strip=True) for th in header_row_element.find_all(['th', 'td'])]

                body = table_to_parse.find('tbody')
                if not body:
                    all_rows_in_table = table_to_parse.find_all('tr')
                    if header_row_element and all_rows_in_table and all_rows_in_table[0] == header_row_element:
                        body_rows_elements = all_rows_in_table[1:]
                    else:
                        body_rows_elements = all_rows_in_table
                    if not body_rows_elements:
                        st.error("Định dạng 1: Không tìm thấy dòng dữ liệu nào trong bảng HTML.")
                        return None, None
                else:
                    body_rows_elements = body.find_all('tr')

                for row_idx, row in enumerate(body_rows_elements):
                    row_data = {}
                    guest_name_parts = []
                    cells = row.find_all(['td', 'th'])
                    for i, cell in enumerate(cells):
                        heading_text = headers_from_html[i] if i < len(headers_from_html) else None
                        if not heading_text: heading_text = cell.get('data-heading', f"Cột {i+1}")
                        
                        cell_text_content = cell.get_text(separator="\\n", strip=True)
                        cell_lines = [line.strip() for line in cell_text_content.split('\\n') if line.strip()]

                        if heading_text == "Tên khách":
                            for line_part in cell_lines:
                                if "khách" in line_part.lower() or "người lớn" in line_part.lower() or "trẻ em" in line_part.lower():
                                    if "Genius" in line_part:
                                         row_data["Thành viên Genius"] = "Có"
                                         line_part = line_part.replace("Genius", "").strip()
                                else:
                                    guest_name_parts.append(line_part)
                            if guest_name_parts:
                                row_data["Tên người đặt"] = " ".join(guest_name_parts)
                                guest_name_parts = []
                            if "Thành viên Genius" not in row_data:
                                genius_svg = cell.find('svg', alt='Genius')
                                if genius_svg or ("Genius" in cell_text_content and "Tên người đặt" in row_data and "Genius" in row_data["Tên người đặt"]):
                                     row_data["Thành viên Genius"] = "Có"
                                     if "Tên người đặt" in row_data:
                                         row_data["Tên người đặt"] = row_data["Tên người đặt"].replace("Genius","").strip()
                                else: row_data["Thành viên Genius"] = "Không"
                        elif heading_text == "Phòng":
                            row_data["Tên chỗ nghỉ"] = cell_lines[0] if cell_lines else "N/A"
                        elif heading_text == "Giá": 
                            row_data["Tổng thanh toán"] = cell_lines[0] if cell_lines else "N/A"
                        elif heading_text == "Mã số đặt phòng": 
                            row_data["Số đặt phòng"] = cell_lines[0] if cell_lines else "N/A"
                        elif heading_text and cell_lines:
                            if heading_text == "Nhận phòng": row_data["Ngày đến_str_original"] = cell_lines[0]
                            elif heading_text == "Ngày đi": row_data["Ngày đi_str_original"] = cell_lines[0]
                            elif heading_text == "Được đặt vào": row_data["Được đặt vào_str_original"] = cell_lines[0]
                            elif heading_text in ["ID chỗ nghỉ", "Vị trí", "Tình trạng", "Hoa hồng", "Số đặt phòng", "Tổng thanh toán"]:
                                 row_data[heading_text] = cell_lines[0]
                    if row_data: parsed_rows_html.append(row_data)

            else:
                table_format2_candidate = None
                potential_tables = soup.find_all('table')
                for pt_check in potential_tables:
                    if pt_check.find('tr', class_='bui-table__row') and pt_check.find(['th', 'td'], attrs={'data-heading': True}):
                        table_format2_candidate = pt_check
                        break
                
                if table_format2_candidate:
                    st.info("Đang phân tích HTML theo định dạng 2 ('bui-table__row' và 'data-heading').")
                    table_to_parse = table_format2_candidate
                    body_rows_elements = table_to_parse.find_all('tr', class_='bui-table__row')
                    if not body_rows_elements : body_rows_elements = table_to_parse.find_all('tr')

                    for row_element in body_rows_elements:
                        current_row_data = {}
                        cells_in_row = row_element.find_all(['th', 'td'], recursive=False)
                        for cell_element in cells_in_row:
                            data_heading_attr = cell_element.get('data-heading')
                            if not data_heading_attr: continue
                            
                            cell_text_val = ""
                            anchor_tag = cell_element.find('a')
                            span_in_cell = cell_element.find('span')
                            
                            if data_heading_attr == "Mã số đặt phòng" and anchor_tag and anchor_tag.find('span'):
                                cell_text_val = anchor_tag.find('span').get_text(strip=True)
                            elif data_heading_attr == "Tên khách" and anchor_tag and anchor_tag.find('span'):
                                cell_text_val = anchor_tag.find('span').get_text(strip=True)
                            elif span_in_cell:
                                cell_text_val = span_in_cell.get_text(strip=True)
                            else:
                                cell_text_val = cell_element.get_text(strip=True)
                            cell_text_val = " ".join(cell_text_val.split())

                            if data_heading_attr == "Tên khách":
                                current_row_data["Tên người đặt"] = cell_text_val
                                current_row_data["Thành viên Genius"] = "Có" if "Genius" in cell_element.get_text(separator=" ", strip=True).lower() else "Không"
                            elif data_heading_attr == "Phòng":
                                current_row_data["Tên chỗ nghỉ"] = cell_text_val.split('\\n')[0].strip()
                            elif data_heading_attr == "Giá":
                                current_row_data["Tổng thanh toán"] = cell_text_val
                            elif data_heading_attr == "Mã số đặt phòng":
                                current_row_data["Số đặt phòng"] = cell_text_val
                            elif data_heading_attr == "Nhận phòng":
                                current_row_data["Ngày đến_str_original"] = cell_text_val
                            elif data_heading_attr == "Ngày đi":
                                current_row_data["Ngày đi_str_original"] = cell_text_val
                            elif data_heading_attr == "Được đặt vào":
                                current_row_data["Được đặt vào_str_original"] = cell_text_val
                            elif data_heading_attr in ["Tình trạng", "Hoa hồng"]:
                                current_row_data[data_heading_attr] = cell_text_val
                        if current_row_data and any(current_row_data.values()):
                            parsed_rows_html.append(current_row_data)
                
                else:
                    st.warning("Không tìm thấy bảng HTML theo định dạng cụ thể. Thử tìm bảng chung...")
                    generic_table_fallback = soup.find('table')
                    if not generic_table_fallback:
                        st.error("Cũng không tìm thấy thẻ <table> nào trong file HTML.")
                        return None, None
                    else:
                        st.info("Đã tìm thấy một thẻ <table> chung, đang thử phân tích (theo logic định dạng 1).")
                        table_to_parse = generic_table_fallback
                        
                        headers_from_html = []
                        header_row_element = table_to_parse.find('thead')
                        if header_row_element: header_row_element = header_row_element.find('tr')
                        if not header_row_element:
                            tbody_for_header = table_to_parse.find('tbody')
                            if tbody_for_header: header_row_element = tbody_for_header.find('tr')
                        if not header_row_element:
                            header_row_element = table_to_parse.find('tr')
                        if header_row_element:
                            headers_from_html = [th.get_text(separator=" ", strip=True) for th in header_row_element.find_all(['th', 'td'])]

                        body = table_to_parse.find('tbody')
                        if not body:
                            all_rows_in_table = table_to_parse.find_all('tr')
                            if header_row_element and all_rows_in_table and all_rows_in_table[0] == header_row_element:
                                body_rows_elements = all_rows_in_table[1:]
                            else:
                                body_rows_elements = all_rows_in_table
                            if not body_rows_elements:
                                st.error("Fallback: Không tìm thấy dòng dữ liệu nào trong bảng HTML.")
                                return None, None
                        else:
                            body_rows_elements = body.find_all('tr')

                        for row_idx, row in enumerate(body_rows_elements):
                            row_data = {}
                            guest_name_parts = []
                            cells = row.find_all(['td', 'th'])
                            for i, cell in enumerate(cells):
                                heading_text = headers_from_html[i] if i < len(headers_from_html) else None
                                if not heading_text: heading_text = cell.get('data-heading', f"Cột {i+1}")
                                
                                cell_text_content = cell.get_text(separator="\\n", strip=True)
                                cell_lines = [line.strip() for line in cell_text_content.split('\\n') if line.strip()]

                                if heading_text == "Tên khách":
                                    for line_part_generic in cell_lines:
                                        if "khách" in line_part_generic.lower() or "người lớn" in line_part_generic.lower() or "trẻ em" in line_part_generic.lower():
                                            if "Genius" in line_part_generic:
                                                 row_data["Thành viên Genius"] = "Có"
                                                 line_part_generic = line_part_generic.replace("Genius", "").strip()
                                        else:
                                            guest_name_parts.append(line_part_generic)
                                    if guest_name_parts:
                                        row_data["Tên người đặt"] = " ".join(guest_name_parts)
                                        guest_name_parts = []
                                    if "Thành viên Genius" not in row_data:
                                        genius_svg_generic = cell.find('svg', alt='Genius')
                                        if genius_svg_generic or ("Genius" in cell_text_content and "Tên người đặt" in row_data and "Genius" in row_data["Tên người đặt"]):
                                             row_data["Thành viên Genius"] = "Có"
                                             if "Tên người đặt" in row_data:
                                                 row_data["Tên người đặt"] = row_data["Tên người đặt"].replace("Genius","").strip()
                                        else: row_data["Thành viên Genius"] = "Không"
                                elif heading_text == "Phòng":
                                    row_data["Tên chỗ nghỉ"] = cell_lines[0] if cell_lines else "N/A"
                                elif heading_text == "Giá": 
                                    row_data["Tổng thanh toán"] = cell_lines[0] if cell_lines else "N/A"
                                elif heading_text == "Mã số đặt phòng": 
                                    row_data["Số đặt phòng"] = cell_lines[0] if cell_lines else "N/A"
                                elif heading_text and cell_lines:
                                    if heading_text == "Nhận phòng": row_data["Ngày đến_str_original"] = cell_lines[0]
                                    elif heading_text == "Ngày đi": row_data["Ngày đi_str_original"] = cell_lines[0]
                                    elif heading_text == "Được đặt vào": row_data["Được đặt vào_str_original"] = cell_lines[0]
                                    elif heading_text in ["ID chỗ nghỉ", "Vị trí", "Tình trạng", "Hoa hồng", "Số đặt phòng", "Tổng thanh toán"]:
                                         row_data[heading_text] = cell_lines[0]
                            if row_data: parsed_rows_html.append(row_data)
            
            if not parsed_rows_html:
                st.error("Không trích xuất được dòng dữ liệu nào từ bảng HTML sau tất cả các lần thử.")
                return None, None
            df_loaded = pd.DataFrame(parsed_rows_html)
            
            html_common_map_after_parse = {}
            df_loaded = df_loaded.rename(columns={k: v for k, v in html_common_map_after_parse.items() if k in df_loaded.columns})

            if 'Ngày đến_str_original' in df_loaded.columns: df_loaded['Ngày đến_str'] = df_loaded['Ngày đến_str_original'].apply(convert_display_date_to_app_format)
            if 'Ngày đi_str_original' in df_loaded.columns: df_loaded['Ngày đi_str'] = df_loaded['Ngày đi_str_original'].apply(convert_display_date_to_app_format)
            if 'Được đặt vào_str_original' in df_loaded.columns: df_loaded['Được đặt vào_str'] = df_loaded['Được đặt vào_str_original'].apply(convert_display_date_to_app_format)
            
            if 'Ngày đến_str' in df_loaded.columns: df_loaded['Check-in Date'] = df_loaded['Ngày đến_str'].apply(parse_app_standard_date)
            if 'Ngày đi_str' in df_loaded.columns: df_loaded['Check-out Date'] = df_loaded['Ngày đi_str'].apply(parse_app_standard_date)
            if 'Được đặt vào_str' in df_loaded.columns: df_loaded['Booking Date'] = df_loaded['Được đặt vào_str'].apply(parse_app_standard_date)
            
            if "Tiền tệ" not in df_loaded.columns: df_loaded["Tiền tệ"] = "VND"
            if "Thành viên Genius" not in df_loaded.columns: df_loaded["Thành viên Genius"] = "Không"

        else:
            st.error(f"Định dạng file '{filename.split('.')[-1]}' không được hỗ trợ.")
            return None, None

        if df_loaded.empty:
            st.error("Không có dữ liệu nào được tải hoặc tất cả các hàng đều trống.")
            return None, None
        df_loaded = df_loaded.dropna(how='all').reset_index(drop=True)
        if df_loaded.empty:
            st.error("Dữ liệu trống sau khi loại bỏ các hàng rỗng.")
            return None, None

        for col_num_common in ["Tổng thanh toán", "Hoa hồng"]:
            if col_num_common in df_loaded.columns:
                 df_loaded[col_num_common] = df_loaded[col_num_common].apply(clean_currency_value)
            else: df_loaded[col_num_common] = 0.0

        cols_to_datetime = ['Check-in Date', 'Check-out Date', 'Booking Date']
        for col_dt in cols_to_datetime:
            if col_dt in df_loaded.columns:
                df_loaded[col_dt] = pd.to_datetime(df_loaded[col_dt], errors='coerce')
            else: df_loaded[col_dt] = pd.NaT

        if not df_loaded.empty and (df_loaded['Check-in Date'].isnull().any() or df_loaded['Check-out Date'].isnull().any()):
            initial_rows = len(df_loaded)
            df_loaded.dropna(subset=['Check-in Date', 'Check-out Date'], inplace=True)
            dropped_rows_count = initial_rows - len(df_loaded)
            if dropped_rows_count > 0:
                st.warning(f"Đã loại bỏ {dropped_rows_count} đặt phòng do ngày check-in hoặc check-out không hợp lệ.")
        if df_loaded.empty:
            st.error("Không còn dữ liệu hợp lệ sau khi loại bỏ các đặt phòng có ngày không hợp lệ.")
            return None, None

        if 'Check-out Date' in df_loaded.columns and 'Check-in Date' in df_loaded.columns:
            df_loaded['Stay Duration'] = (df_loaded['Check-out Date'] - df_loaded['Check-in Date']).dt.days
            df_loaded['Stay Duration'] = df_loaded['Stay Duration'].apply(lambda x: max(0, x) if pd.notna(x) else 0)
        else: df_loaded['Stay Duration'] = 0

        if 'Tổng thanh toán' in df_loaded.columns and 'Stay Duration' in df_loaded.columns:
            df_loaded['Tổng thanh toán'] = pd.to_numeric(df_loaded['Tổng thanh toán'], errors='coerce').fillna(0)
            df_loaded['Giá mỗi đêm'] = np.where(
                (df_loaded['Stay Duration'].notna()) & (df_loaded['Stay Duration'] > 0) & (df_loaded['Tổng thanh toán'].notna()),
                df_loaded['Tổng thanh toán'] / df_loaded['Stay Duration'],
                0.0
            ).round(0)
        else:
            df_loaded['Giá mỗi đêm'] = 0.0


        for original_date_col_name in ['Ngày đến', 'Ngày đi', 'Được đặt vào']:
            source_col_original = f"{original_date_col_name}_str_original"
            source_col_generic = f"{original_date_col_name}_str"
            if original_date_col_name not in df_loaded.columns: df_loaded[original_date_col_name] = pd.NA
            if source_col_original in df_loaded.columns: df_loaded[original_date_col_name] = df_loaded[original_date_col_name].fillna(df_loaded[source_col_original])
            if source_col_generic in df_loaded.columns: df_loaded[original_date_col_name] = df_loaded[original_date_col_name].fillna(df_loaded[source_col_generic])
            if source_col_original in df_loaded.columns: df_loaded.drop(columns=[source_col_original], inplace=True, errors='ignore')
            if source_col_generic in df_loaded.columns: df_loaded.drop(columns=[source_col_generic], inplace=True, errors='ignore')

        for req_col in ALL_REQUIRED_COLS:
            if req_col not in df_loaded.columns:
                if "Date" in req_col and req_col not in ['Ngày đến', 'Ngày đi', 'Được đặt vào']: df_loaded[req_col] = pd.NaT
                elif "Duration" in req_col: df_loaded[req_col] = 0
                elif req_col in ['Tổng thanh toán', 'Hoa hồng', 'Giá mỗi đêm']: df_loaded[req_col] = 0.0
                elif req_col == 'Người thu tiền': df_loaded[req_col] = "N/A"
                else: df_loaded[req_col] = "N/A"

        active_bookings_loaded = df_loaded[df_loaded['Tình trạng'] != 'Đã hủy'].copy() if 'Tình trạng' in df_loaded.columns else pd.DataFrame(columns=ALL_REQUIRED_COLS)
        df_final = df_loaded[[col for col in ALL_REQUIRED_COLS if col in df_loaded.columns]].copy()
        if active_bookings_loaded is not None and not active_bookings_loaded.empty:
            active_bookings_final = active_bookings_loaded[[col for col in ALL_REQUIRED_COLS if col in active_bookings_loaded.columns]].copy()
        else: active_bookings_final = pd.DataFrame(columns=ALL_REQUIRED_COLS)

        st.success(f"Đã xử lý thành công file {filename}. Tìm thấy {len(df_final)} đặt phòng, trong đó {len(active_bookings_final)} đang hoạt động.")
        return df_final, active_bookings_final
    except FileNotFoundError: st.error(f"Lỗi: File {filename} không tìm thấy."); return None, None
    except xlrd.XLRDError: st.error(f"Lỗi khi đọc file Excel cũ (.xls): {filename}."); return None, None
    except openpyxl.utils.exceptions.InvalidFileException: st.error(f"Lỗi khi đọc file Excel (.xlsx): {filename}."); return None, None
    except Exception as e: st.error(f"Lỗi nghiêm trọng xảy ra khi xử lý file {filename}: {e}"); import traceback; st.error(f"Chi tiết lỗi: {traceback.format_exc()}"); return None, None

def create_demo_data() -> Tuple[pd.DataFrame, pd.DataFrame]:
    st.info("Đang tạo dữ liệu demo...")
    demo_data = {
        'Tên chỗ nghỉ': ['Home in Old Quarter - Night market', 'Old Quarter Home- Kitchen & Balcony', 'Home in Old Quarter - Night market', 'Old Quarter Home- Kitchen & Balcony', 'Riverside Boutique Apartment'],
        'Vị trí': ['Phố Cổ Hà Nội, Hoàn Kiếm, Vietnam', '118 Phố Hàng Bạc, Hoàn Kiếm, Vietnam', 'Phố Cổ Hà Nội, Hoàn Kiếm, Vietnam', '118 Phố Hàng Bạc, Hoàn Kiếm, Vietnam', 'Quận 2, TP. Hồ Chí Minh, Vietnam'],
        'Tên người đặt': ['Demo User Alpha', 'Demo User Beta', 'Demo User Alpha', 'Demo User Gamma', 'Demo User Delta'],
        'Thành viên Genius': ['Không', 'Có', 'Không', 'Có', 'Không'],
        'Ngày đến': ['ngày 22 tháng 5 năm 2025', 'ngày 23 tháng 5 năm 2025', 'ngày 25 tháng 5 năm 2025', 'ngày 26 tháng 5 năm 2025', 'ngày 1 tháng 6 năm 2025'],
        'Ngày đi': ['ngày 23 tháng 5 năm 2025', 'ngày 24 tháng 5 năm 2025', 'ngày 26 tháng 5 năm 2025', 'ngày 28 tháng 5 năm 2025', 'ngày 5 tháng 6 năm 2025'],
        'Được đặt vào': ['ngày 20 tháng 5 năm 2025', 'ngày 21 tháng 5 năm 2025', 'ngày 22 tháng 5 năm 2025', 'ngày 23 tháng 5 năm 2025', 'ngày 25 tháng 5 năm 2025'],
        'Tình trạng': ['OK', 'OK', 'Đã hủy', 'OK', 'OK'],
        'Tổng thanh toán': [300000, 450000, 200000, 600000, 1200000],
        'Hoa hồng': [60000, 90000, 40000, 120000, 240000],
        'Tiền tệ': ['VND', 'VND', 'VND', 'VND', 'VND'],
        'Số đặt phòng': [f'DEMO{i+1:09d}' for i in range(5)],
        'Người thu tiền': ['LOC LE', 'THAO LE', 'LOC LE', 'THAO LE', 'LOC LE']
    }
    df_demo = pd.DataFrame(demo_data)
    df_demo['Check-in Date'] = df_demo['Ngày đến'].apply(parse_app_standard_date)
    df_demo['Check-out Date'] = df_demo['Ngày đi'].apply(parse_app_standard_date)
    df_demo['Booking Date'] = df_demo['Được đặt vào'].apply(parse_app_standard_date)
    df_demo['Check-in Date'] = pd.to_datetime(df_demo['Check-in Date'], errors='coerce')
    df_demo['Check-out Date'] = pd.to_datetime(df_demo['Check-out Date'], errors='coerce')
    df_demo['Booking Date'] = pd.to_datetime(df_demo['Booking Date'], errors='coerce')
    df_demo.dropna(subset=['Check-in Date', 'Check-out Date'], inplace=True)
    if not df_demo.empty:
        df_demo['Stay Duration'] = (df_demo['Check-out Date'] - df_demo['Check-in Date']).dt.days
        df_demo['Stay Duration'] = df_demo['Stay Duration'].apply(lambda x: max(0, x) if pd.notna(x) else 0)
    else: df_demo['Stay Duration'] = 0

    if 'Tổng thanh toán' in df_demo.columns and 'Stay Duration' in df_demo.columns:
        df_demo['Tổng thanh toán'] = pd.to_numeric(df_demo['Tổng thanh toán'], errors='coerce').fillna(0)
        df_demo['Giá mỗi đêm'] = np.where(
            (df_demo['Stay Duration'].notna()) & (df_demo['Stay Duration'] > 0) & (df_demo['Tổng thanh toán'].notna()),
            df_demo['Tổng thanh toán'] / df_demo['Stay Duration'],
            0.0
        ).round(0)
    else:
        df_demo['Giá mỗi đêm'] = 0.0

    active_bookings_demo = df_demo[df_demo['Tình trạng'] != 'Đã hủy'].copy()
    return df_demo, active_bookings_demo

def get_room_availability(date_to_check: datetime.date, current_bookings_df: Optional[pd.DataFrame], all_room_types: List[str], rooms_per_type: int = ROOM_UNIT_PER_ROOM_TYPE) -> Dict[str, int]:
    if current_bookings_df is None or current_bookings_df.empty or not all_room_types:
        return {room_type: rooms_per_type for room_type in all_room_types}
    if isinstance(date_to_check, pd.Timestamp): date_to_check_dt = date_to_check.date()
    elif isinstance(date_to_check, datetime.datetime): date_to_check_dt = date_to_check.date()
    elif isinstance(date_to_check, datetime.date): date_to_check_dt = date_to_check
    else: st.error(f"Định dạng ngày không hợp lệ: {date_to_check}"); return {room_type: 0 for room_type in all_room_types}
    availability = {room_type: rooms_per_type for room_type in all_room_types}
    required_date_cols = ['Check-in Date', 'Check-out Date']
    for col in required_date_cols:
        if col not in current_bookings_df.columns or not pd.api.types.is_datetime64_any_dtype(current_bookings_df[col]):
            st.warning(f"Cột ngày '{col}' bị thiếu hoặc không đúng định dạng."); return availability
    active_on_date = current_bookings_df[
        (current_bookings_df['Check-in Date'].dt.date <= date_to_check_dt) &
        (current_bookings_df['Check-out Date'].dt.date > date_to_check_dt) &
        (current_bookings_df['Tình trạng'] != 'Đã hủy')
    ]
    occupied_counts = active_on_date.groupby('Tên chỗ nghỉ').size()
    for room_type_item, occupied_count_val in occupied_counts.items():
        if room_type_item in availability:
            availability[room_type_item] = max(0, rooms_per_type - occupied_count_val)
    return availability

def get_daily_activity(date_to_check: datetime.date, current_bookings_df: Optional[pd.DataFrame]) -> Dict[str, List[Dict]]:
    if current_bookings_df is None or current_bookings_df.empty:
        return {'check_in': [], 'check_out': [], 'occupied': []}
    if isinstance(date_to_check, pd.Timestamp): date_to_check_dt = date_to_check.date()
    elif isinstance(date_to_check, datetime.datetime): date_to_check_dt = date_to_check.date()
    elif isinstance(date_to_check, datetime.date): date_to_check_dt = date_to_check
    else: st.error(f"Định dạng ngày không hợp lệ: {date_to_check}"); return {'check_in': [], 'check_out': [], 'occupied': []}
    result = {'check_in': [], 'check_out': [], 'occupied': []}
    required_date_cols = ['Check-in Date', 'Check-out Date']
    for col in required_date_cols:
        if col not in current_bookings_df.columns or not pd.api.types.is_datetime64_any_dtype(current_bookings_df[col]):
            st.warning(f"Cột ngày '{col}' bị thiếu hoặc không đúng định dạng."); return result
    active_bookings_df_daily = current_bookings_df[current_bookings_df['Tình trạng'] != 'Đã hủy']
    if active_bookings_df_daily.empty: return result
    check_ins_df = active_bookings_df_daily[active_bookings_df_daily['Check-in Date'].dt.date == date_to_check_dt]
    for _, booking in check_ins_df.iterrows():
        result['check_in'].append({'name': booking.get('Tên người đặt', 'N/A'), 'room_type': booking.get('Tên chỗ nghỉ', 'N/A'), 'booking_id': booking.get('Số đặt phòng', 'N/A')})
    check_outs_df = active_bookings_df_daily[active_bookings_df_daily['Check-out Date'].dt.date == date_to_check_dt]
    for _, booking in check_outs_df.iterrows():
        result['check_out'].append({'name': booking.get('Tên người đặt', 'N/A'), 'room_type': booking.get('Tên chỗ nghỉ', 'N/A'), 'booking_id': booking.get('Số đặt phòng', 'N/A')})
    occupied_df = active_bookings_df_daily[
        (active_bookings_df_daily['Check-in Date'].dt.date <= date_to_check_dt) &
        (active_bookings_df_daily['Check-out Date'].dt.date > date_to_check_dt)
    ]
    for _, booking in occupied_df.iterrows():
        result['occupied'].append({
            'name': booking.get('Tên người đặt', 'N/A'), 'room_type': booking.get('Tên chỗ nghỉ', 'N/A'),
            'booking_id': booking.get('Số đặt phòng', 'N/A'),
            'check_in': booking.get('Check-in Date').date() if pd.notnull(booking.get('Check-in Date')) else None,
            'check_out': booking.get('Check-out Date').date() if pd.notnull(booking.get('Check-out Date')) else None,
            'total_payment': booking.get('Tổng thanh toán', 0.0)
        })
    return result

def get_overall_calendar_day_info(date_to_check: datetime.date, current_bookings_df: Optional[pd.DataFrame], hotel_total_capacity: int) -> Dict[str, Any]:
    if current_bookings_df is None or current_bookings_df.empty or hotel_total_capacity == 0:
        return {'occupied_units': 0, 'available_units': hotel_total_capacity, 'guests': [], 'status_text': f"Trống" if hotel_total_capacity > 0 else "N/A", 'color': '#D4EFDF', 'status_indicator_type': 'green_dot' if hotel_total_capacity > 0 else 'error'}
    if isinstance(date_to_check, pd.Timestamp): date_to_check_dt = date_to_check.date()
    elif isinstance(date_to_check, datetime.datetime): date_to_check_dt = date_to_check.date()
    elif isinstance(date_to_check, datetime.date): date_to_check_dt = date_to_check
    else: return {'occupied_units': 0, 'available_units': 0, 'guests': [], 'status_text': "Lỗi ngày", 'color': '#EAECEE', 'status_indicator_type': 'error'}
    required_date_cols = ['Check-in Date', 'Check-out Date']
    for col in required_date_cols:
        if col not in current_bookings_df.columns or not pd.api.types.is_datetime64_any_dtype(current_bookings_df[col]):
            st.warning(f"Cột ngày '{col}' bị thiếu hoặc không đúng định dạng."); return {'occupied_units': 0, 'available_units': hotel_total_capacity, 'guests': [], 'status_text': "Lỗi dữ liệu", 'color': '#EAECEE', 'status_indicator_type': 'error'}
    active_on_date_df = current_bookings_df[
        (current_bookings_df['Check-in Date'].dt.date <= date_to_check_dt) &
        (current_bookings_df['Check-out Date'].dt.date > date_to_check_dt) &
        (current_bookings_df['Tình trạng'] != 'Đã hủy')
    ]
    occupied_units = len(active_on_date_df)
    available_units = max(0, hotel_total_capacity - occupied_units)
    guests_staying_today = active_on_date_df['Tên người đặt'].unique().tolist() if 'Tên người đặt' in active_on_date_df else []
    status_text = ""; color_indicator = ""; status_indicator_type = ""
    if available_units == hotel_total_capacity and hotel_total_capacity > 0: status_text = f"Trống"; status_indicator_type = "green_dot"
    elif available_units > 0: status_text = f"{available_units}/{hotel_total_capacity} trống"; status_indicator_type = "green_dot"
    elif hotel_total_capacity > 0 : status_text = f"Hết phòng"; status_indicator_type = "orange_dash"
    else: status_text = "N/A"; status_indicator_type = "error"
    return {'occupied_units': occupied_units, 'available_units': available_units, 'guests': guests_staying_today, 'status_text': status_text, 'color': color_indicator, 'status_indicator_type': status_indicator_type}

DEFAULT_MESSAGE_TEMPLATE_CONTENT = """
HET PHONG : We sincerely apologize for this inconvenience. Due to an unforeseen issue, the room you booked is no longer available
Thank you for your understanding.
We hope to have the pleasure of welcoming you on your next visit.
Have a pleasant evening

DON PHONG : You're welcome! Please feel free to relax and get some breakfast.
We'll get your room ready and clean for you, and I'll let you know as soon as possible when it's all set

WELCOME :
1. Welcome!
Thanks for your reservation. We look forward to seeing you soon
2. Hello Alejandro,
I've received your reservation for 118 Hang Bac.
Could you please let me know your approximate arrival time for today?
ARRIVAL : When you arrive at 118 Hang Bac, please text me  I will guide you to your room.
EARLY CHECK IN : Hello, I'm so sorry, but the room isn't available right now.
You're welcome to leave your luggage here and use the Wi-Fi.
I'll check again around 12:00 AM and let you know as soon as possible when it's all set

CHECK IN : When you arrive at 118 Hang Bac Street, you will see a souvenir shop at the front.
Please walk into the shop about 10 meters, and you will find a staircase on your right-hand side.
Go up the stairs, then look for your room number.
The door will be unlocked, and the key will be inside the room.
FEED BACK : We hope you had a wonderful stay!
We'd love to hear about your experience – feel free to leave us a review on Booking.com

PARK : Please park your motorbike across the street, but make sure not to block their right-side door.
"""

def parse_message_templates(text_content: str) -> Dict[str, List[Tuple[str, str]]]:
    templates: Dict[str, List[Tuple[str, str]]] = {}
    current_category: Optional[str] = None
    current_label: Optional[str] = None
    current_message_lines: List[str] = []
    cleaned_content = re.sub(r"'", "", text_content)

    def finalize_and_store_message():
        nonlocal current_category, current_label, current_message_lines, templates
        if current_category and current_label and current_message_lines:
            message = "\n".join(current_message_lines).strip()
            if message:
                if current_category not in templates:
                    templates[current_category] = []
                existing_label_index = -1
                for i, (lbl, _) in enumerate(templates[current_category]):
                    if lbl == current_label:
                        existing_label_index = i
                        break
                if existing_label_index != -1:
                    templates[current_category][existing_label_index] = (current_label, message)
                else:
                    templates[current_category].append((current_label, message))
            current_message_lines = []

    for line in cleaned_content.splitlines():
        stripped_line = line.strip()
        main_cat_match = re.match(r'^([A-Z][A-Z\s]*[A-Z]|[A-Z]+)\s*:\s*(.*)', line)
        sub_label_numbered_match = re.match(r'^\s*(\d+\.)\s*(.*)', stripped_line)
        sub_label_named_match = None
        if current_category:
             potential_sub_label_named_match = re.match(r'^\s*([\w\s()]+?)\s*:\s*(.*)', stripped_line)
             if potential_sub_label_named_match:
                 if potential_sub_label_named_match.group(1).strip() != current_category and potential_sub_label_named_match.group(1).strip().isupper() is False:
                     sub_label_named_match = potential_sub_label_named_match
        if main_cat_match:
            potential_cat_name = main_cat_match.group(1).strip()
            if potential_cat_name.isupper():
                finalize_and_store_message()
                current_category = potential_cat_name
                current_label = "DEFAULT"
                message_on_same_line = main_cat_match.group(2).strip()
                if message_on_same_line:
                    current_message_lines.append(message_on_same_line)
            elif current_category and sub_label_named_match is None:
                sub_label_named_match = main_cat_match
        if current_category:
            is_new_sub_label = False
            if sub_label_numbered_match:
                finalize_and_store_message()
                current_label = sub_label_numbered_match.group(1).strip()
                message_on_same_line = sub_label_numbered_match.group(2).strip()
                if message_on_same_line:
                    current_message_lines.append(message_on_same_line)
                is_new_sub_label = True
            elif sub_label_named_match:
                if not (main_cat_match and main_cat_match.group(1).strip().isupper() and main_cat_match.group(1).strip() == sub_label_named_match.group(1).strip()):
                    finalize_and_store_message()
                    current_label = sub_label_named_match.group(1).strip()
                    message_on_same_line = sub_label_named_match.group(2).strip()
                    if message_on_same_line:
                        current_message_lines.append(message_on_same_line)
                    is_new_sub_label = True
            if not is_new_sub_label and main_cat_match is None:
                if stripped_line or current_message_lines:
                    if not current_label and stripped_line:
                        current_label = "DEFAULT"
                    current_message_lines.append(line)
    finalize_and_store_message()
    return templates

def format_templates_to_text(templates_dict: Dict[str, List[Tuple[str, str]]]) -> str:
    output_lines = []
    for category_name in sorted(templates_dict.keys()):
        labeled_messages = templates_dict[category_name]
        default_message_written_on_cat_line = False
        if labeled_messages and labeled_messages[0][0] == "DEFAULT":
            default_msg_text = labeled_messages[0][1]
            msg_lines = default_msg_text.split('\n')
            output_lines.append(f"{category_name} : {msg_lines[0] if msg_lines else ''}")
            if len(msg_lines) > 1:
                output_lines.extend(msg_lines[1:])
            default_message_written_on_cat_line = True
        else:
            output_lines.append(f"{category_name} :")

        for i, (label, msg_text) in enumerate(labeled_messages):
            if label == "DEFAULT" and default_message_written_on_cat_line and i == 0:
                continue
            msg_lines = msg_text.split('\n')
            if not (label == "DEFAULT" and i==0) :
                 if not (default_message_written_on_cat_line and i==0 and label=="DEFAULT"):
                      if not (not default_message_written_on_cat_line and i==0 and label=="DEFAULT" and output_lines and not output_lines[-1].endswith(":")):
                        output_lines.append("")
            if label == "DEFAULT":
                output_lines.extend(msg_lines)
            elif label.endswith('.'):
                output_lines.append(f"{label} {msg_lines[0] if msg_lines else ''}")
                if len(msg_lines) > 1:
                    output_lines.extend(msg_lines[1:])
            else:
                output_lines.append(f"{label} : {msg_lines[0] if msg_lines else ''}")
                if len(msg_lines) > 1:
                    output_lines.extend(msg_lines[1:])
        output_lines.append("")
    return "\n".join(output_lines) if output_lines else ""

@st.dialog("Thông báo")
def show_success_notification_dialog(message):
    st.markdown(f"<h3 style='text-align: center; color: green;'>✅ {message}</h3>", unsafe_allow_html=True)
    st.balloons()
    if st.button("OK", key="success_dialog_ok_button", use_container_width=True):
        st.session_state.show_add_booking_success_dialog = False
        st.rerun()

def extract_booking_info_from_image_content(image_bytes: bytes) -> List[Dict[str, Any]]:
    all_extracted_bookings = []
    try:
        try:
            secrets_path = os.path.join(".streamlit", "secrets.toml")
            with open(secrets_path, "r") as f:
                secrets = toml.load(f)
            api_key = secrets.get("GOOGLE_API_KEY")
            if not api_key:
                raise ValueError("GOOGLE_API_KEY not found in secrets.toml")
            genai.configure(api_key=api_key)
        except (FileNotFoundError, ValueError) as e:
            return [{"errors": [f"Lỗi khi đọc API Key: {e}. Hãy chắc chắn tệp .streamlit/secrets.toml tồn tại và chứa GOOGLE_API_KEY."]}]

        img = Image.open(io.BytesIO(image_bytes))
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = """
            Bạn là một trợ lý nhập liệu chuyên nghiệp cho khách sạn, có nhiệm vụ trích xuất thông tin từ một hình ảnh.
            Hình ảnh này có thể chứa một bảng hoặc danh sách của NHIỀU đặt phòng.

            Nhiệm vụ của bạn:
            1. Quét toàn bộ hình ảnh và xác định từng hàng (mỗi hàng là một đặt phòng riêng biệt).
            2. Với MỖI đặt phòng, hãy trích xuất các thông tin sau.
            3. Trả về kết quả dưới dạng một MẢNG JSON (JSON array), trong đó mỗi phần tử của mảng là một đối tượng JSON đại diện cho một đặt phòng.

            Cấu trúc của mỗi đối tượng JSON trong mảng phải như sau:
            - "guest_name" (string): Họ và tên đầy đủ của khách.
            - "booking_id" (string): Mã số đặt phòng.
            - "is_genius_member" (boolean): True nếu khách là thành viên Genius, ngược lại là false.
            - "check_in_date" (string): Ngày nhận phòng theo định dạng YYYY-MM-DD.
            - "check_out_date" (string): Ngày trả phòng theo định dạng YYYY-MM-DD.
            - "room_type" (string): Tên loại phòng đã đặt.
            - "total_payment" (number): Tổng số tiền thanh toán (chỉ lấy số, loại bỏ ký hiệu tiền tệ và dấu chấm ngăn cách hàng nghìn).
            - "commission" (number): Tiền hoa hồng, nếu có (chỉ lấy số).
            - "currency" (string): Mã tiền tệ (ví dụ: 'VND', 'USD').
            - "num_nights" (number): Tổng số đêm nghỉ.
            - "num_adults" (number): Số lượng người lớn.

            YÊU CẦU CỰC KỲ QUAN TRỌNG:
            - Kết quả cuối cùng PHẢI là một mảng JSON, ví dụ: [ { ...booking1... }, { ...booking2... } ].
            - Chỉ trả về đối tượng JSON thô, không kèm theo bất kỳ văn bản giải thích hay định dạng markdown nào như ```json.
            - Nếu không tìm thấy thông tin cho trường nào của một đặt phòng, hãy đặt giá trị là null.
            - Đảm bảo định dạng ngày tháng phải là YYYY-MM-DD.
        """
        response = model.generate_content([prompt, img], stream=False)
        response.resolve()
        
        try:
            json_text = response.text.strip().replace('```json', '').replace('```', '').strip()
            list_of_bookings_data = json.loads(json_text)

            if isinstance(list_of_bookings_data, dict):
                list_of_bookings_data = [list_of_bookings_data]

            for booking_data in list_of_bookings_data:
                extracted_info = {
                    "guest_name": None, "booking_id": None, "genius_member": "Không",
                    "check_in_date": None, "check_out_date": None, "room_type": None,
                    "total_payment": None, "commission": None, "currency": "VND",
                    "status": "OK", "num_nights": None, "num_adults": None, "errors": []
                }
                
                extracted_info.update({
                    "guest_name": booking_data.get("guest_name"),
                    "booking_id": str(booking_data.get("booking_id")) if booking_data.get("booking_id") else None,
                    "genius_member": "Có" if booking_data.get("is_genius_member") else "Không",
                    "room_type": booking_data.get("room_type"),
                    "total_payment": booking_data.get("total_payment"),
                    "commission": booking_data.get("commission"),
                    "currency": booking_data.get("currency", "VND"),
                    "num_nights": booking_data.get("num_nights"),
                    "num_adults": booking_data.get("num_adults"),
                })

                if booking_data.get("check_in_date"):
                    try:
                        extracted_info["check_in_date"] = datetime.datetime.strptime(booking_data["check_in_date"], '%Y-%m-%d').date()
                    except (ValueError, TypeError):
                        extracted_info["errors"].append(f"Không thể phân tích cú pháp ngày nhận phòng: {booking_data.get('check_in_date')}")
                
                if booking_data.get("check_out_date"):
                    try:
                        extracted_info["check_out_date"] = datetime.datetime.strptime(booking_data["check_out_date"], '%Y-%m-%d').date()
                    except (ValueError, TypeError):
                         extracted_info["errors"].append(f"Không thể phân tích cú pháp ngày trả phòng: {booking_data.get('check_out_date')}")

                if extracted_info["check_in_date"] and extracted_info["check_out_date"]:
                    if extracted_info["check_out_date"] <= extracted_info["check_in_date"]:
                        extracted_info["errors"].append("Ngày trả phòng phải sau ngày nhận phòng.")
                    elif not extracted_info.get("num_nights"):
                        duration = extracted_info["check_out_date"] - extracted_info["check_in_date"]
                        extracted_info["num_nights"] = duration.days
                
                if not extracted_info.get("guest_name"): extracted_info["errors"].append("Thiếu tên khách.")
                if not extracted_info.get("check_in_date"): extracted_info["errors"].append("Thiếu ngày nhận phòng.")
                if not extracted_info.get("check_out_date"): extracted_info["errors"].append("Thiếu ngày trả phòng.")
                
                all_extracted_bookings.append(extracted_info)

        except json.JSONDecodeError:
            all_extracted_bookings.append({"errors": ["Không thể giải mã JSON từ phản hồi API. Phản hồi thô: " + response.text]})
        except Exception as e:
            all_extracted_bookings.append({"errors": [f"Lỗi khi xử lý dữ liệu từ API: {str(e)}"]})

    except Exception as e:
        error_message = f"Đã xảy ra lỗi không mong muốn khi xử lý hình ảnh: {str(e)}"
        st.error(error_message)
        all_extracted_bookings.append({"errors": [error_message]})
        
    return all_extracted_bookings

# --- KHỞI TẠO SESSION STATE ---
if 'df' not in st.session_state: st.session_state.df = None
if 'active_bookings' not in st.session_state: st.session_state.active_bookings = None
if 'room_types' not in st.session_state: st.session_state.room_types = []
if 'data_source' not in st.session_state: st.session_state.data_source = None
if 'uploaded_file_name' not in st.session_state: st.session_state.uploaded_file_name = None
if 'last_action_message' not in st.session_state: st.session_state.last_action_message = None
if 'current_date_calendar' not in st.session_state: st.session_state.current_date_calendar = datetime.date.today()
if 'selected_calendar_date' not in st.session_state: st.session_state.selected_calendar_date = None
if 'booking_sort_column' not in st.session_state:
    st.session_state.booking_sort_column = 'Booking Date'
if 'booking_sort_ascending' not in st.session_state:
    st.session_state.booking_sort_ascending = False

if 'message_templates_dict' not in st.session_state:
    st.session_state.message_templates_dict = parse_message_templates(DEFAULT_MESSAGE_TEMPLATE_CONTENT)

if 'raw_template_content_for_download' not in st.session_state:
    if 'message_templates_dict' in st.session_state and st.session_state.message_templates_dict is not None:
        st.session_state.raw_template_content_for_download = format_templates_to_text(st.session_state.message_templates_dict)
    else:
        st.session_state.raw_template_content_for_download = ""

if 'editing_booking_id_for_dialog' not in st.session_state:
    st.session_state.editing_booking_id_for_dialog = None

if 'show_add_booking_success_dialog' not in st.session_state:
    st.session_state.show_add_booking_success_dialog = False
if 'add_booking_success_message' not in st.session_state:
    st.session_state.add_booking_success_message = ""

if "add_form_check_in_final" not in st.session_state:
    st.session_state.add_form_check_in_final = datetime.date.today()
if "add_form_check_out_final" not in st.session_state:
    st.session_state.add_form_check_out_final = datetime.date.today() + timedelta(days=1)

if 'image_extracted_data_log' not in st.session_state:
    st.session_state.image_extracted_data_log = None

# --- GIAO DIỆN NGƯỜI DÙNG (UI) & LOGIC TẢI DỮ LIỆU ---
st.sidebar.title("🏨 Quản lý phòng")
if not PYPDF2_AVAILABLE and not BS4_AVAILABLE: st.sidebar.warning("Xử lý PDF và HTML bị hạn chế. Cài đặt: `pip install pypdf2 beautifulsoup4`")
elif not PYPDF2_AVAILABLE: st.sidebar.warning("Xử lý PDF sẽ không hoạt động. Cài đặt: `pip install pypdf2`")
elif not BS4_AVAILABLE: st.sidebar.warning("Xử lý HTML sẽ không hoạt động. Cài đặt: `pip install beautifulsoup4`")

uploaded_file = st.sidebar.file_uploader("Tải lên file đặt phòng (Excel, PDF, HTML)", type=['xls', 'xlsx', 'pdf', 'html'], key="file_uploader_key", help="Hỗ trợ file Excel, PDF, HTML từ Booking.com.")
if uploaded_file is not None:
    if st.session_state.uploaded_file_name != uploaded_file.name or st.session_state.df is None:
        with st.spinner(f"Đang xử lý file: {uploaded_file.name}..."):
            df_from_file, active_bookings_from_file = load_data_from_file(uploaded_file)
        if df_from_file is not None and not df_from_file.empty:
            st.session_state.df = df_from_file
            st.session_state.active_bookings = active_bookings_from_file
            st.session_state.room_types = get_cleaned_room_types(df_from_file)
            st.session_state.data_source = 'file'
            st.session_state.uploaded_file_name = uploaded_file.name
            st.sidebar.success(f"Đã tải và xử lý thành công file: {uploaded_file.name}")
            st.session_state.selected_calendar_date = None
            st.rerun()
        else:
            st.sidebar.error(f"Không thể xử lý file {uploaded_file.name} hoặc file không chứa dữ liệu hợp lệ.")
            st.session_state.data_source = 'error_loading_file'
            st.session_state.uploaded_file_name = uploaded_file.name
elif st.session_state.df is None and st.session_state.data_source != 'error_loading_file':
    st.sidebar.info("Đang tải dữ liệu mặc định từ Google Sheets...")
    creds_dict = st.secrets["gcp_service_account"]
    default_sheet_id = "13kQETOUGCVUwUqZrxeLy-WAj3b17SugI4L8Oq09SX2w"
    worksheet_name = "BookingManager"
    df_gsheet = import_from_gsheet(default_sheet_id, creds_dict, worksheet_name)
    if df_gsheet is not None and not df_gsheet.empty:
        st.session_state.df = df_gsheet
        st.session_state.active_bookings = df_gsheet[df_gsheet['Tình trạng'] != 'Đã hủy'].copy() if 'Tình trạng' in df_gsheet.columns else df_gsheet.copy()
        st.session_state.room_types = get_cleaned_room_types(df_gsheet)
        st.session_state.data_source = 'gsheet_default'
    else:
        st.session_state.df, st.session_state.active_bookings = create_demo_data()
        if st.session_state.df is not None and not st.session_state.df.empty:
            st.session_state.room_types = get_cleaned_room_types(st.session_state.df)
        else:
            st.session_state.room_types = []
        st.session_state.data_source = 'demo'
    st.session_state.selected_calendar_date = None


df = st.session_state.get('df')
active_bookings = st.session_state.get('active_bookings')
room_types = st.session_state.get('room_types', []) 
default_min_date = datetime.date.today() - timedelta(days=365)
default_max_date = datetime.date.today() + timedelta(days=365)

if df is not None and not df.empty:
    for col in ['Check-in Date', 'Check-out Date', 'Booking Date']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')
if active_bookings is not None and not active_bookings.empty:
    for col in ['Check-in Date', 'Check-out Date', 'Booking Date']:
        if col in active_bookings.columns:
            active_bookings[col] = pd.to_datetime(active_bookings[col], errors='coerce')

min_date_val = (df['Check-in Date'].min().date() if df is not None and not df.empty and 'Check-in Date' in df.columns and not df['Check-in Date'].dropna().empty else default_min_date)
max_date_val = (df['Check-out Date'].max().date() if df is not None and not df.empty and 'Check-out Date' in df.columns and not df['Check-out Date'].dropna().empty else default_max_date)

# --- CÁC TAB CHỨC NĂNG ---
tab_titles = ["📊 Dashboard", "📅 Lịch phòng", "📋 Quản lý đặt phòng", "📈 Phân tích", "📸 Thêm từ Ảnh", "➕ Thêm đặt phòng", "📝 Xử lý HTML & Nối dữ liệu", "💌 Mẫu tin nhắn"]
tab_dashboard, tab_calendar, tab_booking_mgmt, tab_analytics, tab_add_from_image, tab_add_booking, tab_html_processing, tab_message_templates = st.tabs(tab_titles)

# --- TAB DASHBOARD ---
with tab_dashboard:
    st.header("📊 Tổng quan Dashboard")
    if df is not None and not df.empty and active_bookings is not None:
        st.markdown("#### Số liệu chính")
        
        # --- GIAO DIỆN SỐ LIỆU MỚI VỚI 6 METRIC GỐC ---
        row1_cols = st.columns(3)
        row2_cols = st.columns(3)
        today_dt = datetime.date.today()

        # --- HÀNG 1 ---
        # Metric 1: Tổng số đặt phòng
        total_bookings_count = len(df)
        active_bookings_count = len(active_bookings) if active_bookings is not None else 0
        row1_cols[0].metric(
            label="Tổng Đặt Phòng",
            value=total_bookings_count,
            help=f"{active_bookings_count} đang hoạt động."
        )

        # Metric 2: Tổng TT đã Check-in (Gross)
        total_gross_checked_in = 0
        if not active_bookings.empty:
            checked_in_df = active_bookings[active_bookings['Check-in Date'].dt.date <= today_dt].copy()
            if not checked_in_df.empty:
                checked_in_df['Tổng thanh toán'] = pd.to_numeric(checked_in_df['Tổng thanh toán'], errors='coerce').fillna(0)
                total_gross_checked_in = checked_in_df['Tổng thanh toán'].sum()
        row1_cols[1].metric(
            label="Tổng TT đã C/I (VND)",
            value=f"{total_gross_checked_in/1_000_000:.2f} Tr",
            help=f"Tổng tiền (chưa trừ HH) của các phòng đã check-in: {total_gross_checked_in:,.0f} VND"
        )

        # Metric 3: Tổng TT NET đã Check-in
        total_net_checked_in = 0
        if 'total_gross_checked_in' in locals() and total_gross_checked_in > 0:
             total_net_checked_in = total_gross_checked_in * 0.8 # Giả sử HH 20%
        row1_cols[2].metric(
            label="Tổng TT NET đã C/I (VND)",
            value=f"{total_net_checked_in/1_000_000:.2f} Tr",
            help=f"Tổng tiền thu về (sau 20% HH) của các phòng đã check-in: {total_net_checked_in:,.0f} VND"
        )

        # --- HÀNG 2 ---
        # Metric 4: Tổng TT dự kiến (Tất cả HĐ, Gross)
        total_expected_gross = 0
        if not active_bookings.empty:
            active_bookings['Tổng thanh toán'] = pd.to_numeric(active_bookings['Tổng thanh toán'], errors='coerce').fillna(0)
            total_expected_gross = active_bookings['Tổng thanh toán'].sum()
        row2_cols[0].metric(
            label="Tổng TT dự kiến (Tất cả HĐ)",
            value=f"{total_expected_gross/1_000_000:.2f} Tr",
            help=f"Tổng tiền (chưa trừ HH) của tất cả các phòng đang hoạt động: {total_expected_gross:,.0f} VND"
        )

        # Metric 5: Tổng tiền NET (sau Hoa hồng)
        total_expected_net = total_expected_gross * 0.8 # Giả sử HH 20%
        row2_cols[1].metric(
            label="Tổng tiền NET (sau HH)",
            value=f"{total_expected_net/1_000_000:.2f} Tr",
            help=f"Tổng tiền thu về (sau 20% HH) của tất cả các phòng đang hoạt động: {total_expected_net:,.0f} VND"
        )

        # Metric 6: Tỷ lệ lấp đầy hôm nay
        occupied_today_count = 0
        if not active_bookings.empty:
            active_on_today = active_bookings[
                (active_bookings['Check-in Date'].dt.date <= today_dt) & 
                (active_bookings['Check-out Date'].dt.date > today_dt)
            ]
            occupied_today_count = len(active_on_today)
        occupancy_rate_today = (occupied_today_count / TOTAL_HOTEL_CAPACITY) * 100 if TOTAL_HOTEL_CAPACITY > 0 else 0
        row2_cols[2].metric(
            label="Lấp đầy hôm nay",
            value=f"{occupancy_rate_today:.1f}%",
            delta=f"{occupied_today_count}/{TOTAL_HOTEL_CAPACITY} phòng",
            delta_color="off"
        )

    else:
        st.info(" Dữ liệu không đủ hoặc chưa được tải. Vui lòng tải file đặt phòng hợp lệ.")
        if st.button("🔄 Tải lại dữ liệu demo", key="reload_demo_dashboard"):
            st.session_state.df, st.session_state.active_bookings = create_demo_data()
            st.session_state.room_types = get_cleaned_room_types(st.session_state.df)
            st.session_state.data_source = 'demo'; st.session_state.uploaded_file_name = None; st.session_state.selected_calendar_date = None
            st.rerun()

# --- TAB LỊCH PHÒNG ---
with tab_calendar:
    st.header("📅 Lịch phòng tổng quan")
    st.subheader("Tổng quan phòng trống")
    if active_bookings is not None:
        today_date = datetime.date.today(); tomorrow_date = today_date + timedelta(days=1)
        today_overall_info = get_overall_calendar_day_info(today_date, active_bookings, TOTAL_HOTEL_CAPACITY)
        total_available_today = today_overall_info['available_units']
        tomorrow_overall_info = get_overall_calendar_day_info(tomorrow_date, active_bookings, TOTAL_HOTEL_CAPACITY)
        total_available_tomorrow = tomorrow_overall_info['available_units']
        col_today_avail, col_tomorrow_avail = st.columns(2)
        with col_today_avail:
            st.markdown(f"##### Hôm nay ({today_date.strftime('%d/%m')})")
            if total_available_today > 0: st.info(f"**{total_available_today}** phòng trống / {TOTAL_HOTEL_CAPACITY} tổng số")
            else: st.warning(f"Hết phòng hôm nay ({TOTAL_HOTEL_CAPACITY} phòng đã bị chiếm).")
        with col_tomorrow_avail:
            st.markdown(f"##### Ngày mai ({tomorrow_date.strftime('%d/%m')})")
            if total_available_tomorrow > 0: st.info(f"**{total_available_tomorrow}** phòng trống / {TOTAL_HOTEL_CAPACITY} tổng số")
            else: st.warning(f"Hết phòng ngày mai ({TOTAL_HOTEL_CAPACITY} phòng đã bị chiếm).")
    else: st.info("Không có dữ liệu đặt phòng để tính phòng trống.")
    st.markdown("---")
    col_nav1, col_nav_title, col_nav2 = st.columns([1, 2, 1])
    with col_nav1:
        if st.button("◀️ Tháng trước", key="prev_month_calendar", use_container_width=True):
            current_date_cal = st.session_state.current_date_calendar; first_day_current_month = current_date_cal.replace(day=1); last_day_prev_month = first_day_current_month - timedelta(days=1)
            st.session_state.current_date_calendar = last_day_prev_month.replace(day=1); st.session_state.selected_calendar_date = None; st.rerun()
    with col_nav_title: st.subheader(f"Tháng {st.session_state.current_date_calendar.month} năm {st.session_state.current_date_calendar.year}")
    with col_nav2:
        if st.button("Tháng sau ▶️", key="next_month_calendar", use_container_width=True):
            current_date_cal = st.session_state.current_date_calendar; days_in_month = calendar.monthrange(current_date_cal.year, current_date_cal.month)[1]
            first_day_next_month = current_date_cal.replace(day=1) + timedelta(days=days_in_month + 1)
            st.session_state.current_date_calendar = first_day_next_month.replace(day=1); st.session_state.selected_calendar_date = None; st.rerun()
    if st.button("📅 Về tháng hiện tại", key="today_month_calendar"):
        st.session_state.current_date_calendar = datetime.date.today(); st.session_state.selected_calendar_date = None; st.rerun()

    day_names = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"]
    cols_header = st.columns(7)
    for i, day_name_header in enumerate(day_names): cols_header[i].markdown(f"<div class='day-header'>{day_name_header}</div>", unsafe_allow_html=True)

    if df is not None and not df.empty:
        current_year = st.session_state.current_date_calendar.year; current_month = st.session_state.current_date_calendar.month
        cal_obj = calendar.Calendar(); month_days_matrix = cal_obj.monthdayscalendar(current_year, current_month)
        for week_data in month_days_matrix:
            cols_week = st.columns(7)
            for i, day_num_cal in enumerate(week_data):
                with cols_week[i]:
                    if day_num_cal == 0: st.markdown(f"<div class='day-cell day-disabled'></div>", unsafe_allow_html=True)
                    else:
                        current_day_date_cal = datetime.date(current_year, current_month, day_num_cal)
                        day_info_cal = get_overall_calendar_day_info(current_day_date_cal, active_bookings, TOTAL_HOTEL_CAPACITY)
                        status_indicator_html = ""
                        if day_info_cal['status_indicator_type'] == "green_dot": status_indicator_html = "<div class='dot-indicator dot-green'>•</div>"
                        elif day_info_cal['status_indicator_type'] == "orange_dash": status_indicator_html = "<div class='dot-indicator dot-orange'>—</div>"
                        elif day_info_cal['status_indicator_type'] == "red_x": status_indicator_html = "<div class='dot-indicator dot-red'>✕</div>"
                        day_class = "day-cell"
                        if current_day_date_cal == datetime.date.today(): day_class += " day-today"
                        if st.session_state.selected_calendar_date == current_day_date_cal: day_class += " day-selected"
                        st.markdown(f"""<div class='{day_class}'><div class='day-number'>{day_num_cal}</div>{status_indicator_html}<div class='day-status'>{day_info_cal['status_text']}</div></div>""", unsafe_allow_html=True)
                        button_key_calendar = f"day_button_overlay_{current_day_date_cal.strftime('%Y%m%d')}"
                        if st.button("", key=button_key_calendar, help=f"Xem chi tiết ngày {current_day_date_cal.strftime('%d/%m/%Y')}"):
                            st.session_state.selected_calendar_date = None if st.session_state.selected_calendar_date == current_day_date_cal else current_day_date_cal
                            st.session_state.editing_booking_id_for_dialog = None
                            st.rerun()
    else: st.info("Không có dữ liệu đặt phòng để hiển thị lịch.")

    if st.session_state.selected_calendar_date is not None:
        selected_date_cal = st.session_state.selected_calendar_date
        st.markdown("---")
        with st.expander(f"🗓️ Chi tiết hoạt động ngày: {selected_date_cal.strftime('%A, %d/%m/%Y')}", expanded=True):
            daily_activity_cal = get_daily_activity(selected_date_cal, active_bookings)
            col_checkin_cal, col_checkout_cal, col_occupied_cal = st.columns(3)
            with col_checkin_cal:
                st.markdown("##### 🛬 Khách Check-in")
                if daily_activity_cal['check_in']:
                    st.success(f"**{len(daily_activity_cal['check_in'])}** lượt check-in:")
                    for guest in daily_activity_cal['check_in']: st.markdown(f"- **{guest.get('name','N/A')}** ({guest.get('room_type','N/A')})"); st.caption(f"  Mã ĐP: {guest.get('booking_id','N/A')}")
                else: st.info("Không có khách check-in.")
            with col_checkout_cal:
                st.markdown("##### 🛫 Khách Check-out")
                if daily_activity_cal['check_out']:
                    st.warning(f"**{len(daily_activity_cal['check_out'])}** lượt check-out:")
                    for guest in daily_activity_cal['check_out']: st.markdown(f"- **{guest.get('name','N/A')}** ({guest.get('room_type','N/A')})"); st.caption(f"  Mã ĐP: {guest.get('booking_id','N/A')}")
                else: st.info("Không có khách check-out.")
            with col_occupied_cal:
                st.markdown("##### 🏨 Khách đang ở")
                if daily_activity_cal['occupied']:
                    st.info(f"**{len(daily_activity_cal['occupied'])}** lượt khách ở:")
                    for guest in daily_activity_cal['occupied']:
                        check_in_str = guest['check_in'].strftime('%d/%m') if guest['check_in'] else 'N/A'
                        check_out_str = guest['check_out'].strftime('%d/%m') if guest['check_out'] else 'N/A'
                        total_payment_val = guest.get('total_payment', 0.0)
                        total_payment_str = f"{total_payment_val:,.0f}" if pd.notna(total_payment_val) and total_payment_val != 0.0 else "0"
                        st.markdown(f"- **{guest.get('name','N/A')}** ({guest.get('room_type','N/A')})")
                        st.caption(f"  Từ {check_in_str} đến {check_out_str} (Mã ĐP: {guest.get('booking_id','N/A')}) - Tổng tiền: {total_payment_str}")
                        st.markdown("<div class='guest-separator'></div>", unsafe_allow_html=True)
                else: st.info("Không có khách đang ở.")
            if st.button("Ẩn chi tiết ngày", key="hide_day_details_calendar", type="primary"):
                st.session_state.selected_calendar_date = None; st.rerun()

# --- TAB QUẢN LÝ ĐẶT PHÒNG ---
with tab_booking_mgmt:
    st.header("📋 Quản lý tất cả đặt phòng")
    if df is not None and not df.empty:
        # --- PHẦN LỌC DỮ LIỆU (GIỮ NGUYÊN) ---
        st.markdown("##### Bộ lọc đặt phòng")
        filter_cols_main = st.columns([2, 2, 3])
        with filter_cols_main[0]:
            unique_statuses_mgmt_list = sorted(df['Tình trạng'].dropna().astype(str).unique().tolist()) if 'Tình trạng' in df.columns else []
            status_filter_manage = st.multiselect("Trạng thái:", options=unique_statuses_mgmt_list, default=unique_statuses_mgmt_list, key="status_filter_manage_tab3_v6")
        with filter_cols_main[1]:
            unique_room_types_manage = st.session_state.get('room_types', [])
            room_filter_manage = st.multiselect("Loại phòng:", options=unique_room_types_manage, default=unique_room_types_manage, key="room_filter_manage_tab3_v6")
        with filter_cols_main[2]:
            temp_max_date_filter = max_date_val if min_date_val <= max_date_val else min_date_val + timedelta(days=1)
            date_range_manage = st.date_input("Khoảng ngày check-in:", value=(min_date_val, temp_max_date_filter), min_value=min_date_val, max_value=temp_max_date_filter, key="date_range_filter_manage_tab3_v6")

        df_after_main_filters = df.copy()
        if status_filter_manage and 'Tình trạng' in df_after_main_filters.columns:
            df_after_main_filters = df_after_main_filters[df_after_main_filters['Tình trạng'].isin(status_filter_manage)]
        if room_filter_manage and 'Tên chỗ nghỉ' in df_after_main_filters.columns:
            df_after_main_filters = df_after_main_filters[df_after_main_filters['Tên chỗ nghỉ'].isin(room_filter_manage)]
        if date_range_manage and len(date_range_manage) == 2 and 'Check-in Date' in df_after_main_filters.columns:
            start_date_filter_mgmt, end_date_filter_mgmt = date_range_manage
            df_after_main_filters = df_after_main_filters[(pd.to_datetime(df_after_main_filters['Check-in Date']).dt.date >= start_date_filter_mgmt) & (pd.to_datetime(df_after_main_filters['Check-in Date']).dt.date <= end_date_filter_mgmt)]

        search_term_mgmt = st.text_input("Tìm theo tên khách hoặc mã đặt phòng:", key="search_booking_tab3_v6", placeholder="Nhập từ khóa...")
        if search_term_mgmt:
            df_after_main_filters = df_after_main_filters[
                (df_after_main_filters['Tên người đặt'].astype(str).str.contains(search_term_mgmt, case=False, na=False)) |
                (df_after_main_filters['Số đặt phòng'].astype(str).str.contains(search_term_mgmt, case=False, na=False))
            ]
        
        # --- LOGIC SẮP XẾP ---
        # Khởi tạo session state cho việc sắp xếp nếu chưa có
        if 'sort_column' not in st.session_state:
            st.session_state.sort_column = 'Check-in Date'
        if 'sort_ascending' not in st.session_state:
            st.session_state.sort_ascending = False

        # Sắp xếp DataFrame dựa trên session_state
        try:
            df_filtered = df_after_main_filters.sort_values(
                by=st.session_state.sort_column, 
                ascending=st.session_state.sort_ascending
            )
        except Exception as e:
            st.warning(f"Không thể sắp xếp theo cột '{st.session_state.sort_column}'. Quay về mặc định. Lỗi: {e}")
            st.session_state.sort_column = 'Check-in Date'
            st.session_state.sort_ascending = False
            df_filtered = df_after_main_filters.sort_values(by='Check-in Date', ascending=False)

        st.markdown("---")
        
        if df_filtered.empty:
            st.info("Không có đặt phòng nào phù hợp với bộ lọc hoặc từ khóa tìm kiếm.")
        else:
            delete_button_placeholder = st.empty()
            st.write(f"Tìm thấy {len(df_filtered)} đặt phòng:")
            
            # --- GIAO DIỆN BẢNG VỚI HEADER CÓ THỂ SẮP XẾP ---
            columns_map = {
                'Tên người đặt': 'Khách',
                'Check-in Date': 'Check-in',
                'Check-out Date': 'Check-out',
                'Stay Duration': 'Số đêm',
                'Tình trạng': 'Trạng thái',
                'Tổng thanh toán': 'Tổng tiền (VND)',
                'Booking Date': 'Ngày thêm khách',
                'Người thu tiền': 'Người thu tiền'
            }
            col_ratios = [0.4, 2.5, 1, 1, 0.8, 1, 1.5, 1.5, 1.5, 1]
            
            # Vẽ Header với các nút bấm
            header_cols = st.columns(col_ratios)
            header_cols[0].markdown("**Chọn**")
            
            for i, (col_key, col_title) in enumerate(columns_map.items()):
                with header_cols[i+1]:
                    sort_indicator = ""
                    if st.session_state.sort_column == col_key:
                        sort_indicator = " ▲" if st.session_state.sort_ascending else " ▼"
                    
                    if st.button(f"{col_title}{sort_indicator}", key=f"sort_{col_key}", use_container_width=True):
                        if st.session_state.sort_column == col_key:
                            st.session_state.sort_ascending = not st.session_state.sort_ascending
                        else:
                            st.session_state.sort_column = col_key
                            st.session_state.sort_ascending = True # Mặc định tăng dần cho cột mới
                        st.rerun()

            header_cols[-1].markdown("**Hành động**")
            st.markdown("<hr style='margin:0; padding:0;'>", unsafe_allow_html=True)

            # Vòng lặp để vẽ từng hàng (không thay đổi)
            checkbox_info = {}
            for index, row in df_filtered.iterrows():
                row_cols = st.columns(col_ratios)
                booking_id = row.get('Số đặt phòng', f"index_{index}")
                checkbox_key = f"cb_{booking_id}_{index}"
                is_checked = row_cols[0].checkbox("", key=checkbox_key, label_visibility="collapsed")
                checkbox_info[index] = is_checked

                for i, col_key in enumerate(columns_map.keys()):
                    value = row.get(col_key)
                    if isinstance(value, (datetime.datetime, pd.Timestamp)):
                        row_cols[i+1].write(value.strftime('%d/%m/%Y'))
                    elif col_key in ['Tổng thanh toán', 'Giá mỗi đêm']:
                        try:
                            row_cols[i+1].write(f"{float(value):,.0f}")
                        except (ValueError, TypeError):
                            row_cols[i+1].write("0")
                    else:
                        row_cols[i+1].write(value)
                
                action_col = row_cols[-1]
                if action_col.button("Sửa", key=f"edit_{booking_id}_{index}", use_container_width=True):
                    st.session_state.editing_booking_id_for_dialog = booking_id
                    st.rerun()

            # Xử lý nút xóa ở trên cùng (không thay đổi)
            indices_to_delete = [index for index, checked in checkbox_info.items() if checked]
            if indices_to_delete:
                with delete_button_placeholder.container():
                    st.warning(f"Bạn đã chọn {len(indices_to_delete)} đặt phòng.")
                    if st.button(f"Xác nhận xóa {len(indices_to_delete)} đặt phòng đã chọn", type="primary", use_container_width=True):
                        st.session_state.df = st.session_state.df.drop(index=indices_to_delete).reset_index(drop=True)
                        st.session_state.active_bookings = st.session_state.df[st.session_state.df['Tình trạng'] != 'Đã hủy'].copy()
                        st.session_state.last_action_message = f"Đã xóa thành công {len(indices_to_delete)} đặt phòng."
                        st.rerun()

            if st.session_state.last_action_message:
                st.success(st.session_state.last_action_message)
                st.session_state.last_action_message = None

# --- TAB THÊM TỪ ẢNH (Đã sửa lỗi và nâng cấp) ---
with tab_add_from_image:
    st.header("📸 Thêm Đặt Phòng từ Ảnh")
    st.info(
        "Sử dụng một trong hai cách:\n"
        "1. **Tải lên file ảnh** (.png, .jpg) chứa danh sách đặt phòng.\n"
        "2. **Dán ảnh chụp màn hình** trực tiếp vào khung bên dưới (Ctrl+V)."
    )

    # --- KHỞI TẠO CÁC BIẾN SESSION STATE CẦN THIẾT ---
    if 'image_bytes_to_process' not in st.session_state:
        st.session_state.image_bytes_to_process = None
    if 'extracted_list_data' not in st.session_state:
        st.session_state.extracted_list_data = None
    # THAY ĐỔI 1: Thêm state để lưu trữ dữ liệu thô từ component
    if 'pasted_b64_data' not in st.session_state:
        st.session_state.pasted_b64_data = None

    # --- PHẦN NHẬP LIỆU ---
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Cách 1: Tải lên tệp")
        uploaded_image_file = st.file_uploader(
            "Chọn một file ảnh",
            type=["png", "jpg", "jpeg"],
            key="image_booking_list_uploader"
        )
        if uploaded_image_file:
            st.session_state.image_bytes_to_process = uploaded_image_file.getvalue()
            st.session_state.extracted_list_data = None
            st.session_state.pasted_b64_data = None # Xóa dữ liệu dán cũ
            st.rerun()

    with col2:
        st.subheader("Cách 2: Dán ảnh")
        with open("components/paste_image.html", "r", encoding="utf-8") as f:
            html_code = f.read()
        
        component_return_value = components.html(html_code, height=170)

        # THAY ĐỔI 2: Logic nhận dữ liệu mới - Chỉ lưu và rerun
        if component_return_value and component_return_value != st.session_state.pasted_b64_data:
            # Chỉ lưu dữ liệu vào state và rerun, không xử lý ngay
            st.session_state.pasted_b64_data = component_return_value
            st.session_state.extracted_list_data = None
            st.session_state.image_bytes_to_process = None # Xóa dữ liệu tải lên cũ
            st.rerun()

    st.markdown("---")

    # --- PHẦN XỬ LÝ DỮ LIỆU DÁN (CHẠY Ở LẦN RERUN THỨ 2) ---
    # THAY ĐỔI 3: Tách riêng khối xử lý dữ liệu dán
    if st.session_state.pasted_b64_data and st.session_state.image_bytes_to_process is None:
        try:
            # Bây giờ xử lý dữ liệu từ session_state một cách an toàn
            image_data = st.session_state.pasted_b64_data.split(",")[1]
            st.session_state.image_bytes_to_process = base64.b64decode(image_data)
            # Xóa dữ liệu thô sau khi đã xử lý để tránh lặp lại
            st.session_state.pasted_b64_data = None
            st.rerun() # Rerun một lần nữa để hiển thị ảnh preview
        except Exception as e:
            st.error(f"Không thể xử lý ảnh được dán: {e}")
            st.session_state.pasted_b64_data = None # Xóa dữ liệu lỗi

    # --- PHẦN XỬ LÝ VÀ HIỂN THỊ (GIỮ NGUYÊN) ---
    if st.session_state.image_bytes_to_process and not st.session_state.extracted_list_data:
        st.subheader("Ảnh đã sẵn sàng để xử lý:")
        st.image(st.session_state.image_bytes_to_process, use_column_width=True)

        if st.button("🔍 Trích xuất thông tin từ ảnh này", type="primary"):
            with st.spinner("Đang phân tích ảnh và trích xuất danh sách đặt phòng..."):
                list_of_extracted_data = extract_booking_info_from_image_content(st.session_state.image_bytes_to_process)
                st.session_state.extracted_list_data = list_of_extracted_data
            
            if list_of_extracted_data and not (isinstance(list_of_extracted_data[0], dict) and list_of_extracted_data[0].get("errors")):
                 st.success(f"Hoàn tất! Đã trích xuất được {len(list_of_extracted_data)} đặt phòng. Vui lòng kiểm tra kết quả bên dưới.")
            else:
                 error_msg = list_of_extracted_data[0].get("errors", ["Lỗi không xác định."]) if list_of_extracted_data else ["Không có dữ liệu trả về."]
                 st.error(f"Không thể trích xuất dữ liệu. Lỗi: {error_msg[0]}")
            st.rerun()

    if st.session_state.extracted_list_data:
        st.subheader("Kết quả trích xuất")
        
        # ... (Toàn bộ phần logic hiển thị và thêm DataFrame giữ nguyên như cũ)
        extracted_df = pd.DataFrame(st.session_state.extracted_list_data)

        display_cols = [
            'guest_name', 'check_in_date', 'check_out_date', 'room_type', 
            'total_payment', 'commission', 'booking_id', 'errors'
        ]
        existing_display_cols = [col for col in display_cols if col in extracted_df.columns]
        
        st.dataframe(extracted_df[existing_display_cols])

        if st.button("➕ Thêm tất cả các đặt phòng hợp lệ vào hệ thống", key="add_all_from_image_list"):
            if st.session_state.df is None:
                st.error("Dữ liệu chính chưa được tải. Không thể thêm.")
            else:
                new_bookings_list = []
                skipped_count = 0
                added_count = 0
                
                main_df_booking_ids = set(st.session_state.df['Số đặt phòng'].astype(str).tolist())

                for index, row in extracted_df.iterrows():
                    if (row.get('errors') and any(row['errors'])) or not all([row.get('guest_name'), row.get('check_in_date'), row.get('check_out_date')]):
                        skipped_count += 1
                        continue
                    
                    if str(row.get('booking_id')) in main_df_booking_ids:
                        skipped_count += 1
                        continue

                    check_in = row['check_in_date']
                    check_out = row['check_out_date']
                    stay_duration = (check_out - check_in).days if check_out > check_in else 0
                    total_payment = float(row.get('total_payment', 0))
                    price_per_night = round(total_payment / stay_duration) if stay_duration > 0 else 0.0

                    new_booking_data = {
                        'Tên chỗ nghỉ': row.get('room_type', 'N/A'),
                        'Vị trí': "N/A (từ ảnh)",
                        'Tên người đặt': row.get('guest_name'),
                        'Thành viên Genius': row.get('genius_member', 'Không'),
                        'Ngày đến': f"ngày {check_in.day} tháng {check_in.month} năm {check_in.year}",
                        'Ngày đi': f"ngày {check_out.day} tháng {check_out.month} năm {check_out.year}",
                        'Được đặt vào': f"ngày {datetime.date.today().day} tháng {datetime.date.today().month} năm {datetime.date.today().year}",
                        'Tình trạng': row.get('status', 'OK'),
                        'Tổng thanh toán': total_payment,
                        'Hoa hồng': float(row.get('commission', 0)),
                        'Tiền tệ': row.get('currency', 'VND'),
                        'Số đặt phòng': str(row.get('booking_id', f"IMG_{datetime.datetime.now().strftime('%y%m%d%H%M%S')}_{index}")),
                        'Check-in Date': pd.Timestamp(check_in),
                        'Check-out Date': pd.Timestamp(check_out),
                        'Booking Date': pd.Timestamp(datetime.date.today()),
                        'Stay Duration': stay_duration,
                        'Giá mỗi đêm': price_per_night,
                        'Người thu tiền': "N/A"
                    }
                    new_bookings_list.append(new_booking_data)
                    main_df_booking_ids.add(str(new_booking_data['Số đặt phòng']))
                    added_count += 1

                if new_bookings_list:
                    new_bookings_df = pd.DataFrame(new_bookings_list)
                    st.session_state.df = pd.concat([st.session_state.df, new_bookings_df], ignore_index=True)
                    st.session_state.active_bookings = st.session_state.df[st.session_state.df['Tình trạng'] != 'Đã hủy'].copy()
                    st.session_state.room_types = get_cleaned_room_types(st.session_state.df)
                
                st.session_state.last_action_message = f"✅ Hoàn tất! Đã thêm {added_count} đặt phòng mới. Bỏ qua {skipped_count} đặt phòng (do lỗi hoặc trùng lặp)."
                st.session_state.extracted_list_data = None
                st.session_state.image_bytes_to_process = None
                st.rerun()

        if st.button("Hủy và xóa kết quả", key="clear_image_list_results"):
            st.session_state.extracted_list_data = None
            st.session_state.image_bytes_to_process = None
            st.rerun()

# --- TAB THÊM ĐẶT PHÒNG MỚI ---
with tab_add_booking:
    st.header("➕ Thêm đặt phòng mới")

    room_types_options = st.session_state.get('room_types', []) 
    if not room_types_options:
        st.warning("Không có thông tin loại phòng. Vui lòng tải file dữ liệu trước.")
        room_types_options = ["Chưa có loại phòng - Vui lòng tải dữ liệu"]

    if 'add_form_check_in_final' not in st.session_state:
        st.session_state.add_form_check_in_final = datetime.date.today()

    _min_checkout_date_calculated_final = st.session_state.add_form_check_in_final + timedelta(days=1)

    if 'add_form_check_out_final' not in st.session_state:
        st.session_state.add_form_check_out_final = _min_checkout_date_calculated_final
    else:
        if st.session_state.add_form_check_out_final < _min_checkout_date_calculated_final:
            st.session_state.add_form_check_out_final = _min_checkout_date_calculated_final

    with st.form(key="add_booking_form_v8_stable_dates"):
        st.subheader("Thông tin đặt phòng")
        col_form_add1, col_form_add2 = st.columns(2)

        with col_form_add1:
            guest_name_form = st.text_input("Tên khách*", placeholder="Nhập tên đầy đủ", key="form_v8_guest_name")
            
            default_room_type_val = st.session_state.get("form_v8_room_type", room_types_options[0] if room_types_options else None)
            room_type_idx = room_types_options.index(default_room_type_val) if default_room_type_val in room_types_options else 0
            room_type_form = st.selectbox("Loại phòng*", options=room_types_options, index=room_type_idx, key="form_v8_room_type")
            
            genius_options_add_list = ["Không", "Có"]
            default_genius_val = st.session_state.get("form_v8_genius", genius_options_add_list[0])
            genius_idx = genius_options_add_list.index(default_genius_val) if default_genius_val in genius_options_add_list else 0
            genius_member_form = st.selectbox("Thành viên Genius", options=genius_options_add_list, index=genius_idx, key="form_v8_genius")

        with col_form_add2:
            st.date_input("Ngày check-in*", value=st.session_state.add_form_check_in_final, key="add_form_check_in_final")
            st.date_input("Ngày check-out*", value=st.session_state.add_form_check_out_final, min_value=_min_checkout_date_calculated_final, key="add_form_check_out_final")
            
            status_options_add_list = ["OK", "Đã hủy", "Chờ xử lý"]
            default_status_val = st.session_state.get("form_v8_status", status_options_add_list[0])
            status_idx = status_options_add_list.index(default_status_val) if default_status_val in status_options_add_list else 0
            booking_status_form = st.selectbox("Trạng thái đặt phòng", options=status_options_add_list, index=status_idx, key="form_v8_status")
        
        st.markdown("---"); st.subheader("Thông tin thanh toán")
        col_form_add3, col_form_add4 = st.columns(2)
        with col_form_add3:
            total_payment_form = st.number_input("Tổng thanh toán (VND)*", min_value=0, step=50000, format="%d", key="form_v8_total_payment")
            commission_form = st.number_input("Hoa hồng (VND)", min_value=0, step=10000, format="%d", key="form_v8_commission")
        with col_form_add4:
            currency_options_add_list = ["VND", "USD"]
            default_currency_val = st.session_state.get("form_v8_currency", currency_options_add_list[0])
            currency_idx = currency_options_add_list.index(default_currency_val) if default_currency_val in currency_options_add_list else 0
            currency_form = st.selectbox("Tiền tệ", options=currency_options_add_list, index=currency_idx, key="form_v8_currency")
            
            default_booking_id_add = f"MANUAL{datetime.datetime.now().strftime('%y%m%d%H%M%S')}"
            if 'form_v8_booking_id' not in st.session_state:
                st.session_state.form_v8_booking_id = default_booking_id_add
            booking_id_form = st.text_input("Mã đặt phòng (tự động nếu trống)", key="form_v8_booking_id")

            collector_options_list = ["LOC LE", "THAO LE", "N/A"]
            default_collector_val = st.session_state.get("form_v8_nguoi_thu_tien", collector_options_list[0])
            collector_idx = collector_options_list.index(default_collector_val) if default_collector_val in collector_options_list else 0
            nguoi_thu_tien_form = st.selectbox("Người thu tiền*", options=collector_options_list, index=collector_idx, key="form_v8_nguoi_thu_tien")
        
        submitted_form_add = st.form_submit_button("💾 Thêm đặt phòng này", type="primary")
        
        if submitted_form_add:
            errors = [] 
            final_check_in_date = st.session_state.add_form_check_in_final
            final_check_out_date = st.session_state.add_form_check_out_final

            if not guest_name_form.strip(): errors.append("Tên khách không được để trống.")
            if final_check_out_date <= final_check_in_date: 
                errors.append(f"Ngày check-out ({final_check_out_date.strftime('%d/%m/%Y')}) phải sau ngày check-in ({final_check_in_date.strftime('%d/%m/%Y')}).")
            if total_payment_form <= 0 and booking_status_form == "OK": errors.append("Tổng thanh toán phải > 0 cho đặt phòng 'OK'.")
            if room_type_form == "Chưa có loại phòng - Vui lòng tải dữ liệu" or not room_type_form :
                errors.append("Loại phòng không hợp lệ. Vui lòng tải dữ liệu có thông tin loại phòng.")
            if not nguoi_thu_tien_form: errors.append("Người thu tiền không được để trống.")

            final_booking_id = booking_id_form.strip() if booking_id_form.strip() else default_booking_id_add
            current_df_for_check = st.session_state.get('df')
            if current_df_for_check is not None and not current_df_for_check.empty and 'Số đặt phòng' in current_df_for_check.columns and final_booking_id in current_df_for_check['Số đặt phòng'].values:
                errors.append(f"Mã đặt phòng '{final_booking_id}' đã tồn tại.")

            active_bookings_for_check = st.session_state.get('active_bookings')
            if not errors and booking_status_form == "OK": 
                if active_bookings_for_check is not None and room_types_options and room_type_form not in ["Chưa có loại phòng - Vui lòng tải dữ liệu", None, ""]: 
                    current_check_date_form_add = final_check_in_date 
                    while current_check_date_form_add < final_check_out_date: 
                        availability_check_specific_add = get_room_availability(current_check_date_form_add, active_bookings_for_check, [room_type_form], ROOM_UNIT_PER_ROOM_TYPE)
                        if availability_check_specific_add.get(room_type_form, 0) <= 0:
                            errors.append(f"Phòng '{room_type_form}' đã hết vào ngày {current_check_date_form_add.strftime('%d/%m/%Y')}.")
                            break 
                        
                        occupied_on_this_day = len(active_bookings_for_check[
                            (active_bookings_for_check['Check-in Date'].dt.date <= current_check_date_form_add) &
                            (active_bookings_for_check['Check-out Date'].dt.date > current_check_date_form_add) &
                            (active_bookings_for_check['Tình trạng'] != 'Đã hủy')
                        ])
                        if occupied_on_this_day >= TOTAL_HOTEL_CAPACITY:
                            errors.append(f"Ngày {current_check_date_form_add.strftime('%d/%m/%Y')} đã có đủ {TOTAL_HOTEL_CAPACITY} khách. Không thể thêm đặt phòng mới.")
                            break
                        current_check_date_form_add += timedelta(days=1)
            
            if errors: 
                for error_msg in errors: st.error(error_msg)
            else: 
                default_location = "N/A (Chưa xác định)"
                current_df_for_add = st.session_state.get('df')
                if current_df_for_add is not None and not current_df_for_add.empty and 'Tên chỗ nghỉ' in current_df_for_add.columns and 'Vị trí' in current_df_for_add.columns:
                    room_specific_locations_df = current_df_for_add[current_df_for_add['Tên chỗ nghỉ'] == room_type_form]
                    if not room_specific_locations_df.empty:
                        unique_room_locations = room_specific_locations_df['Vị trí'].dropna().unique()
                        if len(unique_room_locations) > 0 and pd.notna(unique_room_locations[0]):
                            default_location = str(unique_room_locations[0])
                
                stay_duration_val = (final_check_out_date - final_check_in_date).days
                total_payment_val = float(total_payment_form)
                price_per_night_val = round(total_payment_val / stay_duration_val) if stay_duration_val > 0 else 0.0

                new_booking_data = {
                    'Tên chỗ nghỉ': room_type_form, 'Vị trí': default_location,
                    'Tên người đặt': guest_name_form.strip(), 'Thành viên Genius': genius_member_form,
                    'Ngày đến': f"ngày {final_check_in_date.day} tháng {final_check_in_date.month} năm {final_check_in_date.year}",
                    'Ngày đi': f"ngày {final_check_out_date.day} tháng {final_check_out_date.month} năm {final_check_out_date.year}",
                    'Được đặt vào': f"ngày {datetime.date.today().day} tháng {datetime.date.today().month} năm {datetime.date.today().year}",
                    'Tình trạng': booking_status_form, 'Tổng thanh toán': total_payment_val,
                    'Hoa hồng': float(commission_form), 'Tiền tệ': currency_form,
                    'Số đặt phòng': final_booking_id,
                    'Check-in Date': pd.Timestamp(final_check_in_date),
                    'Check-out Date': pd.Timestamp(final_check_out_date),
                    'Booking Date': pd.Timestamp(datetime.date.today()),
                    'Stay Duration': stay_duration_val,
                    'Giá mỗi đêm': price_per_night_val,
                    'Người thu tiền': nguoi_thu_tien_form
                }
                new_booking_df_row = pd.DataFrame([new_booking_data])
                
                df_to_update = st.session_state.get('df')
                if df_to_update is None or df_to_update.empty:
                    st.session_state.df = new_booking_df_row
                else:
                    st.session_state.df = pd.concat([df_to_update, new_booking_df_row], ignore_index=True)
                
                st.session_state.active_bookings = st.session_state.df[st.session_state.df['Tình trạng'] != 'Đã hủy'].copy()
                st.session_state.room_types = get_cleaned_room_types(st.session_state.df)

                success_message = f"Đặt phòng '{final_booking_id}' cho khách '{guest_name_form.strip()}' đã được thêm!"
                st.session_state.add_booking_success_message = success_message
                st.session_state.show_add_booking_success_dialog = True
                
                if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
                    telegram_message = f"📢 Đặt phòng MỚI!\n"
                    telegram_message += f"👤 Khách: {guest_name_form.strip()}\n"
                    telegram_message += f"🏠 Phòng: {room_type_form}\n"
                    telegram_message += f"📅 Check-in: {final_check_in_date.strftime('%d/%m/%Y')}\n"
                    telegram_message += f"📅 Check-out: {final_check_out_date.strftime('%d/%m/%Y')}\n"
                    telegram_message += f"💰 Tổng TT: {total_payment_val:,.0f} {currency_form}\n"
                    telegram_message += f"🆔 Mã ĐP: {final_booking_id}"
                    asyncio.run(send_telegram_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, telegram_message))

                st.session_state.last_action_message = f"Đã thêm đặt phòng {final_booking_id}."
                st.session_state.selected_calendar_date = None 
                
                form_keys_to_clear = [
                    "form_v8_guest_name", "form_v8_room_type", "form_v8_genius",
                    "form_v8_status", "form_v8_total_payment", "form_v8_commission",
                    "form_v8_currency", "form_v8_booking_id", "form_v8_nguoi_thu_tien",
                    "add_form_check_in_final", "add_form_check_out_final"
                ]
                for key_to_clear in form_keys_to_clear:
                    if key_to_clear in st.session_state:
                        del st.session_state[key_to_clear]
                
                st.rerun()

    if st.session_state.get('show_add_booking_success_dialog', False):
        show_success_notification_dialog(st.session_state.get('add_booking_success_message', "Thao tác thành công!"))

# --- TAB XỬ LÝ HTML & NỐI DỮ LIỆU ---
with tab_html_processing:
    st.header("📝 Xử lý File HTML mới và Nối vào Dữ liệu Chính")
    st.info("Tải lên file HTML chứa thông tin đặt phòng mới. Dữ liệu sẽ được hiển thị bên dưới và có thể được nối vào bảng dữ liệu chính.")

    uploaded_html_file_tab = st.file_uploader("Tải lên file HTML đặt phòng mới", type=['html'], key="html_processor_uploader")

    if 'processed_html_data_tab' not in st.session_state:
        st.session_state.processed_html_data_tab = None

    if uploaded_html_file_tab is not None:
        with st.spinner(f"Đang xử lý file HTML: {uploaded_html_file_tab.name}..."):
            df_from_html, _ = load_data_from_file(uploaded_html_file_tab)
        
        if df_from_html is not None and not df_from_html.empty:
            st.session_state.processed_html_data_tab = df_from_html
            st.success(f"Đã xử lý thành công file: {uploaded_html_file_tab.name}. Tìm thấy {len(df_from_html)} đặt phòng.")
        else:
            st.session_state.processed_html_data_tab = None
            st.error(f"Không thể xử lý file {uploaded_html_file_tab.name} hoặc file không chứa dữ liệu hợp lệ.")
    
    if st.session_state.processed_html_data_tab is not None:
        st.subheader("Dữ liệu từ file HTML vừa tải lên:")
        st.dataframe(st.session_state.processed_html_data_tab, height=300)

        if st.button("➕ Nối dữ liệu này vào Bảng dữ liệu chính", key="append_html_data_to_main_df_button"):
            if st.session_state.df is not None and st.session_state.processed_html_data_tab is not None:
                main_df_current = st.session_state.df.copy()
                html_df_to_append = st.session_state.processed_html_data_tab.copy()

                for col_dt in ['Check-in Date', 'Check-out Date', 'Booking Date']:
                    if col_dt in main_df_current.columns:
                        main_df_current[col_dt] = pd.to_datetime(main_df_current[col_dt], errors='coerce')
                    if col_dt in html_df_to_append.columns:
                        html_df_to_append[col_dt] = pd.to_datetime(html_df_to_append[col_dt], errors='coerce')
                
                num_skipped_due_to_name_and_date = 0
                rows_to_append_from_html = []
                skipped_guest_names_for_notification = set()

                if 'Tên người đặt' in main_df_current.columns and 'Tên người đặt' in html_df_to_append.columns and \
                   'Check-in Date' in main_df_current.columns and 'Check-in Date' in html_df_to_append.columns:
                    
                    main_df_current['Check-in Date'] = pd.to_datetime(main_df_current['Check-in Date']).dt.date
                    html_df_to_append['Check-in Date'] = pd.to_datetime(html_df_to_append['Check-in Date']).dt.date

                    guest_checkin_map = main_df_current.groupby('Tên người đặt')['Check-in Date'].apply(set).to_dict()

                    for index, html_row in html_df_to_append.iterrows():
                        guest_name_html = html_row['Tên người đặt']
                        check_in_date_html = html_row['Check-in Date']
                        
                        is_duplicate_by_name_and_date = False
                        if guest_name_html in guest_checkin_map:
                            if check_in_date_html in guest_checkin_map[guest_name_html]:
                                is_duplicate_by_name_and_date = True
                                skipped_guest_names_for_notification.add(guest_name_html)
                        
                        if not is_duplicate_by_name_and_date:
                            rows_to_append_from_html.append(html_row)
                        else:
                            num_skipped_due_to_name_and_date += 1
                    
                    df_to_append_final = pd.DataFrame(rows_to_append_from_html) if rows_to_append_from_html else pd.DataFrame(columns=html_df_to_append.columns)
                
                elif ('Tên người đặt' not in main_df_current.columns or 'Tên người đặt' not in html_df_to_append.columns or \
                      'Check-in Date' not in main_df_current.columns or 'Check-in Date' not in html_df_to_append.columns) and \
                     (not main_df_current.empty and not html_df_to_append.empty and 
                      (('Tên người đặt' in main_df_current.columns and 'Check-in Date' in main_df_current.columns) or 
                       ('Tên người đặt' in html_df_to_append.columns and 'Check-in Date' in html_df_to_append.columns))):
                    st.warning("Không thể thực hiện lọc trùng theo tên khách và ngày check-in do thiếu cột 'Tên người đặt' hoặc 'Check-in Date' ở một trong các bảng. Tiếp tục nối toàn bộ dữ liệu HTML (sau đó sẽ lọc theo Mã ĐP).")
                    df_to_append_final = html_df_to_append
                else:
                    df_to_append_final = html_df_to_append
                
                combined_df = pd.concat([main_df_current, df_to_append_final], ignore_index=True)
                
                initial_row_count_after_concat = len(combined_df)
                num_duplicates_by_id = 0
                if 'Số đặt phòng' in combined_df.columns:
                    if not combined_df.empty: 
                        combined_df.drop_duplicates(subset=['Số đặt phòng'], keep='first', inplace=True)
                        num_duplicates_by_id = initial_row_count_after_concat - len(combined_df)
                
                st.session_state.df = combined_df.reset_index(drop=True)
                st.session_state.active_bookings = st.session_state.df[st.session_state.df['Tình trạng'] != 'Đã hủy'].copy()
                st.session_state.room_types = get_cleaned_room_types(st.session_state.df)
                
                if skipped_guest_names_for_notification:
                    skipped_names_str = ", ".join(sorted(list(skipped_guest_names_for_notification)))
                    st.warning(f"Lưu ý: {num_skipped_due_to_name_and_date} đặt phòng từ HTML cho khách ({skipped_names_str}) đã bị bỏ qua do trùng tên và ngày check-in với đặt phòng hiện có.")

                if num_duplicates_by_id > 0:
                    st.info(f"{num_duplicates_by_id} đặt phòng bổ sung đã bị loại bỏ do Mã Đặt Phòng (sau khi xử lý trùng tên/ngày).")

                if not skipped_guest_names_for_notification and num_duplicates_by_id == 0:
                    st.success("Đã nối dữ liệu từ HTML vào bảng chính. Không có hàng nào bị loại bỏ do trùng lặp.")
                else:
                    st.success("Hoàn tất quá trình nối dữ liệu từ HTML. Vui lòng xem các thông báo (nếu có) ở trên để biết chi tiết về các hàng bị bỏ qua.")
                
                st.info("Vui lòng kiểm tra lại dữ liệu ở tab 'Quản lý đặt phòng'.")
                st.session_state.processed_html_data_tab = None
                st.rerun()
            else:
                st.warning("Không có dữ liệu chính hoặc dữ liệu HTML để thực hiện nối.")

# --- TAB MẪU TIN NHẮN ---
with tab_message_templates:
    st.header("💌 Quản lý Mẫu Tin Nhắn")

    st.subheader("Đồng bộ với Google Sheets (Định dạng 3 cột)")
    
    creds_path_msg = "streamlit-api-461302-5dfbcb4beaba.json"
    sheet_id_msg = st.session_state.get("gsheet_id", "13kQETOUGCVUwUqZrxeLy-WAj3b17SugI4L8Oq09SX2w")
    worksheet_name_msg = "MessageTemplate"
    creds_dict_msg = st.secrets["gcp_service_account"]

    col_gsheet1, col_gsheet2 = st.columns(2)

    with col_gsheet1:
        if st.button("📥 Tải mẫu từ Google Sheets", key="load_templates_from_gsheet_v3", use_container_width=True):
            try:
                with st.spinner(f"Đang tải mẫu từ Google Sheet '{worksheet_name_msg}'..."):
                    df_templates = import_from_gsheet(sheet_id_msg, creds_dict_msg, worksheet_name_msg)
                    
                    if df_templates is not None and not df_templates.empty and all(c in df_templates.columns for c in ['Category', 'Label', 'Message']):
                        templates = {}
                        for _, row in df_templates.iterrows():
                            category = row['Category']
                            label = row['Label']
                            message = row['Message']
                            if category not in templates:
                                templates[category] = []
                            templates[category].append((label, message))
                        
                        st.session_state.message_templates_dict = templates
                        st.session_state.raw_template_content_for_download = format_templates_to_text(templates)
                        
                        st.success(f"Đã tải và làm mới mẫu tin nhắn từ Google Sheets thành công!")
                        st.rerun()
                    else:
                        st.warning("Không tìm thấy dữ liệu hoặc sai định dạng (cần cột Category, Label, Message).")
            except Exception as e:
                st.error(f"Lỗi khi tải mẫu tin nhắn từ Google Sheets: {e}")

    with col_gsheet2:
        if st.button("📤 Lưu mẫu lên Google Sheets", key="save_templates_to_gsheet_v3", use_container_width=True, type="primary"):
            try:
                with st.spinner(f"Đang lưu mẫu lên Google Sheet '{worksheet_name_msg}'..."):
                    current_templates = st.session_state.get('message_templates_dict')
                    if current_templates:
                        template_list_for_df = []
                        for category, labeled_messages in current_templates.items():
                            for label, message in labeled_messages:
                                template_list_for_df.append({
                                    'Category': category,
                                    'Label': label,
                                    'Message': message
                                })

                        if template_list_for_df:
                            df_to_upload = pd.DataFrame(template_list_for_df)
                            upload_to_gsheet(df_to_upload, sheet_id_msg, creds_dict_msg, worksheet_name_msg)
                            st.success("Đã lưu thành công tất cả mẫu tin nhắn lên Google Sheets!")
                        else:
                            st.warning("Không có mẫu tin nhắn để lưu.")
                    else:
                        st.warning("Không có mẫu tin nhắn nào trong hệ thống để lưu.")
            except Exception as e:
                st.error(f"Lỗi khi lưu mẫu tin nhắn lên Google Sheets: {e}")

    st.markdown("---")
    st.subheader("Thêm hoặc Cập nhật Mẫu Tin Nhắn")
    with st.form("add_template_form", clear_on_submit=True):
        new_template_category = st.text_input("Chủ đề chính (VD: CHECK OUT, WIFI INFO):").upper().strip()
        new_template_label = st.text_input("Nhãn phụ (VD: 1., 2., hoặc để trống cho tin nhắn mặc định):").strip()
        new_template_message = st.text_area("Nội dung tin nhắn:", height=150)
        submit_add_template = st.form_submit_button("➕ Thêm / Cập nhật mẫu này")

        if submit_add_template:
            if not new_template_category or not new_template_message:
                st.error("Chủ đề chính và Nội dung tin nhắn không được để trống!")
            else:
                label_to_add = new_template_label if new_template_label else "DEFAULT"
                current_templates = st.session_state.get('message_templates_dict', {}).copy()
                
                if new_template_category not in current_templates:
                    current_templates[new_template_category] = []
                
                label_exists_at_index = -1
                for idx, (lbl, _) in enumerate(current_templates[new_template_category]):
                    if lbl == label_to_add:
                        label_exists_at_index = idx
                        break
                
                if label_exists_at_index != -1:
                    current_templates[new_template_category][label_exists_at_index] = (label_to_add, new_template_message)
                    st.success(f"Đã cập nhật mẫu tin nhắn '{label_to_add}' trong chủ đề '{new_template_category}'.")
                else:
                    current_templates[new_template_category].append((label_to_add, new_template_message))
                    st.success(f"Đã thêm mẫu tin nhắn '{label_to_add}' vào chủ đề '{new_template_category}'.")
                
                st.session_state.message_templates_dict = current_templates
                st.session_state.raw_template_content_for_download = format_templates_to_text(current_templates)
                st.rerun()

    st.markdown("---")
    st.subheader("Danh Sách Mẫu Tin Nhắn Hiện Tại")

    if not st.session_state.get('message_templates_dict'):
        st.info("Chưa có mẫu tin nhắn nào. Hãy thêm mới hoặc tải từ Google Sheets.")
    else:
        for category, labeled_messages in sorted(st.session_state.message_templates_dict.items()):
            with st.expander(f"Chủ đề: {category}", expanded=False):
                if not labeled_messages:
                    st.caption("Không có tin nhắn nào cho chủ đề này.")
                    continue
                for i, (label, message) in enumerate(labeled_messages):
                    st.markdown(f"**Nhãn: `{label}`**")
                    st.text_area(
                        label=f"Content for {label}",
                        value=message,
                        height=max(80, len(message.split('\n')) * 20 + 20),
                        key=f"msg_{category}_{i}", 
                        disabled=True,
                        label_visibility="collapsed"
                    )
                    if i < len(labeled_messages) - 1:
                        st.markdown("---")

# --- SIDEBAR CUỐI TRANG ---
st.sidebar.markdown("---"); st.sidebar.subheader("Thông tin & Tiện ích")

if st.sidebar.button("📧 Gửi Cập Nhật Telegram Hàng Ngày", key="send_daily_telegram_update_button"):
    asyncio.run(send_daily_status_telegram())

st.sidebar.info("""🏨 **Hệ thống Quản lý Phòng Khách sạn v3.2.6**\n\n**Tính năng chính:**\n- Theo dõi tình trạng phòng.\n- Lịch trực quan.\n- Quản lý đặt phòng chi tiết.\n- Phân tích doanh thu.\n- Thêm đặt phòng mới (thủ công & từ ảnh).\n- Xuất dữ liệu CSV & HTML.""")

if st.sidebar.button("🔄 Làm mới dữ liệu & Tải lại từ đầu", key="refresh_data_button_key_final_v2", help="Xóa toàn bộ dữ liệu và bắt đầu lại."):
    keys_to_clear_sidebar = [
        'df', 'active_bookings', 'room_types', 'data_source', 'uploaded_file_name', 
        'last_action_message', 'current_date_calendar', 'selected_calendar_date', 
        'booking_sort_column', 'booking_sort_ascending', 'editing_booking_id_for_dialog',
        'add_form_check_in_final', 'add_form_check_out_final', 
        'message_templates_dict', 'raw_template_content_for_download',
        'image_extracted_data_log', 'image_to_process', 'extracted_list_data'
    ]
    form_keys_to_clear_refresh = [
        "form_v8_guest_name", "form_v8_room_type", "form_v8_genius",
        "form_v8_status", "form_v8_total_payment", "form_v8_commission",
        "form_v8_currency", "form_v8_booking_id", "form_v8_nguoi_thu_tien"
    ]
    keys_to_clear_sidebar.extend(form_keys_to_clear_refresh)

    for key in list(st.session_state.keys()):
        if key.startswith("select_booking_cb_") or key.startswith("dialog_cin_") or key.startswith("dialog_cout_") or key.startswith("tpl_cat_"):
            del st.session_state[key]
            
    for key_to_del_sidebar in keys_to_clear_sidebar:
        if key_to_del_sidebar in st.session_state: 
            del st.session_state[key_to_del_sidebar]
    st.rerun()

if active_bookings is not None and not active_bookings.empty and room_types:
    st.sidebar.markdown("---"); st.sidebar.subheader("🔔 Thông báo nhanh")
    notifications_list_sidebar = []
    today_sb_notif_date = datetime.date.today()
    tomorrow_sb_notif_date = today_sb_notif_date + timedelta(days=1)
    for room_type_alert_sb_item in room_types: 
        availability_sb_room_tomorrow = get_room_availability(tomorrow_sb_notif_date, active_bookings, [room_type_alert_sb_item], ROOM_UNIT_PER_ROOM_TYPE)
        available_tomorrow_count = availability_sb_room_tomorrow.get(room_type_alert_sb_item, ROOM_UNIT_PER_ROOM_TYPE)
        room_display_name_sb = room_type_alert_sb_item[:20] + "..." if len(room_type_alert_sb_item) > 20 else room_type_alert_sb_item
        if available_tomorrow_count == 0: notifications_list_sidebar.append(f"🔴 **{room_display_name_sb}**: HẾT PHÒNG ngày mai!")
        elif available_tomorrow_count == 1: notifications_list_sidebar.append(f"🟡 **{room_display_name_sb}**: Chỉ còn 1 phòng ({available_tomorrow_count} đơn vị) ngày mai.")
        elif available_tomorrow_count < ROOM_UNIT_PER_ROOM_TYPE : notifications_list_sidebar.append(f"🟠 **{room_display_name_sb}**: Còn {available_tomorrow_count} phòng ngày mai.")

    today_activity_sb_data = get_daily_activity(today_sb_notif_date, active_bookings)
    if today_activity_sb_data['check_in']: notifications_list_sidebar.append(f"🛬 **{len(today_activity_sb_data['check_in'])}** check-in hôm nay.")
    if today_activity_sb_data['check_out']: notifications_list_sidebar.append(f"🛫 **{len(today_activity_sb_data['check_out'])}** check-out hôm nay.")
    
    overall_tomorrow_info = get_overall_calendar_day_info(tomorrow_sb_notif_date, active_bookings, TOTAL_HOTEL_CAPACITY)
    if overall_tomorrow_info['available_units'] == 0:
        notifications_list_sidebar.append(f"🆘 **TOÀN KHÁCH SẠN**: HẾT PHÒNG ngày mai!")
    elif overall_tomorrow_info['available_units'] == 1:
        notifications_list_sidebar.append(f"⚠️ **TOÀN KHÁCH SẠN**: Chỉ còn 1 phòng TRỐNG ngày mai.")

    if notifications_list_sidebar:
        for notif_item_sb in notifications_list_sidebar: st.sidebar.warning(notif_item_sb)
    else: st.sidebar.success("✅ Mọi hoạt động đều ổn định!")

st.sidebar.markdown("---"); st.sidebar.subheader("Xuất dữ liệu")
df_main_export_final = st.session_state.get('df')
if df_main_export_final is not None and not df_main_export_final.empty:
    df_export_final_copy_csv = df_main_export_final.copy()
    date_columns_to_format_export = ['Check-in Date', 'Check-out Date', 'Booking Date']
    for col_date_export_final_item in date_columns_to_format_export:
        if col_date_export_final_item in df_export_final_copy_csv.columns:
            df_export_final_copy_csv[col_date_export_final_item] = pd.to_datetime(df_export_final_copy_csv[col_date_export_final_item], errors='coerce').dt.strftime('%d/%m/%Y')
    try:
        full_csv_data_final_export = df_export_final_copy_csv.to_csv(index=False).encode('utf-8-sig')
        st.sidebar.download_button(label="📋 Tải xuống toàn bộ dữ liệu (CSV)", data=full_csv_data_final_export, file_name=f"DanhSachDatPhong_{datetime.date.today().strftime('%Y%m%d')}.csv", mime="text/csv", key="download_full_csv_key_final_v2", help="Tải xuống toàn bộ dữ liệu đặt phòng hiện tại.")
    except Exception as e_export_final: st.sidebar.error(f"Lỗi khi chuẩn bị file CSV: {e_export_final}")

    try:
        df_html_export = df_main_export_final.copy()
        display_columns_for_html = [
            'Số đặt phòng', 'Tên người đặt', 'Tên chỗ nghỉ',
            'Check-in Date', 'Check-out Date', 'Stay Duration',
            'Giá mỗi đêm', 'Tổng thanh toán', 'Tình trạng', 'Booking Date',
            'Người thu tiền'
        ]
        existing_display_columns_html = [col for col in display_columns_for_html if col in df_html_export.columns]

        df_html_export_subset = df_html_export[existing_display_columns_html].copy() if existing_display_columns_html else df_html_export.copy()

        for col_date_html in date_columns_to_format_export:
            if col_date_html in df_html_export_subset.columns:
                df_html_export_subset.loc[:, col_date_html] = pd.to_datetime(df_html_export_subset[col_date_html], errors='coerce').dt.strftime('%d/%m/%Y')

        base_display_columns_map_html = {
            'Số đặt phòng': 'Mã ĐP', 'Tên người đặt': 'Khách',
            'Tên chỗ nghỉ': 'Loại phòng', 'Check-in Date': 'Check-in',
            'Check-out Date': 'Check-out', 'Stay Duration': 'Số đêm',
            'Tình trạng': 'Trạng thái', 'Tổng thanh toán': 'Tổng tiền (VND)',
            'Giá mỗi đêm': 'Giá/đêm (VND)',
            'Booking Date': 'Ngày thêm khách',
            'Người thu tiền': 'Người thu tiền'
        }
        df_html_export_subset_renamed = df_html_export_subset.rename(columns=base_display_columns_map_html)

        html_data = df_html_export_subset_renamed.to_html(index=False, border=1, classes="dataframe_html_export table table-striped table-hover", justify="center", escape=False)

        html_string_final = f"""
        <html>
            <head>
                <title>Danh Sách Đặt Phòng</title>
                <meta charset="UTF-8">
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; }}
                    .dataframe_html_export {{
                        border-collapse: collapse;
                        width: 90%;
                        margin: 20px auto;
                        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                    }}
                    .dataframe_html_export th, .dataframe_html_export td {{
                        border: 1px solid #ddd;
                        padding: 10px;
                        text-align: left;
                    }}
                    .dataframe_html_export th {{
                        background-color: #f2f2f2;
                        font-weight: bold;
                    }}
                    .dataframe_html_export tr:nth-child(even) {{background-color: #f9f9f9;}}
                    .dataframe_html_export tr:hover {{background-color: #f1f1f1;}}
                    h1 {{ text-align: center; color: #333; }}
                </style>
            </head>
            <body>
                <h1>Danh Sách Đặt Phòng - Ngày {datetime.date.today().strftime('%d/%m/%Y')}</h1>
                {html_data}
            </body>
        </html>
        """

        st.sidebar.download_button(
            label="🌐 Tải xuống toàn bộ dữ liệu (HTML)",
            data=html_string_final.encode('utf-8'),
            file_name=f"DanhSachDatPhong_{datetime.date.today().strftime('%Y%m%d')}.html",
            mime="text/html",
            key="download_full_html_key",
            help="Tải xuống toàn bộ dữ liệu đặt phòng hiện tại dưới dạng file HTML."
        )
    except Exception as e_export_html:
        st.sidebar.error(f"Lỗi khi chuẩn bị file HTML để xuất: {e_export_html}")

else:
    st.sidebar.info("Chưa có dữ liệu để xuất.")

# --- DIALOG CHỈNH SỬA ĐẶT PHÒNG ---
if st.session_state.get('editing_booking_id_for_dialog') is not None:
    booking_id_to_edit = st.session_state.editing_booking_id_for_dialog
    booking_to_edit_df = None
    original_booking_index_edit = None

    if st.session_state.get('df') is not None and 'Số đặt phòng' in st.session_state.df.columns:
        booking_to_edit_df_list = st.session_state.df[st.session_state.df['Số đặt phòng'] == booking_id_to_edit]
        if not booking_to_edit_df_list.empty:
            booking_to_edit_df = booking_to_edit_df_list.iloc[0:1]
            original_booking_index_edit = booking_to_edit_df.index[0]
        elif str(booking_id_to_edit).startswith("index_"):
            try:
                idx_val = int(str(booking_id_to_edit).split("_")[1])
                if idx_val in st.session_state.df.index:
                    booking_to_edit_df = st.session_state.df.loc[[idx_val]]
                    original_booking_index_edit = idx_val
                    if 'Số đặt phòng' in booking_to_edit_df.columns and pd.notna(booking_to_edit_df.iloc[0]['Số đặt phòng']):
                        st.session_state.editing_booking_id_for_dialog = booking_to_edit_df.iloc[0]['Số đặt phòng']
                        booking_id_to_edit = st.session_state.editing_booking_id_for_dialog

            except (IndexError, ValueError):
                st.error(f"Không thể tìm thấy đặt phòng với ID chỉ mục không hợp lệ: {booking_id_to_edit}")
                st.session_state.editing_booking_id_for_dialog = None
                st.rerun()


    if booking_to_edit_df is not None and not booking_to_edit_df.empty:
        booking_data_edit = booking_to_edit_df.iloc[0].to_dict()

        @st.dialog(f"Chỉnh sửa Đặt phòng: {booking_id_to_edit}")
        def edit_booking_dialog():
            st.subheader(f"Chỉnh sửa thông tin cho Mã ĐP: {booking_data_edit.get('Số đặt phòng', booking_id_to_edit)}")

            def get_val(key, default_val):
                val = booking_data_edit.get(key)
                if pd.isna(val): return default_val
                return val

            try:
                default_check_in_date_edit = pd.to_datetime(get_val('Check-in Date', datetime.date.today())).date()
            except: default_check_in_date_edit = datetime.date.today()

            try:
                default_check_out_date_edit = pd.to_datetime(get_val('Check-out Date', datetime.date.today() + timedelta(days=1))).date()
            except: default_check_out_date_edit = datetime.date.today() + timedelta(days=1)
            
            if default_check_out_date_edit <= default_check_in_date_edit:
                default_check_out_date_edit = default_check_in_date_edit + timedelta(days=1)


            with st.form(key=f"edit_booking_form_dialog_{booking_id_to_edit}"):
                st.subheader("Thông tin đặt phòng")
                edit_col1, edit_col2 = st.columns(2)
                with edit_col1:
                    edited_guest_name = st.text_input("Tên khách*", value=str(get_val('Tên người đặt', '')), key=f"edit_guest_name_{booking_id_to_edit}")
                    
                    current_room_types_edit = st.session_state.get('room_types', [])
                    default_room_type_edit = str(get_val('Tên chỗ nghỉ', ''))
                    room_type_index_edit = current_room_types_edit.index(default_room_type_edit) if default_room_type_edit in current_room_types_edit else 0
                    edited_room_type = st.selectbox("Loại phòng*", options=current_room_types_edit, index=room_type_index_edit, key=f"edit_room_type_{booking_id_to_edit}")

                    genius_options_edit = ["Không", "Có"]
                    default_genius_edit = str(get_val('Thành viên Genius', 'Không'))
                    genius_index_edit = genius_options_edit.index(default_genius_edit) if default_genius_edit in genius_options_edit else 0
                    edited_genius_member = st.selectbox("Thành viên Genius", options=genius_options_edit, index=genius_index_edit, key=f"edit_genius_{booking_id_to_edit}")

                with edit_col2:
                    edited_check_in_date = st.date_input("Ngày check-in*", value=default_check_in_date_edit, key=f"edit_check_in_{booking_id_to_edit}")
                    
                    min_checkout_for_edit = edited_check_in_date + timedelta(days=1)
                    current_checkout_val_for_edit = default_check_out_date_edit
                    if current_checkout_val_for_edit < min_checkout_for_edit:
                        current_checkout_val_for_edit = min_checkout_for_edit

                    edited_check_out_date = st.date_input("Ngày check-out*", value=current_checkout_val_for_edit, min_value=min_checkout_for_edit, key=f"edit_check_out_{booking_id_to_edit}")
                    
                    status_options_edit = ["OK", "Đã hủy", "Chờ xử lý"]
                    default_status_edit = str(get_val('Tình trạng', 'OK'))
                    status_index_edit = status_options_edit.index(default_status_edit) if default_status_edit in status_options_edit else 0
                    edited_booking_status = st.selectbox("Trạng thái đặt phòng", options=status_options_edit, index=status_index_edit, key=f"edit_status_{booking_id_to_edit}")

                st.markdown("---"); st.subheader("Thông tin thanh toán")
                edit_col3, edit_col4 = st.columns(2)
                with edit_col3:
                    edited_total_payment = st.number_input("Tổng thanh toán (VND)*", min_value=0, value=int(float(get_val('Tổng thanh toán', 0.0))), step=50000, format="%d", key=f"edit_total_payment_{booking_id_to_edit}")
                    edited_commission = st.number_input("Hoa hồng (VND)", min_value=0, value=int(float(get_val('Hoa hồng', 0.0))), step=10000, format="%d", key=f"edit_commission_{booking_id_to_edit}")
                with edit_col4:
                    currency_options_edit = ["VND", "USD"]
                    default_currency_edit = str(get_val('Tiền tệ', 'VND'))
                    currency_index_edit = currency_options_edit.index(default_currency_edit) if default_currency_edit in currency_options_edit else 0
                    edited_currency = st.selectbox("Tiền tệ", options=currency_options_edit, index=currency_index_edit, key=f"edit_currency_{booking_id_to_edit}")
                    edited_booking_id_display_only = st.text_input("Mã đặt phòng (không thể sửa)", value=str(get_val('Số đặt phòng', booking_id_to_edit)), disabled=True, key=f"edit_booking_id_disp_{booking_id_to_edit}")
                    
                    collector_options_edit = ["LOC LE", "THAO LE", "N/A"]
                    default_collector_edit = str(get_val('Người thu tiền', 'N/A'))
                    collector_index_edit = collector_options_edit.index(default_collector_edit) if default_collector_edit in collector_options_edit else (collector_options_edit.index("N/A") if "N/A" in collector_options_edit else 0)
                    edited_collector = st.selectbox("Người thu tiền*", options=collector_options_edit, index=collector_index_edit, key=f"edit_collector_{booking_id_to_edit}")


                submit_edit_button = st.form_submit_button("💾 Lưu thay đổi", type="primary")
                
                if st.form_submit_button("Hủy bỏ"):
                    st.session_state.editing_booking_id_for_dialog = None
                    st.rerun()

            if submit_edit_button:
                edit_errors = []
                if not edited_guest_name.strip(): edit_errors.append("Tên khách không được để trống.")
                if edited_check_out_date <= edited_check_in_date: edit_errors.append("Ngày check-out phải sau ngày check-in.")
                if edited_total_payment <= 0 and edited_booking_status == "OK": edit_errors.append("Tổng thanh toán phải > 0 cho đặt phòng 'OK'.")
                if not edited_collector: edit_errors.append("Người thu tiền không được để trống.")

                if not edit_errors and edited_booking_status == "OK":
                    active_bookings_for_edit_check = st.session_state.get('active_bookings')
                    if active_bookings_for_edit_check is not None:
                        temp_active_bookings_for_check = active_bookings_for_edit_check[active_bookings_for_edit_check['Số đặt phòng'] != booking_id_to_edit]
                        
                        current_check_date_edit_avail = edited_check_in_date
                        while current_check_date_edit_avail < edited_check_out_date:
                            availability_check_specific_edit = get_room_availability(current_check_date_edit_avail, temp_active_bookings_for_check, [edited_room_type], ROOM_UNIT_PER_ROOM_TYPE)
                            if availability_check_specific_edit.get(edited_room_type, 0) <= 0:
                                edit_errors.append(f"Phòng '{edited_room_type}' đã hết vào ngày {current_check_date_edit_avail.strftime('%d/%m/%Y')} (không tính đặt phòng này).")
                                break
                            
                            occupied_on_this_day_edit = len(temp_active_bookings_for_check[
                                (temp_active_bookings_for_check['Check-in Date'].dt.date <= current_check_date_edit_avail) &
                                (temp_active_bookings_for_check['Check-out Date'].dt.date > current_check_date_edit_avail) &
                                (temp_active_bookings_for_check['Tình trạng'] != 'Đã hủy')
                            ])
                            if occupied_on_this_day_edit >= TOTAL_HOTEL_CAPACITY:
                                edit_errors.append(f"Ngày {current_check_date_edit_avail.strftime('%d/%m/%Y')} đã có đủ {TOTAL_HOTEL_CAPACITY} khách (không tính đặt phòng này). Không thể thay đổi.")
                                break
                            current_check_date_edit_avail += timedelta(days=1)
                
                if edit_errors:
                    for err in edit_errors: st.error(err)
                else:
                    df_main = st.session_state.df
                    idx_to_update = original_booking_index_edit

                    if idx_to_update is not None and idx_to_update in df_main.index:
                        df_main.loc[idx_to_update, 'Tên người đặt'] = edited_guest_name.strip()
                        df_main.loc[idx_to_update, 'Tên chỗ nghỉ'] = edited_room_type
                        df_main.loc[idx_to_update, 'Thành viên Genius'] = edited_genius_member
                        df_main.loc[idx_to_update, 'Check-in Date'] = pd.Timestamp(edited_check_in_date)
                        df_main.loc[idx_to_update, 'Check-out Date'] = pd.Timestamp(edited_check_out_date)
                        df_main.loc[idx_to_update, 'Ngày đến'] = f"ngày {edited_check_in_date.day} tháng {edited_check_in_date.month} năm {edited_check_in_date.year}"
                        df_main.loc[idx_to_update, 'Ngày đi'] = f"ngày {edited_check_out_date.day} tháng {edited_check_out_date.month} năm {edited_check_out_date.year}"
                        df_main.loc[idx_to_update, 'Tình trạng'] = edited_booking_status
                        df_main.loc[idx_to_update, 'Tổng thanh toán'] = float(edited_total_payment)
                        df_main.loc[idx_to_update, 'Hoa hồng'] = float(edited_commission)
                        df_main.loc[idx_to_update, 'Tiền tệ'] = edited_currency
                        df_main.loc[idx_to_update, 'Người thu tiền'] = edited_collector

                        stay_duration_edited = (edited_check_out_date - edited_check_in_date).days
                        df_main.loc[idx_to_update, 'Stay Duration'] = stay_duration_edited
                        df_main.loc[idx_to_update, 'Giá mỗi đêm'] = round(float(edited_total_payment) / stay_duration_edited) if stay_duration_edited > 0 else 0.0
                        
                        if 'Booking Date' not in df_main.columns or pd.isna(df_main.loc[idx_to_update, 'Booking Date']):
                             df_main.loc[idx_to_update, 'Booking Date'] = pd.Timestamp(datetime.date.today())
                             df_main.loc[idx_to_update, 'Được đặt vào'] = f"ngày {datetime.date.today().day} tháng {datetime.date.today().month} năm {datetime.date.today().year}"
                        if 'Vị trí' not in df_main.columns or pd.isna(df_main.loc[idx_to_update, 'Vị trí']):
                             df_main.loc[idx_to_update, 'Vị trí'] = "N/A (Chưa xác định)"


                        st.session_state.df = df_main
                        st.session_state.active_bookings = st.session_state.df[st.session_state.df['Tình trạng'] != 'Đã hủy'].copy()
                        st.session_state.room_types = get_cleaned_room_types(st.session_state.df)
                        st.session_state.last_action_message = f"Đã cập nhật thành công đặt phòng '{booking_id_to_edit}'."
                        st.session_state.editing_booking_id_for_dialog = None
                        st.session_state.selected_calendar_date = None

                        if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
                            telegram_message_update = f"✏️ Đặt phòng ĐƯỢC CẬP NHẬT!\n"
                            telegram_message_update += f"🆔 Mã ĐP: {booking_id_to_edit}\n"
                            telegram_message_update += f"👤 Khách: {edited_guest_name.strip()}\n"
                            telegram_message_update += f"🏠 Phòng: {edited_room_type}\n"
                            telegram_message_update += f"📅 Check-in: {edited_check_in_date.strftime('%d/%m/%Y')}\n"
                            telegram_message_update += f"📅 Check-out: {edited_check_out_date.strftime('%d/%m/%Y')}\n"
                            telegram_message_update += f"💰 Tổng TT: {edited_total_payment:,.0f} {edited_currency}\n"
                            telegram_message_update += f"ℹ️ Trạng thái: {edited_booking_status}"
                            asyncio.run(send_telegram_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, telegram_message_update))

                        st.rerun()
                    else:
                        st.error(f"Lỗi: Không tìm thấy đặt phòng với ID {booking_id_to_edit} hoặc chỉ mục {idx_to_update} để cập nhật trong DataFrame.")
                        st.session_state.editing_booking_id_for_dialog = None
                        st.rerun()
        
        edit_booking_dialog()
    
    elif st.session_state.get('editing_booking_id_for_dialog') is not None:
        st.error(f"Không tìm thấy thông tin đặt phòng để chỉnh sửa cho ID: {st.session_state.get('editing_booking_id_for_dialog')}. Đặt phòng có thể đã bị xóa hoặc ID không hợp lệ.")
        st.session_state.editing_booking_id_for_dialog = None

# --- TAB PHÂN TÍCH ---
with tab_analytics:
    st.header("📈 Phân tích & Báo cáo")
    if df is not None and not df.empty and active_bookings is not None and not active_bookings.empty:
        st.sidebar.subheader("Bộ lọc Phân tích")
        min_analytics_filter = min_date_val; max_analytics_filter = max_date_val
        if min_analytics_filter > max_analytics_filter: max_analytics_filter = min_analytics_filter + timedelta(days=1)
        start_date_analytics = st.sidebar.date_input("Ngày bắt đầu (phân tích C/I):", min_analytics_filter, min_value=min_analytics_filter, max_value=max_analytics_filter, key="analytics_start_date_key", help="Lọc theo ngày Check-in.")
        end_date_analytics = st.sidebar.date_input("Ngày kết thúc (phân tích C/I):", max_analytics_filter, min_value=start_date_analytics, max_value=max_analytics_filter, key="analytics_end_date_key", help="Lọc theo ngày Check-in.")
        if start_date_analytics > end_date_analytics: st.error("Lỗi: Ngày bắt đầu không thể sau ngày kết thúc.")
        else:
            analytics_df_filtered = active_bookings[(active_bookings['Check-in Date'].dt.date >= start_date_analytics) & (active_bookings['Check-in Date'].dt.date <= end_date_analytics)].copy()
            
            st.subheader(f"Số liệu tổng hợp đến ngày {datetime.date.today().strftime('%d/%m/%Y')}")
            col_current_metric1, col_current_metric2 = st.columns(2)
            
            today_for_analytics = datetime.date.today()
            checked_in_to_date_df = active_bookings[
                (active_bookings['Check-in Date'].dt.date <= today_for_analytics) &
                (active_bookings['Tình trạng'] != 'Đã hủy')
            ].copy()

            if not checked_in_to_date_df.empty:
                total_guests_checked_in_actual = len(checked_in_to_date_df)
                checked_in_to_date_df['Stay Duration'] = pd.to_numeric(checked_in_to_date_df['Stay Duration'], errors='coerce').fillna(0)
                total_nights_checked_in_actual = checked_in_to_date_df['Stay Duration'].sum()
            else:
                total_guests_checked_in_actual = 0
                total_nights_checked_in_actual = 0

            with col_current_metric1:
                st.metric("Tổng lượt khách đã nhận phòng (đến hiện tại)", f"{total_guests_checked_in_actual:,.0f}")
            with col_current_metric2:
                st.metric("Tổng số đêm khách đã nhận phòng (đến hiện tại)", f"{total_nights_checked_in_actual:,.0f}")
            
            st.markdown("---")

            if not analytics_df_filtered.empty:
                st.subheader(f"Số liệu trong khoảng đã chọn ({start_date_analytics.strftime('%d/%m/%Y')} đến {end_date_analytics.strftime('%d/%m/%Y')})")
                col_metric_anl1, col_metric_anl2, col_metric_anl3, col_metric_anl4 = st.columns(4)
                with col_metric_anl1:
                    analytics_df_filtered['Stay Duration'] = pd.to_numeric(analytics_df_filtered['Stay Duration'], errors='coerce').fillna(0)
                    mean_stay = analytics_df_filtered['Stay Duration'].mean() if not analytics_df_filtered['Stay Duration'].empty else 0
                    st.metric("TB thời gian ở (ngày)", f"{mean_stay:.1f}")
                with col_metric_anl2: total_nights = analytics_df_filtered['Stay Duration'].sum(); st.metric("Tổng số đêm đã đặt", f"{total_nights:,.0f}")
                with col_metric_anl3: mean_payment = analytics_df_filtered['Tổng thanh toán'].mean() if not analytics_df_filtered['Tổng thanh toán'].empty else 0; st.metric("TB Tổng TT/đặt (VND)", f"{mean_payment:,.0f}")
                with col_metric_anl4: st.metric("Tổng lượt khách (OK)", f"{len(analytics_df_filtered):,.0f}")
                st.markdown("---")
                st.subheader("Thống kê theo khách hàng")
                if 'Tên người đặt' in analytics_df_filtered.columns and 'Tổng thanh toán' in analytics_df_filtered.columns:
                    if 'Booking Date' not in analytics_df_filtered.columns:
                        analytics_df_filtered['Booking Date'] = pd.NaT
                    analytics_df_filtered['Booking Date'] = pd.to_datetime(analytics_df_filtered['Booking Date'], errors='coerce')
                    if 'Người thu tiền' not in analytics_df_filtered.columns:
                        analytics_df_filtered['Người thu tiền'] = 'N/A'

                    analytics_df_sorted_for_collector = analytics_df_filtered.sort_values(
                        by=['Tên người đặt', 'Booking Date'], ascending=[True, False]
                    )
                    most_recent_collector = analytics_df_sorted_for_collector.groupby('Tên người đặt').first()['Người thu tiền']

                    guest_stats_anl = analytics_df_filtered.groupby('Tên người đặt').agg(
                        total_payment_sum_agg=('Tổng thanh toán', 'sum'), 
                        avg_stay_duration_agg=('Stay Duration', 'mean'), 
                        last_check_in_date_agg=('Check-in Date', 'max')
                    ).reset_index()
                    
                    guest_stats_anl = pd.merge(guest_stats_anl, most_recent_collector, on='Tên người đặt', how='left')
                    
                    guest_stats_anl.rename(columns={
                        'Tên người đặt': 'Tên khách', 
                        'total_payment_sum_agg': 'Tổng thanh toán (VND)', 
                        'avg_stay_duration_agg': 'TB số đêm ở', 
                        'last_check_in_date_agg': 'Ngày nhận phòng'
                    }, inplace=True)
                    
                    guest_stats_display_anl = guest_stats_anl.copy()
                    if 'Tổng thanh toán (VND)' in guest_stats_display_anl.columns: guest_stats_display_anl['Tổng thanh toán (VND)'] = guest_stats_display_anl['Tổng thanh toán (VND)'].map('{:,.0f}'.format)
                    if 'TB số đêm ở' in guest_stats_display_anl.columns: guest_stats_display_anl['TB số đêm ở'] = guest_stats_display_anl['TB số đêm ở'].map('{:.1f}'.format)
                    if 'Ngày nhận phòng' in guest_stats_display_anl.columns: guest_stats_display_anl['Ngày nhận phòng'] = pd.to_datetime(guest_stats_display_anl['Ngày nhận phòng']).dt.strftime('%d/%m/%Y')
                    
                    cols_display_order = ['Tên khách', 'Tổng thanh toán (VND)', 'TB số đêm ở', 'Ngày nhận phòng']
                    existing_cols_for_display = [col for col in cols_display_order if col in guest_stats_display_anl.columns]

                    st.dataframe(guest_stats_display_anl[existing_cols_for_display].set_index('Tên khách').sort_values(by='Tổng thanh toán (VND)', ascending=False), use_container_width=True)
                    if not guest_stats_anl.empty and 'Tổng thanh toán (VND)' in guest_stats_anl.columns:
                        guest_stats_anl_chart = guest_stats_anl.copy()
                        guest_stats_anl_chart['Tổng thanh toán (VND)'] = pd.to_numeric(guest_stats_anl_chart['Tổng thanh toán (VND)'].replace({',': ''}, regex=True), errors='coerce').fillna(0)
                        guest_revenue_chart_df_anl = guest_stats_anl_chart.sort_values(by='Tổng thanh toán (VND)', ascending=False).head(15)
                        fig_guest_revenue_anl = px.bar(guest_revenue_chart_df_anl, x='Tên khách', y='Tổng thanh toán (VND)', title='Top 15 khách hàng theo tổng thanh toán', labels={'Tổng thanh toán (VND)': 'Tổng thanh toán (VND)', 'Tên khách': 'Tên khách hàng'}, color='Tổng thanh toán (VND)', color_continuous_scale=px.colors.sequential.Viridis, text_auto='.2s')
                        fig_guest_revenue_anl.update_layout(xaxis_tickangle=-45, height=400); st.plotly_chart(fig_guest_revenue_anl, use_container_width=True)
                else: st.info("Không đủ dữ liệu khách hàng để phân tích.")
                st.markdown("---")
                st.subheader("Phân tích khách hàng theo Genius")
                if 'Thành viên Genius' in analytics_df_filtered.columns:
                    col_genius_anl1, col_genius_anl2 = st.columns(2)
                    with col_genius_anl1:
                        genius_counts_anl = analytics_df_filtered['Thành viên Genius'].value_counts().reset_index(); genius_counts_anl.columns = ['Loại thành viên', 'Số lượng đặt phòng']
                        fig_genius_pie_anl = px.pie(genius_counts_anl, names='Loại thành viên', values='Số lượng đặt phòng', title='Tỷ lệ đặt phòng theo thành viên Genius', hole=0.3)
                        fig_genius_pie_anl.update_traces(textposition='inside', textinfo='percent+label'); st.plotly_chart(fig_genius_pie_anl, use_container_width=True)
                    with col_genius_anl2:
                        revenue_by_genius_anl = analytics_df_filtered.groupby('Thành viên Genius')['Tổng thanh toán'].sum().reset_index()
                        fig_genius_revenue_bar_anl = px.bar(revenue_by_genius_anl, x='Thành viên Genius', y='Tổng thanh toán', title='Tổng thanh toán theo loại thành viên Genius', labels={'Tổng thanh toán': 'Tổng thanh toán (VND)'}, color='Thành viên Genius', text_auto='.2s')
                        st.plotly_chart(fig_genius_revenue_bar_anl, use_container_width=True)
                else: st.info("Thiếu cột 'Thành viên Genius' để phân tích.")
                
                st.markdown("---")
                st.subheader("Tổng thanh toán theo Người thu tiền")
                if 'Người thu tiền' in analytics_df_filtered.columns and 'Tổng thanh toán' in analytics_df_filtered.columns:
                    df_for_collector_revenue = analytics_df_filtered.copy()
                    df_for_collector_revenue['Tổng thanh toán'] = pd.to_numeric(df_for_collector_revenue['Tổng thanh toán'], errors='coerce').fillna(0)
                    
                    collector_revenue = df_for_collector_revenue.groupby('Người thu tiền')['Tổng thanh toán'].sum().reset_index()
                    collector_revenue = collector_revenue.sort_values(by='Tổng thanh toán', ascending=False)
                    
                    collector_revenue_display = collector_revenue.copy()
                    collector_revenue_display.rename(columns={'Tổng thanh toán': 'Tổng thanh toán (VND)'}, inplace=True)
                    collector_revenue_display['Tổng thanh toán (VND)'] = collector_revenue_display['Tổng thanh toán (VND)'].map('{:,.0f}'.format)
                    
                    st.dataframe(collector_revenue_display.set_index('Người thu tiền'), use_container_width=True)

                    if not collector_revenue.empty:
                        fig_collector_revenue = px.bar(
                            collector_revenue, 
                            x='Người thu tiền', 
                            y='Tổng thanh toán', 
                            title='Tổng thanh toán theo Người thu tiền',
                            labels={'Tổng thanh toán': 'Tổng thanh toán (VND)', 'Người thu tiền': 'Người thu tiền'},
                            color='Người thu tiền',
                            text_auto='.2s'
                        )
                        fig_collector_revenue.update_layout(height=400)
                        st.plotly_chart(fig_collector_revenue, use_container_width=True)
                else:
                    st.info("Thiếu cột 'Người thu tiền' hoặc 'Tổng thanh toán' để phân tích.")

            else: st.info("Không có đặt phòng nào trong khoảng ngày đã chọn để phân tích.")
    else: st.info("Không có dữ liệu để phân tích. Vui lòng tải file đặt phòng.")

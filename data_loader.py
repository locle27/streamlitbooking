"""
Data Loading Module for Hotel Management System
Handles loading data from Excel, PDF, HTML files and Google Sheets
"""

import streamlit as st
import pandas as pd
import numpy as np
import datetime
import re
import io
import csv
import os
from typing import Tuple, Optional
from utils import parse_app_standard_date, clean_currency_value, ALL_REQUIRED_COLS

# Optional imports
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

try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False

def convert_display_date_to_app_format(display_date_input) -> Optional[str]:
    """Convert display date format to app format"""
    if pd.isna(display_date_input): 
        return None
    if isinstance(display_date_input, (datetime.datetime, datetime.date, pd.Timestamp)):
        return f"ngày {display_date_input.day} tháng {display_date_input.month} năm {display_date_input.year}"
    
    cleaned_date_str = str(display_date_input).replace(',', '').strip().lower()
    m = re.search(r"(\d{1,2})\s*tháng\s*(\d{1,2})\s*(\d{4})", cleaned_date_str)
    if m: 
        return f"ngày {m.group(1)} tháng {m.group(2)} năm {m.group(3)}"
    
    try:
        parsed = pd.to_datetime(cleaned_date_str, errors='coerce', dayfirst=True)
        if pd.notna(parsed): 
            return f"ngày {parsed.day} tháng {parsed.month} năm {parsed.year}"
    except Exception: 
        pass
    return None

def process_dataframe_dates(df: pd.DataFrame) -> pd.DataFrame:
    """Process and standardize date columns in dataframe"""
    # Parse Vietnamese date format columns
    if 'Ngày đến' in df.columns:
        df['Check-in Date'] = df['Ngày đến'].apply(parse_app_standard_date)
    if 'Ngày đi' in df.columns:
        df['Check-out Date'] = df['Ngày đi'].apply(parse_app_standard_date)
    if 'Được đặt vào' in df.columns:
        df['Booking Date'] = df['Được đặt vào'].apply(parse_app_standard_date)
    
    # Convert to datetime
    date_cols = ['Check-in Date', 'Check-out Date', 'Booking Date']
    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')
    
    # Clean currency columns
    for col in ["Tổng thanh toán", "Hoa hồng"]:
        if col in df.columns:
            df[col] = df[col].apply(clean_currency_value)
        else:
            df[col] = 0.0
    
    # Check for invalid dates but only warn if significant amount
    if not df.empty and ('Check-in Date' in df.columns and 'Check-out Date' in df.columns):
        invalid_checkin = df['Check-in Date'].isna().sum()
        invalid_checkout = df['Check-out Date'].isna().sum()
        
        # Only show warning if more than 50% of data has invalid dates
        total_rows = len(df)
        if (invalid_checkin + invalid_checkout) > (total_rows * 0.5):
            st.warning(f"⚠️ Tìm thấy {invalid_checkin} check-in và {invalid_checkout} check-out có ngày không hợp lệ. Dữ liệu vẫn được giữ lại nhưng các tính toán ngày có thể bị ảnh hưởng.")
            
            # Fill invalid dates with today's date for processing
            today = pd.Timestamp.now()
            if invalid_checkin > 0:
                df['Check-in Date'].fillna(today, inplace=True)
                st.info("Đã điền ngày check-in thiếu bằng ngày hôm nay")
            if invalid_checkout > 0:
                df['Check-out Date'].fillna(today + pd.Timedelta(days=1), inplace=True)
                st.info("Đã điền ngày check-out thiếu bằng ngày mai")
        elif invalid_checkin > 0 or invalid_checkout > 0:
            # Silently fill with reasonable dates for small amounts of invalid data
            today = pd.Timestamp.now()
            if invalid_checkin > 0:
                df['Check-in Date'].fillna(today, inplace=True)
            if invalid_checkout > 0:
                df['Check-out Date'].fillna(today + pd.Timedelta(days=1), inplace=True)
    
    # Calculate stay duration
    if 'Check-out Date' in df.columns and 'Check-in Date' in df.columns:
        df['Stay Duration'] = (df['Check-out Date'] - df['Check-in Date']).dt.days
        df['Stay Duration'] = df['Stay Duration'].apply(lambda x: max(0, x) if pd.notna(x) else 1)
    else:
        df['Stay Duration'] = 1
    
    # Calculate price per night
    if 'Tổng thanh toán' in df.columns and 'Stay Duration' in df.columns:
        # Ensure numeric values
        df['Tổng thanh toán'] = pd.to_numeric(df['Tổng thanh toán'], errors='coerce').fillna(0)
        df['Giá mỗi đêm'] = np.where(
            (df['Stay Duration'].notna()) & (df['Stay Duration'] > 0) & (df['Tổng thanh toán'].notna()),
            df['Tổng thanh toán'] / df['Stay Duration'],
            0.0
        ).round(0)
    else:
        df['Giá mỗi đêm'] = 0.0
    
    return df

def ensure_required_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure all required columns exist in dataframe"""
    for col in ALL_REQUIRED_COLS:
        if col not in df.columns:
            if "Date" in col and col not in ['Ngày đến', 'Ngày đi', 'Được đặt vào']:
                df[col] = pd.NaT
            elif "Duration" in col:
                df[col] = 0
            elif col in ['Tổng thanh toán', 'Hoa hồng', 'Giá mỗi đêm']:
                df[col] = 0.0
            else:
                df[col] = "N/A"
    return df

@st.cache_data
def load_excel_file(uploaded_file) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """Load data from Excel file"""
    filename = uploaded_file.name
    try:
        st.info(f"Đang xử lý file Excel: {filename}...")
        engine = 'xlrd' if filename.endswith('.xls') else 'openpyxl'
        df = pd.read_excel(uploaded_file, engine=engine)
        
        # Map Excel columns to app columns
        excel_to_app_map = {
            'Ngày đến': 'Ngày đến', 'Ngày đi': 'Ngày đi',
            'Được đặt vào': 'Được đặt vào', 'Tên chỗ nghỉ': 'Tên chỗ nghỉ',
            'Vị trí': 'Vị trí', 'Tên người đặt': 'Tên người đặt',
            'Thành viên Genius': 'Thành viên Genius', 'Tình trạng': 'Tình trạng',
            'Tổng thanh toán': 'Tổng thanh toán', 'Hoa hồng': 'Hoa hồng',
            'Tiền tệ': 'Tiền tệ', 'Số đặt phòng': 'Số đặt phòng'
        }
        df = df.rename(columns={k: v for k, v in excel_to_app_map.items() if k in df.columns})
        
        # Process dates and ensure columns
        df = process_dataframe_dates(df)
        df = ensure_required_columns(df)
        
        # Get active bookings
        active_bookings = df[df['Tình trạng'] != 'Đã hủy'].copy() if 'Tình trạng' in df.columns else df.copy()
        
        st.success(f"Đã xử lý thành công {filename}. Tìm thấy {len(df)} đặt phòng.")
        return df, active_bookings
        
    except Exception as e:
        st.error(f"Lỗi khi xử lý file Excel: {e}")
        return None, None

@st.cache_data
def load_pdf_file(uploaded_file) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """Load data from PDF file"""
    if not PYPDF2_AVAILABLE:
        st.error("PyPDF2 không được cài đặt. Vui lòng cài: pip install pypdf2")
        return None, None
    
    filename = uploaded_file.name
    try:
        st.info(f"Đang xử lý file PDF: {filename}...")
        reader = PdfReader(uploaded_file)
        text_data = ""
        
        for page_num, page in enumerate(reader.pages):
            page_text = page.extract_text()
            if page_text:
                text_data += page_text + "\n"
        
        if not text_data.strip():
            st.error("File PDF không chứa văn bản.")
            return None, None
        
        # Parse PDF data (simplified - you may need to adjust based on PDF format)
        lines = text_data.splitlines()
        parsed_rows = []
        
        for line in lines:
            # This is a simplified parser - adjust based on your PDF format
            if line.strip() and not line.startswith('#'):
                # Try to parse structured data
                parts = line.split(',')
                if len(parts) >= 5:
                    parsed_rows.append({
                        'Tên chỗ nghỉ': parts[0].strip(),
                        'Tên người đặt': parts[1].strip(),
                        'Ngày đến': parts[2].strip(),
                        'Ngày đi': parts[3].strip(),
                        'Tình trạng': parts[4].strip() if len(parts) > 4 else 'OK'
                    })
        
        if not parsed_rows:
            st.error("Không thể trích xuất dữ liệu từ PDF.")
            return None, None
        
        df = pd.DataFrame(parsed_rows)
        
        # Process and ensure columns
        df = process_dataframe_dates(df)
        df = ensure_required_columns(df)
        
        active_bookings = df[df['Tình trạng'] != 'Đã hủy'].copy()
        
        st.success(f"Đã xử lý thành công PDF. Tìm thấy {len(df)} đặt phòng.")
        return df, active_bookings
        
    except Exception as e:
        st.error(f"Lỗi khi xử lý file PDF: {e}")
        return None, None

@st.cache_data
def load_html_file(uploaded_file) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """Load data from HTML file"""
    if not BS4_AVAILABLE:
        st.error("BeautifulSoup4 không được cài đặt. Vui lòng cài: pip install beautifulsoup4")
        return None, None
    
    filename = uploaded_file.name
    try:
        st.info(f"Đang xử lý file HTML: {filename}...")
        soup = BeautifulSoup(uploaded_file.read(), 'html.parser')
        
        # Find table
        table = soup.find('table', class_='cdd0659f86')
        if not table:
            table = soup.find('table')
            if not table:
                st.error("Không tìm thấy bảng dữ liệu trong HTML.")
                return None, None
        
        # Parse table
        parsed_rows = []
        headers = []
        
        # Get headers
        header_row = table.find('thead')
        if header_row:
            header_row = header_row.find('tr')
            if header_row:
                headers = [th.get_text(strip=True) for th in header_row.find_all('th')]
        
        # Get body
        body = table.find('tbody')
        if not body:
            st.error("Không tìm thấy tbody trong bảng HTML.")
            return None, None
        
        for row in body.find_all('tr'):
            cells = row.find_all(['td', 'th'])
            row_data = {}
            
            for i, cell in enumerate(cells):
                heading = cell.get('data-heading')
                if not heading and i < len(headers):
                    heading = headers[i]
                elif not heading:
                    heading = f"Cột {i+1}"
                
                if heading == "Tên khách":
                    # Extract guest name and Genius status
                    guest_name_tag = cell.find('a')
                    guest_name_text = guest_name_tag.get_text(strip=True) if guest_name_tag else cell.get_text(separator=" ", strip=True)
                    row_data["Tên người đặt"] = guest_name_text.split("Genius")[0].replace("1 khách", "").replace("2 khách", "").strip()
                    
                    genius_svg = cell.find('svg', alt='Genius')
                    row_data["Thành viên Genius"] = "Có" if genius_svg or "Genius" in guest_name_text else "Không"
                else:
                    row_data[heading] = cell.get_text(separator=" ", strip=True)
            
            if row_data:
                parsed_rows.append(row_data)
        
        if not parsed_rows:
            st.error("Không trích xuất được dữ liệu từ HTML.")
            return None, None
        
        df = pd.DataFrame(parsed_rows)
        
        # Map HTML columns
        html_to_app_map = {
            "ID chỗ nghỉ": "ID chỗ nghỉ", "Tên chỗ nghỉ": "Tên chỗ nghỉ",
            "Vị trí": "Vị trí", "Nhận phòng": "Ngày đến",
            "Ngày đi": "Ngày đi", "Tình trạng": "Tình trạng",
            "Tổng thanh toán": "Tổng thanh toán", "Hoa hồng": "Hoa hồng",
            "Số đặt phòng": "Số đặt phòng", "Được đặt vào": "Được đặt vào"
        }
        df = df.rename(columns={k: v for k, v in html_to_app_map.items() if k in df.columns})
        
        # Convert display dates
        for col in ['Ngày đến', 'Ngày đi', 'Được đặt vào']:
            if col in df.columns:
                df[col] = df[col].apply(convert_display_date_to_app_format)
        
        # Add default currency
        if "Tiền tệ" not in df.columns:
            df["Tiền tệ"] = "VND"
        
        # Process and ensure columns
        df = process_dataframe_dates(df)
        df = ensure_required_columns(df)
        
        active_bookings = df[df['Tình trạng'] != 'Đã hủy'].copy()
        
        st.success(f"Đã xử lý thành công HTML. Tìm thấy {len(df)} đặt phòng.")
        return df, active_bookings
        
    except Exception as e:
        st.error(f"Lỗi khi xử lý file HTML: {e}")
        return None, None

def get_gsheet_credentials():
    """Get Google Sheets credentials from file"""
    creds_filename = "streamlit-api-461302-5dfbcb4beaba.json"
    creds_path = creds_filename
    
    try:
        # Check script directory
        script_dir = os.path.dirname(__file__)
        path_in_script_dir = os.path.join(script_dir, creds_filename)
        if os.path.exists(path_in_script_dir):
            creds_path = path_in_script_dir
            st.info(f"Sử dụng credentials từ: {creds_path}")
            return creds_path
    except NameError:
        pass
    
    # Check current working directory
    if not os.path.exists(creds_path):
        cwd = os.getcwd()
        path_in_cwd = os.path.join(cwd, creds_filename)
        if os.path.exists(path_in_cwd):
            creds_path = path_in_cwd
            st.info(f"Sử dụng credentials từ: {creds_path}")
            return creds_path
    
    if os.path.exists(creds_path):
        return creds_path
    
    st.error(f"Không tìm thấy file credentials: {creds_filename}")
    return None

def import_from_gsheet(sheet_id: str, worksheet_name: str = None) -> pd.DataFrame:
    """Import data from Google Sheets"""
    if not GSPREAD_AVAILABLE:
        st.error("gspread không được cài đặt. Vui lòng cài: pip install gspread")
        return pd.DataFrame()
    
    creds_path = get_gsheet_credentials()
    if not creds_path:
        return pd.DataFrame()
    
    try:
        scope = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive',
        ]
        
        creds = Credentials.from_service_account_file(creds_path, scopes=scope)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(sheet_id)
        
        if worksheet_name:
            try:
                worksheet = sh.worksheet(worksheet_name)
            except gspread.WorksheetNotFound:
                st.error(f"Không tìm thấy worksheet '{worksheet_name}'. Sử dụng sheet đầu tiên.")
                worksheet = sh.sheet1
        else:
            worksheet = sh.sheet1
        
        # Get all records
        records = worksheet.get_all_records()
        
        if not records:
            st.warning("Google Sheet trống hoặc không có dữ liệu")
            return pd.DataFrame()
        
        df = pd.DataFrame(records)
        
        # Clean and process the data
        if not df.empty:
            # Remove empty rows
            df = df.dropna(how='all')
            
            # Convert date columns from Google Sheets format
            date_columns = []
            for col in df.columns:
                if any(keyword in col.lower() for keyword in ['date', 'ngày', 'ngay']):
                    date_columns.append(col)
            
            # Fix date formatting issues from Google Sheets
            for col in date_columns:
                if col in df.columns:
                    # Handle datetime objects from Google Sheets
                    df[col] = df[col].apply(lambda x: 
                        x.date() if hasattr(x, 'date') and callable(getattr(x, 'date')) 
                        else x if isinstance(x, datetime.date) 
                        else pd.to_datetime(str(x), errors='coerce').date() if pd.notna(x) and str(x).strip() != ''
                        else None
                    )
            
            # Process with standard date handling
            df = process_dataframe_dates(df)
            df = ensure_required_columns(df)
            
            st.success(f"✅ Đã tải {len(df)} bản ghi từ Google Sheets")
            return df
            
    except gspread.SpreadsheetNotFound:
        st.error("Không tìm thấy Google Sheet với ID đã cung cấp")
    except gspread.APIError as e:
        st.error(f"Lỗi API Google Sheets: {e}")
    except Exception as e:
        st.error(f"Lỗi không xác định khi import từ Google Sheets: {e}")
    
    return pd.DataFrame()

def upload_to_gsheet(df: pd.DataFrame, sheet_id: str, worksheet_name: str = None) -> bool:
    """Upload data to Google Sheets"""
    if not GSPREAD_AVAILABLE:
        st.error("gspread không được cài đặt.")
        return False
    
    creds_path = get_gsheet_credentials()
    if not creds_path:
        return False
    
    try:
        scope = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive',
        ]
        
        creds = Credentials.from_service_account_file(creds_path, scopes=scope)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(sheet_id)
        
        if worksheet_name:
            try:
                worksheet = sh.worksheet(worksheet_name)
            except gspread.WorksheetNotFound:
                worksheet = sh.add_worksheet(title=worksheet_name, rows="100", cols="20")
        else:
            worksheet = sh.sheet1
        
        # Clear existing data
        worksheet.clear()
        
        # Convert all columns to string to avoid serialization issues
        df_str = df.astype(str)
        
        # Update with new data
        worksheet.update([df_str.columns.values.tolist()] + df_str.values.tolist())
        
        st.success(f"Đã upload thành công lên Google Sheets!")
        return True
        
    except Exception as e:
        st.error(f"Lỗi khi upload lên Google Sheets: {e}")
        return False

@st.cache_data
def load_data_from_file(uploaded_file) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """Main function to load data from any supported file type"""
    filename = uploaded_file.name
    
    if filename.endswith(('.xls', '.xlsx')):
        return load_excel_file(uploaded_file)
    elif filename.endswith('.pdf'):
        return load_pdf_file(uploaded_file)
    elif filename.endswith('.html'):
        return load_html_file(uploaded_file)
    else:
        st.error(f"Định dạng file '{filename.split('.')[-1]}' không được hỗ trợ.")
        return None, None

def create_demo_data() -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Create demo data for testing"""
    st.info("Đang tạo dữ liệu demo...")
    
    demo_data = {
        'Tên chỗ nghỉ': ['Home in Old Quarter - Night market', 'Old Quarter Home- Kitchen & Balcony', 
                         'Home in Old Quarter - Night market', 'Old Quarter Home- Kitchen & Balcony', 
                         'Riverside Boutique Apartment'],
        'Vị trí': ['Phố Cổ Hà Nội, Hoàn Kiếm, Vietnam', '118 Phố Hàng Bạc, Hoàn Kiếm, Vietnam', 
                   'Phố Cổ Hà Nội, Hoàn Kiếm, Vietnam', '118 Phố Hàng Bạc, Hoàn Kiếm, Vietnam', 
                   'Quận 2, TP. Hồ Chí Minh, Vietnam'],
        'Tên người đặt': ['Demo User Alpha', 'Demo User Beta', 'Demo User Alpha', 
                          'Demo User Gamma', 'Demo User Delta'],
        'Thành viên Genius': ['Không', 'Có', 'Không', 'Có', 'Không'],
        'Ngày đến': ['ngày 22 tháng 5 năm 2025', 'ngày 23 tháng 5 năm 2025', 
                     'ngày 25 tháng 5 năm 2025', 'ngày 26 tháng 5 năm 2025', 
                     'ngày 1 tháng 6 năm 2025'],
        'Ngày đi': ['ngày 23 tháng 5 năm 2025', 'ngày 24 tháng 5 năm 2025', 
                    'ngày 26 tháng 5 năm 2025', 'ngày 28 tháng 5 năm 2025', 
                    'ngày 5 tháng 6 năm 2025'],
        'Được đặt vào': ['ngày 20 tháng 5 năm 2025', 'ngày 21 tháng 5 năm 2025', 
                         'ngày 22 tháng 5 năm 2025', 'ngày 23 tháng 5 năm 2025', 
                         'ngày 25 tháng 5 năm 2025'],
        'Tình trạng': ['OK', 'OK', 'Đã hủy', 'OK', 'OK'],
        'Tổng thanh toán': [300000, 450000, 200000, 600000, 1200000],
        'Hoa hồng': [60000, 90000, 40000, 120000, 240000],
        'Tiền tệ': ['VND', 'VND', 'VND', 'VND', 'VND'],
        'Số đặt phòng': [f'DEMO{i+1:09d}' for i in range(5)]
    }
    
    df_demo = pd.DataFrame(demo_data)
    
    # Process dates and ensure columns
    df_demo = process_dataframe_dates(df_demo)
    df_demo = ensure_required_columns(df_demo)
    
    active_bookings_demo = df_demo[df_demo['Tình trạng'] != 'Đã hủy'].copy()
    
    return df_demo, active_bookings_demo

@st.cache_data
def parse_customer_html(uploaded_html_file) -> Optional[pd.DataFrame]:
    """Parse customer data from HTML file"""
    if not BS4_AVAILABLE:
        st.error("BeautifulSoup4 không được cài đặt.")
        return None
    
    try:
        st.info(f"Đang xử lý file HTML khách hàng: {uploaded_html_file.name}...")
        soup = BeautifulSoup(uploaded_html_file.read(), 'html.parser')
        
        # Find table
        table = soup.find('table', class_='cdd0659f86')
        if not table:
            table = soup.find('table')
            if not table:
                st.error("Không tìm thấy bảng trong HTML.")
                return None
        
        parsed_rows = []
        headers = []
        
        # Get headers
        header_row = table.find('thead')
        if header_row:
            header_row_tr = header_row.find('tr')
            if header_row_tr:
                headers = [th.get_text(strip=True) for th in header_row_tr.find_all('th')]
        
        # Get body
        body = table.find('tbody')
        if not body:
            # Try to find rows directly
            rows = table.find_all('tr')
            if rows and not headers:
                # First row might be header
                first_row_cells = rows[0].find_all(['th', 'td'])
                headers = [cell.get_text(strip=True) for cell in first_row_cells]
                body_rows = rows[1:]
            else:
                body_rows = rows
        else:
            body_rows = body.find_all('tr')
        
        # Parse rows
        for row in body_rows:
            cells = row.find_all(['td', 'th'])
            row_data = {}
            
            for i, cell in enumerate(cells):
                heading = cell.get('data-heading')
                if not heading and i < len(headers):
                    heading = headers[i]
                elif not heading:
                    heading = f"Cột {i+1}"
                
                text_content = cell.get_text(separator=" ", strip=True)
                
                # Check if this is guest name column
                guest_name_headers = ["tên khách", "họ và tên", "guest name", "customer name", "tên người đặt"]
                is_guest_name_col = any(h.lower() in heading.lower() for h in guest_name_headers)
                
                if is_guest_name_col:
                    # Extract guest name
                    link_tag = cell.find('a')
                    name_text = link_tag.get_text(strip=True) if link_tag else text_content
                    
                    # Check for Genius status
                    if "genius" in name_text.lower():
                        row_data["Thành viên Genius"] = "Có"
                        name_text = re.sub(r'(?i)genius', '', name_text).strip()
                    else:
                        genius_svg = cell.find('svg', alt=lambda x: x and 'genius' in x.lower())
                        row_data["Thành viên Genius"] = "Có" if genius_svg else "Không"
                    
                    # Clean name
                    name_text = re.sub(r'(?i)(1 khách|2 khách|2 người lớn|\d+ adults?)', '', name_text).strip()
                    row_data["Tên người đặt"] = name_text
                    
                    if heading not in row_data:
                        row_data[heading] = text_content
                        
                elif "thành viên genius" in heading.lower() or "genius member" in heading.lower():
                    row_data["Thành viên Genius"] = "Có" if "có" in text_content.lower() or "yes" in text_content.lower() else "Không"
                else:
                    row_data[heading] = text_content
            
            if row_data:
                parsed_rows.append(row_data)
        
        if not parsed_rows:
            st.error("Không trích xuất được dữ liệu từ HTML.")
            return None
        
        df = pd.DataFrame(parsed_rows)
        st.success(f"Đã xử lý thành công. Tìm thấy {len(df)} khách hàng.")
        return df
        
    except Exception as e:
        st.error(f"Lỗi khi xử lý file HTML: {e}")
        return None 
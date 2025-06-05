import logging
import datetime
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import re # For parsing dates if necessary
import asyncio # Added for potentially calling async functions from sync main

# --- CONFIGURATION ---
TELEGRAM_BOT_TOKEN = "7998311603:AAGFoxqsbBe5nhocp9Tco635o9tbdT4DTDI"  # Your Bot Token
GSHEET_CREDENTIALS_FILE = "streamlit-api-461302-5dfbcb4beaba.json" # Path to your credentials, ensure this is correct
GSHEET_SHEET_ID = "13kQETOUGCVUwUqZrxeLy-WAj3b17SugI4L8Oq09SX2w"    # Your Google Sheet ID
GSHEET_WORKSHEET_NAME = "BookingManager"                           # Worksheet name
TARGET_TELEGRAM_CHAT_ID = "1189687917"  # !!! REPLACE WITH THE ACTUAL CHAT ID FOR PROACTIVE REPORTS !!!

# Constants
# ROOM_UNIT_PER_ROOM_TYPE = 4 # This might represent total units if "Tên chỗ nghỉ" are platforms
# For the new request, we assume each unique "Tên chỗ nghỉ" (if it represents a physical room) is 1 unit.
PHYSICAL_ROOMS_TOTAL = 4 # User specified they have 4 physical rooms

# Enable logging for the bot
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- HELPER FUNCTIONS (Adapted from your Streamlit app) ---

def parse_app_standard_date(date_input: any) -> datetime.date | None:
    if pd.isna(date_input):
        return None
    if isinstance(date_input, datetime.datetime):
        return date_input.date()
    if isinstance(date_input, datetime.date):
        return date_input
    try:
        if isinstance(date_input, str):
            try: 
                return pd.to_datetime(date_input, dayfirst=True).date()
            except ValueError:
                try: 
                    return pd.to_datetime(date_input, dayfirst=False).date()
                except ValueError:
                    logger.warning(f"Complex string date format for {date_input}, attempting Vietnamese regex.")
                    match = re.search(r"ngày\s*(\d{1,2})\s*tháng\s*(\d{1,2})\s*năm\s*(\d{4})", date_input.lower())
                    if match:
                        day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
                        return datetime.date(year, month, day)
                    logger.warning(f"Failed to parse complex string date: {date_input}")
                    return None 
        dt_obj = pd.to_datetime(date_input).date()
        return dt_obj
    except Exception as e:
        logger.error(f"Could not parse date: {date_input}, Error: {e}")
        return None

def get_cleaned_room_names(df_source: pd.DataFrame) -> list[str]: # Renamed for clarity
    """Gets unique, cleaned names from 'Tên chỗ nghỉ', assumed to be physical room names for this context."""
    if df_source is None or df_source.empty or 'Tên chỗ nghỉ' not in df_source.columns:
        return []
    try:
        unique_values = df_source['Tên chỗ nghỉ'].dropna().unique()
    except Exception:
        return []
    cleaned_names = []
    seen_names = set()
    for val in unique_values:
        s_val = str(val).strip()
        if s_val and s_val not in seen_names:
            cleaned_names.append(s_val)
            seen_names.add(s_val)
    return sorted(cleaned_names)

def get_physical_room_status(
    date_to_check: datetime.date,
    current_bookings_df: pd.DataFrame,
    physical_room_names: list[str] # These are the unique 'Tên chỗ nghỉ' values treated as physical rooms
) -> dict[str, str]: # Returns {room_name: "Trống" or "Có khách"}
    status = {room_name: "Trống" for room_name in physical_room_names}
    if current_bookings_df is None or current_bookings_df.empty or not physical_room_names:
        return status

    active_on_date = current_bookings_df[
        (current_bookings_df['Check-in Date'].dt.date <= date_to_check) &
        (current_bookings_df['Check-out Date'].dt.date > date_to_check) &
        (current_bookings_df.get('Tình trạng', 'OK') != 'Đã hủy')
    ]
    
    # Since each 'Tên chỗ nghỉ' is treated as a unique physical room, its presence means it's occupied.
    occupied_room_names = active_on_date['Tên chỗ nghỉ'].unique()
    for room_name in occupied_room_names:
        if room_name in status:
            status[room_name] = "Có khách"
    return status

def get_daily_activity_for_bot(date_to_check: datetime.date, current_bookings_df: pd.DataFrame) -> dict[str, list[dict]]:
    """Gets check-ins and check-outs for the bot."""
    activity = {"check_in": [], "check_out": []}
    if current_bookings_df is None or current_bookings_df.empty:
        return activity

    # Check-ins for today
    check_ins_today = current_bookings_df[
        (current_bookings_df['Check-in Date'].dt.date == date_to_check) &
        (current_bookings_df.get('Tình trạng', 'OK') != 'Đã hủy')
    ]
    for _, row in check_ins_today.iterrows():
        payment_amount = 0.0
        try:
            # Assuming the payment column is 'Tổng thanh toán'
            payment_str = row.get('Tổng thanh toán', '0')
            # Basic cleaning: remove non-numeric characters except .
            cleaned_payment_str = re.sub(r'[^\d.]', '', str(payment_str))
            if cleaned_payment_str:
                payment_amount = float(cleaned_payment_str)
        except ValueError:
            logger.warning(f"Could not parse payment amount for booking {row.get('Số đặt phòng', 'N/A')}: {row.get('Tổng thanh toán', 'N/A')}")
            payment_amount = 0.0 # Default to 0 if parsing fails

        activity["check_in"].append({
            "name": row.get('Tên người đặt', 'N/A'),
            "room_name": row.get('Tên chỗ nghỉ', 'N/A'), # 'Tên chỗ nghỉ' is the room identifier here
            "payment": payment_amount
        })

    # Check-outs for today
    check_outs_today = current_bookings_df[
        (current_bookings_df['Check-out Date'].dt.date == date_to_check) &
        (current_bookings_df.get('Tình trạng', 'OK') != 'Đã hủy') # Should not be 'Đã hủy' if checking out
    ]
    for _, row in check_outs_today.iterrows():
        activity["check_out"].append({
            "name": row.get('Tên người đặt', 'N/A'), 
            "room_name": row.get('Tên chỗ nghỉ', 'N/A')
        })
    return activity

def get_overall_availability_for_bot(date_to_check: datetime.date, current_bookings_df: pd.DataFrame, total_physical_rooms: int) -> dict[str, int]:
    """Calculates overall room availability based on active bookings count."""
    if current_bookings_df is None or current_bookings_df.empty:
        return {"available_units": total_physical_rooms, "occupied_units": 0, "total_units": total_physical_rooms}

    # Bookings active on the date_to_check
    # Assumes each row in current_bookings_df is one occupied physical room if active
    active_on_date_df = current_bookings_df[
        (current_bookings_df['Check-in Date'].dt.date <= date_to_check) &
        (current_bookings_df['Check-out Date'].dt.date > date_to_check) &
        (current_bookings_df.get('Tình trạng', 'OK') != 'Đã hủy')
    ]
    occupied_units = len(active_on_date_df)
    available_units = max(0, total_physical_rooms - occupied_units)
    return {"available_units": available_units, "occupied_units": occupied_units, "total_units": total_physical_rooms}

# --- END HELPER FUNCTIONS ---

def get_data_from_gsheet() -> pd.DataFrame:
    """Fetches data from the specified Google Sheet and returns an active bookings DataFrame."""
    try:
        scope = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive',
        ]
        creds = Credentials.from_service_account_file(GSHEET_CREDENTIALS_FILE, scopes=scope)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(GSHEET_SHEET_ID)
        worksheet = sh.worksheet(GSHEET_WORKSHEET_NAME)
        data = worksheet.get_all_values()
        
        if not data or len(data) < 2:
            logger.warning("No data or only header row found in Google Sheet.")
            return pd.DataFrame()
        
        df = pd.DataFrame(data[1:], columns=data[0])
        logger.info(f"Successfully fetched {len(df)} rows from Google Sheet.")

        date_cols_to_parse_robustly = ['Ngày đến', 'Ngày đi'] # Columns likely in Vietnamese string format
        structured_date_cols = ['Check-in Date', 'Check-out Date'] # Columns ideally pre-formatted or easily parsed

        # Attempt to create/populate structured date columns if they don't exist or are incomplete
        for i, structured_col in enumerate(structured_date_cols):
            original_col = date_cols_to_parse_robustly[i]
            if structured_col not in df.columns or df[structured_col].astype(str).str.strip().eq('').all() or df[structured_col].isnull().all(): # Check if column is missing, all empty strings, or all NaNs
                if original_col in df.columns:
                    logger.info(f"Populating '{structured_col}' from '{original_col}' using parse_app_standard_date.")
                    df[structured_col] = df[original_col].apply(parse_app_standard_date)
                else:
                    logger.error(f"Cannot create '{structured_col}' as source '{original_col}' is missing.")
                    return pd.DataFrame() # Critical error if source dates are missing
            else:
                 # If column exists but has some NaNs, try to fill them from original if possible
                 if df[structured_col].isnull().any() and original_col in df.columns:
                    logger.info(f"Attempting to fill NaNs in '{structured_col}' from '{original_col}'.")
                    # Only fill if the original data can be parsed
                    parsed_originals = df[original_col].apply(parse_app_standard_date)
                    df[structured_col] = df[structured_col].fillna(parsed_originals)
        
        # Convert structured date columns to datetime objects
        for col in structured_date_cols:
            df[col] = pd.to_datetime(df[col], errors='coerce')
        
        # Also parse 'Được đặt vào' if it exists
        if 'Được đặt vào' in df.columns:
            df['Được đặt vào'] = df['Được đặt vào'].apply(parse_app_standard_date)
            df['Được đặt vào'] = pd.to_datetime(df['Được đặt vào'], errors='coerce')

        df.dropna(subset=structured_date_cols, inplace=True)
        if df.empty:
            logger.warning("No valid booking data after date parsing and cleaning.")
            return pd.DataFrame()

        if 'Tình trạng' in df.columns:
            active_df = df[df['Tình trạng'] != 'Đã hủy'].copy()
        else:
            active_df = df.copy()
        
        logger.info(f"Found {len(active_df)} active bookings.")
        return active_df
        
    except gspread.exceptions.SpreadsheetNotFound:
        logger.error(f"Spreadsheet not found. Check GSHEET_SHEET_ID: {GSHEET_SHEET_ID}")
        return pd.DataFrame()
    except gspread.exceptions.WorksheetNotFound:
        logger.error(f"Worksheet not found: {GSHEET_WORKSHEET_NAME}. Check GSHEET_WORKSHEET_NAME.")
        return pd.DataFrame()
    except FileNotFoundError:
        logger.error(f"Google Sheets credentials file not found: {GSHEET_CREDENTIALS_FILE}")
        return pd.DataFrame()
    except Exception as e:
        logger.error(f"Error fetching or processing data from Google Sheet: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return pd.DataFrame()

async def send_proactive_detail_report(application: Application, chat_id: str) -> None:
    """
    Proactively sends a detailed room and activity report to the specified chat_id.
    The report is based on data from Google Sheets.
    """
    logger.info(f"Attempting to send proactive detail report to chat ID: {chat_id}")
    
    # Send an initial heads-up message
    try:
        await application.bot.send_message(chat_id=chat_id, text="🤖 Generating proactive hotel report from Google Sheets, please wait...")
    except Exception as e:
        logger.error(f"Failed to send initial message for proactive report to {chat_id}: {e}")
        # Proceed to try and send the report anyway if data fetching works, or handle as critical failure.
        # For now, we'll log and continue.

    active_bookings_df = get_data_from_gsheet()
    if active_bookings_df.empty:
        try:
            await application.bot.send_message(chat_id=chat_id, text="⚠️ Sorry, could not fetch booking data or no active bookings found for the proactive report.")
        except Exception as e_msg:
            logger.error(f"Failed to send 'no data' message for proactive report to {chat_id}: {e_msg}")
        logger.warning(f"Failed to generate proactive report for {chat_id}: No active bookings data.")
        return

    today_dt = datetime.date.today()
    message_parts = [f"📢 Khách sạn Hôm Nay (Báo cáo Tự động) - {today_dt.strftime('%d/%m/%Y')} 📢\n"]

    # Get daily activity (check-ins, check-outs)
    daily_activity = get_daily_activity_for_bot(today_dt, active_bookings_df)
    message_parts.append("➡️ Khách Check-in Hôm Nay:")
    total_check_in_payment = 0
    if daily_activity['check_in']:
        for guest_ci in daily_activity['check_in']:
            payment_str = f"{guest_ci.get('payment', 0):,.0f} VND"
            message_parts.append(f"- {guest_ci['name']} ({guest_ci['room_name']}) - Thu: {payment_str}")
            total_check_in_payment += guest_ci.get('payment', 0)
    else:
        message_parts.append("Không có khách check-in hôm nay.")
    message_parts.append(f"💰 Tổng thu từ khách check-in: {total_check_in_payment:,.0f} VND\n")

    message_parts.append("⬅️ Khách Check-out Hôm Nay:")
    if daily_activity['check_out']:
        for guest_co in daily_activity['check_out']:
            message_parts.append(f"- {guest_co['name']} ({guest_co['room_name']})")
    else:
        message_parts.append("Không có khách check-out hôm nay.")
    message_parts.append("") # Add a blank line

    # Get overall room availability summary
    availability_info = get_overall_availability_for_bot(today_dt, active_bookings_df, PHYSICAL_ROOMS_TOTAL)
    message_parts.append("🏡 Tình trạng phòng tổng quan hôm nay:")
    message_parts.append(f"- Số phòng trống: {availability_info['available_units']} / {availability_info['total_units']}")
            
    full_message = "\n".join(message_parts)
    
    try:
        await application.bot.send_message(chat_id=chat_id, text=full_message)
        logger.info(f"Successfully sent proactive detail report to chat ID: {chat_id}")
    except Exception as e:
        logger.error(f"Error sending proactive detail report to {chat_id}: {e}")
        try:
            await application.bot.send_message(chat_id=chat_id, text=f"⚠️ Error sending full report: {e}")
        except Exception as e_err_msg:
            logger.error(f"Failed to send error notification for proactive report to {chat_id}: {e_err_msg}")

async def detail_room_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    logger.info(f"Received /detailroom command from user {user.username} (ID: {user.id})")
    await update.message.reply_text("Đang lấy thông tin từ Google Sheets, vui lòng đợi...")
    
    active_bookings_df = get_data_from_gsheet()
    if active_bookings_df.empty:
        await update.message.reply_text("Xin lỗi, không thể lấy dữ liệu đặt phòng hoặc không có đặt phòng nào đang hoạt động.")
        return

    today_dt = datetime.date.today()
    message_parts = [f"📢 Cập nhật Khách sạn - {today_dt.strftime('%d/%m/%Y')} 📢\n"]

    # Get daily activity (check-ins, check-outs)
    daily_activity = get_daily_activity_for_bot(today_dt, active_bookings_df)
    message_parts.append("➡️ Khách Check-in Hôm Nay:")
    total_check_in_payment = 0
    if daily_activity['check_in']:
        for guest_ci in daily_activity['check_in']:
            payment_str = f"{guest_ci.get('payment', 0):,.0f} VND" # Format with commas
            message_parts.append(f"- {guest_ci['name']} ({guest_ci['room_name']}) - Thu: {payment_str}")
            total_check_in_payment += guest_ci.get('payment', 0)
    else:
        message_parts.append("Không có khách check-in hôm nay.")
    message_parts.append(f"Tổng thu từ khách check-in: {total_check_in_payment:,.0f} VND\n")

    message_parts.append("⬅️ Khách Check-out Hôm Nay:")
    if daily_activity['check_out']:
        for guest_co in daily_activity['check_out']:
            message_parts.append(f"- {guest_co['name']} ({guest_co['room_name']})")
    else:
        message_parts.append("Không có khách check-out hôm nay.")
    message_parts.append("") # Add a blank line for spacing before room status

    # Get overall room availability summary
    availability_info = get_overall_availability_for_bot(today_dt, active_bookings_df, PHYSICAL_ROOMS_TOTAL)
    message_parts.append("🏡 Tình trạng phòng hôm nay:")
    message_parts.append(f"- Số phòng trống: {availability_info['available_units']}/{availability_info['total_units']}")
            
    full_message = "\n".join(message_parts)
    await update.message.reply_text(full_message)

async def start_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message when the /start command is issued."""
    user = update.effective_user
    logger.info(f"User {user.username} (ID: {user.id}) started the bot.")
    await update.message.reply_text(
        f"Chào {user.mention_html()}! 👋\n\n"
        "Tôi là Bot Quản Lý Khách Sạn của bạn.\n"
        "Gửi lệnh /detailroom để xem tình trạng phòng trống tổng thể, cùng với thông tin khách check-in/out hôm nay.\n\n"
        "Lưu ý: Dữ liệu được lấy từ Google Sheets."
        ,parse_mode='HTML'
    )

def main() -> None:
    """Start the bot."""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command_handler))
    application.add_handler(CommandHandler("detailroom", detail_room_command_handler))

    logger.info("Starting bot polling...")

    # --- Example: How to send a proactive report (e.g., on startup) ---
    # This part is for demonstration. You might want to trigger this based on a schedule or other logic.
    # Ensure TARGET_TELEGRAM_CHAT_ID is set correctly above.
    #
    # async def send_startup_report():
    #     if TARGET_TELEGRAM_CHAT_ID and TARGET_TELEGRAM_CHAT_ID != "YOUR_TARGET_CHAT_ID_HERE":
    #         logger.info(f"Attempting to send startup report to {TARGET_TELEGRAM_CHAT_ID}")
    #         await send_proactive_detail_report(application, TARGET_TELEGRAM_CHAT_ID)
    #     else:
    #         logger.warning("TARGET_TELEGRAM_CHAT_ID is not set or is placeholder. Skipping startup report.")
    #
    # # To run an async function from this synchronous main(), you'd typically use asyncio.run()
    # # For a bot that's already running an asyncio event loop via run_polling(),
    # # you might need to schedule it differently if not on startup, or use application.job_queue if appropriate.
    # # For a simple startup task, creating a new task might work if run_polling sets up the loop.
    # # However, the most straightforward way to run an async function here once is:
    # if TARGET_TELEGRAM_CHAT_ID and TARGET_TELEGRAM_CHAT_ID != "YOUR_TARGET_CHAT_ID_HERE":
    #      asyncio.run(send_proactive_detail_report(application, TARGET_TELEGRAM_CHAT_ID))
    # else:
    #      logger.warning("TARGET_TELEGRAM_CHAT_ID is not set or is placeholder. Proactive report will not be sent on startup example.")
    #
    # Note: Calling asyncio.run() when an event loop is already managed by application.run_polling()
    # might lead to issues. For tasks that run alongside the bot, consider application.job_queue
    # or structuring your main function to be async if you need to await things before polling.
    # For a one-off task *before* polling starts, asyncio.run() is fine.
    # If you want to send it *after* polling starts, you'd need to create a task or use a job queue.

    application.run_polling()

if __name__ == "__main__":
    main() 
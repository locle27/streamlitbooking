import streamlit as st
import pandas as pd
import datetime
from datetime import timedelta
from typing import Optional, List

@st.dialog("✏️ Sửa thông tin đặt phòng")
def show_edit_booking_dialog(booking_id: str, main_df: pd.DataFrame, room_types: List[str]):
    """
    Dialog để edit thông tin đặt phòng với tính năng tự động tính Total Amount hoặc Price per Night
    """
    if main_df is None or main_df.empty:
        st.error("Không tìm thấy dữ liệu đặt phòng")
        return
    
    # Tìm booking cần edit
    booking_row = main_df[main_df['Số đặt phòng'] == booking_id]
    if booking_row.empty:
        st.error(f"Không tìm thấy đặt phòng với mã: {booking_id}")
        return
    
    booking_data = booking_row.iloc[0]
    
    st.subheader(f"Sửa đặt phòng: {booking_id}")
    
    # Initialize session state for dynamic calculation
    price_per_night_key = f"edit_price_per_night_{booking_id}"
    total_payment_key = f"edit_total_payment_{booking_id}"
    
    if price_per_night_key not in st.session_state:
        current_total = float(booking_data.get('Tổng thanh toán', 0))
        current_duration = int(booking_data.get('Stay Duration', 1))
        if current_duration > 0 and current_total > 0:
            st.session_state[price_per_night_key] = current_total / current_duration
        else:
            st.session_state[price_per_night_key] = 500000  # Default price
    
    if total_payment_key not in st.session_state:
        st.session_state[total_payment_key] = float(booking_data.get('Tổng thanh toán', 0))
    
    # Form edit với dữ liệu hiện tại
    with st.form(key=f"edit_booking_form_{booking_id}"):
        col1, col2 = st.columns(2)
        
        with col1:
            new_guest_name = st.text_input(
                "Tên khách*", 
                value=str(booking_data.get('Tên người đặt', '')),
                key=f"edit_guest_{booking_id}"
            )
            
            current_room_type = str(booking_data.get('Tên chỗ nghỉ', ''))
            room_index = 0
            if current_room_type in room_types:
                room_index = room_types.index(current_room_type)
            
            new_room_type = st.selectbox(
                "Loại phòng*", 
                options=room_types, 
                index=room_index,
                key=f"edit_room_{booking_id}"
            )
            
            # Parse ngày hiện tại
            current_checkin = booking_data.get('Check-in Date')
            if pd.notna(current_checkin):
                if isinstance(current_checkin, pd.Timestamp):
                    current_checkin_date = current_checkin.date()
                else:
                    current_checkin_date = pd.to_datetime(current_checkin).date()
            else:
                current_checkin_date = datetime.date.today()
                
            new_checkin = st.date_input(
                "Ngày check-in*",
                value=current_checkin_date,
                key=f"edit_checkin_{booking_id}"
            )
            
        with col2:
            current_checkout = booking_data.get('Check-out Date')
            if pd.notna(current_checkout):
                if isinstance(current_checkout, pd.Timestamp):
                    current_checkout_date = current_checkout.date()
                else:
                    current_checkout_date = pd.to_datetime(current_checkout).date()
            else:
                current_checkout_date = datetime.date.today() + timedelta(days=1)
                
            new_checkout = st.date_input(
                "Ngày check-out*",
                value=current_checkout_date,
                min_value=new_checkin + timedelta(days=1),
                key=f"edit_checkout_{booking_id}"
            )
            
            # Calculate number of nights
            stay_duration = (new_checkout - new_checkin).days
            st.info(f"**Số đêm:** {stay_duration}")
            
            # Status options
            status_options = ["OK", "Đã hủy", "Chờ xử lý"]
            current_status = str(booking_data.get('Tình trạng', 'OK'))
            status_index = 0
            if current_status in status_options:
                status_index = status_options.index(current_status)
                
            new_status = st.selectbox(
                "Trạng thái",
                options=status_options,
                index=status_index,
                key=f"edit_status_{booking_id}"
            )
        
        # Pricing section with bidirectional calculation
        st.subheader("💰 Tính giá linh hoạt")
        st.caption("Bạn có thể chỉnh sửa Tổng thanh toán hoặc Giá mỗi đêm - giá trị còn lại sẽ tự động cập nhật")
        
        col_price1, col_price2 = st.columns(2)
        
        with col_price1:
            # Total payment input (primary control)
            total_payment = st.number_input(
                "Tổng thanh toán (VND)*",
                min_value=0,
                value=int(st.session_state[total_payment_key]),
                step=50000,
                key=f"edit_total_payment_input_{booking_id}",
                help="Chỉnh sửa tổng tiền - giá mỗi đêm sẽ tự động cập nhật"
            )
            
            # Update session state and calculate price per night
            st.session_state[total_payment_key] = total_payment
            if stay_duration > 0:
                calculated_price_per_night = total_payment / stay_duration
                st.session_state[price_per_night_key] = calculated_price_per_night
            
        with col_price2:
            # Price per night input (secondary control)
            price_per_night = st.number_input(
                "Giá mỗi đêm (VND)*",
                min_value=0,
                value=int(st.session_state[price_per_night_key]),
                step=50000,
                key=f"edit_price_night_input_{booking_id}",
                help="Chỉnh sửa giá mỗi đêm - tổng tiền sẽ tự động cập nhật"
            )
            
            # Update session state and calculate total payment
            st.session_state[price_per_night_key] = price_per_night
            calculated_total_payment = price_per_night * stay_duration
            
            # Show the alternative calculation
            st.info(f"**Tính từ giá/đêm:** {calculated_total_payment:,} VND")
        
        # Show current calculation summary
        st.markdown("---")
        col_summary1, col_summary2 = st.columns(2)
        with col_summary1:
            st.success(f"**Tổng hiện tại:** {total_payment:,} VND")
        with col_summary2:
            current_price_per_night = total_payment / stay_duration if stay_duration > 0 else 0
            st.success(f"**Giá/đêm hiện tại:** {current_price_per_night:,.0f} VND")
        
        # Commission calculation
        new_commission = st.number_input(
            "Hoa hồng (VND)",
            min_value=0,
            value=int(float(booking_data.get('Hoa hồng', 0))),
            step=10000,
            key=f"edit_commission_{booking_id}"
        )
        
        # Submit buttons
        col_submit, col_cancel = st.columns(2)
        with col_submit:
            submit_edit = st.form_submit_button("💾 Lưu thay đổi", type="primary")
        with col_cancel:
            cancel_edit = st.form_submit_button("❌ Hủy")
            
        if cancel_edit:
            # Clean up session state
            for key in [price_per_night_key, total_payment_key]:
                if key in st.session_state:
                    del st.session_state[key]
            st.session_state.editing_booking_id_for_dialog = None
            st.rerun()
            
        if submit_edit:
            # Validate input
            errors = []
            
            if not new_guest_name.strip():
                errors.append("Tên khách không được để trống")
                
            if new_checkout <= new_checkin:
                errors.append("Ngày check-out phải sau ngày check-in")
                
            if total_payment <= 0 and new_status == "OK":
                errors.append("Tổng thanh toán phải > 0 cho đặt phòng 'OK'")
                
            if errors:
                for error in errors:
                    st.error(error)
            else:
                # Update booking data
                booking_index = booking_row.index[0]
                
                # Calculate final values
                stay_duration = (new_checkout - new_checkin).days
                final_price_per_night = total_payment / stay_duration if stay_duration > 0 else 0
                
                # Update dataframe
                st.session_state.df.loc[booking_index, 'Tên người đặt'] = new_guest_name.strip()
                st.session_state.df.loc[booking_index, 'Tên chỗ nghỉ'] = new_room_type
                st.session_state.df.loc[booking_index, 'Check-in Date'] = pd.Timestamp(new_checkin)
                st.session_state.df.loc[booking_index, 'Check-out Date'] = pd.Timestamp(new_checkout)
                st.session_state.df.loc[booking_index, 'Tổng thanh toán'] = float(total_payment)
                st.session_state.df.loc[booking_index, 'Hoa hồng'] = float(new_commission)
                st.session_state.df.loc[booking_index, 'Tình trạng'] = new_status
                st.session_state.df.loc[booking_index, 'Stay Duration'] = stay_duration
                st.session_state.df.loc[booking_index, 'Giá mỗi đêm'] = float(final_price_per_night)
                
                # Update display date columns
                st.session_state.df.loc[booking_index, 'Ngày đến'] = f"ngày {new_checkin.day} tháng {new_checkin.month} năm {new_checkin.year}"
                st.session_state.df.loc[booking_index, 'Ngày đi'] = f"ngày {new_checkout.day} tháng {new_checkout.month} năm {new_checkout.year}"
                
                # Update active bookings
                st.session_state.active_bookings = st.session_state.df[st.session_state.df['Tình trạng'] != 'Đã hủy'].copy()
                
                # Set success message and close dialog
                st.session_state.last_action_message = f"Đã cập nhật thành công đặt phòng {booking_id}"
                st.session_state.editing_booking_id_for_dialog = None
                
                # Clean up session state
                for key in [price_per_night_key, total_payment_key]:
                    if key in st.session_state:
                        del st.session_state[key]
                
                st.success("Đã lưu thay đổi thành công!")
                st.rerun() 
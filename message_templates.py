"""
Message Templates Module for Hotel Management System
Handles message templates parsing, formatting and management
"""

import streamlit as st
import re
from typing import Dict, List, Tuple, Optional

# Default message template content
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
I'll check again around 12:00 AM and let you know as soon as possible

CHECK IN : When you arrive at 118 Hang Bac Street, you will see a souvenir shop at the front.
Please walk into the shop about 10 meters, and you will find a staircase on your right-hand side.
Go up the stairs, then look for your room number.
The door will be unlocked, and the key will be inside the room.
FEED BACK : We hope you had a wonderful stay!
We'd love to hear about your experience – feel free to leave us a review on Booking.com

PARK : Please park your motorbike across the street, but make sure not to block their right-side door.
"""

def parse_message_templates(text_content: str) -> Dict[str, List[Tuple[str, str]]]:
    """Parse message templates from text content"""
    templates: Dict[str, List[Tuple[str, str]]] = {}
    current_category: Optional[str] = None
    current_label: Optional[str] = None
    current_message_lines: List[str] = []
    
    # Remove smart quotes
    cleaned_content = re.sub(r"'", "", text_content)

    def finalize_and_store_message():
        nonlocal current_category, current_label, current_message_lines, templates
        if current_category and current_label and current_message_lines:
            message = "\n".join(current_message_lines).strip()
            if message:
                if current_category not in templates:
                    templates[current_category] = []
                
                # Check if label already exists
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
        
        # Check for main category
        main_cat_match = re.match(r'^([A-Z][A-Z\s]*[A-Z]|[A-Z]+)\s*:\s*(.*)', line)
        
        # Check for sub-label (numbered)
        sub_label_numbered_match = re.match(r'^\s*(\d+\.)\s*(.*)', stripped_line)
        
        # Check for sub-label (named)
        sub_label_named_match = None
        if current_category:
            potential_sub_label_named_match = re.match(r'^\s*([\w\s()]+?)\s*:\s*(.*)', stripped_line)
            if potential_sub_label_named_match:
                if (potential_sub_label_named_match.group(1).strip() != current_category and 
                    not potential_sub_label_named_match.group(1).strip().isupper()):
                    sub_label_named_match = potential_sub_label_named_match
        
        if main_cat_match:
            potential_cat_name = main_cat_match.group(1).strip()
            if potential_cat_name.isupper():
                # New category
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
                # Numbered sub-label
                finalize_and_store_message()
                current_label = sub_label_numbered_match.group(1).strip()
                message_on_same_line = sub_label_numbered_match.group(2).strip()
                if message_on_same_line:
                    current_message_lines.append(message_on_same_line)
                is_new_sub_label = True
                
            elif sub_label_named_match:
                # Named sub-label
                if not (main_cat_match and main_cat_match.group(1).strip().isupper() and 
                        main_cat_match.group(1).strip() == sub_label_named_match.group(1).strip()):
                    finalize_and_store_message()
                    current_label = sub_label_named_match.group(1).strip()
                    message_on_same_line = sub_label_named_match.group(2).strip()
                    if message_on_same_line:
                        current_message_lines.append(message_on_same_line)
                    is_new_sub_label = True
            
            if not is_new_sub_label and main_cat_match is None:
                # Regular message line
                if stripped_line or current_message_lines:
                    if not current_label and stripped_line:
                        current_label = "DEFAULT"
                    current_message_lines.append(line)
    
    # Store last message
    finalize_and_store_message()
    
    return templates

def format_templates_to_text(templates_dict: Dict[str, List[Tuple[str, str]]]) -> str:
    """Format templates dictionary back to text format"""
    output_lines = []
    
    for category_name in sorted(templates_dict.keys()):
        labeled_messages = templates_dict[category_name]
        default_message_written_on_cat_line = False
        
        # Check if first message is DEFAULT
        if labeled_messages and labeled_messages[0][0] == "DEFAULT":
            default_msg_text = labeled_messages[0][1]
            msg_lines = default_msg_text.split('\n')
            output_lines.append(f"{category_name} : {msg_lines[0] if msg_lines else ''}")
            if len(msg_lines) > 1:
                output_lines.extend(msg_lines[1:])
            default_message_written_on_cat_line = True
        else:
            output_lines.append(f"{category_name} :")

        # Process other messages
        for i, (label, msg_text) in enumerate(labeled_messages):
            if label == "DEFAULT" and default_message_written_on_cat_line and i == 0:
                continue
            
            msg_lines = msg_text.split('\n')
            
            # Add spacing
            if not (label == "DEFAULT" and i == 0):
                if not (default_message_written_on_cat_line and i == 0 and label == "DEFAULT"):
                    if not (not default_message_written_on_cat_line and i == 0 and 
                            label == "DEFAULT" and output_lines and not output_lines[-1].endswith(":")):
                        output_lines.append("")
            
            if label == "DEFAULT":
                output_lines.extend(msg_lines)
            elif label.endswith('.'):
                # Numbered label
                output_lines.append(f"{label} {msg_lines[0] if msg_lines else ''}")
                if len(msg_lines) > 1:
                    output_lines.extend(msg_lines[1:])
            else:
                # Named label
                output_lines.append(f"{label} : {msg_lines[0] if msg_lines else ''}")
                if len(msg_lines) > 1:
                    output_lines.extend(msg_lines[1:])
        
        output_lines.append("")
    
    return "\n".join(output_lines) if output_lines else ""

def render_message_templates_tab():
    """Render the message templates tab"""
    st.header("💌 Quản lý Mẫu Tin Nhắn")
    
    # Initialize templates if not exists
    if 'message_templates_dict' not in st.session_state:
        st.session_state.message_templates_dict = parse_message_templates(DEFAULT_MESSAGE_TEMPLATE_CONTENT)
    
    if 'raw_template_content_for_download' not in st.session_state:
        st.session_state.raw_template_content_for_download = format_templates_to_text(
            st.session_state.message_templates_dict
        )
    
    # Upload new templates
    st.sidebar.subheader("Tải lên Mẫu Tin Nhắn")
    uploaded_template_file = st.sidebar.file_uploader(
        "Tải lên file .txt chứa mẫu tin nhắn:", 
        type=['txt'], 
        key="template_file_uploader"
    )
    
    if uploaded_template_file is not None:
        try:
            new_content = uploaded_template_file.read().decode("utf-8")
            parsed_templates = parse_message_templates(new_content)
            if parsed_templates:
                st.session_state.message_templates_dict = parsed_templates
                st.session_state.raw_template_content_for_download = format_templates_to_text(parsed_templates)
                st.sidebar.success("Đã tải và phân tích thành công file mẫu tin nhắn!")
                st.rerun()
            else:
                st.sidebar.error("Lỗi khi phân tích file mẫu tin nhắn.")
        except Exception as e:
            st.sidebar.error(f"Lỗi khi xử lý file: {e}")
    
    # Reset to default button
    if st.sidebar.button("🔄 Khôi phục mẫu tin nhắn mặc định", key="reset_default_templates_button"):
        st.session_state.message_templates_dict = parse_message_templates(DEFAULT_MESSAGE_TEMPLATE_CONTENT)
        st.session_state.raw_template_content_for_download = format_templates_to_text(
            st.session_state.message_templates_dict
        )
        st.sidebar.success("Đã khôi phục các mẫu tin nhắn về mặc định!")
        st.rerun()
    
    st.markdown("---")
    
    # Add new template form
    st.subheader("Thêm Mẫu Tin Nhắn Mới")
    with st.form("add_template_form", clear_on_submit=True):
        new_template_category = st.text_input(
            "Chủ đề chính (VD: CHECK OUT, WIFI INFO):"
        ).upper().strip()
        
        new_template_label = st.text_input(
            "Nhãn phụ (VD: Hướng dẫn, Lưu ý 1, 2. - Bỏ trống nếu là tin nhắn chính cho chủ đề):"
        ).strip()
        
        new_template_message = st.text_area("Nội dung tin nhắn:", height=150)
        submit_add_template = st.form_submit_button("➕ Thêm mẫu này")
        
        if submit_add_template:
            if not new_template_category or not new_template_message:
                st.error("Chủ đề chính và Nội dung tin nhắn không được để trống!")
            else:
                label_to_add = new_template_label if new_template_label else "DEFAULT"
                current_templates = st.session_state.message_templates_dict.copy()
                
                if new_template_category not in current_templates:
                    current_templates[new_template_category] = []
                
                # Check if label exists
                label_exists_at_index = -1
                for idx, (lbl, _) in enumerate(current_templates[new_template_category]):
                    if lbl == label_to_add:
                        label_exists_at_index = idx
                        break
                
                if label_exists_at_index != -1:
                    current_templates[new_template_category][label_exists_at_index] = (
                        label_to_add, new_template_message
                    )
                    st.success(f"Đã cập nhật mẫu tin nhắn '{label_to_add}' trong chủ đề '{new_template_category}'.")
                else:
                    current_templates[new_template_category].append((label_to_add, new_template_message))
                    st.success(f"Đã thêm mẫu tin nhắn '{label_to_add}' vào chủ đề '{new_template_category}'.")
                
                st.session_state.message_templates_dict = current_templates
                st.session_state.raw_template_content_for_download = format_templates_to_text(current_templates)
                st.rerun()
    
    st.markdown("---")
    
    # Display current templates
    st.subheader("Danh Sách Mẫu Tin Nhắn Hiện Tại")
    
    if not st.session_state.get('message_templates_dict'):
        st.info("Chưa có mẫu tin nhắn nào. Hãy thêm mới hoặc tải lên file.")
    else:
        for category, labeled_messages in sorted(st.session_state.message_templates_dict.items()):
            with st.expander(f"Chủ đề: {category}", expanded=False):
                if not labeled_messages:
                    st.caption("Không có tin nhắn nào cho chủ đề này.")
                    continue
                
                for i, (label, message) in enumerate(labeled_messages):
                    widget_key_prefix = f"tpl_cat_{''.join(filter(str.isalnum, category))}_lbl_{''.join(filter(str.isalnum, label))}_{i}"
                    
                    col1_msg, col2_msg = st.columns([4, 1])
                    with col1_msg:
                        if label != "DEFAULT":
                            st.markdown(f"**Nhãn: {label}**")
                        else:
                            st.markdown(f"**Nội dung chính:**")
                        
                        st.text_area(
                            label=f"_{label}_in_{category}_content_display_",
                            value=message,
                            height=max(80, len(message.split('\n')) * 20 + 40),
                            key=f"{widget_key_prefix}_text_area_display",
                            disabled=True,
                            help="Nội dung tin nhắn. Bạn có thể chọn và sao chép thủ công từ đây."
                        )
                    
                    if i < len(labeled_messages) - 1:
                        st.markdown("---")
        
        st.markdown("---")
        
        # Download button
        current_raw_template_content = st.session_state.get('raw_template_content_for_download', "")
        if isinstance(current_raw_template_content, str):
            st.download_button(
                label="📥 Tải về tất cả mẫu tin nhắn (TXT)",
                data=current_raw_template_content.encode("utf-8"),
                file_name="message_templates_download.txt",
                mime="text/plain",
                key="download_message_templates_button_v2"
            ) 
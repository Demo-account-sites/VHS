import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import seatsio

# --- PAGE CONFIG ---
st.set_page_config(page_title="Sheet to Seats.io", layout="wide")

# --- AUTHENTICATION ---
def check_password():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if not st.session_state.authenticated:
        st.title("🔐 Login")
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        if st.button("Login"):
            if email == st.secrets["user_email"] and password == st.secrets["user_password"]:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Invalid credentials")
        return False
    return True

# --- DATA FETCHING (GOOGLE SHEETS) ---
def fetch_from_sheet():
    # Authenticate with Google
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    gc = gspread.authorize(creds)
    
    # Open the sheet
    sh = gc.open("VHS availabilities per category") # Your Sheet Name
    worksheet = sh.worksheet("Extract1")
    
    # Get all records as a list of dictionaries
    data = worksheet.get_all_records()
    df = pd.DataFrame(data)
    
    # Clean up: Streamlit likes unique keys. 
    # Ensure 'event_key' (Column F) exists and is handled.
    st.session_state.df = df
    st.session_state.availability = {str(key): "Pending..." for key in df['event_key'] if key}

# --- SEATSIO API CALL ---
def update_seatsio(event_key):
    client = seatsio.Client(seatsio.Region.EU(), secret_key=st.secrets["seatsio_key"])
    try:
        result = client.events.reports.by_category_label(event_key)
        status_list = []
        for category, seat_list in result.items.items():
            booked = sum(getattr(s, 'num_booked', 0) or 0 for s in seat_list)
            held = sum(getattr(s, 'num_held', 0) or 0 for s in seat_list)
            cap = sum(getattr(s, 'capacity', 0) or 0 for s in seat_list)
            status_list.append(f"**{category}**: {booked+held}/{cap}")
        st.session_state.availability[str(event_key)] = " | ".join(status_list)
    except Exception as e:
        st.session_state.availability[str(event_key)] = f"Error: {e}"

# --- MAIN APP UI ---
if check_password():
    st.title("📊 Event Availability Manager")

    if "df" not in st.session_state:
        st.session_state.df = None
    if "availability" not in st.session_state:
        st.session_state.availability = {}

    # Top Action Buttons
    col_a, col_b = st.columns([1, 4])
    if col_a.button("🔄 Sync Sheet"):
        with st.status("Reading Google Sheet...", expanded=False):
            fetch_from_sheet()
        st.rerun()
    
    if st.session_state.df is not None:
        if col_b.button("⚡ Refresh All Seats.io"):
            with st.status("Updating all rows...", expanded=False):
                for key in st.session_state.df['event_key']:
                    if key: update_seatsio(key)
            st.rerun()

        st.divider()

        # Display Custom Table
        # Define column widths to match your sheet's structure
        cols = st.columns([2, 2, 2, 4, 1])
        headers = ["Product", "Show Name", "Start Date", "Availability", "Action"]
        for col, h in zip(cols, headers):
            col.write(f"**{h}**")

        for _, row in st.session_state.df.iterrows():
            key = str(row['event_key'])
            if not key: continue

            c1, c2, c3, c4, c5 = st.columns([2, 2, 2, 4, 1])
            c1.write(row.get('product_name', 'N/A'))
            c2.write(row.get('show_name', 'N/A'))
            c3.write(row.get('show_start_date', 'N/A'))
            
            # Show the availability from session state
            c4.info(st.session_state.availability.get(key, "Pending"))
            
            # Individual row button
            if c5.button("🔄", key=f"btn_{key}"):
                update_seatsio(key)
                st.rerun()
    else:
        st.info("Click 'Sync Sheet' to load the data.")

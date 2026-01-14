import streamlit as st
import pandas as pd
import seatsio
import io

# --- PAGE CONFIG ---
st.set_page_config(page_title="CSV Event Manager", layout="wide")

# --- 1. LOGIN LOGIC ---
def check_password():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        st.title("🔐 Login")
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        if st.button("Login"):
            # These must be set in your Streamlit Cloud Secrets
            if email == st.secrets["user_email"] and password == st.secrets["user_password"]:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Invalid credentials")
        return False
    return True

# --- 2. SEATSIO API FUNCTION ---
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
        
        # Save results to session state so they persist
        st.session_state.availability[str(event_key)] = " | ".join(status_list)
    except Exception as e:
        st.session_state.availability[str(event_key)] = f"Error: {e}"

# --- 3. MAIN APP UI ---
if check_password():
    st.title("📂 CSV Availability Manager")

    # Initialize Session States
    if "df" not in st.session_state:
        st.session_state.df = None
    if "availability" not in st.session_state:
        st.session_state.availability = {}

    # File Uploader
    uploaded_file = st.file_uploader("Upload your event CSV file", type=["csv"])

    if uploaded_file is not None:
        # Load data only if it's the first time or a new file
        if st.session_state.df is None or st.button("🔄 Reload CSV Data"):
            df = pd.read_csv(uploaded_file)
            st.session_state.df = df
            # Reset availability map
            st.session_state.availability = {str(key): "Click to load" for key in df['event_key'] if pd.notnull(key)}
            st.rerun()

    if st.session_state.df is not None:
        st.divider()
        
        # Action Buttons
        if st.button("⚡ Run API for All Rows"):
            with st.status("Fetching all data from Seats.io...", expanded=False) as status:
                for key in st.session_state.df['event_key']:
                    if pd.notnull(key):
                        update_seatsio(key)
                status.update(label="All rows updated!", state="complete")
            st.rerun()

        # Custom Table View
        # Adjust these column names to match your CSV headers exactly
        cols = st.columns([2, 2, 2, 4, 1])
        headers = ["Product", "Show Name", "Start Date", "Live Availability", "Action"]
        for col, h in zip(cols, headers):
            col.write(f"**{h}**")

        for index, row in st.session_state.df.iterrows():
            key = str(row['event_key'])
            if not key or key == "nan":
                continue

            c1, c2, c3, c4, c5 = st.columns([2, 2, 2, 4, 1])
            
            # Using .get() or checking names to prevent errors if CSV headers vary
            c1.write(row.get('product_name', 'N/A'))
            c2.write(row.get('show_name', 'N/A'))
            c3.write(row.get('show_start_date', 'N/A'))
            
            # Show the availability status
            avail_text = st.session_state.availability.get(key, "Pending...")
            if "Error" in avail_text:
                c4.error(avail_text)
            elif "/" in avail_text:
                c4.success(avail_text)
            else:
                c4.info(avail_text)
            
            # Individual Row Button
            if c5.button("🔄", key=f"btn_{index}_{key}"):
                update_seatsio(key)
                st.rerun()

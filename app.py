import streamlit as st
import pandas as pd
import seatsio
from google.cloud import bigquery
from datetime import datetime, time

# --- PAGE CONFIG ---
st.set_page_config(page_title="BigQuery Event Manager", layout="wide")

# --- 1. LOGIN LOGIC ---
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

# --- 2. DATA FETCHING (BIGQUERY) ---
@st.cache_data(ttl=3600) # Check for fresh data every hour
def fetch_bigquery_data():
    # Construct a BigQuery client object.
    client = bigquery.Client.from_service_account_info(st.secrets["gcp_service_account"])
    
    query = """
    SELECT
      p.id AS product_id,
      p.name AS product_name,
      psc.id AS show_id,
      psc.category_name AS show_name,
      ts.start_date_time_tz AS show_start_date,
      ts.event_key AS event_key
    FROM `smeetz-sandbox.ebdb.product_slot_category` AS psc
    JOIN `smeetz-sandbox.ebdb.product` AS p ON p.id = psc.product_id
    JOIN `smeetz-sandbox.ebdb.resource` AS r ON r.id = psc.resource_id
    JOIN `smeetz-sandbox.ebdb.time_slot` AS ts ON ts.category_id = psc.id
    WHERE p.owner_group_id = 19469
      AND p.status = 1
      AND psc.type = 3
      AND psc.cancelled = 0
      AND ts.start_date_time_tz > CURRENT_DATETIME()
    ORDER BY ts.start_date_time_tz;
    """
    query_job = client.query(query)
    return query_job.to_dataframe()

# --- 3. SEATSIO API FUNCTION ---
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

# --- 4. MAIN APP UI ---
if check_password():
    st.title("📂 Live Event Availability (BigQuery)")

    # Initialize Session States
    if "availability" not in st.session_state:
        st.session_state.availability = {}

    # Auto-fetch data
    with st.spinner("Fetching data from BigQuery..."):
        df = fetch_bigquery_data()
        
    # Manual Refresh Button
    if st.sidebar.button("🔄 Force Refresh BigQuery"):
        st.cache_data.clear()
        st.rerun()

    if not df.empty:
        # Initialize availability map if not already present for these keys
        for key in df['event_key']:
            if pd.notnull(key) and str(key) not in st.session_state.availability:
                st.session_state.availability[str(key)] = "Click to load"

        st.divider()
        
        # Action Buttons
        if st.button("⚡ Run API for All Rows"):
            with st.status("Fetching all data from Seats.io...", expanded=False) as status:
                for key in df['event_key']:
                    if pd.notnull(key):
                        update_seatsio(key)
                status.update(label="All rows updated!", state="complete")
            st.rerun()

        # Custom Table View
        cols = st.columns([2, 2, 2, 4, 1])
        headers = ["Product", "Show Name", "Start Date", "Live Availability", "Action"]
        for col, h in zip(cols, headers):
            col.write(f"**{h}**")

        for index, row in df.iterrows():
            key = str(row['event_key'])
            if not key or key == "nan":
                continue

            c1, c2, c3, c4, c5 = st.columns([2, 2, 2, 4, 1])
            
            c1.write(row.get('product_name', 'N/A'))
            c2.write(row.get('show_name', 'N/A'))
            
            # Formatting date if it's a timestamp
            date_val = row.get('show_start_date', 'N/A')
            c3.write(str(date_val))
            
            avail_text = st.session_state.availability.get(key, "Pending...")
            if "Error" in avail_text:
                c4.error(avail_text)
            elif "/" in avail_text:
                c4.success(avail_text)
            else:
                c4.info(avail_text)
            
            if c5.button("🔄", key=f"btn_{index}_{key}"):
                update_seatsio(key)
                st.rerun()
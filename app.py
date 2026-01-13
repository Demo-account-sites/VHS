import streamlit as st
import pandas as pd
from google.cloud import bigquery
import seatsio
from google.oauth2 import service_account

st.set_page_config(page_title="Event Manager", layout="wide")

# --- 1. SESSION STATE INITIALIZATION ---
if "df" not in st.session_state:
    st.session_state.df = None
if "availability" not in st.session_state:
    st.session_state.availability = {}

# --- 2. BIGQUERY FUNCTION ---
def fetch_from_bigquery():
    creds_dict = st.secrets["gcp_service_account"]
    credentials = service_account.Credentials.from_service_account_info(creds_dict)
    bq_client = bigquery.Client(credentials=credentials, project=creds_dict['project_id'])
    
    query = """
    SELECT
      p.name AS product_name,
      psc.category_name AS show_name,
      ts.start_date_time_tz AS show_start_date,
      ts.event_key AS event_key
    FROM `smeetz-sandbox.ebdb.product_slot_category` AS psc
    JOIN `smeetz-sandbox.ebdb.product` AS p ON p.id = psc.product_id
    JOIN `smeetz-sandbox.ebdb.time_slot` AS ts ON ts.category_id = psc.id
    WHERE p.owner_group_id = 19469 AND p.status = 1 AND psc.type = 3
      AND psc.cancelled = 0 AND ts.start_date_time_tz > CURRENT_DATETIME()
    ORDER BY ts.start_date_time_tz;
    """
    df = bq_client.query(query).to_dataframe()
    st.session_state.df = df
    # Reset availability mapping when DB is refreshed
    st.session_state.availability = {key: "Click to load" for key in df['event_key']}

# --- 3. SEATSIO API FUNCTION ---
def update_single_event(event_key):
    client = seatsio.Client(seatsio.Region.EU(), secret_key=st.secrets["seatsio_key"])
    try:
        result = client.events.reports.by_category_label(event_key)
        details = []
        for category, seat_list in result.items.items():
            booked = sum(getattr(s, 'num_booked', 0) or 0 for s in seat_list)
            held = sum(getattr(s, 'num_held', 0) or 0 for s in seat_list)
            cap = sum(getattr(s, 'capacity', 0) or 0 for s in seat_list)
            details.append(f"{category}: {booked+held}/{cap}")
        st.session_state.availability[event_key] = " | ".join(details)
    except Exception as e:
        st.session_state.availability[event_key] = f"Error: {e}"

# --- 4. UI LAYOUT ---
st.title("🎟️ Event Availability Monitor")

col_header1, col_header2 = st.columns([3, 1])
with col_header2:
    if st.button("🔄 Refresh from BigQuery", use_container_width=True):
        with st.spinner("Querying BigQuery..."):
            fetch_from_bigquery()
            # Automatically trigger all API calls after DB refresh
            for key in st.session_state.df['event_key']:
                update_single_event(key)
        st.rerun()

if st.session_state.df is not None:
    # Creating a custom grid since standard dataframes don't support buttons in rows easily
    # Table Header
    h_col1, h_col2, h_col3, h_col4, h_col5 = st.columns([2, 2, 2, 4, 1])
    h_col1.write("**Product**")
    h_col2.write("**Show Name**")
    h_col3.write("**Date**")
    h_col4.write("**Live Availability**")
    h_col5.write("**Action**")
    st.divider()

    # Table Rows
    for _, row in st.session_state.df.iterrows():
        r_col1, r_col2, r_col3, r_col4, r_col5 = st.columns([2, 2, 2, 4, 1])
        
        key = row['event_key']
        r_col1.write(row['product_name'])
        r_col2.write(row['show_name'])
        r_col3.write(row['show_start_date'].strftime("%Y-%m-%d %H:%M"))
        
        # Display the stored availability from session state
        avail_text = st.session_state.availability.get(key, "N/A")
        r_col4.info(avail_text) if "Click" not in avail_text else r_col4.write(avail_text)
        
        # Row-specific refresh button
        if r_col5.button("🔄", key=f"btn_{key}"):
            update_single_event(key)
            st.rerun()
else:
    st.info("Please refresh from BigQuery to load event data.")
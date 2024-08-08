import streamlit as st
import sqlite3
import pandas as pd
import requests
import time
import subprocess
from streamlit_geolocation import streamlit_geolocation
from math import radians, sin, cos, sqrt, atan2
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable
import numpy as np
import time
import random

# Set page configuration
st.set_page_config(page_title="Nearby Stations Finder", page_icon="🔌", layout="wide")

# Custom CSS
st.markdown("""
<style>
    .reportview-container {
        background: #f0f2f6
    }
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    h1 {
        color: #1E88E5;
    }
    .stButton>button {
        background-color: #1E88E5;
        color: white;
    }
    .stSelectbox [data-baseweb="select"] {
        background-color: white;
    }
    .stTextInput>div>div>input {
        background-color: white;
    }
</style>
""", unsafe_allow_html=True)

def geocode_location(location_name):
    geolocator = Nominatim(user_agent="my_app")
    try:
        location = geolocator.geocode(location_name)
        if location:
            return location.latitude, location.longitude
        else:
            return None, None
    except (GeocoderTimedOut, GeocoderUnavailable):
        st.error("Geocoding service is unavailable. Please try again later.")
        return None, None

def get_stations_data(location_node_id):
    # API endpoint
    url = 'https://api.voltaapi.com/v1/pg-graphql'

    # Headers
    headers = {
        'authority': 'api.voltaapi.com',
        'accept': '*/*',
        'accept-language': 'en-US,en;q=0.9',
        'content-type': 'application/json',
        'origin': 'https://voltacharging.com',
        'referer': 'https://voltacharging.com/',
        'x-api-key': 'u74w38X44fa7m3calbsu69blJVcC739z8NWJggVv'
    }

    # GraphQL query and variables
    data = {
        "query": """
            query getStation($locationNodeId: ID!) {
              locationByNodeId(nodeId: $locationNodeId) {
              name
                stationsByLocationId(orderBy: STATION_NUMBER_ASC) {
                  edges {
                    node {
                      id
                      stationNumber
                      name
                      evses {
                        edges {
                          node {
                            state
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
        """,
        "variables": {
            "locationNodeId": location_node_id
        }
    }

    # Making the POST request
    response = requests.post(url, headers=headers, json=data)
    return response.json()

def get_stations_with_charging_state(location_node_id):
    data = get_stations_data(location_node_id)
    stations_data = data['data']['locationByNodeId']['stationsByLocationId']['edges']
    stations_list = []
    station_name = data['data']['locationByNodeId']['name']
    for station in stations_data:
        station_node = station['node']
        charging_states = [evse['node']['state'] for evse in station_node['evses']['edges']]
        stations_list.append({
            "name": station_name,
            "node_name": station_node['name'],
            "stationNumber": station_node['stationNumber'],
            "charging_states": charging_states
        })
    df_stations = pd.DataFrame(stations_list)
    df_expanded = df_stations.explode('charging_states')
    df_expanded.reset_index(drop=True, inplace=True)
    # print(df_expanded)
    # print (df_stations)
    return df_expanded

def haversine_distance(lat1, lon1, lat2, lon2):
    if None in (lat1, lon1, lat2, lon2):
        return None
    
    R = 6371  # Earth's radius in kilometers

    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    
    distance = R * c
    return distance

st.title("🔌 Nearby Charging Stations Finder")

col1, col2 = st.columns(2)

with col1:
    st.subheader("📍 Location")
    location_search = st.text_input("Enter a city name or address:", placeholder="e.g., Sunnyvale, CA")

    if not location_search:
        st.info("Using current or default location")

with col2:
    st.subheader("🔍 Search Options")
    search_radius_miles = st.select_slider("Select search radius (miles):", options=[4, 6, 8, 10, 12], value=4)
    search_radius_km = search_radius_miles * 1.60934  # Convert miles to kilometers

    enable_polling = st.toggle("Enable real-time updates", value=False)
    polling_interval = 2  # Default polling interval in seconds

    enable_notifications = st.toggle("Enable notifications", value=False)

# Default location (Cupertino, CA)
default_lat = 37.3526819
default_lon = -122.0513147

st.markdown("---")

if location_search:
    lat, lon = geocode_location(location_search)
    if lat is not None and lon is not None:
        st.write(f"Searched location: Latitude {lat}, Longitude {lon}")
    else:
        st.error("Location not found. Using default or current location.")
        lat, lon = None, None
else:
    location = streamlit_geolocation()
    if location is None or location.get('latitude') is None or location.get('longitude') is None:
        lat, lon = default_lat, default_lon
        st.write(f"Using default location: Latitude {lat}, Longitude {lon}")
    else:
        lat = location['latitude']
        lon = location['longitude']
        st.write(f"Your current location: Latitude {lat}, Longitude {lon}")

# Ensure lat and lon are not None
if lat is None or lon is None:
    lat, lon = default_lat, default_lon
    st.write(f"Invalid location detected. Using default location: Latitude {lat}, Longitude {lon}")

conn = sqlite3.connect('stations.sqlite')
cursor = conn.cursor()

# Fetch all stations
cursor.execute("SELECT name, latitude, longitude, nodeId FROM stations")
stations = cursor.fetchall()

nearby_stations = []

for station in stations:
    station_name, station_lat, station_lon, node_id = station
    distance = haversine_distance(lat, lon, station_lat, station_lon)
    if distance is not None and distance <= search_radius_km:
        nearby_stations.append({
            'Name': station_name,
            'Latitude': station_lat,
            'Longitude': station_lon,
            'Distance (miles)': f"{distance / 1.60934:.2f}",  # Convert km to miles and format to 2 decimal places
            'NodeId': node_id
        })

if nearby_stations:
    df = pd.DataFrame(nearby_stations)
    df = df.sort_values('Distance (miles)')
    
    def send_notification(node_name, charging_state):
        message = f"{node_name} is {charging_state}"
        subprocess.run(["curl", "-d", message, "ntfy.sh/voltatrack_available"])

    def update_charging_data(previous_data=None):
        all_charging_data = []
        for _, station in df.iterrows():
            charging_data = get_stations_with_charging_state(station['NodeId'])
            charging_data['Distance (miles)'] = station['Distance (miles)']
            all_charging_data.append(charging_data)
    
        combined_data = pd.concat(all_charging_data, ignore_index=True)
        combined_data = combined_data.sort_values('Distance (miles)')
    
        if enable_notifications:
            combined_data['Notify'] = False  # Add checkbox column
    
        if enable_notifications and previous_data is not None:
            for _, current_row in combined_data.iterrows():
                previous_row = previous_data[
                    (previous_data['node_name'] == current_row['node_name']) & 
                    (previous_data['stationNumber'] == current_row['stationNumber'])
                ]
                if not previous_row.empty:
                    prev_state = previous_row['charging_states'].iloc[0]
                    curr_state = current_row['charging_states']
                    if prev_state in ['CHARGING', 'CHARGE_STOPPED'] and curr_state == 'PLUGGED_OUT':
                        send_notification(current_row['node_name'], curr_state)
    
        return combined_data

    combined_data = update_charging_data()
    
    st.subheader(f"🔋 Charging Stations within {search_radius_miles} miles:")
    
    def color_charging_states(val):
        if isinstance(val, bool):  # For checkbox column
            return ''
        bg_color = '#e6ffe6' if val in ['PLUGGED_OUT', 'IDLE'] else '#ffe6e6'
        return f'background-color: {bg_color}; color: #333333;'

    charging_data_container = st.empty()
    
    if enable_notifications:
        columns_to_display = ['node_name', 'stationNumber', 'charging_states', 'Distance (miles)', 'Notify']
    else:
        columns_to_display = ['node_name', 'stationNumber', 'charging_states', 'Distance (miles)']
    
    styled_df = combined_data[columns_to_display].style.applymap(color_charging_states)
    
    # Custom CSS for the dataframe
    st.markdown("""
    <style>
    .dataframe {
        font-family: Arial, sans-serif;
        border-collapse: collapse;
        width: 100%;
    }
    .dataframe td, .dataframe th {
        border: 1px solid #ddd;
        padding: 8px;
    }
    .dataframe td:nth-child(2) {  /* stationNumber column */
        width: 80px;
        text-align: center;
    }
    .dataframe td:last-child {  /* Distance column */
        width: 100px;
        text-align: right;
    }
    .dataframe tr:nth-child(even) {
        background-color: #f9f9f9;
    }
    .dataframe tr:hover {
        background-color: #f5f5f5;
    }
    .dataframe th {
        padding-top: 12px;
        padding-bottom: 12px;
        text-align: left;
        background-color: #1E88E5;
        color: white;
    }
    .dataframe td:nth-child(5) {  /* Notify column */
        width: 50px;
        text-align: center;
    }
    </style>
    """, unsafe_allow_html=True)
    
    if enable_notifications:
        unique_key = f"data_editor_{time.time()}_{random.randint(0, 1000000)}"
        edited_df = charging_data_container.data_editor(
            styled_df,
            use_container_width=True,
            disabled=["node_name", "stationNumber", "charging_states", "Distance (miles)"],
            key=unique_key
        )
    else:
        charging_data_container.dataframe(styled_df, use_container_width=True)

    if enable_polling:
        st.info("🔄 Real-time updates enabled. Data will refresh every 2 seconds.")
        with st.spinner('Updating data...'):
            while True: 
                time.sleep(polling_interval)
                previous_data = combined_data.copy()
                combined_data = update_charging_data(previous_data)
                if enable_notifications:
                    columns_to_display = ['node_name', 'stationNumber', 'charging_states', 'Distance (miles)', 'Notify']
                else:
                    columns_to_display = ['node_name', 'stationNumber', 'charging_states', 'Distance (miles)']
                styled_df = combined_data[columns_to_display].style.applymap(color_charging_states)
                if enable_notifications:
                    unique_key = f"data_editor_loop_{time.time()}_{random.randint(0, 1000000)}"
                    edited_df = charging_data_container.data_editor(
                        styled_df,
                        use_container_width=True,
                        disabled=["node_name", "stationNumber", "charging_states", "Distance (miles)"],
                        key=unique_key
                    )
                else:
                    charging_data_container.dataframe(styled_df, use_container_width=True)
                st.rerun()
else:
    st.warning(f"⚠️ No stations found within {search_radius_miles} miles of your location.")

conn.close()

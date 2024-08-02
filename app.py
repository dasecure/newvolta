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

st.title("Nearby Stations Finder")

# Default location (Cupertino, CA)
default_lat = 37.3526819
default_lon = -122.0513147

# Add search radius selectbox
search_radius_miles = st.selectbox("Select search radius (miles):", [4, 6, 8, 10, 12])
search_radius_km = search_radius_miles * 1.60934  # Convert miles to kilometers

# Add checkbox for polling
enable_polling = st.checkbox("Enable real-time updates", value=False)
polling_interval = 2  # Default polling interval in seconds

# Add checkbox for notifications
enable_notifications = st.checkbox("Enable notifications", value=False)

# Add location search textbox
location_search = st.text_input("Enter a city name or address:")

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
            'Distance (km)': round(distance, 2),
            'NodeId': node_id
        })

if nearby_stations:
    df = pd.DataFrame(nearby_stations)
    df = df.sort_values('Distance (km)')
    
    def send_notification(node_name, charging_state):
        message = f"{node_name} is {charging_state}"
        subprocess.run(["curl", "-d", message, "ntfy.sh/voltatrack_available"])

    def update_charging_data(previous_data=None):
        all_charging_data = []
        for _, station in df.iterrows():
            charging_data = get_stations_with_charging_state(station['NodeId'])
            charging_data['Distance (km)'] = station['Distance (km)']
            all_charging_data.append(charging_data)
    
        combined_data = pd.concat(all_charging_data, ignore_index=True)
        combined_data = combined_data.sort_values('Distance (km)')
    
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
    
    st.write(f"Charging Stations within {search_radius_miles} miles:")
    charging_data_container = st.empty()
    charging_data_container.dataframe(combined_data[['node_name', 'stationNumber', 'charging_states', 'Distance (km)']])

    if enable_polling:
        st.write("Real-time updates enabled. Data will refresh every 2 seconds.")
        while True:
            time.sleep(polling_interval)
            previous_data = combined_data.copy()
            combined_data = update_charging_data(previous_data)
            charging_data_container.dataframe(combined_data[['node_name', 'stationNumber', 'charging_states', 'Distance (km)']])
            st.rerun()
else:
    st.write(f"No stations found within {search_radius_miles} miles of your location.")

conn.close()

import streamlit as st
import sqlite3
import pandas as pd
import requests
from streamlit_geolocation import streamlit_geolocation
from math import radians, sin, cos, sqrt, atan2

def get_stations_with_charging_state(location_node_id):
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
    data = response.json()

    stations_with_state = []
    if data and 'data' in data:
        location = data['data']['locationByNodeId']
        if location and 'stationsByLocationId' in location:
            for edge in location['stationsByLocationId']['edges']:
                station = edge['node']
                evses = station['evses']['edges']
                state = evses[0]['node']['state'] if evses else "Unknown"
                stations_with_state.append({
                    'name': station['name'],
                    'state': state
                })

    return stations_with_state

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
cursor.execute("SELECT nodeId, name, latitude, longitude FROM stations")
stations = cursor.fetchall()

st.write(f"Total stations in database: {len(stations)}")

nearby_stations = []

for station in stations:
    node_id, station_name, station_lat, station_lon = station
    distance = haversine_distance(lat, lon, station_lat, station_lon)
    if distance is not None and distance <= 6.44:  # 4 miles is approximately 6.44 kilometers
        # Fetch station data with charging states
        stations_data = get_stations_with_charging_state(node_id)
        
        if stations_data:
            for station_data in stations_data:
                nearby_stations.append({
                    'Name': f"{station_name} - {station_data['name']}",
                    'Latitude': station_lat,
                    'Longitude': station_lon,
                    'Distance (km)': round(distance, 2),
                    'Charging State': station_data['state']
                })
        else:
            st.write(f"No charging state data for station: {station_name}")

st.write(f"Nearby stations found: {len(nearby_stations)}")

if nearby_stations:
    df = pd.DataFrame(nearby_stations)
    df = df.sort_values('Distance (km)')
    st.write("Stations within 4 miles:")
    
    # Display the results in a neat table
    st.table(df[['Name', 'Distance (km)', 'Charging State']])
else:
    st.write("No stations found within 4 miles of your location.")

conn.close()

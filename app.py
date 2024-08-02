import streamlit as st
import sqlite3
import pandas as pd
import requests
from streamlit_geolocation import streamlit_geolocation
from math import radians, sin, cos, sqrt, atan2
from get_stations_with_charging_state import get_stations_with_charging_state

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
    update_stationsDB(df_stations)
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
    if distance is not None and distance <= 6.44:  # 4 miles is approximately 6.44 kilometers
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
    st.write("Stations within 4 miles:")
    st.dataframe(df[['Name', 'Distance (km)']])

    st.write("Charging Stations and Their States:")
    for _, station in df.iterrows():
        st.write(f"Station: {station['Name']}")
        charging_data = get_stations_with_charging_state(station['NodeId'])
        st.table(charging_data[['node_name', 'stationNumber', 'charging_states']])
else:
    st.write("No stations found within 4 miles of your location.")

conn.close()

import streamlit as st
import sqlite3
import pandas as pd
from streamlit_geolocation import streamlit_geolocation
from math import radians, sin, cos, sqrt, atan2

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371  # Earth's radius in kilometers

    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    
    distance = R * c
    return distance

st.title("Nearby Stations Finder")

location = streamlit_geolocation()

if location:
    lat = location['latitude']
    lon = location['longitude']
    st.write(f"Your current location: Latitude {lat}, Longitude {lon}")

    conn = sqlite3.connect('stations.sqlite')
    cursor = conn.cursor()

    # Fetch all stations
    cursor.execute("SELECT name, latitude, longitude FROM stations")
    stations = cursor.fetchall()

    nearby_stations = []

    for station in stations:
        station_name, station_lat, station_lon = station
        distance = haversine_distance(lat, lon, station_lat, station_lon)
        if distance <= 6.44:  # 4 miles is approximately 6.44 kilometers
            nearby_stations.append({
                'Name': station_name,
                'Latitude': station_lat,
                'Longitude': station_lon,
                'Distance (km)': round(distance, 2)
            })

    if nearby_stations:
        df = pd.DataFrame(nearby_stations)
        df = df.sort_values('Distance (km)')
        st.write("Stations within 4 miles:")
        st.dataframe(df)
    else:
        st.write("No stations found within 4 miles of your location.")

    conn.close()
else:
    st.write("Please enable location access to find nearby stations.")

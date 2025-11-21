#!/usr/bin/env python3
"""
Strike Map Generator

This script takes the CSV output from compile_strike_csv.py and creates an interactive
map of Central Europe showing historical strike locations using GeoNames coordinates.

Usage: python strike_map_generator.py <input_csv> <output_html> [options]
"""

import pandas as pd
import folium
import requests
import time
import json
import os
import sys
import argparse
from typing import Dict, Tuple, Optional, List
from pathlib import Path
import sqlite3
from datetime import datetime


# Configuration
GEONAMES_USERNAME = None  # Will be set from environment variable
GEONAMES_API_BASE = "http://api.geonames.org"
CACHE_DB_FILE = "geonames_cache.db"
REQUEST_DELAY = 0.1  # Delay between API requests to respect rate limits
MAX_RETRIES = 3

# Central Europe bounds for the map
CENTRAL_EUROPE_BOUNDS = {
    'north': 54.0,
    'south': 41.0, 
    'east': 30.0,
    'west': 8.0
}

# Map center (roughly Vienna area)
MAP_CENTER = [48.2082, 16.3738]


class GeoNamesCache:
    """Simple SQLite cache for GeoNames API responses."""
    
    def __init__(self, db_file: str = CACHE_DB_FILE):
        self.db_file = db_file
        self._init_db()
    
    def _init_db(self):
        """Initialize the cache database."""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS geonames_cache (
                geonames_id INTEGER PRIMARY KEY,
                name TEXT,
                latitude REAL,
                longitude REAL,
                country_code TEXT,
                cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
    
    def get(self, geonames_id: int) -> Optional[Dict]:
        """Get cached coordinates for a GeoNames ID."""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name, latitude, longitude, country_code FROM geonames_cache WHERE geonames_id = ?",
            (geonames_id,)
        )
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'name': row[0],
                'latitude': row[1],
                'longitude': row[2],
                'country_code': row[3]
            }
        return None
    
    def set(self, geonames_id: int, name: str, latitude: float, longitude: float, country_code: str):
        """Cache coordinates for a GeoNames ID."""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO geonames_cache 
            (geonames_id, name, latitude, longitude, country_code)
            VALUES (?, ?, ?, ?, ?)
        """, (geonames_id, name, latitude, longitude, country_code))
        conn.commit()
        conn.close()


def setup_geonames_username() -> str:
    """Get GeoNames username from environment variable."""
    username = os.environ.get('GEONAMES_USERNAME')
    if not username:
        print("❌ Error: GEONAMES_USERNAME environment variable not set")
        print("   Please follow these steps:")
        print("   1. Register at http://www.geonames.org/login (free)")
        print("   2. Confirm your email address")
        print("   3. Enable web services at http://www.geonames.org/manageaccount")
        print("   4. Set environment variable: set GEONAMES_USERNAME=your_username")
        print("\n   ⚠️  Important: You must enable 'free web services' in your account!")
        sys.exit(1)
    return username


def get_coordinates_from_geonames(geonames_id: int, cache: GeoNamesCache, username: str) -> Optional[Dict]:
    """Get coordinates for a GeoNames ID, with caching."""
    # Check cache first
    cached = cache.get(geonames_id)
    if cached:
        print(f"    📍 Using cached coordinates for GeoNames ID {geonames_id}: {cached['name']}")
        return cached
    
    print(f"    🌍 Fetching coordinates for GeoNames ID {geonames_id}...")
    
    # Make API request
    for attempt in range(MAX_RETRIES):
        try:
            url = f"{GEONAMES_API_BASE}/getJSON"
            params = {
                'geonameId': geonames_id,
                'username': username
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                # Check for API error messages
                if 'status' in data and 'message' in data['status']:
                    error_msg = data['status']['message']
                    print(f"    ❌ GeoNames API error for ID {geonames_id}: {error_msg}")
                    return None
                
                if 'lat' in data and 'lng' in data:
                    result = {
                        'name': data.get('name', f'ID_{geonames_id}'),
                        'latitude': float(data['lat']),
                        'longitude': float(data['lng']),
                        'country_code': data.get('countryCode', 'XX')
                    }
                    
                    # Cache the result
                    cache.set(geonames_id, result['name'], result['latitude'], 
                             result['longitude'], result['country_code'])
                    
                    print(f"    ✅ Found: {result['name']} ({result['latitude']}, {result['longitude']})")
                    return result
                else:
                    print(f"    ⚠️  Invalid response for GeoNames ID {geonames_id}: {data}")
            elif response.status_code == 401:
                print(f"    ❌ HTTP 401 Unauthorized for GeoNames ID {geonames_id}")
                print(f"    💡 This usually means:")
                print(f"       - Username not set correctly: '{username}'")
                print(f"       - Account not confirmed (check email)")
                print(f"       - Web services not enabled (go to http://www.geonames.org/manageaccount)")
                return None
            elif response.status_code == 403:
                print(f"    ❌ HTTP 403 Forbidden - Daily limit exceeded or web services not enabled")
                print(f"    💡 Enable web services at: http://www.geonames.org/manageaccount")
                return None
            else:
                print(f"    ⚠️  HTTP {response.status_code} for GeoNames ID {geonames_id}")
                if response.text:
                    print(f"    📝 Response: {response.text[:200]}")
            
            if attempt < MAX_RETRIES - 1:
                time.sleep(REQUEST_DELAY * (attempt + 1))
        
        except Exception as e:
            print(f"    ❌ Error fetching GeoNames ID {geonames_id} (attempt {attempt + 1}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(REQUEST_DELAY * (attempt + 1))
    
    print(f"    ❌ Failed to get coordinates for GeoNames ID {geonames_id}")
    return None


def parse_geonames_id(geonames_id_str: str) -> Optional[int]:
    """Parse GeoNames ID from string, handling various formats."""
    if not geonames_id_str or geonames_id_str in ['', 'None', 'null', 'NULL']:
        return None
    
    # Try to extract number from string
    import re
    match = re.search(r'\b(\d+)\b', str(geonames_id_str))
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def test_geonames_api(username: str) -> bool:
    """Test GeoNames API with a known location (Vienna)."""
    print("🧪 Testing GeoNames API connection...")
    try:
        url = f"{GEONAMES_API_BASE}/getJSON"
        params = {
            'geonameId': 2761369,  # Vienna, Austria
            'username': username
        }
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if 'lat' in data and 'lng' in data:
                print(f"✅ GeoNames API test successful: {data.get('name', 'Vienna')}")
                return True
            else:
                print(f"❌ API test failed - invalid response: {data}")
        elif response.status_code == 401:
            print(f"❌ API test failed - 401 Unauthorized")
            print(f"💡 Check: username='{username}', email confirmed, web services enabled")
        else:
            print(f"❌ API test failed - HTTP {response.status_code}: {response.text[:200]}")
        
        return False
        
    except Exception as e:
        print(f"❌ API test failed with exception: {e}")
        return False


def process_strike_locations(df: pd.DataFrame, cache: GeoNamesCache, username: str) -> List[Dict]:
    """Process strike data and get coordinates for all locations."""
    locations = []
    unique_geonames = df['location_geonames_id'].dropna().unique()
    
    print(f"📍 Processing {len(unique_geonames)} unique GeoNames IDs...")
    
    # Test API before processing if we have a username
    if username and not test_geonames_api(username):
        print("⚠️  GeoNames API test failed, but continuing with cache-only mode")
        username = None
    
    geonames_coords = {}
    for geonames_id_str in unique_geonames:
        geonames_id = parse_geonames_id(geonames_id_str)
        if geonames_id:
            coords = get_coordinates_from_geonames(geonames_id, cache, username)
            if coords:
                geonames_coords[geonames_id] = coords
            time.sleep(REQUEST_DELAY)  # Respect rate limits
    
    print(f"✅ Successfully geocoded {len(geonames_coords)} locations")
    
    # Process each strike
    for _, strike in df.iterrows():
        geonames_id = parse_geonames_id(strike.get('location_geonames_id', ''))
        if geonames_id and geonames_id in geonames_coords:
            coords = geonames_coords[geonames_id]
            
            # Check if coordinates are within Central Europe bounds
            lat, lng = coords['latitude'], coords['longitude']
            if (CENTRAL_EUROPE_BOUNDS['south'] <= lat <= CENTRAL_EUROPE_BOUNDS['north'] and
                CENTRAL_EUROPE_BOUNDS['west'] <= lng <= CENTRAL_EUROPE_BOUNDS['east']):
                
                locations.append({
                    'latitude': lat,
                    'longitude': lng,
                    'location_name': coords['name'],
                    'country_code': coords['country_code'],
                    'strike_data': strike.to_dict(),
                    'geonames_id': geonames_id
                })
    
    print(f"📍 {len(locations)} strikes mapped within Central Europe bounds")
    return locations


def create_popup_html(location: Dict) -> str:
    """Create HTML popup content for a strike location."""
    strike = location['strike_data']
    
    # Format date
    pub_date = strike.get('publication_date', 'Unknown')
    event_date = strike.get('event_date', 'Unknown')
    
    # Clean and format fields
    industry = strike.get('industry_txt', 'Unknown')
    participants = strike.get('participants_txt', 'Unknown')
    firm_name = strike.get('firm_name', 'Unknown')
    location_txt = strike.get('location_txt', location['location_name'])
    status = strike.get('strike_status', 'Unknown')
    description = strike.get('description_en', 'No description available')
    
    html = f"""
    <div style="width: 300px; font-family: Arial, sans-serif;">
        <h4 style="margin: 0 0 10px 0; color: #d73027;">
            📍 {location['location_name']} ({location['country_code']})
        </h4>
        
        <p style="margin: 5px 0;"><strong>📅 Publication:</strong> {pub_date}</p>
        <p style="margin: 5px 0;"><strong>⚡ Event Date:</strong> {event_date}</p>
        <p style="margin: 5px 0;"><strong>🏭 Industry:</strong> {industry}</p>
        <p style="margin: 5px 0;"><strong>👥 Participants:</strong> {participants}</p>
        <p style="margin: 5px 0;"><strong>🏢 Firm:</strong> {firm_name}</p>
        <p style="margin: 5px 0;"><strong>📍 Location:</strong> {location_txt}</p>
        <p style="margin: 5px 0;"><strong>📊 Status:</strong> {status}</p>
        
        <div style="margin-top: 10px; padding: 8px; background-color: #f5f5f5; border-left: 3px solid #d73027;">
            <strong>Description:</strong><br>
            <em>{description}</em>
        </div>
        
        <p style="margin: 10px 0 0 0; font-size: 10px; color: #666;">
            GeoNames ID: {location['geonames_id']}
        </p>
    </div>
    """
    return html


def create_strike_map(locations: List[Dict], output_file: str, title: str = "Historical Strikes in Central Europe"):
    """Create an interactive map with strike locations."""
    print(f"🗺️  Creating interactive map with {len(locations)} locations...")
    
    # Create base map
    m = folium.Map(
        location=MAP_CENTER,
        zoom_start=6,
        tiles='OpenStreetMap'
    )
    
    # Add title
    title_html = f'''
    <h3 align="center" style="font-size:20px; margin-top:0px;">
        <b>{title}</b>
    </h3>
    '''
    m.get_root().html.add_child(folium.Element(title_html))
    
    # Color scheme for different time periods or industries
    colors = ['red', 'blue', 'green', 'purple', 'orange', 'darkred', 'lightred', 
              'beige', 'darkblue', 'darkgreen', 'cadetblue', 'darkpurple', 'white', 
              'pink', 'lightblue', 'lightgreen', 'gray', 'black', 'lightgray']
    
    # Group strikes by location for clustering
    location_groups = {}
    for loc in locations:
        key = f"{loc['latitude']:.4f},{loc['longitude']:.4f}"
        if key not in location_groups:
            location_groups[key] = []
        location_groups[key].append(loc)
    
    # Add markers
    for location_key, loc_strikes in location_groups.items():
        if len(loc_strikes) == 1:
            # Single strike at this location
            location = loc_strikes[0]
            popup_html = create_popup_html(location)
            
            folium.Marker(
                location=[location['latitude'], location['longitude']],
                popup=folium.Popup(popup_html, max_width=350),
                tooltip=f"{location['location_name']} - {len(loc_strikes)} strike(s)",
                icon=folium.Icon(color='red', icon='info-sign')
            ).add_to(m)
        else:
            # Multiple strikes at this location - use marker cluster
            location = loc_strikes[0]  # Use first for coordinates
            
            # Create combined popup for multiple strikes
            combined_html = f"""
            <div style="width: 350px; font-family: Arial, sans-serif;">
                <h4 style="margin: 0 0 10px 0; color: #d73027;">
                    📍 {location['location_name']} ({location['country_code']})
                </h4>
                <p><strong>{len(loc_strikes)} strikes recorded at this location:</strong></p>
                <div style="max-height: 300px; overflow-y: auto;">
            """
            
            for i, strike_loc in enumerate(loc_strikes, 1):
                strike = strike_loc['strike_data']
                combined_html += f"""
                <div style="border-bottom: 1px solid #eee; padding: 5px 0;">
                    <strong>Strike #{i}</strong><br>
                    📅 {strike.get('publication_date', 'Unknown')}<br>
                    🏭 {strike.get('industry_txt', 'Unknown')}<br>
                    👥 {strike.get('participants_txt', 'Unknown')}<br>
                    <em>{strike.get('description_en', 'No description')}</em>
                </div>
                """
            
            combined_html += "</div></div>"
            
            folium.Marker(
                location=[location['latitude'], location['longitude']],
                popup=folium.Popup(combined_html, max_width=400),
                tooltip=f"{location['location_name']} - {len(loc_strikes)} strike(s)",
                icon=folium.Icon(color='darkred', icon='warning-sign')
            ).add_to(m)
    
    # Add legend
    legend_html = '''
    <div style="position: fixed; 
                bottom: 50px; left: 50px; width: 200px; height: 80px; 
                background-color: white; border:2px solid grey; z-index:9999; 
                font-size:14px; padding: 10px">
    <p><b>Strike Locations</b></p>
    <p><i class="fa fa-info-circle" style="color:red"></i> Single strike</p>
    <p><i class="fa fa-warning" style="color:darkred"></i> Multiple strikes</p>
    </div>
    '''
    m.get_root().html.add_child(folium.Element(legend_html))
    
    # Save map
    m.save(output_file)
    print(f"✅ Map saved to: {output_file}")


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Create an interactive map of historical strikes from CSV data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python strike_map_generator.py strikes.csv strikes_map.html
  python strike_map_generator.py strikes.csv map.html --title "Népszava Strikes 1903-1920"
  python strike_map_generator.py strikes.csv map.html --cache-only

Requirements:
  - GEONAMES_USERNAME environment variable must be set
  - Register free account at http://www.geonames.org/login
  - Input CSV must have 'location_geonames_id' column
        """
    )
    
    parser.add_argument('input_csv', 
                       help='CSV file from compile_strike_csv.py')
    parser.add_argument('output_html', 
                       help='Output HTML file for the interactive map')
    parser.add_argument('--title', 
                       default='Historical Strikes in Central Europe',
                       help='Title for the map (default: %(default)s)')
    parser.add_argument('--cache-only', 
                       action='store_true',
                       help='Only use cached coordinates, skip API calls')
    
    return parser.parse_args()


def main():
    # Parse arguments
    args = parse_arguments()
    
    # Setup GeoNames username
    if not args.cache_only:
        username = setup_geonames_username()
        print(f"🌍 Using GeoNames username: {username}")
    else:
        username = None
        print("📦 Cache-only mode: will only use previously cached coordinates")
    
    # Check input file
    if not os.path.exists(args.input_csv):
        print(f"❌ Input CSV file not found: {args.input_csv}")
        sys.exit(1)
    
    print("🚀 Starting Strike Map Generator...")
    print(f"📊 Input CSV: {args.input_csv}")
    print(f"🗺️  Output HTML: {args.output_html}")
    print(f"📍 Map title: {args.title}")
    
    # Load CSV data
    print(f"\n📈 Loading strike data...")
    try:
        df = pd.read_csv(args.input_csv)
        print(f"✅ Loaded {len(df)} strike records")
        
        if 'location_geonames_id' not in df.columns:
            print("❌ Error: 'location_geonames_id' column not found in CSV")
            print(f"   Available columns: {', '.join(df.columns)}")
            sys.exit(1)
        
        # Count records with GeoNames IDs
        valid_geonames = df[df['location_geonames_id'].notna() & 
                          (df['location_geonames_id'] != '') & 
                          (df['location_geonames_id'] != 'None')].shape[0]
        print(f"📍 {valid_geonames} records have GeoNames IDs")
        
    except Exception as e:
        print(f"❌ Error loading CSV file: {e}")
        sys.exit(1)
    
    # Initialize cache
    cache = GeoNamesCache()
    
    # Process locations and get coordinates
    try:
        effective_username = None if args.cache_only else username
        locations = process_strike_locations(df, cache, effective_username)
        
        if not locations:
            print("❌ No valid locations found for mapping!")
            print("   Check that your CSV has valid GeoNames IDs and they resolve to Central European locations")
            sys.exit(1)
        
        # Create map
        create_strike_map(locations, args.output_html, args.title)
        
        # Final summary
        print(f"\n{'='*80}")
        print(f"🎉 Map generation complete!")
        print(f"📊 Total strikes in CSV: {len(df)}")
        print(f"📍 Strikes mapped: {len(locations)}")
        print(f"🗺️  Map saved to: {args.output_html}")
        print(f"📦 Cache database: {CACHE_DB_FILE}")
        
        print(f"\n💡 To view the map:")
        print(f"   Open {args.output_html} in your web browser")
        
    except Exception as e:
        print(f"❌ Error generating map: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
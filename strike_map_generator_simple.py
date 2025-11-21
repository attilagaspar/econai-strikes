#!/usr/bin/env python3
"""
Simple Strike Map Generator (No API)

This script takes CSV data with latitude/longitude coordinates and creates an interactive
map of Central Europe showing historical strike locations.

Usage: python strike_map_generator_simple.py <input_csv> <output_html> [options]

CSV Requirements:
- Must have 'latitude' and 'longitude' columns with numeric coordinates
- Optional: 'location_name' or 'location_txt' for location names
"""

import pandas as pd
import folium
import os
import sys
import argparse
from typing import Dict, List
from pathlib import Path


# Central Europe bounds for the map
CENTRAL_EUROPE_BOUNDS = {
    'north': 54.0,
    'south': 41.0, 
    'east': 30.0,
    'west': 8.0
}

# Map center (roughly Vienna area)
MAP_CENTER = [48.2082, 16.3738]


def validate_coordinates(lat: float, lon: float) -> bool:
    """Check if coordinates are valid and within reasonable bounds."""
    if not (-90 <= lat <= 90):
        return False
    if not (-180 <= lon <= 180):
        return False
    return True


def is_in_central_europe(lat: float, lon: float) -> bool:
    """Check if coordinates are within Central Europe bounds."""
    return (CENTRAL_EUROPE_BOUNDS['south'] <= lat <= CENTRAL_EUROPE_BOUNDS['north'] and
            CENTRAL_EUROPE_BOUNDS['west'] <= lon <= CENTRAL_EUROPE_BOUNDS['east'])


def process_strike_locations(df: pd.DataFrame) -> List[Dict]:
    """Process strike data and extract valid coordinates."""
    locations = []
    
    # Check required columns
    if 'latitude' not in df.columns or 'longitude' not in df.columns:
        raise ValueError("CSV must contain 'latitude' and 'longitude' columns")
    
    print(f"📍 Processing {len(df)} strike records...")
    
    valid_coords = 0
    in_bounds = 0
    
    for idx, strike in df.iterrows():
        try:
            # Get coordinates - handle various data types
            lat_val = strike.get('latitude', None)
            lon_val = strike.get('longitude', None)
            
            # Skip if either coordinate is missing or NaN
            if pd.isna(lat_val) or pd.isna(lon_val):
                continue
                
            lat = float(lat_val)
            lon = float(lon_val)
            
            # Validate coordinates
            if not validate_coordinates(lat, lon):
                continue
            
            valid_coords += 1
            
            # Check if in Central Europe bounds
            if not is_in_central_europe(lat, lon):
                continue
            
            in_bounds += 1
            
            # Get location name (try multiple column names)
            location_name = None
            for col in ['location_name', 'location_txt', 'location']:
                if col in df.columns and col in strike and pd.notna(strike[col]) and str(strike[col]).strip() != '':
                    location_name = str(strike[col]).strip()
                    break
            
            if not location_name:
                location_name = f"Strike #{idx + 1}"
            
            # Convert strike to dict safely
            strike_dict = {}
            for col in df.columns:
                val = strike[col]
                if pd.isna(val):
                    strike_dict[col] = ''
                else:
                    strike_dict[col] = str(val) if not isinstance(val, (int, float)) else val
            
            locations.append({
                'latitude': lat,
                'longitude': lon,
                'location_name': location_name,
                'strike_data': strike_dict,
                'index': idx
            })
            
        except (ValueError, TypeError) as e:
            # Skip rows with invalid coordinates
            continue
    
    print(f"✅ {valid_coords} records with valid coordinates")
    print(f"📍 {in_bounds} strikes within Central Europe bounds")
    return locations


def create_popup_html(location: Dict) -> str:
    """Create HTML popup content for a strike location."""
    strike = location['strike_data']
    
    # Safely get values with defaults
    def safe_get(key, default='Unknown'):
        val = strike.get(key, default)
        if pd.isna(val) or val == '' or str(val).lower() in ['nan', 'none', 'null']:
            return default
        return str(val)
    
    # Format date
    pub_date = safe_get('publication_date')
    event_date = safe_get('event_date')
    
    # Clean and format fields
    industry = safe_get('industry_txt')
    participants = safe_get('participants_txt')
    firm_name = safe_get('firm_name')
    location_txt = safe_get('location_txt', location['location_name'])
    status = safe_get('strike_status')
    description = safe_get('description_en', safe_get('description', 'No description available'))
    
    # Get country if available
    country = safe_get('country', safe_get('country_code', ''))
    country_display = f" ({country})" if country and country != 'Unknown' else ""
    
    html = f"""
    <div style="width: 300px; font-family: Arial, sans-serif;">
        <h4 style="margin: 0 0 10px 0; color: #d73027;">
            📍 {location['location_name']}{country_display}
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
            Coordinates: {location['latitude']:.4f}, {location['longitude']:.4f}
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
    
    # Group strikes by location for clustering (same coordinates)
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
                tooltip=f"{location['location_name']} - 1 strike",
                icon=folium.Icon(color='red', icon='info-sign')
            ).add_to(m)
        else:
            # Multiple strikes at this location
            location = loc_strikes[0]  # Use first for coordinates
            
            # Create combined popup for multiple strikes
            combined_html = f"""
            <div style="width: 350px; font-family: Arial, sans-serif;">
                <h4 style="margin: 0 0 10px 0; color: #d73027;">
                    📍 {location['location_name']}
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
                    <em>{strike.get('description_en', strike.get('description', 'No description'))[:100]}...</em>
                </div>
                """
            
            combined_html += f"""
                </div>
                <p style="margin: 10px 0 0 0; font-size: 10px; color: #666;">
                    Coordinates: {location['latitude']:.4f}, {location['longitude']:.4f}
                </p>
            </div>
            """
            
            folium.Marker(
                location=[location['latitude'], location['longitude']],
                popup=folium.Popup(combined_html, max_width=400),
                tooltip=f"{location['location_name']} - {len(loc_strikes)} strikes",
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


def analyze_csv_coordinates(df: pd.DataFrame):
    """Analyze and report on coordinate data in the CSV."""
    print("\n📊 CSV Coordinate Analysis:")
    
    # Check for coordinate columns
    coord_cols = []
    for col in ['latitude', 'longitude', 'lat', 'lon', 'lng']:
        if col in df.columns:
            coord_cols.append(col)
    
    print(f"   Available coordinate columns: {coord_cols}")
    
    if 'latitude' in df.columns and 'longitude' in df.columns:
        # Count valid coordinates
        valid_lat = pd.to_numeric(df['latitude'], errors='coerce').notna()
        valid_lon = pd.to_numeric(df['longitude'], errors='coerce').notna()
        valid_both = valid_lat & valid_lon
        
        print(f"   Records with valid latitude: {valid_lat.sum()}")
        print(f"   Records with valid longitude: {valid_lon.sum()}")
        print(f"   Records with both coordinates: {valid_both.sum()}")
        
        if valid_both.sum() > 0:
            # Analyze coordinate ranges
            valid_df = df[valid_both].copy()
            valid_df['latitude'] = pd.to_numeric(valid_df['latitude'])
            valid_df['longitude'] = pd.to_numeric(valid_df['longitude'])
            
            print(f"   Latitude range: {valid_df['latitude'].min():.4f} to {valid_df['latitude'].max():.4f}")
            print(f"   Longitude range: {valid_df['longitude'].min():.4f} to {valid_df['longitude'].max():.4f}")
            
            # Check Central Europe bounds
            in_bounds = ((valid_df['latitude'] >= CENTRAL_EUROPE_BOUNDS['south']) &
                        (valid_df['latitude'] <= CENTRAL_EUROPE_BOUNDS['north']) &
                        (valid_df['longitude'] >= CENTRAL_EUROPE_BOUNDS['west']) &
                        (valid_df['longitude'] <= CENTRAL_EUROPE_BOUNDS['east']))
            
            print(f"   Records within Central Europe bounds: {in_bounds.sum()}")
    else:
        print("   ❌ Missing required 'latitude' and 'longitude' columns")


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Create an interactive map of strikes using latitude/longitude from CSV.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python strike_map_generator_simple.py strikes.csv strikes_map.html
  python strike_map_generator_simple.py strikes.csv map.html --title "Strike Locations"
  python strike_map_generator_simple.py strikes.csv map.html --analyze

Requirements:
  - CSV must contain 'latitude' and 'longitude' columns with numeric values
  - Optional: 'location_name', 'location_txt', or 'location' for location names
        """
    )
    
    parser.add_argument('input_csv', 
                       help='CSV file with latitude/longitude columns')
    parser.add_argument('output_html', 
                       help='Output HTML file for the interactive map')
    parser.add_argument('--title', 
                       default='Historical Strikes in Central Europe',
                       help='Title for the map (default: %(default)s)')
    parser.add_argument('--analyze', 
                       action='store_true',
                       help='Show detailed analysis of coordinate data')
    
    return parser.parse_args()


def main():
    # Parse arguments
    args = parse_arguments()
    
    # Check input file
    if not os.path.exists(args.input_csv):
        print(f"❌ Input CSV file not found: {args.input_csv}")
        sys.exit(1)
    
    print("🚀 Starting Simple Strike Map Generator...")
    print(f"📊 Input CSV: {args.input_csv}")
    print(f"🗺️  Output HTML: {args.output_html}")
    print(f"📍 Map title: {args.title}")
    
    # Load CSV data
    print(f"\n📈 Loading strike data...")
    try:
        df = pd.read_csv(args.input_csv)
        print(f"✅ Loaded {len(df)} strike records")
        
        # Show column information
        print(f"   Columns: {', '.join(df.columns)}")
        
        # Analyze coordinates if requested
        if args.analyze:
            analyze_csv_coordinates(df)
        
        # Check for required columns
        if 'latitude' not in df.columns or 'longitude' not in df.columns:
            print("❌ Error: 'latitude' and 'longitude' columns not found in CSV")
            print("   This version requires coordinates to be already present in the CSV")
            print("   Use the original strike_map_generator.py for GeoNames API lookups")
            sys.exit(1)
        
    except Exception as e:
        print(f"❌ Error loading CSV file: {e}")
        sys.exit(1)
    
    # Process locations
    try:
        locations = process_strike_locations(df)
        
        if not locations:
            print("❌ No valid locations found for mapping!")
            print("   Check that your CSV has valid latitude/longitude coordinates")
            print("   and that some are within Central European bounds")
            sys.exit(1)
        
        # Create map
        create_strike_map(locations, args.output_html, args.title)
        
        # Final summary
        print(f"\n{'='*80}")
        print(f"🎉 Map generation complete!")
        print(f"📊 Total strikes in CSV: {len(df)}")
        print(f"📍 Strikes mapped: {len(locations)}")
        print(f"🗺️  Map saved to: {args.output_html}")
        
        print(f"\n💡 To view the map:")
        print(f"   Open {args.output_html} in your web browser")
        
    except Exception as e:
        print(f"❌ Error generating map: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
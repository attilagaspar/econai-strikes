#!/usr/bin/env python3
"""
Location Geocoding Script

This script takes a CSV file with location columns and uses the GeoNames API to find
GeoNames IDs for unique location names. It handles data cleaning, API rate limiting,
and creates detailed mapping files.

Usage: python geocode_locations.py <input_csv> [options]

Required Environment Variable:
  GEONAMES_USERNAME - Your GeoNames username (register at geonames.org)

Output Files:
  location_official_to_geonameid.csv - Mappings for location_official values
  location_txt_to_geonameid.csv - Mappings for location_txt values
"""

import pandas as pd
import requests
import time
import os
import sys
import argparse
import re
import csv
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
import sqlite3


# Configuration
GEONAMES_API_BASE = "http://api.geonames.org"
REQUEST_DELAY = 1.0  # 1 second between requests
ERROR_RETRY_DELAY = 600  # 10 minutes on error
MAX_RETRIES = 3
CACHE_DB_FILE = "geocoding_cache.db"

# Central Europe countries to prioritize in search
CENTRAL_EUROPE_COUNTRIES = [
    'HU',  # Hungary
    'AT',  # Austria  
    'CZ',  # Czech Republic
    'SK',  # Slovakia
    'PL',  # Poland
    'RO',  # Romania
    'SI',  # Slovenia
    'HR',  # Croatia
    'DE',  # Germany
    'CH',  # Switzerland
]


class GeocodingCache:
    """SQLite cache for geocoding results."""
    
    def __init__(self, db_file: str = CACHE_DB_FILE):
        self.db_file = db_file
        self._init_db()
    
    def _init_db(self):
        """Initialize the cache database."""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS geocoding_cache (
                original_value TEXT,
                cleaned_value TEXT,
                geonames_id INTEGER,
                name TEXT,
                country_code TEXT,
                latitude REAL,
                longitude REAL,
                cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (cleaned_value)
            )
        """)
        conn.commit()
        conn.close()
    
    def get(self, cleaned_value: str) -> Optional[Dict]:
        """Get cached geocoding result."""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT geonames_id, name, country_code, latitude, longitude FROM geocoding_cache WHERE cleaned_value = ?",
            (cleaned_value,)
        )
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'geonames_id': row[0],
                'name': row[1],
                'country_code': row[2],
                'latitude': row[3],
                'longitude': row[4]
            }
        return None
    
    def set(self, original_value: str, cleaned_value: str, geonames_id: int, 
            name: str, country_code: str, latitude: float, longitude: float):
        """Cache geocoding result."""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO geocoding_cache 
            (original_value, cleaned_value, geonames_id, name, country_code, latitude, longitude)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (original_value, cleaned_value, geonames_id, name, country_code, latitude, longitude))
        conn.commit()
        conn.close()


def setup_geonames_username() -> str:
    """Get GeoNames username from environment variable."""
    #username = os.environ.get('GEONAMES_USERNAME')
    username = "attilagaspar"  # Hardcoded for testing purposes
    if not username:
        print("❌ Error: GEONAMES_USERNAME environment variable not set")
        print("   Please follow these steps:")
        print("   1. Register at http://www.geonames.org/login (free)")
        print("   2. Confirm your email address")
        print("   3. Enable web services at http://www.geonames.org/manageaccount")
        print("   4. Set environment variable: set GEONAMES_USERNAME=your_username")
        sys.exit(1)
    return username


def clean_location_name(location: str) -> str:
    """Clean location name by removing content in parentheses."""
    if not location or pd.isna(location):
        return ""
    
    # Remove content in parentheses
    cleaned = re.sub(r'\([^)]*\)', '', str(location)).strip()
    
    # Remove extra whitespace
    cleaned = ' '.join(cleaned.split())
    
    return cleaned


def split_location_name(location: str) -> List[str]:
    """Split location name on hyphens and return all parts."""
    if not location:
        return []
    
    # Split on various separators
    parts = re.split(r'[-–—/]', location)
    
    # Clean and filter parts
    cleaned_parts = []
    for part in parts:
        cleaned_part = part.strip()
        if cleaned_part and len(cleaned_part) > 1:  # Avoid single characters
            cleaned_parts.append(cleaned_part)
    
    return cleaned_parts


def geocode_with_geonames(location: str, username: str, cache: GeocodingCache) -> Optional[Dict]:
    """Geocode a location using GeoNames search API."""
    if not location:
        return None
    
    # Check cache first
    cached = cache.get(location)
    if cached:
        print(f"    💾 Cached: {location} -> {cached['name']} ({cached['geonames_id']})")
        return cached
    
    print(f"    🌍 Searching: {location}")
    
    # Try different search strategies
    search_params_list = [
        # 1. Exact search with Central Europe countries
        {
            'q': location,
            'maxRows': 10,
            'featureClass': 'P',  # Populated places
            'countryBias': ','.join(CENTRAL_EUROPE_COUNTRIES),
            'username': username,
            'type': 'json'
        },
        # 2. Broader search without country restriction
        {
            'q': location,
            'maxRows': 10,
            'featureClass': 'P',
            'username': username,
            'type': 'json'
        },
        # 3. Admin areas search
        {
            'q': location,
            'maxRows': 10,
            'featureClass': 'A',  # Admin areas
            'countryBias': ','.join(CENTRAL_EUROPE_COUNTRIES),
            'username': username,
            'type': 'json'
        }
    ]
    
    for attempt, search_params in enumerate(search_params_list):
        try:
            url = f"{GEONAMES_API_BASE}/searchJSON"
            response = requests.get(url, params=search_params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                
                # Check for API errors
                if 'status' in data:
                    error_msg = data['status'].get('message', 'Unknown error')
                    if 'daily limit' in error_msg.lower():
                        print(f"    ⏰ Daily limit reached, waiting {ERROR_RETRY_DELAY//60} minutes...")
                        time.sleep(ERROR_RETRY_DELAY)
                        continue
                    else:
                        print(f"    ❌ API error: {error_msg}")
                        return None
                
                # Process results
                geonames = data.get('geonames', [])
                if geonames:
                    # Prefer results from Central Europe
                    best_result = None
                    for result in geonames:
                        country_code = result.get('countryCode', '')
                        if country_code in CENTRAL_EUROPE_COUNTRIES:
                            best_result = result
                            break
                    
                    # If no Central Europe result, take the first one
                    if not best_result:
                        best_result = geonames[0]
                    
                    # Extract data
                    geonames_id = int(best_result['geonameId'])
                    name = best_result.get('name', location)
                    country_code = best_result.get('countryCode', 'XX')
                    latitude = float(best_result['lat'])
                    longitude = float(best_result['lng'])
                    
                    # Cache the result
                    result_dict = {
                        'geonames_id': geonames_id,
                        'name': name,
                        'country_code': country_code,
                        'latitude': latitude,
                        'longitude': longitude
                    }
                    
                    cache.set(location, location, geonames_id, name, country_code, latitude, longitude)
                    
                    print(f"    ✅ Found: {name} ({country_code}) -> ID: {geonames_id}")
                    return result_dict
            
            elif response.status_code == 401:
                print(f"    ❌ HTTP 401 - Check your GeoNames username and account setup")
                return None
            elif response.status_code == 403:
                print(f"    ❌ HTTP 403 - Daily limit or web services not enabled")
                return None
            else:
                print(f"    ⚠️  HTTP {response.status_code}: {response.text[:100]}")
        
        except Exception as e:
            print(f"    ❌ Request error (attempt {attempt + 1}): {e}")
        
        # Wait between attempts
        time.sleep(REQUEST_DELAY)
    
    print(f"    ❌ No results found for: {location}")
    return None


def process_locations(locations: List[str], username: str, cache: GeocodingCache, 
                     progress_prefix: str = "") -> List[Dict]:
    """Process a list of unique locations and geocode them."""
    results = []
    total = len(locations)
    
    for i, original_location in enumerate(locations):
        print(f"\n{progress_prefix}[{i+1}/{total}] Processing: {original_location}")
        
        # Clean the location
        cleaned_location = clean_location_name(original_location)
        
        if not cleaned_location:
            results.append({
                'original_value': original_location,
                'cleaned_value': '',
                'geonames_id': '',
                'resolved_name': '',
                'country_code': '',
                'latitude': '',
                'longitude': '',
                'search_strategy': 'skipped_empty'
            })
            continue
        
        # Try to geocode the cleaned location
        geocode_result = None
        search_strategy = 'direct'
        
        # First attempt: direct search
        geocode_result = geocode_with_geonames(cleaned_location, username, cache)
        
        # If no result and location contains separators, try splitting
        if not geocode_result and any(sep in cleaned_location for sep in ['-', '–', '—', '/']):
            print(f"    🔄 Trying split strategy for: {cleaned_location}")
            parts = split_location_name(cleaned_location)
            search_strategy = 'split'
            
            for part in parts:
                print(f"      🧩 Trying part: {part}")
                part_result = geocode_with_geonames(part, username, cache)
                if part_result:
                    geocode_result = part_result
                    search_strategy = f'split_part_{part}'
                    break
                time.sleep(REQUEST_DELAY)
        
        # Record result
        if geocode_result:
            results.append({
                'original_value': original_location,
                'cleaned_value': cleaned_location,
                'geonames_id': geocode_result['geonames_id'],
                'resolved_name': geocode_result['name'],
                'country_code': geocode_result['country_code'],
                'latitude': geocode_result['latitude'],
                'longitude': geocode_result['longitude'],
                'search_strategy': search_strategy
            })
        else:
            results.append({
                'original_value': original_location,
                'cleaned_value': cleaned_location,
                'geonames_id': '',
                'resolved_name': '',
                'country_code': '',
                'latitude': '',
                'longitude': '',
                'search_strategy': 'not_found'
            })
        
        # Wait between requests
        time.sleep(REQUEST_DELAY)
    
    return results


def save_geocoding_results(results: List[Dict], output_file: str):
    """Save geocoding results to CSV file."""
    if not results:
        print(f"⚠️  No results to save to {output_file}")
        return
    
    print(f"💾 Saving {len(results)} results to: {output_file}")
    
    columns = [
        'original_value',
        'cleaned_value', 
        'geonames_id',
        'resolved_name',
        'country_code',
        'latitude',
        'longitude',
        'search_strategy'
    ]
    
    try:
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=columns)
            writer.writeheader()
            writer.writerows(results)
        
        # Print summary
        found_count = sum(1 for r in results if r['geonames_id'])
        print(f"    ✅ Successfully geocoded: {found_count}/{len(results)} locations")
        
    except Exception as e:
        print(f"❌ Error saving results: {e}")


def analyze_csv_locations(df: pd.DataFrame, column: str) -> List[str]:
    """Extract unique location values from a CSV column."""
    if column not in df.columns:
        print(f"⚠️  Column '{column}' not found in CSV")
        return []
    
    # Get unique non-empty values
    unique_values = df[column].dropna().astype(str)
    unique_values = unique_values[unique_values != ''].unique()
    
    print(f"📍 Found {len(unique_values)} unique values in '{column}' column")
    return sorted(unique_values.tolist())


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Geocode location names using GeoNames API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python geocode_locations.py strikes.csv
  python geocode_locations.py strikes.csv --columns location_txt
  python geocode_locations.py strikes.csv --test-api

Requirements:
  - GEONAMES_USERNAME environment variable must be set
  - Input CSV should have 'location_official' and/or 'location_txt' columns
        """
    )
    
    parser.add_argument('input_csv', 
                       help='Input CSV file with location columns')
    parser.add_argument('--columns', 
                       nargs='+',
                       default=['location_official', 'location_txt'],
                       help='Location columns to process (default: location_official location_txt)')
    parser.add_argument('--test-api', 
                       action='store_true',
                       help='Test API connection with a known location')
    
    return parser.parse_args()


def test_geonames_api(username: str) -> bool:
    """Test GeoNames API with Vienna."""
    print("🧪 Testing GeoNames API connection...")
    try:
        url = f"{GEONAMES_API_BASE}/searchJSON"
        params = {
            'q': 'Vienna',
            'maxRows': 1,
            'username': username,
            'type': 'json'
        }
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if 'geonames' in data and data['geonames']:
                print(f"✅ API test successful: {data['geonames'][0]['name']}")
                return True
            else:
                print(f"❌ API test failed - no results: {data}")
        else:
            print(f"❌ API test failed - HTTP {response.status_code}")
        
        return False
        
    except Exception as e:
        print(f"❌ API test failed: {e}")
        return False


def main():
    # Parse arguments
    args = parse_arguments()
    
    # Setup GeoNames username
    username = setup_geonames_username()
    print(f"🌍 Using GeoNames username: {username}")
    
    # Test API if requested
    if args.test_api:
        success = test_geonames_api(username)
        sys.exit(0 if success else 1)
    
    # Check input file
    if not os.path.exists(args.input_csv):
        print(f"❌ Input CSV file not found: {args.input_csv}")
        sys.exit(1)
    
    print("🚀 Starting Location Geocoding...")
    print(f"📊 Input CSV: {args.input_csv}")
    print(f"📍 Processing columns: {', '.join(args.columns)}")
    
    # Load CSV
    try:
        df = pd.read_csv(args.input_csv)
        print(f"✅ Loaded {len(df)} records from CSV")
        
    except Exception as e:
        print(f"❌ Error loading CSV: {e}")
        sys.exit(1)
    
    # Initialize cache
    cache = GeocodingCache()
    
    # Process each column
    for column in args.columns:
        print(f"\n{'='*80}")
        print(f"🔍 Processing column: {column}")
        
        # Get unique locations
        unique_locations = analyze_csv_locations(df, column)
        
        if not unique_locations:
            print(f"⚠️  No locations to process in column '{column}'")
            continue
        
        # Process locations
        results = process_locations(
            unique_locations, 
            username, 
            cache, 
            progress_prefix=f"{column}: "
        )
        
        # Save results
        output_file = f"{column}_to_geonameid.csv"
        save_geocoding_results(results, output_file)
    
    # Final summary
    print(f"\n{'='*80}")
    print(f"🎉 Geocoding complete!")
    print(f"💾 Cache database: {CACHE_DB_FILE}")
    print(f"📊 Processed columns: {', '.join(args.columns)}")


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
Compile Strike CSV

This script compiles strike data from individual JSON files (output of strike_llm_cleaner.py)
into a single CSV file for analysis.

Usage: python compile_strike_csv.py <input_folder> <output_csv_file>
"""

import json
import os
import sys
import csv
from pathlib import Path
from typing import List, Dict, Any
import unicodedata


def natural_sort_key(text: str) -> List:
    """Generate a natural sorting key that handles numbers correctly."""
    import re
    
    def convert(text_part):
        return int(text_part) if text_part.isdigit() else text_part.lower()
    
    return [convert(c) for c in re.split('([0-9]+)', text)]


def find_json_files(input_folder: str) -> List[str]:
    """Find all JSON files in the input folder and return them in sorted order."""
    json_files = []
    
    print(f"🔍 Scanning directory: {input_folder}")
    
    for root, dirs, files in os.walk(input_folder):
        for file in files:
            if file.lower().endswith('.json'):
                json_files.append(os.path.join(root, file))
    
    # Sort files using natural sorting
    json_files.sort(key=lambda x: natural_sort_key(x))
    
    print(f"✓ Found {len(json_files)} JSON files")
    return json_files


def extract_strikes_from_json(json_path: str) -> List[Dict[str, Any]]:
    """Extract strike data and metadata from a single JSON file."""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Get publication date and source info
        publication_date = data.get("publication_date", "")
        source_file = data.get("source_file", os.path.basename(json_path))
        newspaper_header = data.get("newspaper_header", "")
        
        # Get strikes array
        strikes = data.get("strikes", [])
        
        # Add metadata to each strike
        enriched_strikes = []
        for strike in strikes:
            if isinstance(strike, dict):
                # Create a new strike dict with added metadata
                enriched_strike = {
                    "publication_date": publication_date,
                    "source_file": source_file,
                    "newspaper_header": newspaper_header,
                    **strike  # Add all original strike fields
                }
                enriched_strikes.append(enriched_strike)
        
        return enriched_strikes
    
    except Exception as e:
        print(f"    ⚠️  Error reading {json_path}: {e}")
        return []


def get_all_csv_columns(all_strikes: List[Dict[str, Any]]) -> List[str]:
    """Get all unique columns from all strikes to ensure consistent CSV headers."""
    all_columns = set()
    
    for strike in all_strikes:
        all_columns.update(strike.keys())
    
    # Define preferred column order
    preferred_order = [
        "publication_date",
        "source_file", 
        "newspaper_header",
        "event_date",
        "industry_txt",
        "industry_SIC",
        "participants_txt", 
        "participants_ISCO",
        "firm_name",
        "location_txt",
        "location_official",
        "location_geonames_id",
        "strike_status",
        "description_en"
    ]
    
    # Start with preferred columns that exist
    ordered_columns = [col for col in preferred_order if col in all_columns]
    
    # Add any remaining columns
    remaining_columns = sorted(all_columns - set(ordered_columns))
    ordered_columns.extend(remaining_columns)
    
    return ordered_columns


def write_strikes_to_csv(all_strikes: List[Dict[str, Any]], output_path: str):
    """Write all strikes to a CSV file."""
    if not all_strikes:
        print("⚠️  No strikes found to write to CSV")
        return
    
    # Get all columns
    columns = get_all_csv_columns(all_strikes)
    
    print(f"📊 Writing {len(all_strikes)} strikes to CSV with {len(columns)} columns")
    print(f"📝 Columns: {', '.join(columns[:5])}{'...' if len(columns) > 5 else ''}")
    
    try:
        with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=columns, extrasaction='ignore')
            
            # Write header
            writer.writeheader()
            
            # Write data
            for strike in all_strikes:
                # Ensure all fields are strings to avoid CSV writing issues
                cleaned_strike = {}
                for column in columns:
                    value = strike.get(column, "")
                    # Convert to string and handle None values
                    if value is None:
                        cleaned_strike[column] = ""
                    else:
                        cleaned_strike[column] = str(value)
                
                writer.writerow(cleaned_strike)
    
    except Exception as e:
        print(f"❌ Error writing CSV file: {e}")
        raise


def main():
    if len(sys.argv) != 3:
        print("Usage: python compile_strike_csv.py <input_folder> <output_csv_file>")
        print("\nThis script compiles strike data from JSON files (output of strike_llm_cleaner.py)")
        print("into a single CSV file for analysis.")
        print("\nFeatures:")
        print("- Processes all JSON files in the input folder")
        print("- Adds publication_date as a column for each strike record")
        print("- Includes source file information for traceability")
        print("- Handles missing fields gracefully")
        print("- Orders columns logically for analysis")
        sys.exit(1)
    
    input_folder = sys.argv[1]
    output_csv_file = sys.argv[2]
    
    # Validate input
    if not os.path.exists(input_folder):
        print(f"❌ Input folder not found: {input_folder}")
        sys.exit(1)
    
    # Create output directory if needed
    output_dir = os.path.dirname(output_csv_file)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    
    print("🚀 Starting Strike CSV Compilation...")
    print(f"📁 Input folder: {input_folder}")
    print(f"📄 Output CSV file: {output_csv_file}")
    
    # Find all JSON files
    json_files = find_json_files(input_folder)
    
    if not json_files:
        print("❌ No JSON files found in input folder!")
        sys.exit(1)
    
    # Process all files and collect strikes
    all_strikes = []
    processed_files = 0
    total_strikes_per_file = []
    
    print(f"\n📋 Processing {len(json_files)} JSON files...")
    
    for i, json_path in enumerate(json_files):
        filename = os.path.basename(json_path)
        print(f"[{i+1}/{len(json_files)}] Processing: {filename}")
        
        strikes = extract_strikes_from_json(json_path)
        if strikes:
            all_strikes.extend(strikes)
            total_strikes_per_file.append((filename, len(strikes)))
            print(f"    ✅ Added {len(strikes)} strike(s)")
        else:
            print(f"    ⚠️  No strikes found")
        
        processed_files += 1
    
    # Write to CSV
    print(f"\n📝 Compiling CSV...")
    write_strikes_to_csv(all_strikes, output_csv_file)
    
    # Final summary
    print(f"\n{'='*80}")
    print(f"🎉 CSV compilation complete!")
    print(f"📁 Processed files: {processed_files}")
    print(f"📊 Total strikes compiled: {len(all_strikes)}")
    print(f"📄 Output file: {output_csv_file}")
    
    if total_strikes_per_file:
        print(f"\n📈 Top files by strike count:")
        # Sort by strike count and show top 5
        top_files = sorted(total_strikes_per_file, key=lambda x: x[1], reverse=True)[:5]
        for filename, count in top_files:
            print(f"    {count:3d} strikes: {filename}")
    
    if len(all_strikes) == 0:
        print("⚠️  No strikes were found in any JSON files.")
        print("   Make sure the input folder contains processed files from strike_llm_cleaner.py")


if __name__ == "__main__":
    main()
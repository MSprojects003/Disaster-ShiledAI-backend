# download_worldbank_data.py
"""
Script to download World Bank IDA Resource Allocation Index data
and integrate it into the resource CSV file.
Run: python download_worldbank_data.py
"""

import pandas as pd
import requests
import os
import json
from datetime import datetime

def download_worldbank_data():
    """
    Download IDA Resource Allocation Index for Sri Lanka from World Bank API.
    The API returns data in JSON format.
    """
    print("📊 Downloading World Bank data for Sri Lanka...")
    
    # World Bank API URL for IDA Resource Allocation Index (IQ.CPA.IRAI.XQ)
    # For Sri Lanka (country code: LK)
    url = "http://api.worldbank.org/v2/country/LK/indicator/IQ.CPA.IRAI.XQ?format=json"
    
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        # The API returns a list: [metadata, data]
        data = response.json()
        
        if len(data) < 2 or not data[1]:
            print("❌ No data received from World Bank API")
            return None
        
        # Extract the data
        records = []
        for item in data[1]:
            if item.get('value') is not None:
                records.append({
                    'year': int(item['date']),
                    'irai_score': float(item['value']),
                    'country': item['country']['value'],
                    'country_code': item['country']['id']
                })
        
        # Sort by year
        records.sort(key=lambda x: x['year'])
        
        # Create DataFrame
        df = pd.DataFrame(records)
        
        print(f"✅ Downloaded {len(df)} records for Sri Lanka")
        print(f"   Years: {df['year'].min()} to {df['year'].max()}")
        print(f"   Latest Score ({df['year'].max()}): {df[df['year'] == df['year'].max()]['irai_score'].values[0]}")
        
        return df
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Network error: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"❌ Error parsing JSON: {e}")
        return None
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return None

def save_to_csv(df, output_path='data/resources/worldbank_data.csv'):
    """
    Save the downloaded data to a CSV file.
    """
    if df is None or df.empty:
        print("❌ No data to save")
        return False
    
    try:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Save to CSV
        df.to_csv(output_path, index=False)
        print(f"✅ Data saved to {output_path}")
        return True
    except Exception as e:
        print(f"❌ Error saving CSV: {e}")
        return False

def add_to_resource_csv(worldbank_df, resource_csv_path='data/resources/resource_inventory.csv'):
    """
    Add World Bank data as new resources to the existing resource CSV.
    """
    if worldbank_df is None or worldbank_df.empty:
        print("❌ No World Bank data to add")
        return False
    
    try:
        # Check if resource CSV exists
        if not os.path.exists(resource_csv_path):
            print(f"⚠️ Resource CSV not found at {resource_csv_path}")
            print("   Creating new file with World Bank data only...")
            
            # Create new resource CSV with World Bank data
            new_resources = []
            
            # Add each year as a separate resource record
            for _, row in worldbank_df.iterrows():
                new_resources.append({
                    'resource_type': f'irai_score_{row["year"]}',
                    'total': row['irai_score'],
                    'available': row['irai_score'],
                    'deployed': 0,
                    'unit': 'index',
                    'description': f'IDA Resource Allocation Index (1-6) - {row["year"]}',
                    'district': 'National'
                })
            
            # Add the latest year as a separate resource
            latest = worldbank_df.iloc[-1]
            new_resources.append({
                'resource_type': 'irai_score_latest',
                'total': latest['irai_score'],
                'available': latest['irai_score'],
                'deployed': 0,
                'unit': 'index',
                'description': f'IDA Resource Allocation Index Latest ({latest["year"]})',
                'district': 'National'
            })
            
            # Save to CSV
            df = pd.DataFrame(new_resources)
            df.to_csv(resource_csv_path, index=False)
            print(f"✅ Created new resource CSV with {len(new_resources)} World Bank records")
            return True
        
        # If resource CSV exists, append World Bank data
        print(f"📂 Reading existing resource CSV: {resource_csv_path}")
        existing_df = pd.read_csv(resource_csv_path)
        
        # Create new records from World Bank data
        new_records = []
        for _, row in worldbank_df.iterrows():
            # Check if this year already exists
            existing = existing_df[existing_df['resource_type'] == f'irai_score_{row["year"]}']
            if existing.empty:
                new_records.append({
                    'resource_type': f'irai_score_{row["year"]}',
                    'total': row['irai_score'],
                    'available': row['irai_score'],
                    'deployed': 0,
                    'unit': 'index',
                    'description': f'IDA Resource Allocation Index - {row["year"]}',
                    'district': 'National'
                })
        
        # Add latest year if not already present
        latest = worldbank_df.iloc[-1]
        existing_latest = existing_df[existing_df['resource_type'] == 'irai_score_latest']
        if existing_latest.empty:
            new_records.append({
                'resource_type': 'irai_score_latest',
                'total': latest['irai_score'],
                'available': latest['irai_score'],
                'deployed': 0,
                'unit': 'index',
                'description': f'IDA Resource Allocation Index Latest ({latest["year"]})',
                'district': 'National'
            })
        
        if new_records:
            # Append to existing DataFrame
            new_df = pd.DataFrame(new_records)
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
            combined_df.to_csv(resource_csv_path, index=False)
            print(f"✅ Added {len(new_records)} new records to resource CSV")
        else:
            print("ℹ️ No new records to add (all already exist)")
        
        return True
        
    except Exception as e:
        print(f"❌ Error updating resource CSV: {e}")
        return False

def main():
    """Main function to download and integrate World Bank data."""
    print("="*60)
    print("🌐 World Bank Data Integration Script")
    print("="*60)
    
    # Step 1: Download data
    df = download_worldbank_data()
    
    if df is None:
        print("❌ Script failed - no data downloaded")
        return
    
    # Step 2: Save raw data
    save_to_csv(df)
    
    # Step 3: Add to resource CSV
    add_to_resource_csv(df)
    
    print("\n📊 Summary of World Bank Data:")
    print(f"   Records: {len(df)}")
    print(f"   Years: {df['year'].min()} to {df['year'].max()}")
    print(f"   Latest Score ({df['year'].max()}): {df[df['year'] == df['year'].max()]['irai_score'].values[0]}")
    print(f"   Highest Score: {df['irai_score'].max()} ({df[df['irai_score'] == df['irai_score'].max()]['year'].values[0]})")
    print(f"   Lowest Score: {df['irai_score'].min()} ({df[df['irai_score'] == df['irai_score'].min()]['year'].values[0]})")
    print("\n✅ Script completed successfully!")

if __name__ == "__main__":
    main()
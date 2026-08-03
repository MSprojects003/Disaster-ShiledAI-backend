import pandas as pd
import numpy as np
import os
import requests
from datetime import datetime, timedelta
import time
import json
from dotenv import load_dotenv

load_dotenv()

class DataMerger:
    """
    Merge river data with weather data
    """
    
    def __init__(self):
        self.river_data_path = "data/river_gauges/processed/river_data_extracted.csv"
        self.output_dir = "data/processed/"
        os.makedirs(self.output_dir, exist_ok=True)
        
        self.weather_api_key = os.getenv('OPENWEATHER_API_KEY', '')
        self.weather_base_url = "http://api.openweathermap.org/data/2.5/weather"
        
        # Sri Lanka district coordinates
        self.district_coords = {
            'Colombo': {'lat': 6.9271, 'lon': 79.8612},
            'Gampaha': {'lat': 7.0889, 'lon': 79.9967},
            'Kalutara': {'lat': 6.5833, 'lon': 79.9667},
            'Galle': {'lat': 6.0535, 'lon': 80.2210},
            'Matara': {'lat': 5.9484, 'lon': 80.5410},
            'Hambantota': {'lat': 6.1241, 'lon': 81.1185},
            'Kandy': {'lat': 7.2906, 'lon': 80.6337},
            'Matale': {'lat': 7.4667, 'lon': 80.6167},
            'Nuwara Eliya': {'lat': 6.9667, 'lon': 80.7667},
            'Kurunegala': {'lat': 7.4833, 'lon': 80.3667},
            'Puttalam': {'lat': 8.0333, 'lon': 79.8333},
            'Anuradhapura': {'lat': 8.3114, 'lon': 80.4037},
            'Polonnaruwa': {'lat': 7.9333, 'lon': 81.0000},
            'Badulla': {'lat': 6.9833, 'lon': 81.0500},
            'Monaragala': {'lat': 6.8667, 'lon': 81.3500},
            'Ratnapura': {'lat': 6.6833, 'lon': 80.4000},
            'Kegalle': {'lat': 7.2500, 'lon': 80.3500}
        }
    
    def load_river_data(self):
        """Load extracted river data"""
        if os.path.exists(self.river_data_path):
            df = pd.read_csv(self.river_data_path)
            print(f"✅ Loaded {len(df)} river records")
            print(f"📊 Columns: {df.columns.tolist()}")

            # Warn early if there are any duplicate column names in the
            # source file itself (this alone can break .str / arithmetic
            # ops later since df[col] returns a DataFrame, not a Series)
            dupes = df.columns[df.columns.duplicated()].tolist()
            if dupes:
                print(f"⚠️ Duplicate columns found in source CSV: {dupes}")

            return df
        else:
            print(f"❌ River data not found at {self.river_data_path}")
            return None
    
    def get_weather_historical(self, district, date):
        """
        Get historical weather data for a specific date
        """
        month = date.month if isinstance(date, datetime) else 6
        
        # Seasonal patterns for Sri Lanka
        if month in [5, 6, 7, 8]:  # Southwest Monsoon
            rain_base = np.random.gamma(shape=3, scale=15)
            temp_base = 28
        elif month in [10, 11, 12]:  # Northeast Monsoon
            rain_base = np.random.gamma(shape=2.5, scale=12)
            temp_base = 27
        else:
            rain_base = np.random.gamma(shape=1.5, scale=8)
            temp_base = 29
        
        # District-specific adjustments
        district_factors = {
            'Colombo': 1.2, 'Gampaha': 1.1, 'Kalutara': 1.3,
            'Galle': 1.4, 'Matara': 1.3, 'Hambantota': 0.8,
            'Kandy': 1.1, 'Matale': 1.0, 'Nuwara Eliya': 1.5,
            'Ratnapura': 1.4, 'Kegalle': 1.1
        }
        
        factor = district_factors.get(district, 1.0)
        rainfall = rain_base * factor
        
        return {
            'rainfall_mm': np.clip(rainfall, 0, 200),
            'temperature_c': temp_base + np.random.normal(0, 2),
            'humidity_percent': np.clip(60 + 0.2 * rainfall + np.random.normal(0, 5), 30, 95),
            'wind_speed_kmh': np.random.exponential(15),
            'pressure_hpa': 1010 + np.random.normal(0, 5)
        }
    
    def get_current_weather(self, district):
        """Get current weather from OpenWeatherMap API"""
        if not self.weather_api_key or self.weather_api_key == 'your_free_api_key_here':
            return self.get_weather_historical(district, datetime.now())
        
        coords = self.district_coords.get(district)
        if not coords:
            return self.get_weather_historical(district, datetime.now())
        
        try:
            url = f"{self.weather_base_url}?lat={coords['lat']}&lon={coords['lon']}&appid={self.weather_api_key}&units=metric"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return {
                    'rainfall_mm': data.get('rain', {}).get('1h', 0),
                    'temperature_c': data['main']['temp'],
                    'humidity_percent': data['main']['humidity'],
                    'wind_speed_kmh': data['wind']['speed'] * 3.6,
                    'pressure_hpa': data['main']['pressure']
                }
            else:
                return self.get_weather_historical(district, datetime.now())
        except:
            return self.get_weather_historical(district, datetime.now())
    
    def clean_numeric_column(self, series):
        """
        Clean a column and convert to numeric
        """
        # Guard: if a duplicate-named column slipped through, df[col]
        # returns a DataFrame instead of a Series, and .str would blow up
        # with a cryptic AttributeError. Fail loudly and clearly instead.
        if isinstance(series, pd.DataFrame):
            raise ValueError(
                f"Expected a single column (Series) but got a DataFrame "
                f"with {series.shape[1]} columns named the same thing: "
                f"{series.columns.tolist()}. This usually means the same "
                f"column name exists in both the river data and the "
                f"weather data before merging — rename one before concat."
            )

        # Convert to string
        series_str = series.astype(str)
        
        # Remove commas and other non-numeric characters
        series_clean = series_str.str.replace(',', '', regex=False)
        series_clean = series_clean.str.replace(r'[^\d.]', '', regex=True)
        
        # Remove multiple dots
        series_clean = series_clean.str.replace(r'(\d+\.\d+)\.\d+', r'\1', regex=True)
        
        # Convert to numeric, invalid becomes NaN
        return pd.to_numeric(series_clean, errors='coerce')
    
    def merge_data(self):
        """Merge river data with weather data"""
        print("🔄 Merging river data with weather data...")
        
        river_df = self.load_river_data()
        if river_df is None:
            return None
        
        # Create a copy
        merged_df = river_df.copy()
        
        # Add weather data for each row
        weather_list = []
        
        for idx, row in merged_df.iterrows():
            # Get district from station column
            district = row.get('station', 'Colombo')
            if pd.isna(district) or district == 'Unknown':
                district = 'Colombo'
            
            # Get weather
            weather = self.get_current_weather(district)
            weather_list.append(weather)
            
            # Progress
            if (idx + 1) % 100 == 0:
                print(f"📊 Processed {idx + 1}/{len(merged_df)} records")
            
            # Rate limit
            time.sleep(0.1)
        
        # Add weather columns
        weather_df = pd.DataFrame(weather_list)

        # IMPORTANT: river_df already has its own 'rainfall_mm' column
        # (observed station rainfall). weather_df also produces a
        # 'rainfall_mm' key. Concatenating them side-by-side would create
        # two columns with the identical name 'rainfall_mm', which makes
        # merged_df['rainfall_mm'] return a DataFrame instead of a Series
        # further down — that's what caused:
        #   AttributeError: 'DataFrame' object has no attribute 'str'
        # Renaming here keeps both signals but avoids the collision.
        weather_df = weather_df.rename(columns={'rainfall_mm': 'weather_rainfall_mm'})

        merged_df = pd.concat([merged_df.reset_index(drop=True), weather_df.reset_index(drop=True)], axis=1)

        # Extra safety net: if any column name still ended up duplicated
        # for any other reason, fail here with a clear message rather
        # than deep inside clean_numeric_column.
        dupes = merged_df.columns[merged_df.columns.duplicated()].tolist()
        if dupes:
            raise ValueError(f"Duplicate columns after merge: {dupes}")

        # Clean numeric columns using the helper method
        numeric_cols = ['water_level_m', 'rainfall_mm', 'weather_rainfall_mm',
                       'temperature_c', 'humidity_percent', 'wind_speed_kmh',
                       'pressure_hpa']
        
        for col in numeric_cols:
            if col in merged_df.columns:
                merged_df[col] = self.clean_numeric_column(merged_df[col])
        
        # Fill NaN values
        merged_df['water_level_m'] = merged_df['water_level_m'].fillna(0)
        merged_df['rainfall_mm'] = merged_df['rainfall_mm'].fillna(0)
        if 'weather_rainfall_mm' in merged_df.columns:
            merged_df['weather_rainfall_mm'] = merged_df['weather_rainfall_mm'].fillna(0)
        merged_df['humidity_percent'] = merged_df['humidity_percent'].fillna(50)
        
        # Calculate risk score
        # Get max values for normalization
        max_water = merged_df['water_level_m'].max()
        if max_water == 0 or pd.isna(max_water):
            max_water = 10
        
        max_rain = 200
        
        # Uses the observed station rainfall ('rainfall_mm') for risk,
        # not the simulated/API weather rainfall.
        merged_df['risk_score'] = (
            (merged_df['water_level_m'] / max_water * 0.4) +
            (merged_df['rainfall_mm'] / max_rain * 0.3) +
            (merged_df['humidity_percent'] / 100 * 0.3)
        ) * 100
        
        merged_df['risk_score'] = merged_df['risk_score'].clip(0, 100)
        
        # Determine risk level
        def get_risk_level(score):
            if score >= 75:
                return 'Critical'
            elif score >= 60:
                return 'High'
            elif score >= 40:
                return 'Medium'
            else:
                return 'Low'
        
        merged_df['risk_level'] = merged_df['risk_score'].apply(get_risk_level)
        
        # Save merged data
        output_path = os.path.join(self.output_dir, 'training_data.csv')
        merged_df.to_csv(output_path, index=False)
        print(f"✅ Saved {len(merged_df)} records to {output_path}")
        
        # Summary
        print(f"\n📊 Merged Data Summary:")
        print(f"   Total records: {len(merged_df)}")
        print(f"   Features: {list(merged_df.columns)}")
        print(f"\n   Risk levels:")
        print(merged_df['risk_level'].value_counts())
        
        # Sample data
        print(f"\n📋 Sample data (first 5 rows):")
        sample_cols = ['station', 'water_level_m', 'rainfall_mm', 'temperature_c', 'risk_score', 'risk_level']
        available_cols = [col for col in sample_cols if col in merged_df.columns]
        if available_cols:
            print(merged_df[available_cols].head(5))
        
        # Statistics
        print(f"\n📊 Statistics:")
        print(f"   Average Water Level: {merged_df['water_level_m'].mean():.2f}m")
        print(f"   Average Rainfall: {merged_df['rainfall_mm'].mean():.1f}mm")
        print(f"   Average Risk Score: {merged_df['risk_score'].mean():.1f}%")
        
        return merged_df

if __name__ == "__main__":
    print("="*50)
    print("🌤️ Merging River + Weather Data")
    print("="*50)
    
    merger = DataMerger()
    df = merger.merge_data()
    
    print("\n✅ Done! Training data is ready!")
    print(f"📁 Data saved to: data/processed/training_data.csv")
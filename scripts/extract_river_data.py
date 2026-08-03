import os
import re
import pandas as pd
import PyPDF2
from datetime import datetime
from collections import defaultdict

class RiverDataExtractor:
    """
    Extract river level and rainfall data from DMC PDFs
    """
    
    def __init__(self):
        self.pdf_dir = "data/river_gauges/dmc_original/"
        self.output_dir = "data/river_gauges/processed/"
        os.makedirs(self.output_dir, exist_ok=True)
        
        self.all_data = []
        
        # Common river stations in Sri Lanka
        self.river_stations = [
            'Nagalagam Street', 'Hanwella', 'Glencourse', 'Kithulgala',
            'Holombuwa', 'Deraniyagala', 'Norwood', 'Puttapula', 'Ellagawa',
            'Rathnapura', 'Magura', 'Kalawellawa', 'Millakanda',
            'Baddegama', 'Thawalama', 'Thalghagoda', 'Panadugama',
            'Pitabeddara', 'Urawa', 'Moraketiya', 'Thanamawila',
            'Wellawaya', 'Kuda Oya', 'Katharagama', 'Nakkala',
            'Siyambalanduwa', 'Padiyathalawa', 'Manampitiya',
            'Weraganthota', 'Peradeniya', 'Nawalapitiya', 'Thaldena',
            'Horowpothana', 'Yaka Wewa', 'Thanthirimale', 'Galgamuwa',
            'Moragaswewa', 'Badalgama', 'Girillla', 'Dunamale'
        ]
        
        self.basin_map = {
            'Nagalagam Street': 'Kelani Ganga',
            'Hanwella': 'Kelani Ganga',
            'Glencourse': 'Kelani Ganga',
            'Kithulgala': 'Kelani Ganga',
            'Peradeniya': 'Mahaweli Ganga',
            'Rathnapura': 'Kalu Ganga',
            'Kalawellawa': 'Kalu Ganga',
            'Baddegama': 'Gin Ganga',
            'Panadugama': 'Nilwala Ganga',
            'Pitabeddara': 'Nilwala Ganga'
        }
    
    def clean_number(self, value):
        """Clean and convert a string to number"""
        if value is None:
            return None
        try:
            # Convert to string
            value = str(value)
            # Keep only digits and dots
            cleaned = re.sub(r'[^\d.]', '', value)
            # Remove multiple dots
            cleaned = re.sub(r'(\d+\.\d+)\.\d+', r'\1', cleaned)
            # Convert to float
            if cleaned and cleaned != '.':
                return float(cleaned)
            return None
        except:
            return None
    
    def extract_from_pdf(self, pdf_path):
        """
        Extract data from a single PDF
        """
        try:
            with open(pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                text = ""
                for page in reader.pages:
                    text += page.extract_text()
                
                # Determine report type
                if 'Water Level' in text or 'Islandwide' in text:
                    return self._extract_water_level_data(text, pdf_path)
                elif 'Flood Warning' in text:
                    return self._extract_flood_warning_data(text, pdf_path)
                elif 'Withdrawal' in text:
                    return None  # Skip withdrawal notices
                else:
                    return None
                    
        except Exception as e:
            # Skip files with errors
            return None
    
    def _extract_water_level_data(self, text, pdf_path):
        """
        Extract water level data from Islandwide reports
        """
        data = []
        
        # Extract date from text
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', text)
        report_date = date_match.group(1) if date_match else 'Unknown'
        
        # Extract time
        time_match = re.search(r'(\d{1,2}:\d{2})\s*(?:AM|PM|am|pm)', text)
        report_time = time_match.group(1) if time_match else 'Unknown'
        
        # Look for station data
        lines = text.split('\n')
        
        for line in lines:
            for station in self.river_stations:
                if station in line:
                    # Extract numbers
                    numbers = re.findall(r'\d+\.?\d*', line)
                    
                    if len(numbers) >= 1:
                        # Clean each number
                        clean_numbers = []
                        for num in numbers:
                            cleaned = self.clean_number(num)
                            if cleaned is not None:
                                clean_numbers.append(cleaned)
                        
                        if clean_numbers:
                            water_level = clean_numbers[0] if len(clean_numbers) > 0 else None
                            rainfall = clean_numbers[1] if len(clean_numbers) > 1 else None
                            alert_level = clean_numbers[2] if len(clean_numbers) > 2 else None
                            
                            basin = self.basin_map.get(station, 'Unknown')
                            
                            data.append({
                                'date': report_date,
                                'time': report_time,
                                'station': station,
                                'river_basin': basin,
                                'water_level_m': water_level,
                                'rainfall_mm': rainfall,
                                'alert_level_m': alert_level,
                                'source_file': os.path.basename(pdf_path)
                            })
                    break
        
        return data
    
    def _extract_flood_warning_data(self, text, pdf_path):
        """
        Extract data from Flood Warning PDFs
        """
        data = []
        
        # Extract date
        date_match = re.search(r'(\d{4}\.\d{2}\.\d{2})', text)
        report_date = date_match.group(1).replace('.', '-') if date_match else 'Unknown'
        
        # Extract river name
        river_match = re.search(r'(Kuda Ganga|Kalu River|Mahaweli|Kelani|Nilwala|Gin|Maha Oya)', text)
        river = river_match.group(1) if river_match else 'Unknown'
        
        # Extract locations
        locations = []
        loc_pattern = r'(Bulathsinhala|Madurawala|Palindanuwara|Kandy|Colombo|Galle|Matara|Ratnapura)'
        loc_matches = re.findall(loc_pattern, text)
        locations = list(set(loc_matches))
        
        # Extract water levels
        level_match = re.search(r'(\d+\.?\d*)\s*(?:m|ft|meters|metres)', text)
        water_level = self.clean_number(level_match.group(1)) if level_match else None
        
        # Extract rainfall
        rain_match = re.search(r'(\d+\.?\d*)\s*(?:mm|mm rainfall|rainfall)', text)
        rainfall = self.clean_number(rain_match.group(1)) if rain_match else None
        
        # Check for alert level
        if 'Amber' in text:
            alert_level = 'Amber'
        elif 'Red' in text:
            alert_level = 'Red'
        elif 'Green' in text:
            alert_level = 'Green'
        else:
            alert_level = 'Unknown'
        
        # Only add if we have some data
        if water_level or rainfall:
            data.append({
                'date': report_date,
                'station': river,
                'river_basin': river,
                'water_level_m': water_level,
                'rainfall_mm': rainfall,
                'alert_level': alert_level,
                'locations': ', '.join(locations) if locations else 'Unknown',
                'report_type': 'Flood Warning',
                'source_file': os.path.basename(pdf_path)
            })
        
        return data
    
    def process_all_pdfs(self):
        """
        Process all PDFs in the directory
        """
        print("📊 Processing all PDFs...")
        
        pdf_files = [f for f in os.listdir(self.pdf_dir) if f.endswith('.pdf')]
        print(f"📁 Found {len(pdf_files)} PDF files")
        
        successful = 0
        for i, pdf_file in enumerate(pdf_files, 1):
            pdf_path = os.path.join(self.pdf_dir, pdf_file)
            
            # Show progress every 10 files
            if i % 10 == 0:
                print(f"📄 [{i}/{len(pdf_files)}] Processing... ({successful} successful so far)")
            
            extracted = self.extract_from_pdf(pdf_path)
            if extracted:
                if isinstance(extracted, list):
                    self.all_data.extend(extracted)
                    successful += 1
                else:
                    self.all_data.append(extracted)
                    successful += 1
        
        print(f"\n✅ Extracted {len(self.all_data)} records from {successful} PDFs (out of {len(pdf_files)})")
        return self.all_data
    
    def save_to_csv(self):
        """
        Save extracted data to CSV with cleaning
        """
        if not self.all_data:
            print("⚠️ No data to save")
            return
        
        df = pd.DataFrame(self.all_data)
        
        # Clean numeric columns
        numeric_cols = ['water_level_m', 'rainfall_mm', 'alert_level_m']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = df[col].apply(self.clean_number)
        
        # Remove rows with no numeric data
        df = df.dropna(subset=['water_level_m', 'rainfall_mm'], how='all')
        
        # Sort by date if available
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            df = df.sort_values('date')
        
        # Save main dataset
        csv_path = os.path.join(self.output_dir, 'river_data_extracted.csv')
        df.to_csv(csv_path, index=False)
        print(f"✅ Saved {len(df)} records to {csv_path}")
        
        # Create summary by station
        if 'station' in df.columns and not df['station'].isna().all():
            try:
                numeric_df = df.select_dtypes(include=['float64', 'int64'])
                if not numeric_df.empty:
                    summary = df.groupby('station')[numeric_df.columns].agg(['count', 'mean', 'min', 'max'])
                    summary_path = os.path.join(self.output_dir, 'station_summary.csv')
                    summary.to_csv(summary_path)
                    print(f"✅ Saved station summary to {summary_path}")
            except Exception as e:
                print(f"⚠️ Could not create station summary: {e}")
        
        # Alert summary
        if 'alert_level' in df.columns:
            alert_counts = df[df['alert_level'] != 'Unknown']['alert_level'].value_counts()
            if not alert_counts.empty:
                print(f"\n📊 Alert Level Summary:")
                print(alert_counts)
        
        # Sample preview
        print(f"\n📋 Sample data (first 5 rows):")
        print(df.head())
        print(f"\n📊 Data summary:")
        print(f"   Total records: {len(df)}")
        if 'date' in df.columns:
            print(f"   Date range: {df['date'].min()} to {df['date'].max()}")
        print(f"   Unique stations: {df['station'].nunique() if 'station' in df.columns else 0}")
        
        return df

if __name__ == "__main__":
    print("="*50)
    print("📊 DMC River Data Extractor")
    print("="*50)
    
    extractor = RiverDataExtractor()
    data = extractor.process_all_pdfs()
    df = extractor.save_to_csv()
    
    print("\n✅ Done! River data is ready for training!")
    print(f"📁 Data saved to: {extractor.output_dir}river_data_extracted.csv")
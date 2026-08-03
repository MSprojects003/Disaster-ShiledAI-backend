import os
import requests
from bs4 import BeautifulSoup
import time
import pandas as pd
import re
from datetime import datetime
import json
from urllib.parse import urljoin, urlparse
import PyPDF2
import io

class DMCRiverDataDownloader:
    """
    Automatically download ALL river data from DMC Sri Lanka
    """
    
    def __init__(self):
        self.base_url = "http://www.drr.dmc.gov.lk/"
        self.reports_url = "http://www.drr.dmc.gov.lk/index.php?option=com_dmcreports&view=reports&Itemid=277&limit=0&search=river&report_type_id=0&fromdate=&todate=&lang=en"
        
        # Create directories
        self.download_dir = "data/river_gauges/dmc_original/"
        self.processed_dir = "data/river_gauges/processed/"
        os.makedirs(self.download_dir, exist_ok=True)
        os.makedirs(self.processed_dir, exist_ok=True)
        
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        self.reports_data = []
    
    def get_report_list(self):
        """
        Get all report links from the DMC website
        """
        print("📡 Fetching report list from DMC website...")
        
        try:
            response = self.session.get(self.reports_url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find the table with reports
            table = soup.find('table')
            if not table:
                print("⚠️ No table found. The website structure might have changed.")
                return []
            
            rows = table.find_all('tr')
            reports = []
            
            for row in rows:
                cols = row.find_all('td')
                if len(cols) >= 4:
                    # Extract title
                    title_td = cols[0]
                    title = title_td.get_text(strip=True) if title_td else "Unknown"
                    
                    # Extract date
                    date_td = cols[1]
                    date = date_td.get_text(strip=True) if date_td else "Unknown"
                    
                    # Extract time
                    time_td = cols[2]
                    time_str = time_td.get_text(strip=True) if time_td else "Unknown"
                    
                    # Find download link
                    download_link = None
                    for a in row.find_all('a'):
                        href = a.get('href', '')
                        if 'download' in href.lower() or '.pdf' in href.lower():
                            download_link = a.get('href')
                            break
                    
                    if download_link:
                        # Convert relative URL to absolute
                        if not download_link.startswith('http'):
                            download_link = urljoin(self.base_url, download_link)
                        
                        reports.append({
                            'title': title,
                            'date': date,
                            'time': time_str,
                            'download_url': download_link
                        })
            
            print(f"✅ Found {len(reports)} reports")
            return reports
            
        except Exception as e:
            print(f"❌ Error fetching report list: {e}")
            return []
    
    def download_pdf(self, report):
        """
        Download a single PDF
        """
        title = report['title']
        date = report['date']
        download_url = report['download_url']
        
        # Clean filename
        safe_title = re.sub(r'[^\w\s-]', '', title).strip()
        safe_title = safe_title.replace(' ', '_')
        filename = f"{date}_{safe_title}.pdf"
        filepath = os.path.join(self.download_dir, filename)
        
        # Skip if already downloaded
        if os.path.exists(filepath):
            return {'status': 'skipped', 'filepath': filepath}
        
        try:
            response = self.session.get(download_url, timeout=60)
            response.raise_for_status()
            
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            return {'status': 'success', 'filepath': filepath, 'size': len(response.content)}
            
        except Exception as e:
            return {'status': 'error', 'error': str(e), 'url': download_url}
    
    def download_all(self):
        """
        Download all reports
        """
        print("🚀 Starting download of ALL DMC reports...")
        
        reports = self.get_report_list()
        if not reports:
            print("❌ No reports found to download")
            return
        
        print(f"📊 Found {len(reports)} reports to download")
        print("⏳ Downloading... (this may take a while)")
        
        results = {
            'success': 0,
            'skipped': 0,
            'error': 0,
            'errors': []
        }
        
        for i, report in enumerate(reports, 1):
            print(f"📥 [{i}/{len(reports)}] Downloading: {report['title']}...")
            
            result = self.download_pdf(report)
            
            if result['status'] == 'success':
                results['success'] += 1
                # Extract data from PDF
                self.extract_data_from_pdf(result['filepath'], report)
            elif result['status'] == 'skipped':
                results['skipped'] += 1
            else:
                results['error'] += 1
                results['errors'].append(result)
            
            # Store report data
            self.reports_data.append({
                'title': report['title'],
                'date': report['date'],
                'time': report['time'],
                'status': result['status'],
                'filepath': result.get('filepath', '')
            })
            
            # Be nice to the server
            time.sleep(1)
        
        # Save summary
        self.save_summary(results)
        
        return results
    
    def extract_data_from_pdf(self, filepath, report):
        """
        Extract text from PDF
        """
        try:
            with open(filepath, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                text = ""
                for page in reader.pages:
                    text += page.extract_text()
                
                # Extract river levels from text
                river_data = self.parse_river_text(text, report)
                
                if river_data:
                    # Save to CSV
                    self.save_to_csv(river_data, filepath)
                
        except Exception as e:
            print(f"⚠️ Could not extract text from {filepath}: {e}")
    
    def parse_river_text(self, text, report):
        """
        Parse river data from PDF text
        """
        data = []
        
        # Look for river level patterns
        lines = text.split('\n')
        for line in lines:
            # Check for station name pattern
            if any(river in line.lower() for river in ['ganga', 'oya', 'river']):
                # Extract numbers (water levels)
                numbers = re.findall(r'\d+\.?\d*', line)
                if len(numbers) >= 2:
                    data.append({
                        'report_title': report['title'],
                        'report_date': report['date'],
                        'report_time': report['time'],
                        'text_line': line.strip(),
                        'extracted_numbers': numbers
                    })
        
        return data
    
    def save_to_csv(self, data, filepath):
        """
        Save extracted data to CSV
        """
        if data:
            df = pd.DataFrame(data)
            csv_filename = os.path.basename(filepath).replace('.pdf', '.csv')
            csv_path = os.path.join(self.processed_dir, csv_filename)
            df.to_csv(csv_path, index=False)
    
    def save_summary(self, results):
        """
        Save download summary
        """
        summary = {
            'download_date': datetime.now().isoformat(),
            'total_reports': len(self.reports_data),
            'results': results,
            'reports': self.reports_data
        }
        
        with open(os.path.join(self.processed_dir, 'download_summary.json'), 'w') as f:
            json.dump(summary, f, indent=2)
        
        print("\n" + "="*50)
        print("📊 DOWNLOAD SUMMARY")
        print("="*50)
        print(f"✅ Success: {results['success']}")
        print(f"⏭️ Skipped: {results['skipped']}")
        print(f"❌ Errors: {results['error']}")
        print(f"📁 Total reports: {len(self.reports_data)}")
        print("="*50)

    def create_integrated_dataset(self):
        """
        Create a single CSV with ALL data from all PDFs
        """
        all_data = []
        
        # Load all extracted CSV files
        for csv_file in os.listdir(self.processed_dir):
            if csv_file.endswith('.csv') and csv_file != 'integrated_river_data.csv':
                try:
                    df = pd.read_csv(os.path.join(self.processed_dir, csv_file))
                    all_data.append(df)
                except:
                    pass
        
        if all_data:
            combined = pd.concat(all_data, ignore_index=True)
            combined.to_csv(os.path.join(self.processed_dir, 'integrated_river_data.csv'), index=False)
            print(f"✅ Created integrated dataset with {len(combined)} records")
            return combined
        
        return None

if __name__ == "__main__":
    # Run the downloader
    downloader = DMCRiverDataDownloader()
    
    # Step 1: Download all PDFs
    results = downloader.download_all()
    
    # Step 2: Create integrated dataset
    print("\n📊 Creating integrated dataset...")
    downloader.create_integrated_dataset()
    
    print("\n✅ Done! All data saved to:")
    print(f"   📁 PDFs: {downloader.download_dir}")
    print(f"   📁 Processed CSVs: {downloader.processed_dir}")
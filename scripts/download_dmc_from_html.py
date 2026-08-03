import os
import requests
from bs4 import BeautifulSoup
import time
import re
from datetime import datetime
import json
from urllib.parse import urljoin
import PyPDF2
import pandas as pd

class DMCDownloaderFromHTML:
    """
    Download DMC reports using saved HTML file
    """
    
    def __init__(self):
        self.base_url = "http://www.drr.dmc.gov.lk/"
        self.html_file = "data/river_gauges/dmc_reports.html"
        
        # Create directories
        self.download_dir = "data/river_gauges/dmc_original/"
        self.processed_dir = "data/river_gauges/processed/"
        os.makedirs(self.download_dir, exist_ok=True)
        os.makedirs(self.processed_dir, exist_ok=True)
        
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def extract_links_from_html(self):
        """
        Extract report links from saved HTML file
        """
        print("📡 Reading HTML file...")
        
        if not os.path.exists(self.html_file):
            print(f"❌ HTML file not found: {self.html_file}")
            print("📋 Please save the DMC webpage as HTML first:")
            print("   1. Open: http://www.drr.dmc.gov.lk/index.php?option=com_dmcreports&view=reports&Itemid=277&limit=0&search=river&report_type_id=0&fromdate=&todate=&lang=en")
            print("   2. Right-click → Save Page As → HTML file")
            print(f"   3. Save as: {self.html_file}")
            return []
        
        try:
            with open(self.html_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            soup = BeautifulSoup(content, 'html.parser')
            
            # Find all links
            reports = []
            
            # Look for table rows with links
            for a in soup.find_all('a'):
                href = a.get('href', '')
                text = a.get_text(strip=True)
                
                # Check if it's a download link
                if 'download' in href.lower() or (href.endswith('.pdf')):
                    # Find parent row for context
                    parent_row = a.find_parent('tr')
                    if parent_row:
                        cols = parent_row.find_all('td')
                        if len(cols) >= 3:
                            title = cols[0].get_text(strip=True) if len(cols) > 0 else text
                            date = cols[1].get_text(strip=True) if len(cols) > 1 else "Unknown"
                            time_str = cols[2].get_text(strip=True) if len(cols) > 2 else "Unknown"
                        else:
                            title = text
                            date = "Unknown"
                            time_str = "Unknown"
                    else:
                        title = text
                        date = "Unknown"
                        time_str = "Unknown"
                    
                    # Make sure title is not empty
                    if not title or title.lower() in ['download', 'view', '']:
                        continue
                    
                    # Convert to absolute URL
                    if not href.startswith('http'):
                        href = urljoin(self.base_url, href)
                    
                    reports.append({
                        'title': title,
                        'date': date,
                        'time': time_str,
                        'download_url': href
                    })
            
            # Remove duplicates
            seen = set()
            unique_reports = []
            for report in reports:
                key = (report['title'], report['date'])
                if key not in seen:
                    seen.add(key)
                    unique_reports.append(report)
            
            print(f"✅ Found {len(unique_reports)} unique reports")
            
            # Print first few reports as sample
            print("\n📋 Sample reports:")
            for i, report in enumerate(unique_reports[:5], 1):
                print(f"  {i}. {report['title']} ({report['date']})")
            
            return unique_reports
            
        except Exception as e:
            print(f"❌ Error parsing HTML: {e}")
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
        safe_title = re.sub(r'[\/:*?"<>|]', '_', safe_title)  # Remove invalid filename chars
        safe_title = safe_title[:50]  # Limit length
        filename = f"{date}_{safe_title}.pdf"
        filepath = os.path.join(self.download_dir, filename)
        
        # Skip if already downloaded
        if os.path.exists(filepath):
            print(f"  ⏭️ Already downloaded: {filename}")
            return {'status': 'skipped', 'filepath': filepath}
        
        try:
            response = self.session.get(download_url, timeout=60)
            response.raise_for_status()
            
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            print(f"  ✅ Downloaded: {filename} ({len(response.content)/1024:.1f} KB)")
            return {'status': 'success', 'filepath': filepath}
            
        except Exception as e:
            print(f"  ❌ Error: {e}")
            return {'status': 'error', 'error': str(e), 'url': download_url}
    
    def download_all(self):
        """
        Download all reports
        """
        print("\n🚀 Starting download of ALL DMC reports...")
        
        reports = self.extract_links_from_html()
        if not reports:
            print("❌ No reports found to download")
            return
        
        print(f"\n📊 Found {len(reports)} reports to download")
        print("⏳ Downloading...\n")
        
        results = {
            'success': 0,
            'skipped': 0,
            'error': 0,
            'errors': []
        }
        
        for i, report in enumerate(reports, 1):
            print(f"📥 [{i}/{len(reports)}] {report['title']}")
            result = self.download_pdf(report)
            
            if result['status'] == 'success':
                results['success'] += 1
            elif result['status'] == 'skipped':
                results['skipped'] += 1
            else:
                results['error'] += 1
                results['errors'].append(result)
            
            # Be nice to the server
            time.sleep(0.5)
        
        # Save summary
        self.save_summary(results, reports)
        
        return results
    
    def save_summary(self, results, reports):
        """
        Save download summary
        """
        summary = {
            'download_date': datetime.now().isoformat(),
            'total_reports': len(reports),
            'results': results,
            'reports_attempted': [
                {
                    'title': r['title'],
                    'date': r['date'],
                    'status': 'downloaded' if any(r['title'] in str(f) for f in os.listdir(self.download_dir)) else 'unknown'
                }
                for r in reports
            ]
        }
        
        with open(os.path.join(self.processed_dir, 'download_summary.json'), 'w') as f:
            json.dump(summary, f, indent=2)
        
        print("\n" + "="*50)
        print("📊 DOWNLOAD SUMMARY")
        print("="*50)
        print(f"✅ Success: {results['success']}")
        print(f"⏭️ Skipped: {results['skipped']}")
        print(f"❌ Errors: {results['error']}")
        print(f"📁 Total reports: {len(reports)}")
        print("="*50)

if __name__ == "__main__":
    # Run the downloader
    downloader = DMCDownloaderFromHTML()
    results = downloader.download_all()
    
    print("\n✅ Done! All data saved to:")
    print(f"   📁 PDFs: {downloader.download_dir}")
    print(f"   📁 Processed CSVs: {downloader.processed_dir}")
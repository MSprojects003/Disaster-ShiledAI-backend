import os
import requests
import zipfile
import io
import pandas as pd
import geopandas as gpd
import json
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SriLankaRoadDownloaderFixed:
    """
    Download Sri Lanka road network (ROADS ONLY)
    """
    
    def __init__(self):
        self.data_dir = "data/infrastructure/"
        self.roads_dir = os.path.join(self.data_dir, "sri_lanka_roads/")
        self.output_dir = os.path.join(self.data_dir, "processed/")
        
        # Create directories
        os.makedirs(self.roads_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)
        
        # CORRECT download sources for ROADS
        self.sources = [
            {
                'name': 'HDX Roads',
                'url': 'https://data.humdata.org/dataset/52d9a2c9-a3f8-4647-8a18-33f64e1fb76c/resource/7d15f624-c441-419a-9633-b8a8d38d28d0/download/hotosm_lka_roads_osm_shp.zip',
                'file': 'hotosm_lka_roads_osm_shp.zip',
                'is_roads': True
            },
            {
                'name': 'GeoFabrik Roads',
                'url': 'https://download.geofabrik.de/asia/sri-lanka-latest-free.shp.zip',
                'file': 'sri_lanka_roads_geofabrik.zip',
                'is_roads': True
            }
        ]
    
    def download_roads(self):
        """
        Try downloading from multiple sources
        """
        logger.info("📥 Attempting to download Sri Lanka road network...")
        
        for source in self.sources:
            try:
                logger.info(f"   Trying: {source['name']}")
                response = requests.get(source['url'], timeout=300, stream=True)
                
                if response.status_code == 200:
                    zip_path = os.path.join(self.roads_dir, source['file'])
                    
                    total_size = int(response.headers.get('content-length', 0))
                    block_size = 8192
                    
                    with open(zip_path, 'wb') as f:
                        downloaded = 0
                        for chunk in response.iter_content(chunk_size=block_size):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                if total_size > 0:
                                    progress = (downloaded / total_size) * 100
                                    if int(progress) % 10 == 0:
                                        logger.info(f"      Downloading... {progress:.0f}%")
                    
                    logger.info(f"✅ Downloaded from {source['name']}: {zip_path}")
                    return zip_path
                    
                else:
                    logger.warning(f"   ❌ {source['name']} failed: {response.status_code}")
                    
            except Exception as e:
                logger.warning(f"   ❌ {source['name']} error: {e}")
        
        logger.error("❌ All download sources failed.")
        return None
    
    def extract_and_load(self, zip_path):
        """
        Extract and load the shapefile
        """
        if not zip_path:
            return False
        
        logger.info("📦 Extracting and loading road data...")
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(self.roads_dir)
            
            # Find road shapefiles (not admin boundaries)
            shp_files = []
            for shp in Path(self.roads_dir).glob("**/*.shp"):
                # Skip admin boundary files
                if 'admin' not in str(shp).lower() and 'boundary' not in str(shp).lower():
                    shp_files.append(shp)
            
            if not shp_files:
                # If no roads found, try all shp files
                shp_files = list(Path(self.roads_dir).glob("**/*.shp"))
            
            if not shp_files:
                logger.error("❌ No shapefile found")
                return False
            
            # Check if it's roads (contains 'highway' column)
            for shp_path in shp_files:
                try:
                    test_gdf = gpd.read_file(shp_path)
                    if 'highway' in test_gdf.columns:
                        self.roads_gdf = test_gdf
                        logger.info(f"✅ Found ROADS dataset: {shp_path}")
                        logger.info(f"   Loaded {len(self.roads_gdf)} road segments")
                        break
                except:
                    continue
            
            if not hasattr(self, 'roads_gdf'):
                logger.warning("⚠️ No road dataset found. Loading first shapefile...")
                self.roads_gdf = gpd.read_file(shp_files[0])
            
            logger.info(f"   Columns: {self.roads_gdf.columns.tolist()}")
            
            # Show sample
            sample_cols = ['osm_id', 'name', 'highway', 'surface', 'geometry']
            existing_cols = [c for c in sample_cols if c in self.roads_gdf.columns]
            if existing_cols:
                print(self.roads_gdf[existing_cols].head(5))
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Extraction failed: {e}")
            return False
    
    def process_roads(self):
        """Process roads into Infrastructure Agent format"""
        if not hasattr(self, 'roads_gdf') or self.roads_gdf is None:
            logger.error("❌ No road data loaded. Run extract_and_load first.")
            return None
        
        logger.info("🔄 Processing roads for Infrastructure Agent...")
        
        road_data = []
        
        for idx, row in self.roads_gdf.iterrows():
            geometry = row.geometry
            centroid = geometry.centroid if geometry.geom_type != 'LineString' else geometry.interpolate(0.5, normalized=True)
            
            name = row.get('name', None)
            if pd.isna(name) or name == '':
                name = f"Road_{row.get('osm_id', idx)}"
            
            highway = row.get('highway', 'unknown')
            if pd.isna(highway):
                highway = 'unknown'
            
            # Get surface type
            surface = row.get('surface', None)
            if pd.isna(surface):
                surface = 'unknown'
            
            # Determine if paved
            is_paved = surface in ['paved', 'asphalt', 'concrete', 'paving_stones'] if surface else None
            
            # Get road length
            length = geometry.length * 0.01  # Approximate conversion to km
            
            road_data.append({
                'road_id': row.get('osm_id', idx),
                'name': name,
                'highway': highway,
                'surface': surface,
                'is_paved': is_paved,
                'elevation': 50,  # Default elevation
                'length_km': length,
                'geometry': geometry.wkt,
                'status': 'Normal',
                'condition_score': 100
            })
        
        self.roads_df = pd.DataFrame(road_data)
        
        logger.info(f"✅ Processed {len(self.roads_df)} road segments")
        logger.info(f"   Road types: {self.roads_df['highway'].value_counts().head(10)}")
        
        # Save to CSV
        output_csv = os.path.join(self.output_dir, 'sri_lanka_roads.csv')
        self.roads_df.to_csv(output_csv, index=False)
        logger.info(f"💾 Saved to: {output_csv}")
        
        return self.roads_df
    
    def create_infrastructure_csv(self):
        """Create the final infrastructure CSV"""
        if self.roads_df is None:
            logger.error("❌ No road data. Run process_roads first.")
            return
        
        infra_df = self.roads_df[['road_id', 'name', 'highway', 'surface', 
                                  'is_paved', 'elevation', 'length_km']].copy()
        infra_df['districts'] = 'Unknown'
        infra_df['status'] = 'Normal'
        infra_df['condition_score'] = 100
        
        output_path = os.path.join(self.output_dir, 'infrastructure_roads.csv')
        infra_df.to_csv(output_path, index=False)
        logger.info(f"✅ Saved infrastructure roads to: {output_path}")
    
    def run(self):
        """Run the complete pipeline"""
        print("="*60)
        print("🚗 Sri Lanka Road Network Downloader")
        print("   (Downloading ROADS, not admin boundaries)")
        print("="*60)
        
        # Step 1: Download
        zip_path = self.download_roads()
        if zip_path:
            # Step 2: Extract and load
            if self.extract_and_load(zip_path):
                # Step 3: Process
                self.process_roads()
                # Step 4: Create infrastructure CSV
                self.create_infrastructure_csv()
        else:
            logger.info("\n📋 Manual download instructions:")
            logger.info("   1. Go to: https://download.geofabrik.de/asia/sri-lanka.html")
            logger.info("   2. Download 'sri-lanka-latest-free.shp.zip'")
            logger.info(f"   3. Extract to: {self.roads_dir}")
            logger.info("   4. Run this script again")
        
        print("\n" + "="*60)
        print("✅ Done!")
        print("="*60)

if __name__ == "__main__":
    downloader = SriLankaRoadDownloaderFixed()
    downloader.run()
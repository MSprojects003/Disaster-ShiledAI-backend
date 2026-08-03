"""
View and analyze DesInventar data
"""
import pandas as pd
import os
import json

def view_desinventar_data():
    """View the downloaded DesInventar data"""
    
    data_dir = 'data/historical/processed/'
    
    # Load main dataset
    csv_path = os.path.join(data_dir, 'desinventar_sri_lanka_1974_2022.csv')
    if os.path.exists(csv_path):
        df = pd.read_csv(csv_path)
        
        print("="*60)
        print("📊 DesInventar Data Overview")
        print("="*60)
        print(f"\nTotal Records: {len(df)}")
        print(f"Districts: {df['district'].nunique()}")
        print(f"Columns: {df.columns.tolist()}")
        
        print("\n📋 Top 10 Most Affected Districts:")
        print(df[['district', 'total_events', 'historical_risk_score']].head(10))
        
        print("\n📊 Disaster Type Distribution:")
        disaster_cols = ['cyclone', 'drought', 'flood', 'heavy_rain', 'landslide', 'lightning', 'strong_wind']
        totals = df[disaster_cols].sum()
        for col, val in totals.items():
            print(f"   {col}: {val:,}")
        
        print(f"\n📁 Data saved at: {csv_path}")
    else:
        print("❌ Data not found. Run download_desinventar.py first.")
    
    # Load summary
    summary_path = os.path.join(data_dir, 'dataset_summary.json')
    if os.path.exists(summary_path):
        with open(summary_path, 'r') as f:
            summary = json.load(f)
        
        print("\n📋 Summary from JSON:")
        print(json.dumps(summary, indent=2)[:500] + "...")

if __name__ == "__main__":
    view_desinventar_data()
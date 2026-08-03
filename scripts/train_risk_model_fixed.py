import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
from sklearn.utils.class_weight import compute_class_weight
import xgboost as xgb
import joblib
import os
import json
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

class RiskModelTrainerFixed:
    """
    Train risk prediction model with proper handling
    """
    
    def __init__(self):
        self.data_path = "data/processed/training_data.csv"
        self.model_dir = "models_saved/"
        os.makedirs(self.model_dir, exist_ok=True)
        
        self.features = [
            'water_level_m', 
            'rainfall_mm',
            'temperature_c',
            'humidity_percent',
            'wind_speed_kmh',
            'pressure_hpa'
        ]
        
        self.target = 'risk_level'
        self.risk_mapping = {'Low': 0, 'Medium': 1, 'High': 2, 'Critical': 3}
        self.reverse_mapping = {0: 'Low', 1: 'Medium', 2: 'High', 3: 'Critical'}
    
    def load_data(self):
        """Load the training dataset"""
        if os.path.exists(self.data_path):
            df = pd.read_csv(self.data_path)
            print(f"✅ Loaded {len(df)} records from {self.data_path}")
            return df
        else:
            print(f"❌ Data not found at {self.data_path}")
            return None
    
    def augment_data(self, df):
        """
        Augment data to create more High/Critical risk samples
        """
        print("\n📊 Augmenting data for better class balance...")
        
        # Get current distribution
        print(f"   Current distribution:")
        print(df['risk_level'].value_counts())
        
        # Create synthetic High risk samples
        high_risk_samples = []
        
        # For each district, create high-risk scenarios
        districts = df['station'].unique()
        
        for district in districts:
            # Base values from existing data
            district_data = df[df['station'] == district]
            if len(district_data) == 0:
                continue
            
            base_water = district_data['water_level_m'].mean()
            base_rain = district_data['rainfall_mm'].mean()
            
            # Create high-risk variations
            for _ in range(10):  # 10 samples per district
                high_risk_samples.append({
                    'station': district,
                    'river_basin': district_data['river_basin'].mode()[0] if len(district_data) > 0 else 'Unknown',
                    'water_level_m': base_water + np.random.uniform(3, 8),
                    'rainfall_mm': base_rain + np.random.uniform(50, 150),
                    'temperature_c': np.random.uniform(25, 30),
                    'humidity_percent': np.random.uniform(80, 98),
                    'wind_speed_kmh': np.random.uniform(10, 35),
                    'pressure_hpa': np.random.uniform(1000, 1015),
                    'risk_level': 'High'
                })
                
                # Also create Critical samples
                if np.random.random() > 0.7:
                    high_risk_samples.append({
                        'station': district,
                        'river_basin': district_data['river_basin'].mode()[0] if len(district_data) > 0 else 'Unknown',
                        'water_level_m': base_water + np.random.uniform(8, 15),
                        'rainfall_mm': base_rain + np.random.uniform(100, 200),
                        'temperature_c': np.random.uniform(22, 28),
                        'humidity_percent': np.random.uniform(90, 100),
                        'wind_speed_kmh': np.random.uniform(20, 50),
                        'pressure_hpa': np.random.uniform(995, 1008),
                        'risk_level': 'Critical'
                    })
        
        # Create synthetic Medium risk samples (to balance)
        medium_samples = []
        for _ in range(50):
            district = np.random.choice(districts)
            district_data = df[df['station'] == district]
            if len(district_data) == 0:
                continue
            
            base_water = district_data['water_level_m'].mean()
            base_rain = district_data['rainfall_mm'].mean()
            
            medium_samples.append({
                'station': district,
                'river_basin': district_data['river_basin'].mode()[0] if len(district_data) > 0 else 'Unknown',
                'water_level_m': base_water + np.random.uniform(1, 3),
                'rainfall_mm': base_rain + np.random.uniform(20, 60),
                'temperature_c': np.random.uniform(26, 32),
                'humidity_percent': np.random.uniform(60, 85),
                'wind_speed_kmh': np.random.uniform(5, 20),
                'pressure_hpa': np.random.uniform(1005, 1018),
                'risk_level': 'Medium'
            })
        
        # Convert to DataFrame
        high_df = pd.DataFrame(high_risk_samples)
        medium_df = pd.DataFrame(medium_samples)
        
        # Combine with original
        augmented_df = pd.concat([df, high_df, medium_df], ignore_index=True)
        
        print(f"   After augmentation:")
        print(augmented_df['risk_level'].value_counts())
        
        return augmented_df
    
    def prepare_data(self, df):
        """Prepare data for training"""
        print("\n📊 Preparing data for training...")
        
        # Augment data
        df = self.augment_data(df)
        
        # Convert target to numeric
        df['risk_numeric'] = df['risk_level'].map(self.risk_mapping)
        df = df.dropna(subset=['risk_numeric'])
        
        # Prepare features
        X = df[self.features].fillna(0)
        y = df['risk_numeric'].astype(int)
        
        # FIXED: value_counts() gives COUNTS indexed by class number
        # (e.g. 0 -> 820, 1 -> 146 ...). Calling .map(reverse_mapping)
        # on that tries to look up the *counts* (820, 146, ...) in a
        # dict that only has keys 0-3, so every row came back NaN.
        # What we actually want is the counts, labeled by class name —
        # so rename the index instead of mapping the values.
        counts_by_class = y.value_counts().sort_index()
        counts_by_class.index = counts_by_class.index.map(self.reverse_mapping)
        print(f"\n   Final class distribution:")
        print(counts_by_class)
        
        print(f"\n   Features shape: {X.shape}")
        print(f"   Classes: {sorted(y.unique())}")
        
        return X, y
    
    def train_models(self, X, y):
        """Train multiple models with class weighting"""
        print("\n🚀 Training models...")
        
        # Handle class imbalance with class weights
        classes = np.unique(y)
        class_weights = compute_class_weight('balanced', classes=classes, y=y)
        weight_dict = dict(zip(classes, class_weights))
        print(f"   Class weights: {weight_dict}")
        
        # Split data with stratification
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )
        
        print(f"   Training set: {len(X_train)} records")
        print(f"   Test set: {len(X_test)} records")
        
        models = {}
        results = {}
        
        # 1. Random Forest with class weights
        print("\n🌲 Training Random Forest with class weights...")
        rf = RandomForestClassifier(
            n_estimators=150,
            max_depth=12,
            min_samples_split=3,
            class_weight=weight_dict,
            random_state=42,
            n_jobs=-1
        )
        rf.fit(X_train, y_train)
        models['random_forest'] = rf
        
        # 2. XGBoost with scale_pos_weight
        print("⚡ Training XGBoost with scale_pos_weight...")
        scale_weights = {}
        for cls in classes:
            if cls == 0:  # Low risk
                scale_weights[cls] = 1.0
            else:
                scale_weights[cls] = len(y[y==0]) / len(y[y==cls]) if len(y[y==cls]) > 0 else 1.0
        
        xgb_model = xgb.XGBClassifier(
            n_estimators=150,
            max_depth=8,
            learning_rate=0.1,
            scale_pos_weight=scale_weights.get(1, 1.0),
            random_state=42,
            use_label_encoder=False,
            eval_metric='mlogloss'
        )
        xgb_model.fit(X_train, y_train)
        models['xgboost'] = xgb_model
        
        # 3. Ensemble
        print("🎯 Creating Ensemble...")
        y_pred_rf = rf.predict(X_test)
        y_pred_xgb = xgb_model.predict(X_test)
        y_pred_ensemble = ((y_pred_rf + y_pred_xgb) / 2).round().astype(int)
        
        # Evaluate
        print("\n📊 Model Performance:")
        print("-" * 40)
        
        for name, model in models.items():
            y_pred = model.predict(X_test)
            acc = accuracy_score(y_test, y_pred)
            results[name] = {
                'accuracy': acc,
                'predictions': y_pred
            }
            print(f"   {name}: {acc:.2%}")
        
        # Ensemble accuracy
        acc_ensemble = accuracy_score(y_test, y_pred_ensemble)
        print(f"   ensemble: {acc_ensemble:.2%}")
        
        return models, X_test, y_test, y_pred_ensemble
    
    def save_models(self, models, X, y):
        """Save trained models"""
        print("\n💾 Saving models...")

        for name, model in models.items():
            path = os.path.join(self.model_dir, f'{name}_model.pkl')
            joblib.dump(model, path)
            print(f"   ✅ Saved {name} to {path}")

        # Save feature info
        feature_info = {
            'features': self.features,
            'n_samples': len(X),
            'n_features': len(self.features),
            'target_mapping': self.risk_mapping,
            'reverse_mapping': self.reverse_mapping,
            # FIXED: y.unique() / sorted() return numpy int64 values,
            # which json.dump can't serialize on its own
            # (TypeError: Object of type int32/int64 is not JSON
            # serializable). Cast each to a plain Python int.
            'classes_present': [int(c) for c in sorted(y.unique())],
            'trained_date': datetime.now().isoformat()
        }

        with open(os.path.join(self.model_dir, 'feature_info.json'), 'w') as f:
            json.dump(feature_info, f, indent=2)
        print(f"   ✅ Saved feature info to {self.model_dir}feature_info.json")

    def run(self):
        """Run the complete training pipeline"""
        print("="*50)
        print("🚀 Risk Prediction Model Training (FIXED)")
        print("="*50)

        # Load data
        df = self.load_data()
        if df is None:
            return

        # Prepare data
        X, y = self.prepare_data(df)

        # Train models
        models, X_test, y_test, y_pred = self.train_models(X, y)

        # Save models
        self.save_models(models, X, y)

        # Print feature importance
        print("\n📊 Feature Importance (Random Forest):")
        rf = models['random_forest']
        importance = pd.DataFrame({
            'feature': self.features,
            'importance': rf.feature_importances_
        }).sort_values('importance', ascending=False)
        print(importance)

        # Confusion matrix
        print("\n📊 Confusion Matrix:")
        print(confusion_matrix(y_test, y_pred))

        # Classification report
        print("\n📊 Classification Report:")
        target_names = [self.reverse_mapping[i] for i in sorted(set(y))]
        print(classification_report(
            y_test, y_pred,
            labels=sorted(set(y)),
            target_names=target_names
        ))

        print("\n✅ Training complete!")
        print(f"📁 Models saved to: {self.model_dir}")

if __name__ == "__main__":
    trainer = RiskModelTrainerFixed()
    trainer.run()
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
import xgboost as xgb
import joblib
import os
import json
from datetime import datetime

class RiskModelTrainer:
    """
    Train risk prediction model on real Sri Lanka data
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

        # Filled in during prepare_data() with whichever risk labels are
        # actually usable after rare-class handling, so save_models() /
        # reporting can reflect the real label set instead of assuming
        # all four of Low/Medium/High/Critical are present.
        self.class_names = ['Low', 'Medium', 'High', 'Critical']
    
    def load_data(self):
        """Load the training dataset"""
        if os.path.exists(self.data_path):
            df = pd.read_csv(self.data_path)
            print(f"✅ Loaded {len(df)} records from {self.data_path}")
            print(f"📊 Features: {df.columns.tolist()}")
            return df
        else:
            print(f"❌ Data not found at {self.data_path}")
            return None
    
    def prepare_data(self, df):
        """Prepare data for training"""
        print("\n📊 Preparing data for training...")
        
        # Check for missing values
        print(f"   Missing values:")
        print(df[self.features + [self.target]].isnull().sum())
        
        # Drop rows with missing target
        df = df.dropna(subset=[self.target])
        
        # Convert target to numeric
        risk_mapping = {'Low': 0, 'Medium': 1, 'High': 2, 'Critical': 3}
        df['risk_numeric'] = df[self.target].map(risk_mapping)
        
        # Drop rows with NaN target
        df = df.dropna(subset=['risk_numeric'])
        df['risk_numeric'] = df['risk_numeric'].astype(int)

        # --- Handle rare/singleton classes ---
        # train_test_split(..., stratify=y) requires every class to have
        # at least 2 members (1 to go to train, 1 to test). Real disaster
        # data is naturally imbalanced — Critical events are rare by
        # definition — so a class can easily end up with 0 or 1 samples.
        # Rather than crash, fold any class with fewer than 2 samples
        # into the next class down (e.g. a lone 'High' merges into
        # 'Medium'), and report exactly what happened.
        counts = df['risk_numeric'].value_counts().sort_index()
        print(f"\n   Raw class counts before rare-class handling:")
        print(counts)

        rare_classes = counts[counts < 2].index.tolist()
        if rare_classes:
            print(f"\n⚠️ Classes with <2 samples will be merged into the "
                  f"next lower class: {rare_classes}")
            for cls in sorted(rare_classes, reverse=True):
                target_cls = cls - 1
                # Keep merging down until we land on a class with enough
                # members, in case multiple adjacent classes are rare.
                while target_cls in rare_classes and target_cls > 0:
                    target_cls -= 1
                df.loc[df['risk_numeric'] == cls, 'risk_numeric'] = target_cls
                print(f"   Merged class {cls} -> {target_cls}")

            print(f"\n   Class counts after merging:")
            print(df['risk_numeric'].value_counts().sort_index())

        # Recompute which of the four names are actually still in play,
        # for reporting later (classification_report needs a matching
        # target_names list length).
        used_classes = sorted(df['risk_numeric'].unique().tolist())
        all_names = ['Low', 'Medium', 'High', 'Critical']
        self.class_names = [all_names[c] for c in used_classes]
        
        X = df[self.features].fillna(0)
        y = df['risk_numeric']
        
        print(f"\n   Features shape: {X.shape}")
        print(f"   Final target distribution:")
        print(y.value_counts().sort_index())
        
        return X, y
    
    def train_models(self, X, y):
        """Train multiple models"""
        print("\n🚀 Training models...")

        # Guard again at split time: even after merging rare classes in
        # prepare_data, double-check nothing slipped through with <2
        # members (e.g. if this method is ever called on data that
        # skipped prepare_data). Falls back to an unstratified split
        # rather than crashing.
        counts = y.value_counts()
        can_stratify = counts.min() >= 2
        if not can_stratify:
            print(f"⚠️ Still found a class with <2 samples {counts.to_dict()}; "
                  f"falling back to a non-stratified split.")

        split_kwargs = dict(test_size=0.2, random_state=42)
        if can_stratify:
            split_kwargs['stratify'] = y

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, **split_kwargs
        )
        
        print(f"   Training set: {len(X_train)} records")
        print(f"   Test set: {len(X_test)} records")
        
        models = {}
        results = {}
        
        # 1. Random Forest
        print("\n🌲 Training Random Forest...")
        rf = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            min_samples_split=5,
            random_state=42,
            n_jobs=-1
        )
        rf.fit(X_train, y_train)
        models['random_forest'] = rf
        
        # 2. XGBoost
        print("⚡ Training XGBoost...")
        xgb_model = xgb.XGBClassifier(
            n_estimators=100,
            max_depth=6,
            learning_rate=0.1,
            random_state=42,
            use_label_encoder=False,
            eval_metric='mlogloss'
        )
        xgb_model.fit(X_train, y_train)
        models['xgboost'] = xgb_model
        
        # 3. Ensemble (average predictions)
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
        
        # Save each model
        for name, model in models.items():
            path = os.path.join(self.model_dir, f'{name}_model.pkl')
            joblib.dump(model, path)
            print(f"   ✅ Saved {name} to {path}")
        
        # Save feature info
        feature_info = {
            'features': self.features,
            'n_samples': len(X),
            'n_features': len(self.features),
            'target_mapping': {'Low': 0, 'Medium': 1, 'High': 2, 'Critical': 3},
            'classes_present': self.class_names,
            'trained_date': datetime.now().isoformat()
        }
        
        with open(os.path.join(self.model_dir, 'feature_info.json'), 'w') as f:
            json.dump(feature_info, f, indent=2)
        print(f"   ✅ Saved feature info to {self.model_dir}feature_info.json")
    
    def run(self):
        """Run the complete training pipeline"""
        print("="*50)
        print("🚀 Risk Prediction Model Training")
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
        
        print("\n📊 Classification Report:")
        # target_names must match exactly the classes that survived
        # rare-class merging in prepare_data(), not always all four.
        print(classification_report(
            y_test, y_pred,
            labels=sorted(y_test.unique().tolist()),
            target_names=self.class_names
        ))
        
        print("\n✅ Training complete!")
        print(f"📁 Models saved to: {self.model_dir}")

if __name__ == "__main__":
    trainer = RiskModelTrainer()
    trainer.run()
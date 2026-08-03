"""
Train Infrastructure Agent ML Model
"""

import os
import sys
import pandas as pd
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from app.models.infrastructure_model import infrastructure_model
from scripts.generate_infrastructure_training_data import InfrastructureDataGenerator

def train_infrastructure_model():
    """
    Train the infrastructure ML model
    """
    print("="*60)
    print("🏗️ Training Infrastructure ML Model")
    print("="*60)
    
    # Step 1: Generate training data
    print("\n📊 Step 1: Generating training data...")
    generator = InfrastructureDataGenerator()
    df = generator.generate_training_data(n_samples=10000)
    
    # Step 2: Train model
    print("\n🤖 Step 2: Training ML model...")
    results = infrastructure_model.train(df)
    
    if results:
        print("\n✅ Training complete!")
        print(f"   Random Forest Accuracy: {results['random_forest_accuracy']:.2%}")
        print(f"   Logistic Regression Accuracy: {results['logistic_regression_accuracy']:.2%}")
        print(f"   Ensemble Accuracy: {results['ensemble_accuracy']:.2%}")
        print(f"\n📁 Model saved to: models_saved/infrastructure/")
    else:
        print("\n❌ Training failed!")

if __name__ == "__main__":
    train_infrastructure_model()
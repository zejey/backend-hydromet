"""
Analyze class distribution in your training data
"""
import pandas as pd
import numpy as np
from datetime import datetime
import sys
sys. path.insert(0, 'scripts')
from model import engineer_features, hazard_score

# Load data
df = pd.read_csv('scripts/export.csv')
df = engineer_features(df)
df["event"] = df.apply(hazard_score, axis=1)

print("=" * 70)
print("📊 DATA DISTRIBUTION ANALYSIS")
print("=" * 70)

# Overall distribution
total = len(df)
no_hazard = (df['event'] == 0).sum()
hazard = (df['event'] == 1).sum()

print(f"\n📈 Overall Class Distribution:")
print(f"   Total samples: {total:,}")
print(f"   Class 0 (No Hazard): {no_hazard:,} ({no_hazard/total*100:. 2f}%)")
print(f"   Class 1 (Hazard):    {hazard:,} ({hazard/total*100:.2f}%)")
print(f"   ⚖️  Imbalance Ratio: 1:{no_hazard/hazard:.1f}")

# Check if hazard rate is too low
if hazard/total < 0.03:
    print(f"\n🚨 CRITICAL: Only {hazard/total*100:.2f}% hazards!")
    print(f"   This is why CV fails - some folds have 0 hazards")
elif hazard/total < 0.05:
    print(f"\n⚠️  WARNING: Only {hazard/total*100:.2f}% hazards")
    print(f"   Consider lowering thresholds to get 5-10% hazard rate")
else:
    print(f"\n✅ Good: {hazard/total*100:.2f}% hazard rate")

# Handle different timestamp column names
timestamp_col = None
for col in ['ts', 'timestamp', 'date', 'datetime']:
    if col in df. columns:
        timestamp_col = col
        break

if timestamp_col:
    # Convert timestamp to datetime
    if timestamp_col == 'ts': 
        df['date'] = pd.to_datetime(df['ts'], unit='s', errors='coerce')
    else:
        df['date'] = pd.to_datetime(df[timestamp_col], errors='coerce')
    
    # Show date range
    if df['date'].notna().any():
        date_min = df['date'].min()
        date_max = df['date'].max()
        days = (date_max - date_min).days
        print(f"\n📅 Date Range:")
        print(f"   From: {date_min}")
        print(f"   To:    {date_max}")
        print(f"   Duration: {days} days")
        
        # Monthly distribution
        df['year_month'] = df['date'].dt.to_period('M')
        monthly_hazards = df. groupby('year_month')['event'].agg(['sum', 'count', 'mean'])
        
        print(f"\n📊 Hazard Distribution by Month:")
        print(monthly_hazards)
else:
    print(f"\n⚠️  No timestamp column found.  Available columns:")
    print(f"   {list(df.columns)}")

# Show which hazards are triggered
from model import hazard_score as hs
hazard_rows = df[df['event'] == 1]

if len(hazard_rows) > 0:
    all_hazards = []
    for _, row in hazard_rows.iterrows():
        _, hazards = hs(row. to_dict(), explain=True)
        all_hazards.extend(hazards)
    
    from collections import Counter
    hazard_counts = Counter(all_hazards)
    
    print(f"\n⚠️  Most Common Hazard Types:")
    for hazard, count in hazard_counts.most_common(10):
        print(f"   {hazard}: {count} times")
else:
    print(f"\n❌ NO HAZARDS DETECTED IN DATA!")
    print(f"   Your thresholds are too strict!")

# Show sample hazard events
if len(hazard_rows) > 0:
    print(f"\n📋 Sample Hazard Events (first 5):")
    sample_cols = ['date', 'temperature', 'precipitation', 'wind_speed', 'pressure']
    available_cols = [col for col in sample_cols if col in df.columns]
    if available_cols:
        print(hazard_rows[available_cols].head())
    else:
        # Show first 5 columns if standard ones not available
        print(hazard_rows. iloc[:, :5].head())

# Show basic statistics
print(f"\n📊 Weather Statistics:")
stats_cols = ['temperature', 'precipitation', 'wind_speed', 'pressure', 'humidity']
available_stats = [col for col in stats_cols if col in df.columns]
if available_stats:
    print(df[available_stats].describe())
else:
    print(f"⚠️  Standard columns not found.  Available columns:")
    print(f"   {list(df.columns)}")

print("=" * 70)

# Summary recommendations
print("\n💡 RECOMMENDATIONS:")
print("=" * 70)

if hazard/total < 0.05:
    print("1. ⚠️  Hazard rate is too low (4.07%)")
    print("   → Lower hazard thresholds in config. py")
    print("   → Target:  5-10% hazard rate")
    print()
    
if total < 1000:
    print("2. ⚠️  Small dataset (762 samples)")
    print("   → Collect more data if possible")
    print("   → Use stratified CV (not TimeSeriesSplit)")
    print()

print("3. ✅ Use these settings in model.py:")
print("   → StratifiedKFold instead of TimeSeriesSplit")
print("   → SMOTE with sampling_strategy=0.5")
print("   → scoring='balanced_accuracy' or 'roc_auc'")
print("=" * 70)
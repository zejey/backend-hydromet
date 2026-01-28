#!/bin/bash

# List of all your tables from the screenshot
tables=(
    "admin"
    "admin_invites"
    "auth_password_resets"
    "emergency_hotlines"
    "evacuation_centers"
    "government_agencies"
    "hazard_locations"
    "notifications"
    "otp_requests"
    "preventive_measures"
    "safety_categories"
    "users"
    "weather_observations"
)

echo "🚀 Exporting all tables from Railway..."
echo "================================================"

# Create exports directory
mkdir -p railway_exports
cd railway_exports

# Export each table
for table in "${tables[@]}"
do
    echo "📊 Exporting $table..."
    railway run psql -c "\copy $table TO STDOUT WITH CSV HEADER" > "${table}. csv"
    
    # Check if export was successful
    if [ -s "${table}.csv" ]; then
        rows=$(wc -l < "${table}.csv")
        echo "✅ $table:  $((rows - 1)) rows exported"
    else
        echo "⚠️  $table: No data or empty"
    fi
    echo "---"
done

echo "================================================"
echo "✅ All tables exported to ./railway_exports/"
echo "📁 Files created:"
ls -lh *.csv
"""
Hazard notification templates with SMS variants
"""

hazard_notification_templates = {
    "Tropical Cyclone": {
        "in_app": {
            "title": "Tropical Cyclone Alert",
            "message": "A tropical cyclone has been detected. Please secure your property and follow official instructions."
        },
        "sms": "TYPHOON ALERT: Tropical cyclone detected. Secure property and follow official instructions."
    },
    "Tropical Storm": {
        "in_app": {
            "title": "Tropical Storm Warning",
            "message": "A tropical storm is likely in your area. Expect strong winds and heavy rain. Stay safe indoors."
        },
        "sms": "STORM WARNING: Strong winds & heavy rain expected. Stay indoors."
    },
    "Flood Risk": {
        "in_app": {
            "title": "Flood Risk Warning",
            "message": "Heavy rain detected. Flooding may occur in low-lying areas. Stay alert and prepare to evacuate if necessary."
        },
        "sms": "FLOOD ALERT: Heavy rain detected. Prepare for possible flooding in low areas."
    },
    "Windstorm": {
        "in_app": {
            "title": "Strong Winds Detected",
            "message": "Very strong winds are expected. Secure loose objects and avoid unnecessary travel."
        },
        "sms": "STRONG WINDS: Secure objects & avoid travel. Stay safe."
    },
    "Heatwave": {
        "in_app": {
            "title": "Heatwave Alert",
            "message": "High temperatures detected. Stay hydrated, avoid direct sunlight, and check on vulnerable individuals."
        },
        "sms": "HEATWAVE: High temp alert. Stay hydrated & avoid sun."
    },
    "Possible Cyclone": {
        "in_app": {
            "title": "Cyclone Risk",
            "message": "Very low pressure detected. Cyclone may develop. Stay tuned for updates."
        },
        "sms": "CYCLONE RISK: Low pressure. Monitor for updates."
    },
    "Low Pressure": {
        "in_app": {
            "title": "Low Pressure Advisory",
            "message": "A low pressure system is present. Weather may change rapidly."
        },
        "sms": "LOW PRESSURE: Weather may change. Stay alert."
    },
    "General Hazard": {
        "in_app": {
            "title": "Weather Hazard Detected",
            "message": "Unusual hazardous weather conditions detected. Please monitor updates."
        },
        "sms": "WEATHER ALERT: Hazardous conditions detected. Monitor updates."
    }
}
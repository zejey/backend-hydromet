def determine_hazard_type(hazards):
    if "very low pressure" in hazards and "very strong wind" in hazards and "heavy rain" in hazards:
        return "Tropical Cyclone"
    elif "very strong wind" in hazards and "heavy rain" in hazards:
        return "Tropical Storm"
    elif "heavy rain" in hazards:
        return "Flood Risk"
    elif "very strong wind" in hazards:
        return "Windstorm"
    elif "extreme heat" in hazards or "very hot" in hazards or "hot" in hazards:
        return "Heatwave"
    elif "very low pressure" in hazards:
        return "Possible Cyclone"
    elif "low pressure" in hazards:
        return "Low Pressure"
    else:
        return "None"
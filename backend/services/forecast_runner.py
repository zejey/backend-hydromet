def run_forecast(force_hazard=None):
    if force_hazard is not None and not isinstance(force_hazard, bool):
        raise ValueError("force_hazard must be a boolean.")
    # Existing code for running forecast...

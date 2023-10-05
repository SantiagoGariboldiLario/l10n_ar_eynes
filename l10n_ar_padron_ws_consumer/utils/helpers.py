from datetime import date


def get_current_period():
    return date.today().replace(day=1)

"""Verified venue metadata supplement for the app's weather feed."""
import re
from simmah_weather import venue_location as base_venue_location

# ESPN venue 3712; coordinates corroborated by UNF's stadium collection:
# https://digitalcommons.unf.edu/historical_architecture_main/61/
EVERBANK = (30.3239, -81.6375, False)
VENUES = {'3712': EVERBANK}
NAMES = {'everbankstadium': EVERBANK, 'everbankfield': EVERBANK,
         'tiaabankfield': EVERBANK}


def venue_location(venue):
    """Resolve the actual scheduled venue, never a team's nominal home city."""
    existing = base_venue_location(venue)
    if existing is not None:
        return existing
    if str(venue.get('id', '')) in VENUES:
        return VENUES[str(venue['id'])]
    name = re.sub(r'[^a-z0-9]', '', str(venue.get('fullName', '')).casefold())
    return NAMES.get(name)

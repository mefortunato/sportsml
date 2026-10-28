"""Kickoff weather: ``temp`` (F) and ``wind`` (mph).

nflverse's schedule carries both for most played outdoor games (from Pro
Football Reference), but none for upcoming games and only part of some
recent seasons. Those gaps are filled from Open-Meteo (no key needed) at the
stadium's coordinates and the kickoff hour: its historical reanalysis for
past games, its forecast for games in the next two weeks. Indoor games get
no wind and a room temperature, so the features say "no weather" rather
than "unknown".

Retractable roofs are decided close to kickoff, so upcoming games often have
no ``roof``; they take the stadium's most common earlier roof.
"""

from __future__ import annotations

import datetime
import logging

import pandas as pd

logger = logging.getLogger(__name__)

WEATHER_COLUMNS = ["temp", "wind"]
INDOOR = {"dome", "closed"}
INDOOR_TEMP = 70.0

# (latitude, longitude) of stadiums that host outdoor or retractable-roof
# games, by nflverse stadium_id; others are always indoor or long gone.
STADIUMS = {
    "ATL97": (33.755, -84.401),
    "BAL00": (39.278, -76.623),
    "BOS00": (42.091, -71.264),
    "BUF00": (42.774, -78.787),
    "CAR00": (35.226, -80.853),
    "CHI98": (41.862, -87.617),
    "CIN00": (39.095, -84.516),
    "CLE00": (41.506, -81.700),
    "DAL00": (32.748, -97.093),
    "DEN00": (39.744, -105.020),
    "FRA00": (50.069, 8.645),
    "GER00": (48.219, 11.625),
    "GNB00": (44.501, -88.062),
    "HOU00": (29.685, -95.411),
    "IND00": (39.760, -86.164),
    "JAX00": (30.324, -81.637),
    "KAN00": (39.049, -94.484),
    "LON00": (51.556, -0.280),
    "LON02": (51.604, -0.066),
    "MAD01": (40.453, -3.688),
    "MEX00": (19.303, -99.150),
    "MIA00": (25.958, -80.239),
    "NAS00": (36.166, -86.771),
    "NYC01": (40.814, -74.074),
    "PHI00": (39.901, -75.168),
    "PHO00": (33.528, -112.263),
    "PIT00": (40.447, -80.016),
    "RIO00": (-22.912, -43.230),
    "SAO00": (-23.545, -46.474),
    "SEA00": (47.595, -122.332),
    "SFO01": (37.403, -121.970),
    "TAM00": (27.976, -82.503),
    "WAS00": (38.908, -76.864),
}

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
# the archive trails real time by a few days; the forecast reaches 16 days
ARCHIVE_LAG_DAYS = 7
FORECAST_DAYS = 15
RETRIES = 3
# consecutive failed requests after which the rest are skipped
MAX_FAILURES = 3


def open_meteo(url: str, lat: float, lon: float, start: str, end: str) -> pd.Series:
    """Hourly ``(temp, wind)`` at a point, indexed by US Eastern hour.

    Rate-limited (429) and dropped requests are retried after 10, 20 and
    40 seconds.
    """
    import time

    import httpx

    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start,
        "end_date": end,
        "hourly": "temperature_2m,wind_speed_10m",
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "timezone": "America/New_York",
    }
    for attempt in range(RETRIES + 1):
        try:
            resp = httpx.get(url, params=params, timeout=20)
        except httpx.TransportError:
            if attempt == RETRIES:
                raise
        else:
            if resp.status_code != 429 or attempt == RETRIES:
                break
        time.sleep(10 * 2**attempt)
    resp.raise_for_status()
    hourly = resp.json()["hourly"]
    return pd.DataFrame(
        {"temp": hourly["temperature_2m"], "wind": hourly["wind_speed_10m"]},
        index=pd.to_datetime(hourly["time"]),
    )


def kickoff_hour(schedule: pd.DataFrame) -> pd.Series:
    """Kickoff rounded to the hour (US Eastern, as nflverse lists it)."""
    time = schedule["gametime"].fillna("13:00")
    return pd.to_datetime(schedule["gameday"] + " " + time).dt.round("h")


def fill_roof(schedule: pd.DataFrame) -> pd.Series:
    """``roof``, with missing values set to the stadium's most common one."""
    known = schedule.dropna(subset=["roof", "stadium_id"])
    usual = known.groupby("stadium_id")["roof"].agg(lambda r: r.mode().iloc[0])
    return schedule["roof"].fillna(schedule["stadium_id"].map(usual))


def weather_features(
    schedule: pd.DataFrame,
    today: datetime.date | None = None,
    fetch=open_meteo,
) -> pd.DataFrame:
    """The schedule with ``roof`` filled and ``temp`` / ``wind`` for every
    game whose weather is known or forecast.

    Args:
        schedule: nflverse schedule (one row per game).
        today: Splits past games (archive) from upcoming ones (forecast).
        fetch: ``fetch(url, lat, lon, start, end)`` -> hourly frame, as
            :func:`open_meteo`.
    """
    today = today or datetime.date.today()
    schedule = schedule.copy()
    schedule["roof"] = fill_roof(schedule)
    indoor = schedule["roof"].isin(INDOOR)
    schedule.loc[indoor, "temp"] = INDOOR_TEMP
    schedule.loc[indoor, "wind"] = 0.0

    kickoff = kickoff_hour(schedule)
    days = (kickoff.dt.date - today).map(lambda d: d.days)
    missing = (
        schedule[WEATHER_COLUMNS].isna().any(axis=1)
        & schedule["stadium_id"].isin(STADIUMS)
        & (days <= FORECAST_DAYS)
    )
    archive = days < -ARCHIVE_LAG_DAYS
    # one request per stadium and season
    groups = [schedule["stadium_id"], schedule["season"], archive]
    failures = 0
    for (stadium, _, use_archive), rows in schedule[missing].groupby(
        [g[missing] for g in groups]
    ):
        if failures >= MAX_FAILURES:
            logger.warning("Open-Meteo unreachable; leaving weather gaps")
            break
        hours = kickoff[rows.index]
        url = ARCHIVE_URL if use_archive else FORECAST_URL
        start, end = (h.date().isoformat() for h in (hours.min(), hours.max()))
        try:
            hourly = fetch(url, *STADIUMS[stadium], start, end)
        except Exception as error:  # weather is optional; keep the rest
            logger.warning("no weather for %s %s-%s: %s", stadium, start, end, error)
            failures += 1
            continue
        failures = 0
        values = hourly.reindex(hours.to_numpy())
        for col in WEATHER_COLUMNS:
            filled = rows[col].fillna(pd.Series(values[col].to_numpy(), rows.index))
            schedule.loc[rows.index, col] = filled
    return schedule

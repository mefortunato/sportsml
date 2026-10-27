"""Responses shaped like CollegeFootballData's v2 API (camelCase)."""


def game(gid, week, home, away, hp, ap, start, season=2024, season_type="regular",
         neutral=False, conf=False, notes=None, completed=True,
         home_class="fbs", away_class="fbs"):  # fmt: skip
    return {
        "id": gid,
        "season": season,
        "week": week,
        "seasonType": season_type,
        "startDate": start,
        "startTimeTBD": False,
        "completed": completed,
        "neutralSite": neutral,
        "conferenceGame": conf,
        "venue": "Stadium",
        "homeId": 1,
        "homeTeam": home,
        "homeClassification": home_class,
        "homeConference": "SEC" if home_class == "fbs" else "Big Sky",
        "homePoints": hp if completed else None,
        "awayId": 2,
        "awayTeam": away,
        "awayClassification": away_class,
        "awayConference": "SEC" if away_class == "fbs" else "Big Sky",
        "awayPoints": ap if completed else None,
        "notes": notes,
    }


SCHEDULE = [
    game(1, 1, "Alabama", "Montana State", 49, 7, "2024-08-31T23:00:00.000Z",
         away_class="fcs"),
    game(2, 1, "Georgia", "Clemson", 34, 3, "2024-08-31T19:30:00.000Z", neutral=True),
    game(3, 1, "Montana", "Montana State", 20, 24, "2024-08-31T20:00:00.000Z",
         home_class="fcs", away_class="fcs"),
    game(4, 2, "Alabama", "Georgia", 41, 34, "2024-09-07T23:30:00.000Z", conf=True),
    # cancelled: never completed, in the past
    game(5, 2, "Clemson", "Auburn", None, None, "2024-09-07T16:00:00.000Z",
         completed=False),
    game(6, 3, "Clemson", "Georgia", 17, 24, "2024-09-21T16:00:00.000Z"),
    game(7, 1, "Georgia", "Alabama", 10, 28, "2024-12-20T01:00:00.000Z",
         season_type="postseason", neutral=True, notes="CFP First Round Game"),
    game(8, 1, "Clemson", "Auburn", 31, 30, "2024-12-28T20:00:00.000Z",
         season_type="postseason", neutral=True, notes="Gator Bowl"),
    game(9, 1, "Alabama", "Ohio State", 20, 27, "2025-01-10T00:30:00.000Z",
         season_type="postseason", neutral=True,
         notes="CFP Semifinal at the Cotton Bowl Classic"),
    game(10, 1, "Notre Dame", "Ohio State", 23, 34, "2025-01-21T00:30:00.000Z",
         season_type="postseason", neutral=True,
         notes="College Football Playoff National Championship"),
    # scheduled, not played yet
    game(11, 1, "Georgia", "Auburn", None, None, "2099-12-31T20:00:00.000Z",
         season_type="postseason", neutral=True, completed=False,
         notes="Sugar Bowl"),
]  # fmt: skip


def box_team(name, home_away, points, yards, third="5-12"):
    stats = {
        "totalYards": str(yards),
        "rushingTDs": "2",
        "thirdDownEff": third,
        "fourthDownEff": "1-2",
        "completionAttempts": "20-31",
        "totalPenaltiesYards": "5-45",
        "possessionTime": "31:30",
        "sacks": "3",
    }
    return {
        "teamId": 1,
        "team": name,
        "conference": "SEC",
        "homeAway": home_away,
        "points": points,
        "stats": [{"category": k, "stat": v} for k, v in stats.items()],
    }


BOX = [
    {"id": 1, "teams": [box_team("Alabama", "home", 49, 550),
                        box_team("Montana State", "away", 7, 210, "3-14")]},
    {"id": 2, "teams": [box_team("Georgia", "home", 34, 450),
                        box_team("Clemson", "away", 3, 240)]},
    {"id": 4, "teams": [box_team("Alabama", "home", 41, 500),
                        box_team("Georgia", "away", 34, 480)]},
]  # fmt: skip


def line(provider, spread=None, total=None, home_ml=None, away_ml=None):
    return {
        "provider": provider,
        "spread": spread,
        "formattedSpread": "",
        "spreadOpen": None,
        "overUnder": total,
        "overUnderOpen": None,
        "homeMoneyline": home_ml,
        "awayMoneyline": away_ml,
    }


LINES = [
    # home favored by 38.5; the preferred book has no moneyline
    {"id": 1, "lines": [line("Bovada", -38.5, 55.5, -50000, 0),
                        line("teamrankings", -37.0, 54.0)]},
    {"id": 2, "lines": [line("numberfire", -10.0, 47.0),
                        line("DraftKings", -13.5, 48.5, -500, 375)]},
    {"id": 4, "lines": [line("ESPN Bet", 1.5, 50.5, 105, -125)]},
    {"id": 11, "lines": [line("DraftKings", -3.0, 52.5, -150, 130)]},
]  # fmt: skip

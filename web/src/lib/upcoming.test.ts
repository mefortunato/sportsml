import { describe, expect, it } from "vitest";
import {
  currentUpcoming,
  isPast,
  sortGames,
  sortOptions,
  todayEastern,
} from "./upcoming";
import type { Prediction, Upcoming, UpcomingGame } from "./types";

const team = (key: string) => ({ team: key, name: key });
const game = (id: string, prediction: Partial<Prediction>): UpcomingGame => ({
  game_id: id,
  season: 2026,
  date: 9,
  kickoff: null,
  home: team("H"),
  away: team("A"),
  neutral: false,
  spread: null,
  moneyline: null,
  total_line: null,
  total_odds: null,
  prediction: {
    margin: 0,
    win_prob: 0.5,
    edge: null,
    ats_pick: null,
    ...prediction,
  },
});

const games = [
  game("a", { edge: 1.5, ml_edge: 0.02 }),
  game("b", { edge: -4, total_edge: 2 }),
  game("c", { edge: null }),
  game("d", { edge: 4, ml_edge: -0.08 }),
];

describe("upcoming sort", () => {
  it("puts the biggest edge first either way, unlined games last", () => {
    expect(sortGames(games, "spread").map((g) => g.game_id)).toEqual([
      "b",
      "d",
      "a",
      "c",
    ]);
    expect(sortGames(games, "moneyline").map((g) => g.game_id)).toEqual([
      "d",
      "a",
      "b",
      "c",
    ]);
    expect(sortGames(games, "total").map((g) => g.game_id)).toEqual([
      "b",
      "a",
      "c",
      "d",
    ]);
  });

  it("keeps kickoff order and does not reorder the input", () => {
    expect(sortGames(games, "kickoff")).toBe(games);
    sortGames(games, "spread");
    expect(games.map((g) => g.game_id)).toEqual(["a", "b", "c", "d"]);
  });

  it("offers only markets some game has an edge on", () => {
    expect(sortOptions(games)).toEqual([
      "kickoff",
      "spread",
      "moneyline",
      "total",
    ]);
    expect(sortOptions([games[2]])).toEqual(["kickoff"]);
  });
});

describe("current upcoming", () => {
  const at = (id: string, date: number, kickoff: string | null) => ({
    ...game(id, {}),
    date,
    kickoff,
  });
  const week = (date: number, games: UpcomingGame[]): Upcoming => ({
    season: 2026,
    date,
    dates: [8, 9, 10],
    games,
  });
  const w8 = week(8, [
    at("a", 8, "2026-11-01 13:00"),
    at("b", 8, "2026-11-01 20:15"),
  ]);
  const w9 = week(9, [
    at("c", 9, "2026-11-01 19:00"),
    at("d", 9, "2026-11-02 19:00"),
  ]);
  const w10 = week(10, [at("e", 10, null)]);
  const file = {
    default: w8,
    by_date: { "2026-8": w8, "2026-9": w9, "2026-10": w10 },
  };
  const today = "2026-11-02";

  it("reads today in US Eastern", () => {
    // 02:00 UTC on the 3rd is still the evening of the 2nd in New York
    expect(todayEastern(new Date("2026-11-03T02:00:00Z"))).toBe("2026-11-02");
    expect(isPast(at("x", 1, "2026-11-01 23:59"), today)).toBe(true);
    expect(isPast(at("x", 1, "2026-11-02 00:01"), today)).toBe(false);
    expect(isPast(at("x", 1, null), today)).toBe(false);
  });

  it("skips past games and dates with nothing left by default", () => {
    const now = currentUpcoming(file, null, null, today);
    expect(now.date).toBe(9);
    expect(now.dates).toEqual([9, 10]);
    expect(now.games.map((g) => g.game_id)).toEqual(["d"]);
  });

  it("empties an asked-for date that has passed", () => {
    const old = currentUpcoming(file, 2026, 8, today);
    expect(old.date).toBe(8);
    expect(old.games).toEqual([]);
    expect(() => currentUpcoming(file, 2026, 99, today)).toThrow();
  });

  it("shows nothing once every game has passed", () => {
    const done = currentUpcoming(file, null, null, "2026-12-01");
    expect(done.dates).toEqual([10]);
    expect(done.games.map((g) => g.game_id)).toEqual(["e"]);
    const allTimed = { default: w8, by_date: { "2026-8": w8, "2026-9": w9 } };
    expect(currentUpcoming(allTimed, null, null, "2026-12-01").games).toEqual(
      [],
    );
  });
});

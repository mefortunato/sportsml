import { describe, expect, it } from "vitest";
import { sortGames, sortOptions } from "./upcoming";
import type { Prediction, UpcomingGame } from "./types";

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

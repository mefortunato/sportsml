// Shapes returned by the FastAPI backend (src/sportsml/web/api.py).

export type Side = 'home' | 'away';

export interface Team {
	team: string;
	name: string;
	nickname?: string;
	color?: string;
	color2?: string;
	logo?: string;
	conference?: string;
	division?: string;
}

export interface Metrics {
	n: number;
	rmse: number;
	mae: number;
	accuracy: number;
	brier?: number;
	log_loss?: number;
}

export interface SportInfo {
	sport: string;
	label: string;
	date_label: string;
	has_spread: boolean;
	challenge_games: number;
	built_at?: string | null;
	refreshed_at?: string | null;
	model?: { family: string; metrics: Record<string, Metrics> } | null;
	backtest?: {
		seasons: number[];
		overall: { model: Metrics; market?: Metrics };
		ats?: { win_pct?: number; bets?: number };
	} | null;
}

export interface Prediction {
	/** Home team's predicted margin. */
	margin: number;
	/** P(home team wins). */
	win_prob: number;
	/** Model margin minus the spread (home perspective). */
	edge: number | null;
	ats_pick: Side | null;
}

export interface GameHeader {
	game_id: string;
	season: number;
	date: number;
	kickoff: string | null;
	home: Team;
	away: Team;
	neutral: boolean;
	/** Market's expected home margin: positive means the home team is favored. */
	spread: number | null;
}

export interface UpcomingGame extends GameHeader {
	prediction: Prediction;
}

export interface Upcoming {
	season: number | null;
	date: number | null;
	dates: number[];
	games: UpcomingGame[];
}

export interface WinLoss {
	wins: number;
	losses: number;
	ties: number;
}

export interface AtsRecord {
	wins: number;
	losses: number;
	pushes: number;
}

export interface RecentGame {
	game_id: string;
	season: number;
	date: number;
	opp: Team;
	location: number | null;
	score: number | null;
	opp_score: number | null;
	margin: number;
	spread: number | null;
	ats: 'W' | 'L' | 'P' | null;
}

export interface TeamSummary {
	team: Team;
	/** Season the averages and records cover (last season before an opener). */
	season: number;
	current_season: boolean;
	games: number;
	record: WinLoss;
	ats: AtsRecord;
	averages: Record<string, number | null>;
	recent: RecentGame[];
}

export interface StatDef {
	key: string;
	label: string;
	decimals: number;
	higher_is_better: boolean;
}

export interface GameResult {
	home_score: number | null;
	away_score: number | null;
	margin: number;
	covered: Side | 'push' | null;
}

export interface Matchup extends GameHeader {
	summaries: { home: TeamSummary; away: TeamSummary };
	stats: StatDef[];
}

export interface GameDetail extends Matchup {
	prediction: Prediction | null;
	result: GameResult | null;
}

export interface ChallengeGame extends Matchup {
	pool_size: number;
}

export interface ChallengeAnswer {
	game_id: string;
	pick: Side;
	covered: Side | 'push' | null;
	correct: boolean;
	spread: number;
	result: GameResult;
	model: Prediction & { correct: boolean };
}

/** Model and (when the sport has lines) market metrics on the same games. */
export interface SourceMetrics {
	model: Metrics;
	market?: Metrics;
}

/** Betting the model's side vs the spread when it disagrees by > min_edge. */
export interface AtsRow {
	min_edge: number;
	bets: number;
	wins: number;
	losses: number;
	pushes: number;
	win_pct: number | null;
	ci95_low: number | null;
	ci95_high: number | null;
	roi: number;
}

export interface CalibrationBin {
	predicted: number;
	actual: number;
	n: number;
}

/** Walk-forward backtest results (the same predictions as the challenge). */
export interface Performance {
	seasons: number[];
	overall: SourceMetrics;
	by_season: Record<string, SourceMetrics>;
	by_phase: Record<string, SourceMetrics>;
	ats?: AtsRow[];
	ats_by_season?: Record<string, AtsRow>;
	edge_correlation?: { r: number; ci95_low: number; ci95_high: number };
	calibration: { model: CalibrationBin[]; market?: CalibrationBin[] };
}

export interface RankingSeries {
	team: Team;
	/** Average predicted margin vs every other team, before each date. */
	ratings: (number | null)[];
}

export interface RankingSeason {
	season: number;
	/** backtest: that season's walk-forward model; current: the served model. */
	source: 'backtest' | 'current';
	dates: number[];
	teams: RankingSeries[];
}

export interface Rankings {
	seasons: RankingSeason[];
	date_label: string;
}

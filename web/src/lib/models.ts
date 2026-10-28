// How each model family the site can serve is described to readers. The
// family comes from `sports.json` (`model.family`, set by `sportsml web build
// --family`), so serving another model needs only an entry here.

export interface ModelInfo {
	/** Short name, e.g. for the header badge. */
	name: string;
	/** The home page's headline: "<headline> predictions, scored against Vegas". */
	headline: string;
	/** Completes "<Sport> predictions from ...". */
	source: string;
	/** "How the predictions are made" paragraphs. */
	how: string[];
	/** How often the predictions change. */
	refresh: string;
}

const MODELS: Record<string, ModelInfo> = {
	calibrated_elo: {
		name: 'Elo',
		headline: 'Calibrated Elo',
		source: 'calibrated Elo ratings',
		how: [
			'Every team has an Elo rating. After each game the winner takes rating points from the loser: more for a bigger margin, fewer when the favorite wins as expected. Between seasons every rating moves part of the way back to average.',
			"Each sport's settings (how far one game moves a rating, the home edge, how much ratings fall back between seasons) are tuned on past seasons, and the rating gap is converted to points by fitting it to past margins. The win probability comes from that margin, calibrated on the most recent past season."
		],
		refresh: 'Ratings update with every result; the settings are re-tuned monthly during the season.'
	},
	elo: {
		name: 'Elo',
		headline: 'Elo',
		source: 'Elo ratings',
		how: [
			"Every team has an Elo rating, with FiveThirtyEight's settings: after each game the winner takes rating points from the loser, more for a bigger margin. The win probability comes from the rating gap, calibrated on past seasons."
		],
		refresh: 'Ratings update with every result.'
	},
	transformer: {
		name: 'Transformer',
		headline: 'Neural network',
		source: "a transformer over each team's recent games",
		how: [
			"A transformer, the kind of neural network behind language models, reads each team's most recent games: its box-score stats, results and home field, and in college football how strong each opponent was. From the two teams' histories it predicts the margin and the total points. The win probability comes from the margin, calibrated on past seasons."
		],
		refresh: 'The model is retrained monthly during the season.'
	}
};

export function modelInfo(family: string | null | undefined): ModelInfo {
	return (
		MODELS[family ?? ''] ?? {
			name: 'Model',
			headline: 'Game',
			source: 'a model fit on past seasons',
			how: ['The model predicts the margin from past results; the win probability comes from the margin, calibrated on past seasons.'],
			refresh: 'Results refresh daily.'
		}
	);
}

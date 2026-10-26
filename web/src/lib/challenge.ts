import { writable, type Readable } from 'svelte/store';
import type { ChallengeAnswer } from './types';

/** The player's and the model's against-the-spread record on the same games. */
export interface ChallengeRecord {
	played: number;
	player: { wins: number; losses: number };
	model: { wins: number; losses: number };
	/** Games where the player picked the same side as the model. */
	agreed: number;
	streak: number;
	bestStreak: number;
	/** Recently played game ids, so they are not served again soon. */
	seen: string[];
}

const SEEN_LIMIT = 300;

export function emptyRecord(): ChallengeRecord {
	return {
		played: 0,
		player: { wins: 0, losses: 0 },
		model: { wins: 0, losses: 0 },
		agreed: 0,
		streak: 0,
		bestStreak: 0,
		seen: []
	};
}

/** The record after one answered game (pure). */
export function applyAnswer(record: ChallengeRecord, answer: ChallengeAnswer): ChallengeRecord {
	const streak = answer.correct ? record.streak + 1 : 0;
	return {
		played: record.played + 1,
		player: {
			wins: record.player.wins + (answer.correct ? 1 : 0),
			losses: record.player.losses + (answer.correct ? 0 : 1)
		},
		model: {
			wins: record.model.wins + (answer.model.correct ? 1 : 0),
			losses: record.model.losses + (answer.model.correct ? 0 : 1)
		},
		agreed: record.agreed + (answer.pick === answer.model.ats_pick ? 1 : 0),
		streak,
		bestStreak: Math.max(record.bestStreak, streak),
		seen: [...record.seen.filter((id) => id !== answer.game_id), answer.game_id].slice(
			-SEEN_LIMIT
		)
	};
}

type Storage = Pick<globalThis.Storage, 'getItem' | 'setItem' | 'removeItem'>;

function key(sport: string) {
	return `sportsml:challenge:${sport}`;
}

function browserStorage(): Storage | null {
	try {
		return globalThis.localStorage ?? null;
	} catch {
		return null;
	}
}

export function loadRecord(sport: string, storage: Storage | null = browserStorage()) {
	try {
		const saved = storage?.getItem(key(sport));
		return saved ? { ...emptyRecord(), ...JSON.parse(saved) } : emptyRecord();
	} catch {
		return emptyRecord();
	}
}

export function saveRecord(
	sport: string,
	record: ChallengeRecord,
	storage: Storage | null = browserStorage()
) {
	try {
		storage?.setItem(key(sport), JSON.stringify(record));
	} catch {
		// storage full or blocked: the record still lives for this visit
	}
}

export interface ChallengeStore extends Readable<ChallengeRecord> {
	record(answer: ChallengeAnswer): void;
	reset(): void;
}

/** A store of the sport's record, persisted to localStorage on every change. */
export function challengeStore(
	sport: string,
	storage: Storage | null = browserStorage()
): ChallengeStore {
	const store = writable(loadRecord(sport, storage));
	const update = (next: ChallengeRecord) => {
		saveRecord(sport, next, storage);
		store.set(next);
	};
	let current = loadRecord(sport, storage);
	store.subscribe((value) => (current = value));
	return {
		subscribe: store.subscribe,
		record: (answer) => update(applyAnswer(current, answer)),
		reset: () => update(emptyRecord())
	};
}

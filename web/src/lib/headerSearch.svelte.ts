import { untrack } from 'svelte';
import type { Team } from './types';

/** What the page on show does with a team picked in the header search. */
export interface TeamTarget {
	sport: string;
	/** What picking does, shown beside the team ("Highlight"). */
	verb: string;
	pick: (team: Team) => void;
}

// The header search and the page under it. A page that can show a team
// registers with `onTeamPick`; a team picked for another sport or page is
// left in `pending` for the page the search then goes to.
export const teamSearch = $state<{
	target: TeamTarget | null;
	pending: { sport: string; team: Team } | null;
}>({ target: null, pending: null });

/** Let the header search hand this page its sport's teams while the calling
 * component is mounted, including one picked on the way here. Call it
 * during component init, after the state `pick` changes is set up. */
export function onTeamPick(sport: () => string, verb: string, pick: (team: Team) => void) {
	$effect(() => {
		const target = { sport: sport(), verb, pick };
		teamSearch.target = target;
		const pending = teamSearch.pending;
		if (pending?.sport === target.sport) {
			teamSearch.pending = null;
			untrack(() => pick(pending.team));
		}
		return () => {
			if (teamSearch.target?.pick === pick) teamSearch.target = null;
		};
	});
}

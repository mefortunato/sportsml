import type { Team } from './types';

/** How the page under the header wants its team search to behave. */
export interface SearchConfig {
	/** Teams to suggest; with `onpick`, picking one calls it. */
	teams?: Team[];
	onpick?: (team: Team) => void;
	picked?: (team: string) => boolean;
	placeholder?: string;
}

// The header's search box, shared with the page it searches. Pages that
// search call `useHeaderSearch` and read `headerSearch.query`; on any other
// page the box is hidden.
export const headerSearch = $state<{ query: string; config: SearchConfig | null }>({
	query: '',
	config: null
});

/** Show the header search for this page, configured by `config()`, while the
 * calling component is mounted. Call it during component init. */
export function useHeaderSearch(config: () => SearchConfig = () => ({})) {
	$effect(() => {
		headerSearch.config = config();
	});
	$effect(() => {
		// each page starts with an empty box
		headerSearch.query = '';
		return () => {
			headerSearch.config = null;
			headerSearch.query = '';
		};
	});
}

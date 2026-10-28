<script lang="ts">
	import type { Matchup } from '$lib/types';
	import RecentGames from './RecentGames.svelte';
	import StatComparison from './StatComparison.svelte';

	/** Pre-game team stats, records and recent form (shared by game and challenge). */
	let {
		matchup,
		dateLabel = 'Week',
		splitSeason = false
	}: { matchup: Matchup; dateLabel?: string; splitSeason?: boolean } = $props();
</script>

<div class="section card">
	<h2>Team stats</h2>
	<StatComparison
		stats={matchup.stats}
		away={matchup.summaries.away}
		home={matchup.summaries.home}
		{dateLabel}
		{splitSeason}
	/>
</div>

<div class="section">
	<h2>Recent form</h2>
	<div class="grid-2">
		<div class="card"><RecentGames summary={matchup.summaries.away} {dateLabel} /></div>
		<div class="card"><RecentGames summary={matchup.summaries.home} {dateLabel} /></div>
	</div>
</div>

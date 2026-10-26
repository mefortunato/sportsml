<script lang="ts">
	import { kickoffLabel, signed, spreadLabel } from '$lib/format';
	import type { UpcomingGame } from '$lib/types';
	import SpreadChart from './SpreadChart.svelte';
	import TeamBadge from './TeamBadge.svelte';
	import WinProbBar from './WinProbBar.svelte';

	let { game, sport }: { game: UpcomingGame; sport: string } = $props();

	const prediction = $derived(game.prediction);
	const pick = $derived(
		prediction.ats_pick === null ? null : prediction.ats_pick === 'home' ? game.home : game.away
	);
	// edge toward the picked side, always positive
	const edge = $derived(prediction.edge === null ? null : Math.abs(prediction.edge));
</script>

<a class="card game" href="/{sport}/games/{encodeURIComponent(game.game_id)}">
	<div class="top">
		<div class="teams">
			<TeamBadge team={game.away} label="name" />
			<span class="muted at">{game.neutral ? 'vs' : '@'}</span>
			<TeamBadge team={game.home} label="name" />
		</div>
		<span class="muted small">{kickoffLabel(game.kickoff)}</span>
	</div>

	<SpreadChart
		home={game.home}
		away={game.away}
		spread={game.spread}
		model={prediction.margin}
	/>

	<WinProbBar home={game.home} away={game.away} probability={prediction.win_prob} />

	<div class="bottom small">
		<span class="pill">Vegas {spreadLabel(game.home, game.away, game.spread)}</span>
		{#if pick && edge !== null}
			<span class="pill accent">Model: {pick.team} covers · edge {signed(edge)}</span>
		{:else}
			<span class="pill">No line yet</span>
		{/if}
	</div>
</a>

<style>
	.game {
		display: flex;
		flex-direction: column;
		gap: 12px;
		color: inherit;
		transition: border-color 0.15s;
	}
	.game:hover {
		text-decoration: none;
		border-color: var(--accent);
	}
	.top {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 8px;
		flex-wrap: wrap;
	}
	.teams {
		display: flex;
		align-items: center;
		gap: 8px;
		min-width: 0;
	}
	.at {
		font-weight: 600;
	}
	.bottom {
		display: flex;
		gap: 8px;
		flex-wrap: wrap;
	}
</style>

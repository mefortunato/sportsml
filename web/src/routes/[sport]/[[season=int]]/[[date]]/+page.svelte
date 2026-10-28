<script lang="ts">
	import { dateText, seasonText } from '$lib/format';
	import { links } from '$lib/links';
	import GameCard from '$lib/components/GameCard.svelte';
	import { gameOdds } from '$lib/odds';
	import { SORT_LABELS, sortGames, sortOptions, type GameSort } from '$lib/upcoming';

	let { data } = $props();
	const info = $derived(data.info);
	const upcoming = $derived(data.upcoming);

	const SORT_KEY = 'sportsml:upcoming-sort';
	function savedSort(): GameSort {
		try {
			return (globalThis.localStorage?.getItem(SORT_KEY) as GameSort | null) ?? 'kickoff';
		} catch {
			return 'kickoff';
		}
	}

	let sort = $state<GameSort>(savedSort());
	const options = $derived(sortOptions(upcoming.games));
	// a remembered market this week's games have no lines for falls back to kickoff
	const active = $derived(options.includes(sort) ? sort : 'kickoff');
	const games = $derived(sortGames(upcoming.games, active));

	function choose(next: GameSort) {
		sort = next;
		try {
			globalThis.localStorage?.setItem(SORT_KEY, next);
		} catch {
			// remembering the order is only a convenience
		}
	}
</script>

<div class="container section">
	<div class="heading">
		<div>
			<h1>
				{info.label} ·
				{dateText(info.date_label, upcoming.date, upcoming.date_names?.[String(upcoming.date)])}
				{#if upcoming.season}<span class="muted">{seasonText(upcoming.season, info.split_season)}</span>{/if}
			</h1>
			<p class="muted small legend">
				<span class="key vegas"></span> Vegas line
				<span class="key model"></span> model's predicted margin
				<span class="key edge"></span> where they disagree · right of center favors the home team
			</p>
		</div>
		{#if upcoming.dates.length > 1}
			<nav class="dates">
				{#each upcoming.dates as date (date)}
					<a
						class="pill"
						class:accent={date === upcoming.date}
						href={links.upcoming(info.sport, upcoming.season, date)}>{dateText(info.date_label, date, upcoming.date_names?.[String(date)])}</a
					>
				{/each}
			</nav>
		{/if}
	</div>

	{#if upcoming.games.length === 0}
		<div class="card">
			<h2>No upcoming games</h2>
			<p class="muted">
				The schedule has no unplayed games right now. Try
				<a href={links.challenge(info.sport)}>beating the model on past games</a>.
			</p>
		</div>
	{:else}
		{#if options.length > 1}
			<div class="sort" role="group" aria-label="Order games">
				<span class="muted small">Sort by</span>
				{#each options as option (option)}
					<button
						class="pill"
						class:accent={active === option}
						aria-pressed={active === option}
						onclick={() => choose(option)}>{SORT_LABELS[option]}</button
					>
				{/each}
				{#if active !== 'kickoff'}
					<span class="muted small">biggest disagreement with the market first</span>
				{/if}
			</div>
		{/if}
		<div class="games">
			{#each games as game (game.game_id)}
				<GameCard {game} sport={info.sport} odds={gameOdds(data.odds, game.game_id)} />
			{/each}
		</div>
	{/if}
</div>

<style>
	.heading {
		display: flex;
		justify-content: space-between;
		align-items: flex-end;
		gap: 16px;
		flex-wrap: wrap;
		margin-bottom: 16px;
	}
	.legend {
		display: flex;
		align-items: center;
		gap: 6px;
		flex-wrap: wrap;
		margin: 0;
	}
	.key {
		display: inline-block;
		width: 10px;
		height: 10px;
		margin-left: 6px;
	}
	.key.vegas {
		background: var(--vegas);
		transform: rotate(45deg);
	}
	.key.model {
		background: var(--accent);
		border-radius: 50%;
	}
	.key.edge {
		background: var(--accent-soft);
		width: 18px;
		border-radius: 3px;
	}
	.dates {
		display: flex;
		gap: 6px;
		flex-wrap: wrap;
	}
	.dates a:hover {
		text-decoration: none;
	}
	.sort {
		display: flex;
		align-items: center;
		gap: 6px;
		flex-wrap: wrap;
		margin-bottom: 16px;
	}
	.games {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(min(100%, 480px), 1fr));
		gap: 16px;
	}
</style>

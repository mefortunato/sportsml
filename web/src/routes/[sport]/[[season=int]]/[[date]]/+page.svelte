<script lang="ts">
	import { links } from '$lib/links';
	import GameCard from '$lib/components/GameCard.svelte';

	let { data } = $props();
	const info = $derived(data.info);
	const upcoming = $derived(data.upcoming);
</script>

<div class="container section">
	<div class="heading">
		<div>
			<h1>
				{info.label} · {info.date_label}
				{upcoming.date ?? '—'}
				{#if upcoming.season}<span class="muted">{upcoming.season}</span>{/if}
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
						href={links.upcoming(info.sport, upcoming.season, date)}>{info.date_label} {date}</a
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
		<div class="games">
			{#each upcoming.games as game (game.game_id)}
				<GameCard {game} sport={info.sport} />
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
	.games {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(min(100%, 480px), 1fr));
		gap: 16px;
	}
</style>

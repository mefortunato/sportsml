<script lang="ts">
	import '../app.css';
	import { page } from '$app/state';
	import { pct } from '$lib/format';

	let { data, children } = $props();

	const sport = $derived(page.params.sport);
	const info = $derived(data.sports.find((s) => s.sport === sport));
	const path = $derived(page.url.pathname);
	const backtest = $derived(info?.backtest);
</script>

<header>
	<div class="container bar">
		<a class="brand" href="/">SportsML</a>
		{#if data.sports.length > 1}
			<nav class="sports">
				{#each data.sports as s (s.sport)}
					<a href="/{s.sport}" class:active={s.sport === sport}>{s.label}</a>
				{/each}
			</nav>
		{/if}
		{#if info}
			<nav class="pages">
				<a href="/{info.sport}" class:active={path === `/${info.sport}`}>Upcoming</a>
				{#if info.has_spread && info.challenge_games}
					<a href="/{info.sport}/challenge" class:active={path.endsWith('/challenge')}
						>Beat the model</a
					>
				{/if}
			</nav>
		{/if}
	</div>
</header>

<main>
	{@render children()}
</main>

<footer class="container small muted">
	{#if info}
		<span>{info.label} predictions by a transformer over each team's recent games.</span>
		{#if backtest?.overall?.model?.brier && backtest.overall.market?.brier}
			<span>
				Walk-forward backtest {backtest.seasons[0]}–{backtest.seasons.at(-1)}: Brier
				{backtest.overall.model.brier.toFixed(3)} vs Vegas {backtest.overall.market.brier.toFixed(3)},
				picks {pct(backtest.overall.model.accuracy)} of winners (Vegas {pct(
					backtest.overall.market.accuracy
				)}).
			</span>
		{/if}
		{#if info.refreshed_at || info.built_at}
			<span>Data as of {(info.refreshed_at ?? info.built_at ?? '').replace('T', ' ')}.</span>
		{/if}
		<span>For entertainment, not betting advice.</span>
	{/if}
</footer>

<style>
	header {
		background: var(--surface);
		border-bottom: 1px solid var(--border);
		position: sticky;
		top: 0;
		z-index: 10;
	}
	.bar {
		display: flex;
		align-items: center;
		gap: 20px;
		height: 56px;
	}
	.brand {
		font-weight: 800;
		font-size: 1.1rem;
		color: var(--text);
	}
	nav {
		display: flex;
		gap: 4px;
	}
	nav a {
		color: var(--muted);
		padding: 6px 10px;
		border-radius: 8px;
		font-weight: 600;
	}
	nav a:hover {
		text-decoration: none;
		background: var(--surface-2);
	}
	nav a.active {
		color: var(--text);
		background: var(--surface-2);
	}
	.pages {
		margin-left: auto;
	}
	main {
		min-height: calc(100vh - 160px);
		padding-bottom: 32px;
	}
	footer {
		display: flex;
		flex-direction: column;
		gap: 2px;
		padding-top: 16px;
		padding-bottom: 24px;
		border-top: 1px solid var(--border);
	}
</style>

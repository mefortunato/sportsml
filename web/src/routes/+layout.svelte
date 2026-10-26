<script lang="ts">
	import { links } from '$lib/links';
	import '../app.css';
	import { page } from '$app/state';
	import { pct } from '$lib/format';

	let { data, children } = $props();

	const sport = $derived(page.params.sport);
	const info = $derived(data.sports.find((s) => s.sport === sport));
	// route ids, not page.url: in the hash-routed build the URL is the frame's
	const route = $derived(page.route.id ?? '');
	const backtest = $derived(info?.backtest);
</script>

<header>
	<div class="container bar">
		<a class="brand" href={links.home()}>SportsML</a>
		{#if data.sports.length > 1}
			<nav class="sports">
				{#each data.sports as s (s.sport)}
					<a href={links.upcoming(s.sport)} class:active={s.sport === sport}>{s.label}</a>
				{/each}
			</nav>
		{/if}
		{#if info}
			<nav class="pages">
				<a href={links.upcoming(info.sport)} class:active={route.startsWith('/[sport]/[[season')}>Upcoming</a>
				<a href={links.rankings(info.sport)} class:active={route === '/[sport]/rankings'}>Rankings</a>
				{#if info.challenge_games}
					<a href={links.performance(info.sport)} class:active={route === '/[sport]/performance'}
						>Performance</a
					>
				{/if}
				{#if info.has_spread && info.challenge_games}
					<a href={links.challenge(info.sport)} class:active={route === '/[sport]/challenge'}
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
		top: env(safe-area-inset-top, 0px);
		z-index: 10;
	}
	/* paints the phone's safe-area band above the sticky header */
	:global(body)::before {
		content: '';
		position: fixed;
		inset: 0 0 auto;
		height: env(safe-area-inset-top, 0px);
		z-index: 10;
		background: var(--surface);
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
		min-width: 0;
		overflow-x: auto;
		scrollbar-width: none;
	}
	nav a {
		white-space: nowrap;
	}
	@media (max-width: 640px) {
		.bar {
			flex-wrap: wrap;
			height: auto;
			row-gap: 2px;
			padding-block: 8px;
		}
		.pages {
			margin-left: -8px;
			flex-basis: 100%;
		}
		nav a {
			padding: 6px 8px;
		}
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

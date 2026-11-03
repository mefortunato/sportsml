<script lang="ts">
	import { links } from '$lib/links';
	import '../app.css';
	import { page } from '$app/state';
	import { pct, seasonsText } from '$lib/format';
	import { effectiveTheme, otherTheme, storeTheme, storedTheme, type Theme } from '$lib/theme';

	let { data, children } = $props();

	const sport = $derived(page.params.sport);
	const info = $derived(data.sports.find((s) => s.sport === sport));
	// route ids, not page.url: in the hash-routed build the URL is the frame's
	const route = $derived(page.route.id ?? '');
	const backtest = $derived(info?.backtest);

	// null until mounted: the prerendered artifact shell can't know the theme
	let theme = $state<Theme | null>(null);

	$effect(() => {
		const root = document.documentElement;
		const stored = storedTheme();
		if (stored) root.dataset.theme = stored;
		const media = matchMedia('(prefers-color-scheme: dark)');
		const sync = () => (theme = effectiveTheme(root.dataset.theme, media.matches));
		sync();
		// follow the OS (or a host page re-theming us) until the reader picks
		media.addEventListener('change', sync);
		const observer = new MutationObserver(sync);
		observer.observe(root, { attributes: true, attributeFilter: ['data-theme'] });
		return () => {
			media.removeEventListener('change', sync);
			observer.disconnect();
		};
	});

	function toggleTheme() {
		if (!theme) return;
		const next = otherTheme(theme);
		document.documentElement.dataset.theme = next;
		storeTheme(next);
	}
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
				{#if info.challenge_games && (info.has_spread || info.markets?.length)}
					<a href={links.challenge(info.sport)} class:active={route === '/[sport]/challenge'}
						>Beat the model</a
					>
				{/if}
			</nav>
		{/if}
		<button
			class="theme"
			type="button"
			onclick={toggleTheme}
			disabled={!theme}
			aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
			title={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
		>
			{#if theme === 'dark'}
				<!-- sun -->
				<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
					<circle cx="12" cy="12" r="4.5" />
					<path
						d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M4.9 19.1l1.8-1.8M17.3 6.7l1.8-1.8"
					/>
				</svg>
			{:else}
				<!-- moon -->
				<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
					<path d="M20.5 14.5A8.5 8.5 0 0 1 9.5 3.5a8.5 8.5 0 1 0 11 11Z" />
				</svg>
			{/if}
		</button>
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
				Walk-forward backtest {seasonsText(backtest.seasons, info.split_season)}: Brier
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
	.theme {
		flex: none;
		display: inline-grid;
		place-items: center;
		width: 34px;
		height: 34px;
		padding: 0;
		background: transparent;
		border-color: transparent;
		color: var(--muted);
	}
	.theme:hover,
	.theme:focus-visible {
		background: var(--surface-2);
		color: var(--text);
	}
	.theme:disabled {
		opacity: 1;
		cursor: default;
	}
	.theme svg {
		fill: none;
		stroke: currentColor;
		stroke-width: 2;
		stroke-linecap: round;
		stroke-linejoin: round;
	}
	/* no page nav: keep the toggle at the far right */
	.brand + .theme,
	.sports + .theme {
		margin-left: auto;
	}
	@media (max-width: 640px) {
		.theme {
			order: 1;
			margin-left: auto;
		}
		.pages {
			order: 2;
		}
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

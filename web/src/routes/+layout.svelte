<script lang="ts">
	import { links } from '$lib/links';
	import '../app.css';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { pct, seasonsText } from '$lib/format';
	import { effectiveTheme, otherTheme, storeTheme, storedTheme, type Theme } from '$lib/theme';

	let { data, children } = $props();

	const sport = $derived(page.params.sport);
	const info = $derived(data.sports.find((s) => s.sport === sport));
	// route ids, not page.url: in the hash-routed build the URL is the frame's
	const route = $derived(page.route.id ?? '');
	const backtest = $derived(info?.backtest);

	// the current sport's pages, shared by the desktop links and the phone dropdown
	const pages = $derived(
		info
			? [
					{ label: 'Upcoming', href: links.upcoming(info.sport), active: route.startsWith('/[sport]/[[season') },
					{ label: 'Recent', href: links.recent(info.sport), active: route.startsWith('/[sport]/recent') },
					{ label: 'Rankings', href: links.rankings(info.sport), active: route === '/[sport]/rankings' },
					...(info.has_team_map
						? [{ label: 'Team map', href: links.teamMap(info.sport), active: route === '/[sport]/map' }]
						: []),
					...(info.challenge_games
						? [{ label: 'Performance', href: links.performance(info.sport), active: route === '/[sport]/performance' }]
						: []),
					...(info.challenge_games && (info.has_spread || info.markets?.length)
						? [{ label: 'Beat the model', href: links.challenge(info.sport), active: route === '/[sport]/challenge' }]
						: [])
				]
			: []
	);
	const activePage = $derived(pages.find((p) => p.active));

	function navigate(event: Event) {
		const href = (event.currentTarget as HTMLSelectElement).value;
		if (href) goto(href);
	}

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
		{#if pages.length}
			<nav class="pages">
				{#each pages as p (p.label)}
					<a href={p.href} class:active={p.active}>{p.label}</a>
				{/each}
			</nav>
		{/if}
		<!-- phones: dropdowns instead of link rows that would scroll sideways -->
		<div class="menus">
			{#if data.sports.length > 1}
				<select aria-label="Sport" value={info ? links.upcoming(info.sport) : ''} onchange={navigate}>
					{#if !info}<option value="" disabled>Sport</option>{/if}
					{#each data.sports as s (s.sport)}
						<option value={links.upcoming(s.sport)}>{s.label}</option>
					{/each}
				</select>
			{/if}
			{#if pages.length}
				<select aria-label="Page" value={activePage?.href ?? ''} onchange={navigate}>
					{#if !activePage}<option value="" disabled>Page</option>{/if}
					{#each pages as p (p.label)}
						<option value={p.href}>{p.label}</option>
					{/each}
				</select>
			{/if}
		</div>
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
		flex-wrap: wrap;
		align-items: center;
		gap: 4px 20px;
		min-height: 56px;
		padding-block: 8px;
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
	/* the sport's pages: a second row under the sports */
	.pages {
		order: 1;
		flex-basis: 100%;
		margin-left: -10px;
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
	.theme {
		margin-left: auto;
	}
	.menus {
		display: none;
	}
	@media (max-width: 760px) {
		nav {
			display: none;
		}
		.menus {
			display: flex;
			gap: 6px;
			margin-left: auto;
			min-width: 0;
		}
		.menus select {
			min-width: 0;
			padding: 6px 8px;
			border: 1px solid var(--border);
			border-radius: 8px;
			background-color: var(--surface-2);
			color: var(--text);
			font: inherit;
			font-size: 0.9rem;
			font-weight: 600;
		}
		/* the sport keeps its full name; a long page name gives way first */
		.menus select:first-child {
			flex: none;
		}
		.bar {
			flex-wrap: nowrap;
			gap: 8px;
		}
		.theme {
			margin-left: 0;
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

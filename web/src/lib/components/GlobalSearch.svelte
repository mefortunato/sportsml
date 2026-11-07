<script lang="ts">
	import { goto } from '$app/navigation';
	import { api } from '$lib/api';
	import { teamSearch } from '$lib/headerSearch.svelte';
	import { links, sportPages } from '$lib/links';
	import { globalSearch, type PageResult, type TeamResult } from '$lib/search';
	import type { SportInfo } from '$lib/types';
	import TeamBadge from './TeamBadge.svelte';

	// The header's search: every sport's pages and teams, one pick away.
	let { sports, current }: { sports: SportInfo[]; current?: string } = $props();

	interface TeamIndex {
		teams: TeamResult[];
		/** Each team's next game date, by `${sport}/${team}`, for those with one. */
		next: Map<string, { season: number | null; date: number }>;
	}

	const id = 'site-search';
	let input = $state<HTMLInputElement>();
	let query = $state('');
	let open = $state(false);
	let active = $state(0);
	let index = $state<TeamIndex | null>(null);
	let loading: Promise<void> | null = null;

	const pages = $derived(
		sports.flatMap((s) =>
			sportPages(s).map((p): PageResult => ({ sport: s.sport, sportLabel: s.label, label: p.label, href: p.href }))
		)
	);
	const results = $derived(globalSearch(query, pages, index?.teams ?? [], current));
	type Item = { kind: 'page'; page: PageResult } | { kind: 'team'; team: TeamResult };
	const items = $derived<Item[]>([
		...results.pages.map((page) => ({ kind: 'page' as const, page })),
		...results.teams.map((team) => ({ kind: 'team' as const, team }))
	]);
	const typed = $derived(query.trim() !== '');
	const showList = $derived(open && typed);

	$effect(() => {
		// a new query starts from its best match
		void query;
		active = 0;
	});

	// the teams load on first use: every sport's rankings and upcoming files
	function loadTeams() {
		loading ??= Promise.all(
			sports.map(async (s) => {
				const { teams, next } = await api
					.searchTeams(s.sport)
					.catch(() => ({ teams: [], next: new Map<string, { season: number | null; date: number }>() }));
				return { s, teams, next };
			})
		).then((all) => {
			index = {
				teams: all.flatMap(({ s, teams }) =>
					teams.map((team) => ({ sport: s.sport, sportLabel: s.label, team }))
				),
				next: new Map(
					all.flatMap(({ s, next }) => [...next].map(([team, when]) => [`${s.sport}/${team}`, when] as const))
				)
			};
		});
	}

	/** Where picking `t` takes the reader, and what it does there. */
	function teamAction(t: TeamResult): { verb: string; run: () => void } {
		const target = teamSearch.target;
		if (target?.sport === t.sport) return { verb: target.verb, run: () => target.pick(t.team) };
		const next = index?.next.get(`${t.sport}/${t.team.team}`);
		const href = next ? links.upcoming(t.sport, next.season, next.date) : links.rankings(t.sport);
		return {
			verb: next ? 'Upcoming games' : 'Rankings',
			run: () => {
				teamSearch.pending = { sport: t.sport, team: t.team };
				goto(href);
			}
		};
	}

	function choose(item: Item) {
		query = '';
		open = false;
		input?.blur();
		if (item.kind === 'page') goto(item.page.href);
		else teamAction(item.team).run();
	}

	function keydown(event: KeyboardEvent) {
		if (event.key === 'Escape') {
			if (showList) open = false;
			else {
				query = '';
				input?.blur();
			}
			event.preventDefault();
			return;
		}
		if (!items.length) return;
		if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
			event.preventDefault();
			open = true;
			const step = event.key === 'ArrowDown' ? 1 : -1;
			active = (active + step + items.length) % items.length;
		} else if (event.key === 'Enter' && showList) {
			event.preventDefault();
			choose(items[active]);
		}
	}

	// "/" anywhere outside a form field jumps to the search
	function shortcut(event: KeyboardEvent) {
		if (event.key !== '/' || event.metaKey || event.ctrlKey || event.altKey) return;
		const el = event.target as HTMLElement | null;
		if (el?.closest('input, textarea, select, [contenteditable="true"]')) return;
		event.preventDefault();
		input?.focus();
	}
</script>

<svelte:window onkeydown={shortcut} />

<div class="search">
	<label class="sr-only" for={id}>Search teams and pages</label>
	<svg class="icon" viewBox="0 0 16 16" aria-hidden="true">
		<circle cx="7" cy="7" r="4.5" fill="none" stroke="currentColor" stroke-width="1.6" />
		<path d="M10.5 10.5 14 14" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
	</svg>
	<input
		bind:this={input}
		{id}
		type="search"
		autocomplete="off"
		spellcheck="false"
		placeholder="Search teams and pages"
		bind:value={query}
		role="combobox"
		aria-expanded={showList}
		aria-controls="{id}-list"
		aria-autocomplete="list"
		aria-activedescendant={showList && items.length ? `${id}-${active}` : undefined}
		oninput={() => (open = true)}
		onfocus={() => {
			open = true;
			loadTeams();
		}}
		onblur={() => (open = false)}
		onkeydown={keydown}
	/>
	{#if !typed}<kbd class="hint" aria-hidden="true">/</kbd>{/if}
	<ul id="{id}-list" class="list" role="listbox" aria-label="Search results" hidden={!showList}>
		{#each items as item, i (item.kind === 'page' ? `p ${item.page.href}` : `t ${item.team.sport} ${item.team.team.team}`)}
			{#if i === 0 && item.kind === 'page'}<li class="group" role="presentation">Pages</li>{/if}
			{#if item.kind === 'team' && (i === 0 || items[i - 1].kind === 'page')}
				<li class="group" role="presentation">Teams</li>
			{/if}
			<!-- mousedown, not click: the input's blur would close the list first -->
			<li
				id="{id}-{i}"
				role="option"
				aria-selected={i === active}
				class:active={i === active}
				onmousedown={(event) => {
					event.preventDefault();
					choose(item);
				}}
				onmouseenter={() => (active = i)}
			>
				{#if item.kind === 'page'}
					<span class="sport">{item.page.sportLabel}</span>
					<span class="name">{item.page.label}</span>
				{:else}
					<TeamBadge team={item.team.team} label="none" size={20} />
					<span class="name">{item.team.team.name}</span>
					<span class="sport">{item.team.sportLabel}</span>
					<span class="verb muted small">{teamAction(item.team).verb}</span>
				{/if}
			</li>
		{/each}
		{#if !index}
			<li class="note muted small" role="presentation">Loading teams…</li>
		{:else if !items.length}
			<li class="note muted small" role="presentation">No team or page matches “{query.trim()}”.</li>
		{/if}
	</ul>
</div>

<style>
	.search {
		position: relative;
		width: 100%;
	}
	.icon {
		position: absolute;
		left: 10px;
		top: 50%;
		width: 14px;
		height: 14px;
		transform: translateY(-50%);
		color: var(--muted);
		pointer-events: none;
	}
	input {
		width: 100%;
		font: inherit;
		font-size: 0.9rem;
		padding: 6px 28px 6px 30px;
		border-radius: 8px;
		border: 1px solid var(--border);
		background: var(--surface);
		color: var(--text);
	}
	input:focus {
		outline: 2px solid var(--accent);
		outline-offset: -1px;
	}
	.hint {
		position: absolute;
		right: 8px;
		top: 50%;
		transform: translateY(-50%);
		padding: 0 5px;
		border: 1px solid var(--border);
		border-radius: 4px;
		font: inherit;
		font-size: 0.75rem;
		line-height: 1.4;
		color: var(--muted);
		pointer-events: none;
	}
	input:focus ~ .hint {
		display: none;
	}
	.list {
		position: absolute;
		z-index: 20;
		top: calc(100% + 4px);
		right: 0;
		width: max(100%, 360px);
		max-width: calc(100vw - 32px);
		margin: 0;
		padding: 4px;
		list-style: none;
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: 8px;
		box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
		max-height: min(420px, 70vh);
		overflow-y: auto;
	}
	.list[hidden] {
		display: none;
	}
	li {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 5px 8px;
		border-radius: 6px;
	}
	li[role='option'] {
		cursor: pointer;
	}
	li.active {
		background: var(--accent-soft);
	}
	.group {
		padding: 6px 8px 2px;
		font-size: 0.75rem;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: var(--muted);
	}
	.note {
		padding: 6px 8px;
	}
	.name {
		flex: 1;
		min-width: 0;
		font-weight: 600;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.sport {
		flex: none;
		padding: 0 6px;
		border-radius: 4px;
		background: var(--surface-2);
		font-size: 0.75rem;
		font-weight: 700;
		color: var(--muted);
	}
	.verb {
		flex: none;
	}
	.sr-only {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip: rect(0 0 0 0);
		white-space: nowrap;
	}
</style>

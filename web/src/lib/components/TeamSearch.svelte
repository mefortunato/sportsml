<script lang="ts">
	import { searchTeams } from '$lib/search';
	import type { Team } from '$lib/types';
	import TeamBadge from './TeamBadge.svelte';

	// A search box for a team. On its own it is a filter: the page reads
	// `query` and narrows what it shows. Given `teams` and `onpick`, it also
	// suggests the teams the query names, to pick with a click or the keyboard.
	let {
		query = $bindable(''),
		teams = [],
		onpick,
		picked = () => false,
		label = 'Find a team',
		placeholder = 'Search teams'
	}: {
		query?: string;
		teams?: Team[];
		onpick?: (team: Team) => void;
		/** Whether a suggestion is already picked (highlighted on the page). */
		picked?: (team: string) => boolean;
		label?: string;
		placeholder?: string;
	} = $props();

	const id = `team-search-${Math.random().toString(36).slice(2, 8)}`;
	let open = $state(false);
	let active = $state(0);
	const suggestions = $derived(onpick ? searchTeams(teams, query) : []);
	const showList = $derived(open && suggestions.length > 0);

	$effect(() => {
		// a new query starts from its best match
		void query;
		active = 0;
	});

	function pick(team: Team) {
		onpick?.(team);
		query = '';
		open = false;
	}

	function keydown(event: KeyboardEvent) {
		if (event.key === 'Escape') {
			if (showList) open = false;
			else query = '';
			event.preventDefault();
			return;
		}
		if (!suggestions.length) return;
		if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
			event.preventDefault();
			open = true;
			const step = event.key === 'ArrowDown' ? 1 : -1;
			active = (active + step + suggestions.length) % suggestions.length;
		} else if (event.key === 'Enter' && showList) {
			event.preventDefault();
			pick(suggestions[active]);
		}
	}
</script>

<div class="search">
	<label class="sr-only" for={id}>{label}</label>
	<svg class="icon" viewBox="0 0 16 16" aria-hidden="true">
		<circle cx="7" cy="7" r="4.5" fill="none" stroke="currentColor" stroke-width="1.6" />
		<path d="M10.5 10.5 14 14" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
	</svg>
	<input
		{id}
		type="search"
		autocomplete="off"
		spellcheck="false"
		{placeholder}
		bind:value={query}
		role={onpick ? 'combobox' : undefined}
		aria-expanded={onpick ? showList : undefined}
		aria-controls={onpick ? `${id}-list` : undefined}
		aria-autocomplete={onpick ? 'list' : undefined}
		aria-activedescendant={showList ? `${id}-${active}` : undefined}
		oninput={() => (open = true)}
		onfocus={() => (open = true)}
		onblur={() => (open = false)}
		onkeydown={keydown}
	/>
	{#if onpick}
		<ul id="{id}-list" class="list" role="listbox" aria-label="Matching teams" hidden={!showList}>
			{#each suggestions as team, i (team.team)}
				<!-- mousedown, not click: the input's blur would close the list first -->
				<li
					id="{id}-{i}"
					role="option"
					aria-selected={i === active}
					class:active={i === active}
					onmousedown={(event) => {
						event.preventDefault();
						pick(team);
					}}
					onmouseenter={() => (active = i)}
				>
					<TeamBadge {team} label="none" size={20} />
					<span class="name">{team.name}</span>
					{#if picked(team.team)}<span class="muted small">highlighted</span>{/if}
				</li>
			{/each}
		</ul>
	{/if}
</div>

<style>
	.search {
		position: relative;
		width: min(100%, 280px);
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
		padding: 6px 10px 6px 30px;
		border-radius: 8px;
		border: 1px solid var(--border);
		background: var(--surface);
		color: var(--text);
	}
	input:focus {
		outline: 2px solid var(--accent);
		outline-offset: -1px;
	}
	.list {
		position: absolute;
		z-index: 10;
		top: calc(100% + 4px);
		left: 0;
		right: 0;
		margin: 0;
		padding: 4px;
		list-style: none;
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: 8px;
		box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
		max-height: 320px;
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
		cursor: pointer;
	}
	li.active {
		background: var(--accent-soft);
	}
	.name {
		flex: 1;
		min-width: 0;
		font-weight: 600;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
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

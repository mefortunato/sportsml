<script lang="ts">
	import TeamBadge from '$lib/components/TeamBadge.svelte';
	import TeamMap3D from '$lib/components/TeamMap3D.svelte';
	import { dateText, seasonText, signed } from '$lib/format';
	import {
		filterOptions,
		matchesFilter,
		MAX_PINS,
		togglePin,
		type Pins,
		type TeamFilter
	} from '$lib/rankings';
	import { positionAt, ranksAt } from '$lib/teammap';
	import { untrack } from 'svelte';

	let { data } = $props();
	const info = $derived(data.info);
	const map = $derived(data.teamMap);

	let frame = $state(0);
	let filter = $state<TeamFilter>({});
	let pins = $state<Pins>({});

	// start at the latest date
	$effect(() => {
		if (map) untrack(() => (frame = map.dates.length - 1));
	});

	const last = $derived(map ? map.dates.length - 1 : 0);
	const shown = $derived(Math.round(frame));
	const options = $derived(filterOptions(map ? map.teams.map((t) => t.team) : []));
	const filtering = $derived(Boolean(filter.conference));
	const visible = $derived(
		map && filtering
			? new Set(map.teams.filter((t) => matchesFilter(t.team, filter)).map((t) => t.team.team))
			: null
	);
	const isVisible = (team: string) => !visible || visible.has(team);
	const divisionLabel = (conference: string, division: string) =>
		division.startsWith(`${conference} `) ? division.slice(conference.length + 1) : division;

	// every filter change starts from that view's top teams at the latest date
	$effect(() => {
		if (!map) return;
		const top = [...ranksAt(map.teams, last).keys()].filter(isVisible).slice(0, MAX_PINS);
		untrack(() => (pins = Object.fromEntries(top.map((team, i) => [team, i + 1]))));
	});
	const toggle = (team: string) => (pins = togglePin(pins, team));
	const pinned = $derived(
		map ? map.teams.filter((t) => t.team.team in pins).sort((a, b) => pins[a.team.team] - pins[b.team.team]) : []
	);

	// who the model sees most differently than at the season's first date
	const movers = $derived.by(() => {
		if (!map || shown === 0) return [];
		const ranks = ranksAt(map.teams, shown);
		const firstRanks = ranksAt(map.teams, 0);
		return map.teams
			.filter((t) => isVisible(t.team.team))
			.map((t) => {
				const [a, b] = [positionAt(t, 0), positionAt(t, shown)];
				const moved = a && b ? Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]) : null;
				const [r0, r1] = [t.ratings[0], t.ratings[shown]];
				return {
					t,
					moved,
					rating: r1,
					change: r0 !== null && r1 !== null ? r1 - r0 : null,
					rank: ranks.get(t.team.team) ?? null,
					rankChange:
						firstRanks.has(t.team.team) && ranks.has(t.team.team)
							? (firstRanks.get(t.team.team) as number) - (ranks.get(t.team.team) as number)
							: null
				};
			})
			.filter((m) => m.moved !== null)
			.sort((a, b) => (b.moved as number) - (a.moved as number))
			.slice(0, 10);
	});
	const dateAt = (i: number) =>
		map ? dateText(info.date_label, map.dates[i], map.date_names?.[i]) : '';
</script>

<div class="container section">
	<h1>Team map</h1>
	<p class="muted intro">
		The model keeps an internal picture of each team, a long list of numbers learned from its recent
		games. This map squeezes those pictures into three dimensions with UMAP, so teams the model
		sees as alike sit close together. Every {info.date_label.toLowerCase()} of the season is
		laid out in the same space: press play to watch teams move as their results come in. The axes
		have no units; only closeness means anything. Color is the team's average predicted margin.
	</p>

	{#if !map}
		<div class="card">No team map for this sport yet.</div>
	{:else}
		<p class="muted small source">
			{seasonText(map.season, info.split_season)}, from the current model, before each
			{info.date_label.toLowerCase()}'s games.
		</p>
		{#if options.conferences.length}
			<nav class="filters" aria-label="Teams">
				<button class="pill" class:accent={!filtering} aria-pressed={!filtering} onclick={() => (filter = {})}
					>All teams</button
				>
				{#each options.conferences as conference (conference)}
					<button
						class="pill"
						class:accent={filter.conference === conference && !filter.division}
						aria-pressed={filter.conference === conference}
						onclick={() => (filter = { conference })}>{conference}</button
					>
				{/each}
			</nav>
			{#if filter.conference && options.divisions[filter.conference]?.length}
				{@const conference = filter.conference}
				<nav class="filters divisions" aria-label="{conference} divisions">
					{#each options.divisions[conference] as division (division)}
						<button
							class="pill"
							class:accent={filter.division === division}
							aria-pressed={filter.division === division}
							onclick={() => (filter = filter.division === division ? { conference } : { conference, division })}
							>{divisionLabel(conference, division)}</button
						>
					{/each}
				</nav>
			{/if}
		{/if}

		<div class="card">
			<div class="legend">
				{#each pinned as t (t.team.team)}
					<button class="chip" onclick={() => toggle(t.team.team)} aria-label="Stop highlighting {t.team.name}">
						<span class="swatch" style:background="var(--series-{pins[t.team.team]})"></span>
						{t.team.name}
						<span class="x" aria-hidden="true">×</span>
					</button>
				{/each}
				<span class="muted small">Highlighted teams trace their path. Click a dot to highlight it (up to {MAX_PINS}).</span>
			</div>
			<TeamMap3D {map} {pins} {visible} dateLabel={info.date_label} bind:frame ontoggle={toggle} />
		</div>

		<div class="card section">
			<h2>
				Moved most since {dateAt(0)}
				<span class="muted small">before {dateAt(shown)}</span>
			</h2>
			{#if !movers.length}
				<p class="muted small">Move the timeline past the first {info.date_label.toLowerCase()} to compare.</p>
			{:else}
				<p class="muted small note">
					Distance each team has traveled through the map since the first {info.date_label.toLowerCase()}:
					the teams the model has changed its mind about most.
				</p>
				<div class="scroll">
					<table class="movers">
						<thead>
							<tr>
								<th>Team</th>
								<th class="num">Moved</th>
								<th class="num">Rank</th>
								<th class="num">Avg margin</th>
								<th class="num">Since {dateAt(0)}</th>
							</tr>
						</thead>
						<tbody>
							{#each movers as m (m.t.team.team)}
								{@const slot = pins[m.t.team.team]}
								<tr class:pinned={slot !== undefined}>
									<td class="team-cell">
										<button class="team" onclick={() => toggle(m.t.team.team)} aria-pressed={slot !== undefined}>
											<span class="swatch" style:background={slot ? `var(--series-${slot})` : 'transparent'}></span>
											<TeamBadge team={m.t.team} label="none" size={22} />
											<span class="name">{m.t.team.name}</span>
										</button>
									</td>
									<td class="num tabular">{(m.moved as number).toFixed(2)}</td>
									<td class="num tabular">
										{m.rank ?? '–'}
										{#if m.rankChange}
											<span class:up={m.rankChange > 0} class:down={m.rankChange < 0}
												>{m.rankChange > 0 ? '▲' : '▼'}{Math.abs(m.rankChange)}</span
											>
										{/if}
									</td>
									<td class="num tabular">{m.rating === null ? '–' : signed(m.rating)}</td>
									<td class="num tabular" class:up={(m.change ?? 0) > 0} class:down={(m.change ?? 0) < 0}
										>{m.change === null ? '–' : signed(m.change)}</td
									>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}
		</div>
	{/if}
</div>

<style>
	.intro {
		max-width: 68ch;
	}
	.source {
		margin: 0 0 12px;
	}
	.filters {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
		margin: 0 0 8px;
	}
	.filters button {
		cursor: pointer;
	}
	.legend {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
		align-items: center;
		margin-bottom: 8px;
		/* clear of the camera buttons in the chart's top right */
		padding-right: 0;
	}
	.chip {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		padding: 3px 10px;
		border-radius: 999px;
		font-size: 0.85rem;
		cursor: pointer;
	}
	.chip .x {
		color: var(--muted);
	}
	.swatch {
		display: inline-block;
		width: 10px;
		height: 10px;
		border-radius: 50%;
		flex: none;
	}
	.note {
		margin: 0 0 8px;
		max-width: 68ch;
	}
	.scroll {
		overflow-x: auto;
	}
	.movers {
		width: 100%;
		border-collapse: collapse;
	}
	.movers th {
		text-align: left;
		font-size: 0.8rem;
		color: var(--muted);
		font-weight: 600;
		padding: 6px 8px;
		border-bottom: 1px solid var(--border);
		white-space: nowrap;
	}
	.movers td {
		padding: 4px 8px;
		border-bottom: 1px solid var(--border);
	}
	.movers tr.pinned td {
		background: var(--surface-2);
	}
	.num {
		text-align: right;
		width: 1%;
		white-space: nowrap;
	}
	.team-cell {
		width: 100%;
		max-width: 0;
		min-width: 140px;
	}
	.team {
		overflow: hidden;
		width: 100%;
		display: flex;
		align-items: center;
		gap: 8px;
		background: none;
		border: 0;
		padding: 2px 0;
		color: inherit;
		font: inherit;
		cursor: pointer;
	}
	.name {
		font-weight: 600;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.up {
		color: var(--good);
	}
	.down {
		color: var(--bad);
	}
</style>

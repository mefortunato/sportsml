<script lang="ts">
	import RankingsChart from '$lib/components/RankingsChart.svelte';
	import TeamBadge from '$lib/components/TeamBadge.svelte';
	import { dateText, seasonText, signed } from '$lib/format';
	import {
		filterOptions,
		matchesFilter,
		MAX_PINS,
		playoffRanks,
		rankAt,
		reconcilePins,
		togglePin,
		type Pins,
		type TeamFilter
	} from '$lib/rankings';
	import type { PlayoffStage } from '$lib/types';
	import { untrack } from 'svelte';

	let { data } = $props();
	const info = $derived(data.info);
	const rankings = $derived(data.rankings);

	let chosen = $state<number | null>(null);
	const season = $derived(
		rankings.seasons.find((s) => s.season === chosen) ?? rankings.seasons[0]
	);
	let pins = $state<Pins>({});
	let index = $state<number | null>(null);
	let filter = $state<TeamFilter>({});

	const options = $derived(filterOptions(season ? season.teams.map((t) => t.team) : []));
	// how the season ended for the last teams standing (a quick check of the
	// ratings: these teams should rank near the top)
	const playoffs = $derived(season?.playoffs ?? {});
	const hasPlayoffs = $derived(Object.keys(playoffs).length > 0);
	const SHORT: Record<PlayoffStage, string> = {
		champion: 'Champion',
		runner_up: 'Runner-up',
		semifinal: 'Final four'
	};
	const stageLabel = (stage: PlayoffStage) => rankings.playoff_labels?.[stage] ?? SHORT[stage];

	// a season whose playoffs are not played yet has no final four to show
	$effect(() => {
		if (filter.playoffs && !hasPlayoffs) filter = {};
	});

	const filtering = $derived(Boolean(filter.conference || filter.playoffs));
	const visible = $derived(
		season && filtering
			? new Set(
					season.teams.filter((t) => matchesFilter(t.team, filter, playoffs)).map((t) => t.team.team)
				)
			: null
	);
	const filterLabel = $derived(
		filter.playoffs ? 'final four' : (filter.division ?? filter.conference ?? null)
	);
	const isVisible = (team: string) => !visible || visible.has(team);

	// Every season or filter change starts from that view's top teams; teams
	// highlighted by hand last until the next change.
	$effect(() => {
		if (!season) return;
		const top = rankAt(season, season.dates.length - 1).filter((r) => isVisible(r.team.team));
		untrack(() => (pins = reconcilePins({}, top)));
	});

	const shown = $derived(season ? (index ?? season.dates.length - 1) : 0);
	const rows = $derived(season ? rankAt(season, shown).filter((r) => isVisible(r.team.team)) : []);
	const finalists = $derived(season && hasPlayoffs ? playoffRanks(season, shown) : []);
	const divisionLabel = (conference: string, division: string) =>
		division.startsWith(`${conference} `) ? division.slice(conference.length + 1) : division;
	const pinnedTeams = $derived(
		season
			? season.teams
					.filter((t) => t.team.team in pins)
					.sort((a, b) => pins[a.team.team] - pins[b.team.team])
			: []
	);
	const toggle = (team: string) => (pins = togglePin(pins, team));
</script>

<div class="container section">
	<h1>Power rankings</h1>
	<p class="muted intro">
		Each team's average predicted margin against every other team on a neutral field, before each
		{info.date_label.toLowerCase()}'s games. Above zero, the model expects the team to beat an
		average opponent by that many points; higher is better.
	</p>

	{#if !season}
		<div class="card">No rankings yet.</div>
	{:else}
		<nav class="filters" aria-label="Season">
			{#each rankings.seasons as s (s.season)}
				<button class="pill" class:accent={s.season === season.season} onclick={() => (chosen = s.season)}
					>{seasonText(s.season, info.split_season)}</button
				>
			{/each}
		</nav>
		{#if options.conferences.length || hasPlayoffs}
			<nav class="filters" aria-label="Teams">
				<button class="pill" class:accent={!filtering} aria-pressed={!filtering} onclick={() => (filter = {})}
					>All teams</button
				>
				{#each options.conferences as conference (conference)}
					<button
						class="pill"
						class:accent={filter.conference === conference}
						aria-pressed={filter.conference === conference}
						onclick={() => (filter = { conference })}>{conference}</button
					>
				{/each}
				{#if hasPlayoffs}
					<button
						class="pill"
						class:accent={filter.playoffs}
						aria-pressed={!!filter.playoffs}
						onclick={() => (filter = { playoffs: true })}>Final four</button
					>
				{/if}
			</nav>
			{#if filter.conference && options.divisions[filter.conference]?.length}
				{@const conference = filter.conference}
				<nav class="filters divisions" aria-label="{conference} divisions">
					<button class="pill" class:accent={!filter.division} aria-pressed={!filter.division} onclick={() => (filter = { conference })}
						>All {conference}</button
					>
					{#each options.divisions[conference] as division (division)}
						<button
							class="pill"
							class:accent={filter.division === division}
							aria-pressed={filter.division === division}
							onclick={() => (filter = { conference, division })}>{divisionLabel(conference, division)}</button
						>
					{/each}
				</nav>
			{/if}
		{/if}
		<p class="muted small source">
			{#if season.source === 'backtest'}
				{seasonText(season.season, info.split_season)}: from that season's walk-forward model, trained only on seasons before
				{seasonText(season.season, info.split_season)}, with each {info.date_label.toLowerCase()}'s results added as they happened.
			{:else}
				{seasonText(season.season, info.split_season)}: from the current model, with each {info.date_label.toLowerCase()}'s results
				added as they happened.
			{/if}
		</p>

		<div class="card">
			<div class="legend">
				{#each pinnedTeams as t (t.team.team)}
					<button class="chip" onclick={() => toggle(t.team.team)} aria-label="Stop highlighting {t.team.name}">
						<span class="swatch" style:background="var(--series-{pins[t.team.team]})"></span>
						{t.team.name}
						<span class="x" aria-hidden="true">×</span>
					</button>
				{/each}
				<span class="muted small">
					Gray lines are the other {filterLabel ? `${filterLabel} ` : ''}teams. Click a line or a row
					to highlight it (up to {MAX_PINS}).
				</span>
			</div>
			<RankingsChart {season} {visible} dateLabel={info.date_label} {pins} bind:index ontoggle={toggle} />
		</div>

		<div class="card section">
			<h2>
				Before {dateText(info.date_label, season.dates[shown], season.date_names?.[shown])},
				{seasonText(season.season, info.split_season)}
				{#if filterLabel}<span class="muted"> · {filterLabel}</span>{/if}
				{#if index !== null}<span class="muted small">(hovered)</span>{/if}
			</h2>
			{#if finalists.length}
				<p class="muted small check">
					Where the final four ranked:
					{#each finalists as { row, stage }, i (row.team.team)}
						{i ? ' · ' : ''}<strong class="finalist">{row.team.team} #{row.rank}</strong>
						({stageLabel(stage)})
					{/each}
				</p>
			{/if}
			<table class="ranks">
				<thead>
					<tr>
						<th class="num">{visible ? 'League rank' : 'Rank'}</th>
						<th>Team</th>
						<th class="num">Avg margin</th>
						<th class="num">Change</th>
					</tr>
				</thead>
				<tbody>
					{#each rows as row (row.team.team)}
						{@const slot = pins[row.team.team]}
						<tr class:pinned={slot !== undefined}>
							<td class="num tabular">{row.rank}</td>
							<td class="team-cell">
								<button class="team" onclick={() => toggle(row.team.team)} aria-pressed={slot !== undefined}>
									<span class="swatch" style:background={slot ? `var(--series-${slot})` : 'transparent'}></span>
									<TeamBadge team={row.team} label="none" size={22} />
									<span class="name full">{row.team.name}</span>
									<span class="name short">{row.team.nickname ?? row.team.team}</span>
									{#if playoffs[row.team.team]}
										{@const stage = playoffs[row.team.team]}
										<span class="stage" class:champion={stage === 'champion'} title={stageLabel(stage)}>
											<span class="full">{stageLabel(stage)}</span>
											<span class="short">{SHORT[stage]}</span>
										</span>
									{/if}
								</button>
							</td>
							<td class="num tabular">{signed(row.rating)}</td>
							<td class="num tabular change" class:up={(row.change ?? 0) > 0} class:down={(row.change ?? 0) < 0}>
								{#if row.change === null || row.change === 0}–{:else if row.change > 0}▲ {row.change}{:else}▼ {-row.change}{/if}
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
</div>

<style>
	.intro {
		max-width: 68ch;
	}
	.filters {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
		margin: 12px 0 6px;
	}
	.filters button {
		cursor: pointer;
	}
	.filters.divisions {
		margin-top: 0;
	}
	.source {
		margin: 0 0 12px;
	}
	.legend {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
		align-items: center;
		margin-bottom: 8px;
	}
	.chip {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		padding: 3px 10px;
		border-radius: 999px;
		font-size: 0.85rem;
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
	.ranks {
		width: 100%;
		border-collapse: collapse;
	}
	.ranks th {
		text-align: left;
		font-size: 0.8rem;
		color: var(--muted);
		font-weight: 600;
		padding: 6px 8px;
		border-bottom: 1px solid var(--border);
	}
	.ranks td {
		padding: 4px 8px;
		border-bottom: 1px solid var(--border);
	}
	.ranks tr.pinned td {
		background: var(--surface-2);
	}
	.num {
		text-align: right;
		width: 1%;
		white-space: nowrap;
	}
	/* the name column takes the slack and truncates instead of widening */
	.team-cell {
		width: 100%;
		max-width: 0;
	}
	.name {
		font-weight: 600;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.short {
		display: none;
	}
	.stage {
		flex: none;
		font-size: 0.75rem;
		font-weight: 600;
		color: var(--muted);
		border: 1px solid var(--border);
		border-radius: 999px;
		padding: 1px 8px;
		white-space: nowrap;
	}
	.stage.champion {
		color: var(--accent);
		border-color: var(--accent);
		background: var(--accent-soft);
	}
	.check {
		margin: 0 0 8px;
	}
	.finalist {
		color: var(--text);
		font-variant-numeric: tabular-nums;
	}
	@media (max-width: 640px) {
		.full {
			display: none;
		}
		.short {
			display: inline;
		}
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
		min-width: 0;
		max-width: 100%;
	}
	.change.up {
		color: var(--good);
	}
	.change.down {
		color: var(--bad);
	}
</style>

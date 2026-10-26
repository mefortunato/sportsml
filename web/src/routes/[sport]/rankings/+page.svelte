<script lang="ts">
	import RankingsChart from '$lib/components/RankingsChart.svelte';
	import TeamBadge from '$lib/components/TeamBadge.svelte';
	import { signed } from '$lib/format';
	import { defaultPins, MAX_PINS, rankAt, togglePin, type Pins } from '$lib/rankings';

	let { data } = $props();
	const info = $derived(data.info);
	const rankings = $derived(data.rankings);

	let chosen = $state<number | null>(null);
	const season = $derived(
		rankings.seasons.find((s) => s.season === chosen) ?? rankings.seasons[0]
	);
	let pins = $state<Pins>({});
	let index = $state<number | null>(null);

	// a new season starts with its top teams highlighted
	$effect(() => {
		if (season) pins = defaultPins(season);
	});

	const shown = $derived(season ? (index ?? season.dates.length - 1) : 0);
	const rows = $derived(season ? rankAt(season, shown) : []);
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
					>{s.season}</button
				>
			{/each}
		</nav>
		<p class="muted small source">
			{#if season.source === 'backtest'}
				{season.season}: from that season's walk-forward model, trained only on seasons before
				{season.season}, with each {info.date_label.toLowerCase()}'s results added as they happened.
			{:else}
				{season.season}: from the current model, with each {info.date_label.toLowerCase()}'s results
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
					Gray lines are the other teams. Click a line or a row to highlight it (up to {MAX_PINS}).
				</span>
			</div>
			<RankingsChart {season} dateLabel={info.date_label} {pins} bind:index ontoggle={toggle} />
		</div>

		<div class="card section">
			<h2>
				Before {info.date_label}
				{season.dates[shown]}, {season.season}
				{#if index !== null}<span class="muted small">(hovered)</span>{/if}
			</h2>
			<table class="ranks">
				<thead>
					<tr>
						<th class="num">Rank</th>
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
							<td>
								<button class="team" onclick={() => toggle(row.team.team)} aria-pressed={slot !== undefined}>
									<span class="swatch" style:background={slot ? `var(--series-${slot})` : 'transparent'}></span>
									<TeamBadge team={row.team} label="name" size={22} />
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
	.team {
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

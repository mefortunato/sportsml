<script lang="ts">
	import { atsRecord, seasonText, winLoss } from '$lib/format';
	import type { StatDef, TeamSummary } from '$lib/types';
	import TeamBadge from './TeamBadge.svelte';

	let {
		stats,
		away,
		home,
		dateLabel = 'Week',
		splitSeason = false
	}: {
		stats: StatDef[];
		away: TeamSummary;
		home: TeamSummary;
		dateLabel?: string;
		splitSeason?: boolean;
	} = $props();

	function better(stat: StatDef, a: number | null, h: number | null): 'away' | 'home' | null {
		if (a === null || h === null || a === h) return null;
		return (a > h) === stat.higher_is_better ? 'away' : 'home';
	}

	// bar length (% of its half) grows with the value; stats that can be negative
	// (EPA) are measured from a baseline below the lower of the two
	function share(a: number | null, h: number | null, side: 'away' | 'home') {
		if (a === null || h === null) return 0;
		const value = side === 'away' ? a : h;
		const lo = Math.min(a, h, 0);
		const hi = Math.max(a, h);
		const base = lo < 0 ? lo - (Math.abs(lo) + Math.abs(hi)) / 2 : 0;
		return hi === base ? 0 : ((value - base) / (hi - base)) * 100;
	}

	const fmt = (value: number | null, decimals: number) =>
		value === null || value === undefined ? '—' : value.toFixed(decimals);

	function basis(summary: TeamSummary) {
		const games = `${summary.games} game${summary.games === 1 ? '' : 's'}`;
		const season = seasonText(summary.season, splitSeason);
		return summary.current_season
			? `${season} season, ${games}`
			: `${season} season (last season), ${games}`;
	}
</script>

<div class="compare">
	<div class="head">
		<div>
			<TeamBadge team={away.team} label="name" />
			<div class="muted small">{basis(away)}</div>
		</div>
		<div class="center muted small">per game,<br />before this {dateLabel.toLowerCase()}</div>
		<div class="right">
			<TeamBadge team={home.team} label="name" />
			<div class="muted small">{basis(home)}</div>
		</div>
	</div>

	<div class="row record">
		<span class="value tabular">{winLoss(away.record)}</span>
		<span class="label">Record</span>
		<span class="value tabular right">{winLoss(home.record)}</span>
	</div>
	<div class="row record">
		<span class="value tabular">{atsRecord(away.ats)}</span>
		<span class="label">Against the spread</span>
		<span class="value tabular right">{atsRecord(home.ats)}</span>
	</div>

	{#each stats as stat (stat.key)}
		{@const a = away.averages[stat.key] ?? null}
		{@const h = home.averages[stat.key] ?? null}
		{@const best = better(stat, a, h)}
		<div class="row">
			<span class="value tabular" class:best={best === 'away'}>{fmt(a, stat.decimals)}</span>
			<span class="label">
				{stat.label}
				<span class="bars">
					<span class="half left">
						<span class="bar" class:best={best === 'away'} style:width="{share(a, h, 'away')}%"></span>
					</span>
					<span class="half">
						<span class="bar" class:best={best === 'home'} style:width="{share(a, h, 'home')}%"></span>
					</span>
				</span>
			</span>
			<span class="value tabular right" class:best={best === 'home'}>{fmt(h, stat.decimals)}</span>
		</div>
	{/each}
</div>

<style>
	.head {
		display: grid;
		grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
		gap: 12px;
		align-items: center;
		padding-bottom: 10px;
		border-bottom: 1px solid var(--border);
	}
	.head > div {
		min-width: 0;
	}
	.head .right {
		text-align: right;
		display: flex;
		flex-direction: column;
		align-items: flex-end;
	}
	.center {
		text-align: center;
	}
	.row {
		display: grid;
		grid-template-columns: 70px 1fr 70px;
		align-items: center;
		gap: 10px;
		padding: 6px 0;
		border-bottom: 1px solid var(--border);
	}
	.row:last-child {
		border-bottom: 0;
	}
	.row.record .label {
		font-weight: 600;
	}
	.label {
		text-align: center;
		font-size: 0.85rem;
		color: var(--muted);
	}
	.value {
		font-weight: 600;
	}
	.value.best {
		color: var(--good);
	}
	.right {
		text-align: right;
	}
	.bars {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 2px;
		height: 5px;
		margin-top: 3px;
	}
	.half {
		display: flex;
	}
	.half.left {
		justify-content: flex-end;
	}
	.bar {
		display: block;
		height: 100%;
		background: var(--border);
		border-radius: 0 3px 3px 0;
	}
	.half.left .bar {
		border-radius: 3px 0 0 3px;
	}
	.bar.best {
		background: var(--good);
	}
</style>

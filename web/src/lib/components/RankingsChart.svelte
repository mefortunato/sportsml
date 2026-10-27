<script lang="ts">
	import { signed } from '$lib/format';
	import { rankAt, yExtent, type Pins } from '$lib/rankings';
	import type { RankingSeason } from '$lib/types';

	// Every team's rating by date: highlighted teams in their series color with
	// an end label, the rest as thin gray context. Hover finds the nearest
	// line; click highlights it.
	let {
		season,
		dateLabel = 'Week',
		pins,
		visible = null,
		index = $bindable(null),
		ontoggle
	}: {
		season: RankingSeason;
		dateLabel?: string;
		pins: Pins;
		/** Teams to draw (null: all). The axis and ranks stay league-wide. */
		visible?: Set<string> | null;
		/** Hovered date index (null: none). */
		index?: number | null;
		ontoggle: (team: string) => void;
	} = $props();

	// drawn at the container's own width, so text stays 12px on phones too
	let width = $state(760);
	const W = $derived(Math.max(300, Math.round(width)));
	const narrow = $derived(W < 560);
	const H = $derived(narrow ? 320 : 400);
	// the right margin holds the end labels: wide enough for the longest one,
	// using teams' short abbreviations when full names (college teams are
	// keyed by school name) would take more than a third of the chart
	const CHAR = 7; // px per character of a 12px label, a little generous
	const labelSpace = (texts: string[]) =>
		24 + CHAR * Math.max(0, ...texts.map((t) => t.length));
	const labelTexts = $derived.by(() => {
		const labelled = labelledLines();
		const full = labelled.map((l) => `${l.key} ${signed(l.value)}`);
		if (labelSpace(full) <= W / 3) return new Map(labelled.map((l, i) => [l.key, full[i]]));
		return new Map(labelled.map((l) => [l.key, `${l.team.abbr ?? l.key} ${signed(l.value)}`]));
	});
	const M = $derived({
		top: 14,
		right: Math.max(narrow ? 74 : 92, labelSpace([...labelTexts.values()])),
		bottom: 34,
		left: 40
	});
	const plotW = $derived(W - M.left - M.right);
	const plotH = $derived(H - M.top - M.bottom);

	const extent = $derived(yExtent(season));
	const first = $derived(season.dates[0]);
	const last = $derived(season.dates[season.dates.length - 1]);
	const x = (date: number) =>
		M.left + (last === first ? plotW / 2 : ((date - first) / (last - first)) * plotW);
	const y = (value: number) => M.top + ((extent.max - value) / (2 * extent.max)) * plotH;

	const yTicks = $derived.by(() => {
		const ticks = [];
		for (let v = -extent.max; v <= extent.max + 1e-9; v += extent.step) ticks.push(v);
		return ticks;
	});
	const xTicks = $derived.by(() => {
		const every = Math.ceil(season.dates.length / (narrow ? 8 : 14));
		return season.dates.filter((_, i) => i % every === 0 || i === season.dates.length - 1);
	});

	function path(ratings: (number | null)[]) {
		let d = '';
		let open = false;
		ratings.forEach((v, i) => {
			if (v === null) {
				open = false;
				return;
			}
			d += `${open ? 'L' : 'M'}${x(season.dates[i]).toFixed(1)},${y(v).toFixed(1)}`;
			open = true;
		});
		return d;
	}

	let hoverTeam = $state<string | null>(null);

	const lines = $derived(
		season.teams
			.filter((t) => !visible || visible.has(t.team.team))
			.map((t) => ({ key: t.team.team, team: t.team, ratings: t.ratings, d: path(t.ratings) }))
	);
	const pinned = $derived(
		lines.filter((l) => l.key in pins).sort((a, b) => pins[a.key] - pins[b.key])
	);

	// end labels for highlighted teams (for every line when only a few are
	// drawn, so none is identified by color alone), nudged apart
	const LABEL_ALL = 4;
	// from the season itself, not `lines`: the right margin depends on these
	// labels, and `lines` is drawn with that margin
	function labelledLines() {
		const drawn = season.teams.filter((t) => !visible || visible.has(t.team.team));
		const labelled = drawn.length <= LABEL_ALL ? drawn : drawn.filter((t) => t.team.team in pins);
		return labelled
			.map((t) => {
				let i = t.ratings.length - 1;
				while (i >= 0 && t.ratings[i] === null) i--;
				return i < 0 ? null : { key: t.team.team, team: t.team, value: t.ratings[i] as number };
			})
			.filter((l) => l !== null);
	}
	const endLabels = $derived.by(() => {
		const labels = labelledLines()
			.map((l) => ({
				key: l.key,
				slot: pins[l.key] as number | undefined,
				value: l.value,
				text: labelTexts.get(l.key) ?? l.key,
				at: y(l.value)
			}))
			.sort((a, b) => a.at - b.at);
		for (let i = 1; i < labels.length; i++)
			labels[i].at = Math.max(labels[i].at, labels[i - 1].at + 15);
		return labels;
	});

	const shown = $derived(index ?? season.dates.length - 1);
	const rows = $derived(rankAt(season, shown));
	const rankOf = $derived(new Map(rows.map((r) => [r.team.team, r])));
	const tipTeams = $derived(
		[...pinned.map((l) => l.key), ...(hoverTeam && !(hoverTeam in pins) ? [hoverTeam] : [])]
			.map((key) => rankOf.get(key))
			.filter((r) => r !== undefined)
			.sort((a, b) => a.rank - b.rank)
	);

	let svg: SVGSVGElement;

	function locate(event: PointerEvent) {
		const box = svg.getBoundingClientRect();
		const px = ((event.clientX - box.left) / box.width) * W;
		const py = ((event.clientY - box.top) / box.height) * H;
		let best = 0;
		season.dates.forEach((date, i) => {
			if (Math.abs(x(date) - px) < Math.abs(x(season.dates[best]) - px)) best = i;
		});
		index = best;
		// nearest line at that date, within a forgiving hit distance
		let nearest: string | null = null;
		let distance = 18;
		for (const l of lines) {
			const v = l.ratings[best];
			if (v === null) continue;
			const dy = Math.abs(y(v) - py);
			if (dy < distance) [nearest, distance] = [l.key, dy];
		}
		hoverTeam = nearest;
	}

	function leave() {
		index = null;
		hoverTeam = null;
	}

	function key(event: KeyboardEvent) {
		const n = season.dates.length;
		if (event.key === 'ArrowLeft') index = Math.max(0, (index ?? n - 1) - 1);
		else if (event.key === 'ArrowRight') index = Math.min(n - 1, (index ?? n - 1) + 1);
		else if (event.key === 'Escape') leave();
		else return;
		event.preventDefault();
	}

	const tipLeft = $derived(index === null ? 0 : (x(season.dates[index]) / W) * 100);
</script>

<div
	class="chart"
	bind:clientWidth={width}
	role="slider"
	tabindex="0"
	aria-label="{dateLabel} shown in the table below; left and right arrows step through {dateLabel.toLowerCase()}s"
	aria-valuemin={first}
	aria-valuemax={last}
	aria-valuenow={season.dates[shown]}
	aria-valuetext="{dateLabel} {season.dates[shown]}"
	onpointermove={locate}
	onpointerdown={locate}
	onpointerleave={leave}
	onclick={() => hoverTeam && ontoggle(hoverTeam)}
	onkeydown={key}
	class:pointing={hoverTeam !== null}
>
	<svg
		bind:this={svg}
		viewBox="0 0 {W} {H}"
		role="img"
		aria-label="Average predicted margin of every team by {dateLabel.toLowerCase()}"
	>
		{#each yTicks as tick (tick)}
			<line class="grid" class:zero={tick === 0} x1={M.left} x2={M.left + plotW} y1={y(tick)} y2={y(tick)} />
			<text class="tick" x={M.left - 8} y={y(tick)} text-anchor="end" dominant-baseline="middle"
				>{tick === 0 ? '0' : signed(tick, 0)}</text
			>
		{/each}
		{#each xTicks as date (date)}
			<text class="tick" x={x(date)} y={M.top + plotH + 20} text-anchor="middle">{date}</text>
		{/each}
		<text class="axis" x={M.left + plotW / 2} y={H - 2} text-anchor="middle">{dateLabel}</text>

		{#if index !== null}
			<line class="crosshair" x1={x(season.dates[index])} x2={x(season.dates[index])} y1={M.top} y2={M.top + plotH} />
		{/if}

		{#each lines as l (l.key)}
			{#if !(l.key in pins) && l.key !== hoverTeam}
				<path class="context" d={l.d} />
			{/if}
		{/each}
		{#each lines as l (l.key)}
			{#if l.key === hoverTeam && !(l.key in pins)}
				<path class="halo" d={l.d} />
				<path class="hover" d={l.d} />
			{/if}
		{/each}
		{#each pinned as l (l.key)}
			<path class="halo" d={l.d} />
			<path class="pinned" d={l.d} style:stroke="var(--series-{pins[l.key]})" class:emphasis={l.key === hoverTeam} />
		{/each}

		{#if index !== null}
			{#each tipTeams as row (row.team.team)}
				<circle
					class="marker"
					cx={x(season.dates[index])}
					cy={y(row.rating)}
					r="4.5"
					style:fill={row.team.team in pins ? `var(--series-${pins[row.team.team]})` : 'var(--text)'}
				/>
			{/each}
		{/if}

		{#each endLabels as label (label.key)}
			<circle
				class="swatch"
				cx={M.left + plotW + 10}
				cy={label.at}
				r="4"
				style:fill={label.slot ? `var(--series-${label.slot})` : 'var(--context-line)'}
			/>
			<text class="end" class:context={!label.slot} x={M.left + plotW + 18} y={label.at} dominant-baseline="middle"
				>{label.text}</text
			>
		{/each}
	</svg>

	{#if index !== null && tipTeams.length}
		<div class="tooltip" style:left="{tipLeft}%" class:flip={tipLeft > 60}>
			<div class="tip-head">{dateLabel} {season.dates[index]}</div>
			{#each tipTeams as row (row.team.team)}
				<div class="tip-row">
					<span
						class="dot"
						style:background={row.team.team in pins ? `var(--series-${pins[row.team.team]})` : 'var(--text)'}
					></span>
					<span class="tip-team">#{row.rank} {row.team.team}</span>
					<span class="tabular">{signed(row.rating)}</span>
				</div>
			{/each}
			{#if hoverTeam && !(hoverTeam in pins)}
				<div class="tip-hint">Click to highlight</div>
			{/if}
		</div>
	{/if}
</div>

<style>
	.chart {
		position: relative;
	}
	svg {
		display: block;
		width: 100%;
		height: auto;
		touch-action: pan-y;
	}
	.chart.pointing {
		cursor: pointer;
	}
	.chart:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
		border-radius: 6px;
	}
	.grid {
		stroke: var(--border);
		stroke-width: 1;
	}
	.grid.zero {
		stroke: var(--muted);
		stroke-opacity: 0.6;
	}
	.tick,
	.axis {
		fill: var(--muted);
		font-size: 12px;
		font-variant-numeric: tabular-nums;
	}
	.crosshair {
		stroke: var(--muted);
		stroke-opacity: 0.5;
	}
	path {
		fill: none;
		stroke-linejoin: round;
		stroke-linecap: round;
	}
	.context {
		stroke: var(--context-line);
		stroke-width: 1.25;
	}
	.halo {
		stroke: var(--surface);
		stroke-width: 5;
	}
	.hover {
		stroke: var(--text);
		stroke-width: 2;
	}
	.pinned {
		stroke-width: 2.25;
	}
	.pinned.emphasis {
		stroke-width: 3;
	}
	.marker {
		stroke: var(--surface);
		stroke-width: 2;
	}
	.end {
		fill: var(--text);
		font-size: 12px;
		font-weight: 600;
		font-variant-numeric: tabular-nums;
	}
	.end.context {
		fill: var(--muted);
		font-weight: 500;
	}
	.tooltip {
		position: absolute;
		top: 8px;
		transform: translateX(12px);
		pointer-events: none;
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: 8px;
		box-shadow: var(--shadow);
		padding: 8px 10px;
		font-size: 0.8rem;
		min-width: 130px;
	}
	.tooltip.flip {
		transform: translateX(calc(-100% - 12px));
	}
	.tip-head {
		font-weight: 600;
		margin-bottom: 4px;
	}
	.tip-row {
		display: grid;
		grid-template-columns: auto 1fr auto;
		gap: 6px;
		align-items: center;
	}
	.dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
	}
	.tip-hint {
		color: var(--muted);
		margin-top: 4px;
	}
</style>

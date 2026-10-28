<script lang="ts">
	import type { Team } from '$lib/types';

	let {
		team,
		size = 28,
		label = 'abbr'
	}: { team: Team; size?: number; label?: 'abbr' | 'name' | 'nickname' | 'none' } = $props();

	// the team-colored chip shows until the logo has loaded, and stays if it fails.
	// Keyed by URL: a reused badge (e.g. the next challenge game) starts over.
	let loadedLogo = $state<string>();
	let failedLogo = $state<string>();
	const loaded = $derived(!!team.logo && loadedLogo === team.logo);
	const failed = $derived(!!team.logo && failedLogo === team.logo);
	// chip text: the second team color where it reads on the first (contrast
	// 3:1 or more), else white or black, whichever reads better
	function luminance(hex: string): number | null {
		const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
		if (!m) return null;
		const [r, g, b] = [0, 2, 4].map((i) => {
			const c = parseInt(m[1].slice(i, i + 2), 16) / 255;
			return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
		});
		return 0.2126 * r + 0.7152 * g + 0.0722 * b;
	}
	const contrast = (a: number, b: number) => (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
	const chipText = $derived.by(() => {
		const bg = team.color ? luminance(team.color) : null;
		if (bg === null) return '#fff';
		const second = team.color2 ? luminance(team.color2) : null;
		if (second !== null && contrast(bg, second) >= 3) return team.color2;
		return contrast(bg, 1) >= contrast(bg, 0) ? '#fff' : '#000';
	});
	const text = $derived(
		label === 'name'
			? team.name
			: label === 'nickname'
				? (team.nickname ?? team.name)
				: (team.abbr ?? team.team)
	);
</script>

<span class="badge" title={team.name}>
	<span class="mark" style:width="{size}px" style:height="{size}px">
		{#if !loaded}
			<span
				class="chip"
				style:background={team.color ?? 'var(--muted)'}
				style:color={chipText}
				style:font-size="{Math.max(9, size * 0.32)}px">{team.abbr ?? team.team}</span
			>
		{/if}
		{#if team.logo && !failed}
			<img
				src={team.logo}
				alt=""
				width={size}
				height={size}
				loading="lazy"
				class:loaded
				onload={() => (loadedLogo = team.logo)}
				onerror={() => (failedLogo = team.logo)}
			/>
		{/if}
	</span>
	{#if label !== 'none'}
		<span class="label">{text}</span>
	{/if}
</span>

<style>
	.badge {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		min-width: 0;
	}
	.mark {
		position: relative;
		flex: none;
	}
	img {
		position: absolute;
		inset: 0;
		object-fit: contain;
		opacity: 0;
	}
	img.loaded {
		opacity: 1;
	}
	.chip {
		position: absolute;
		inset: 0;
		display: grid;
		place-items: center;
		border-radius: 50%;
		font-weight: 700;
	}
	.label {
		font-weight: 600;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
</style>

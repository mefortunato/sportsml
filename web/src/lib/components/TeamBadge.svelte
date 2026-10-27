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
				style:color={team.color2 && team.color2 !== team.color ? team.color2 : '#fff'}
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

<script lang="ts">
	let { data } = $props();
</script>

<div class="container section">
	{#if data.sports.length === 0}
		<div class="card">
			<h1>No data yet</h1>
			<p class="muted">Run <code>sportsml web build</code> to prepare predictions.</p>
		</div>
	{:else}
		<h1>Choose a sport</h1>
		<div class="grid-2">
			{#each data.sports as sport (sport.sport)}
				<a class="card" href="/{sport.sport}"><h2>{sport.label}</h2></a>
			{/each}
		</div>
	{/if}
</div>

<script lang="ts">
	// The landing page's explainer: one made-up game walked through the whole
	// loop (recent games -> model -> prediction -> Vegas's line -> scored).
	// Colors are the theme tokens, so it follows light and dark; with reduced
	// motion it does not play on its own and nothing slides.
	import { onMount } from 'svelte';

	const STEPS = [
		{
			title: 'Recent games',
			text: "Start from each team's recent games: who won, by how much, the box-score stats and where it was played."
		},
		{
			title: 'The model reads them',
			text: 'A neural network reads both histories and has learned, from years of past games, what tends to decide a matchup.'
		},
		{
			title: 'A prediction',
			text: 'It predicts the margin, Home by 4.5, and turns it into each team\'s chance to win.'
		},
		{
			title: 'Next to Vegas',
			text: "The betting line has Home by 2.5. The model expects 2 points more, so its pick is Home to cover."
		},
		{
			title: 'Scored',
			text: 'Home wins by 7: the pick was right. Every past season is replayed like this, so the site can show how often the model beats Vegas, and how often it does not.'
		}
	];
	// how long each step stays up (ms); the last one longer before the loop
	const DURATION = [3200, 3200, 3400, 3800, 5200];

	// past results, positive = won by (most recent last)
	const HOME = [7, -3, 14, 10, -6, 3, 21, -2];
	const AWAY = [-10, 4, -7, 3, -14, 6, -3, -1];
	const MAX = 21;

	// the number line runs Away by 10 ... Home by 10
	const RANGE = 10;
	const MODEL = 4.5;
	const VEGAS = 2.5;
	const FINAL = 7;
	const WIN = 0.63; // P(Home wins) at a 4.5-point margin
	const at = (margin: number) => 50 + (margin / RANGE) * 50;

	let step = $state(0);
	let playing = $state(true);
	let visible = $state(true);
	let reduced = $state(false);
	let root: HTMLElement;

	onMount(() => {
		const query = window.matchMedia('(prefers-reduced-motion: reduce)');
		reduced = query.matches;
		if (reduced) {
			playing = false;
			step = STEPS.length - 1;
		}
		const onChange = () => (reduced = query.matches);
		query.addEventListener('change', onChange);
		// only run while on screen
		const observer = new IntersectionObserver(([entry]) => (visible = entry.isIntersecting));
		observer.observe(root);
		return () => {
			query.removeEventListener('change', onChange);
			observer.disconnect();
		};
	});

	$effect(() => {
		if (!playing || !visible) return;
		const timer = setTimeout(() => (step = (step + 1) % STEPS.length), DURATION[step]);
		return () => clearTimeout(timer);
	});

	function go(index: number) {
		step = index;
		playing = false;
	}

	function bars(results: number[]) {
		const w = 160 / results.length;
		return results.map((m, i) => {
			const h = (Math.abs(m) / MAX) * 26;
			return { x: i * w + 3, w: w - 6, y: m > 0 ? 30 - h : 30, h, up: m > 0, i };
		});
	}
</script>

<section class="card how" class:still={reduced} bind:this={root} aria-labelledby="how-title">
	<div class="top">
		<h2 id="how-title">How it works, in one game</h2>
		<button
			class="toggle"
			type="button"
			onclick={() => (playing = !playing)}
			aria-pressed={!playing}
			aria-label={playing ? 'Pause the animation' : 'Play the animation'}
		>
			{#if playing}
				<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="3" y="2" width="3.5" height="12" rx="1" /><rect x="9.5" y="2" width="3.5" height="12" rx="1" /></svg>
				Pause
			{:else}
				<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 2.5v11l9.5-5.5z" /></svg>
				Play
			{/if}
		</button>
	</div>

	<div class="stage" aria-hidden="true">
		<!-- 1: both teams' recent games -->
		<div class="panel history" class:lit={step === 0}>
			<div class="label">Recent games</div>
			{#each [{ name: 'Home', games: HOME, cls: 'home' }, { name: 'Away', games: AWAY, cls: 'away' }] as team (team.name)}
				<div class="team">
					<span class="name {team.cls}">{team.name}</span>
					<svg viewBox="0 0 160 60" class="bars {team.cls}" preserveAspectRatio="none">
						<line x1="0" x2="160" y1="30" y2="30" class="base" />
						{#each bars(team.games) as b (b.i)}
							<rect
								x={b.x}
								y={b.y}
								width={b.w}
								height={b.h}
								rx="1.5"
								class:up={b.up}
								style:animation-delay="{b.i * 90}ms"
							/>
						{/each}
					</svg>
				</div>
			{/each}
			<div class="key"><span>▲ won by</span><span>▼ lost by</span></div>
		</div>

		<div class="flow" class:on={step >= 1}><span></span><span></span><span></span></div>

		<!-- 2: the model -->
		<div class="panel model" class:lit={step === 1} class:on={step >= 1}>
			<div class="label">Model</div>
			<svg viewBox="0 0 120 90" class="net">
				{#each [15, 45, 75] as y1 (y1)}
					{#each [10, 32, 58, 80] as y2 (y2)}
						<line x1="16" y1={y1} x2="60" y2={y2} />
						<line x1="60" y1={y2} x2="104" y2="45" />
					{/each}
				{/each}
				{#each [15, 45, 75] as y, i (y)}<circle cx="16" cy={y} r="6" style:animation-delay="{i * 120}ms" />{/each}
				{#each [10, 32, 58, 80] as y, i (y)}<circle cx="60" cy={y} r="6" style:animation-delay="{360 + i * 120}ms" />{/each}
				<circle cx="104" cy="45" r="8" class="out" style:animation-delay="900ms" />
			</svg>
			<div class="caption">Learned from years of games</div>
		</div>

		<div class="flow" class:on={step >= 2}><span></span><span></span><span></span></div>

		<!-- 3-5: prediction, Vegas, result -->
		<div class="panel output" class:lit={step >= 2}>
			<div class="label">Prediction</div>
			<div class="line">
				<div class="gap" class:on={step >= 3} style:left="{at(VEGAS)}%" style:width="{at(MODEL) - at(VEGAS)}%"></div>
				<div class="axis"></div>
				<div class="tick" style:left="50%"></div>
				<div class="mark vegas" class:on={step >= 3} style:left="{at(VEGAS)}%">
					<span class="tag">Vegas<br /><b>+2.5</b></span>
				</div>
				<div class="mark model" class:on={step >= 2} style:left="{step >= 2 ? at(MODEL) : 50}%">
					<span class="tag">Model<br /><b>+4.5</b></span>
				</div>
				<div class="mark final" class:on={step >= 4} style:left="{at(FINAL)}%">
					<span class="tag">Final<br /><b>+7</b></span>
				</div>
			</div>
			<div class="ends"><span>Away by 10</span><span>Even</span><span>Home by 10</span></div>

			<div class="win" class:on={step >= 2}>
				<div class="win-labels"><span>Away {Math.round((1 - WIN) * 100)}%</span><span>chance to win</span><span>{Math.round(WIN * 100)}% Home</span></div>
				<div class="win-bar">
					<div class="away" style:width="{step >= 2 ? (1 - WIN) * 100 : 50}%"></div>
					<div class="home"></div>
				</div>
			</div>

			<div class="verdict">
				<span class="pick" class:on={step === 3}>Pick: Home −2.5</span>
				<span class="right" class:on={step >= 4}>✓ Home won 27–20, pick right</span>
			</div>
		</div>
	</div>

	<ol class="steps">
		{#each STEPS as s, i (s.title)}
			<li class:active={i === step} class:done={i < step}>
				<button type="button" onclick={() => go(i)} aria-current={i === step ? 'step' : undefined}>
					<span class="n">{i + 1}</span>
					<span class="t">{s.title}</span>
				</button>
			</li>
		{/each}
	</ol>
	<p class="text" aria-live={playing ? 'off' : 'polite'}>
		<strong>{STEPS[step].title}.</strong>
		{STEPS[step].text}
	</p>
	<p class="muted small note">An illustration with made-up teams, not a real prediction.</p>
</section>

<style>
	.how {
		--home: var(--series-1);
		--away: var(--series-2);
		--model: var(--accent);
		--ease: cubic-bezier(0.22, 1, 0.36, 1);
		display: grid;
		gap: 14px;
	}
	.top {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 8px;
	}
	.top h2 {
		margin: 0;
	}
	.toggle {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		padding: 4px 10px;
		font-size: 0.8rem;
		background: var(--surface-2);
	}
	.toggle svg {
		width: 12px;
		height: 12px;
		fill: currentColor;
	}

	/* the three panels with the flow between them */
	.stage {
		display: grid;
		grid-template-columns: minmax(0, 1fr) 36px minmax(0, 0.8fr) 36px minmax(0, 1.4fr);
		align-items: stretch;
	}
	.panel {
		border: 1px solid var(--border);
		border-radius: 8px;
		background: var(--surface-2);
		padding: 12px;
		display: grid;
		gap: 8px;
		align-content: start;
		transition:
			border-color 0.4s,
			box-shadow 0.4s;
	}
	.panel.lit {
		border-color: var(--model);
		box-shadow: 0 0 0 3px var(--accent-soft);
	}
	.label {
		font-size: 0.72rem;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--muted);
	}

	/* recent games */
	.team {
		display: grid;
		grid-template-columns: 44px minmax(0, 1fr);
		align-items: center;
		gap: 6px;
	}
	.name {
		font-weight: 700;
		font-size: 0.85rem;
	}
	.name.home {
		color: var(--home);
	}
	.name.away {
		color: var(--away);
	}
	.bars {
		width: 100%;
		height: 52px;
		overflow: visible;
	}
	.bars .base {
		stroke: var(--context-line);
		stroke-width: 1;
		vector-effect: non-scaling-stroke;
	}
	.bars.home rect {
		fill: var(--home);
	}
	.bars.away rect {
		fill: var(--away);
	}
	.bars rect {
		transform-box: fill-box;
		transform-origin: top;
	}
	.bars rect.up {
		transform-origin: bottom;
	}
	/* bars regrow each time the loop comes back round */
	.how:not(.still) .history.lit .bars rect {
		animation: grow 0.5s var(--ease) backwards;
	}
	@keyframes grow {
		from {
			transform: scaleY(0);
		}
	}
	.key {
		display: flex;
		gap: 12px;
		font-size: 0.72rem;
		color: var(--muted);
	}

	/* dots flowing from one panel to the next */
	.flow {
		position: relative;
		align-self: center;
		height: 2px;
		margin: 0 4px;
		background: var(--border);
	}
	.flow::after {
		content: '';
		position: absolute;
		right: -2px;
		top: -4px;
		border: 5px solid transparent;
		border-left-color: var(--border);
		border-right: 0;
	}
	.flow.on {
		background: var(--model);
	}
	.flow.on::after {
		border-left-color: var(--model);
	}
	.flow span {
		position: absolute;
		top: -3px;
		left: 0;
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: var(--model);
		opacity: 0;
	}
	.how:not(.still) .flow.on span {
		animation: travel 1.2s linear infinite;
	}
	.flow span:nth-child(2) {
		animation-delay: 0.4s !important;
	}
	.flow span:nth-child(3) {
		animation-delay: 0.8s !important;
	}
	@keyframes travel {
		0% {
			left: 0;
			opacity: 0;
		}
		20% {
			opacity: 1;
		}
		80% {
			opacity: 1;
		}
		100% {
			left: calc(100% - 8px);
			opacity: 0;
		}
	}

	/* the model */
	.model {
		justify-items: center;
		text-align: center;
	}
	.model .label {
		justify-self: stretch;
		text-align: left;
	}
	.net {
		width: 100%;
		max-width: 140px;
		height: auto;
	}
	.net line {
		stroke: var(--context-line);
		stroke-width: 1;
		transition: stroke 0.4s;
	}
	.net circle {
		fill: var(--surface);
		stroke: var(--muted);
		stroke-width: 1.5;
		transition:
			fill 0.4s,
			stroke 0.4s;
	}
	.model.on .net line {
		stroke: var(--accent-soft);
	}
	.model.on .net circle {
		stroke: var(--model);
	}
	.model.on .net circle.out {
		fill: var(--model);
	}
	.how:not(.still) .model.lit .net circle {
		animation: pulse 1.2s ease-in-out infinite both;
	}
	@keyframes pulse {
		0%,
		100% {
			fill: var(--surface);
		}
		40% {
			fill: var(--model);
		}
	}
	.caption {
		font-size: 0.75rem;
		color: var(--muted);
	}

	/* the margin number line */
	.line {
		position: relative;
		height: 64px;
		margin: 0 22px;
	}
	.axis {
		position: absolute;
		left: 0;
		right: 0;
		bottom: 10px;
		height: 2px;
		background: var(--border);
	}
	.tick {
		position: absolute;
		bottom: 4px;
		width: 2px;
		height: 14px;
		margin-left: -1px;
		background: var(--border);
	}
	.gap {
		position: absolute;
		bottom: 4px;
		height: 14px;
		background: var(--accent-soft);
		border-radius: 3px;
		opacity: 0;
		transition: opacity 0.5s 0.3s;
	}
	.gap.on {
		opacity: 1;
	}
	.mark {
		position: absolute;
		bottom: 4px;
		width: 14px;
		height: 14px;
		margin-left: -7px;
		border-radius: 50%;
		border: 2px solid var(--surface);
		opacity: 0;
		transform: scale(0.4);
		transition:
			left 0.9s var(--ease),
			opacity 0.4s,
			transform 0.4s var(--ease);
	}
	.mark.on {
		opacity: 1;
		transform: scale(1);
	}
	.mark .tag {
		position: absolute;
		left: 50%;
		bottom: 18px;
		transform: translateX(-50%);
		font-size: 0.7rem;
		line-height: 1.15;
		text-align: center;
		white-space: nowrap;
		color: var(--muted);
	}
	.mark .tag b {
		font-size: 0.85rem;
		font-variant-numeric: tabular-nums;
	}
	.mark.model {
		background: var(--model);
		z-index: 2;
	}
	.mark.model b {
		color: var(--model);
	}
	.mark.vegas {
		background: var(--vegas);
		border-radius: 3px;
	}
	.mark.vegas b {
		color: var(--vegas);
	}
	/* the Vegas tag sits low and to the left so it clears the model's */
	.mark.vegas .tag {
		transform: translateX(-100%);
		left: -2px;
		bottom: 14px;
		text-align: right;
	}
	.mark.final {
		background: var(--good);
		transform: scale(0.4) rotate(45deg);
		border-radius: 2px;
	}
	.mark.final.on {
		transform: scale(1) rotate(45deg);
	}
	.mark.final .tag {
		/* undo the diamond's rotation and sit to the right */
		transform: rotate(-45deg) translate(10px, -18px);
		transform-origin: 0 0;
		left: 0;
		top: 0;
		text-align: left;
	}
	.mark.final b {
		color: var(--good);
	}
	.ends {
		display: flex;
		justify-content: space-between;
		font-size: 0.7rem;
		color: var(--muted);
		margin-top: -4px;
	}

	/* win probability */
	.win {
		opacity: 0.35;
		transition: opacity 0.5s;
	}
	.win.on {
		opacity: 1;
	}
	.win-labels {
		display: flex;
		justify-content: space-between;
		font-size: 0.75rem;
		margin-bottom: 4px;
		font-variant-numeric: tabular-nums;
	}
	.win-labels span:nth-child(2) {
		color: var(--muted);
	}
	.win-labels span:first-child {
		color: var(--away);
		font-weight: 700;
	}
	.win-labels span:last-child {
		color: var(--home);
		font-weight: 700;
	}
	.win:not(.on) .win-labels span:first-child,
	.win:not(.on) .win-labels span:last-child {
		visibility: hidden;
	}
	.win-bar {
		display: flex;
		gap: 2px;
		height: 8px;
		border-radius: 999px;
		overflow: hidden;
	}
	.win-bar .away {
		background: var(--away);
		transition: width 1s var(--ease);
	}
	.win-bar .home {
		flex: 1;
		background: var(--home);
	}
	.win:not(.on) .win-bar div {
		background: var(--border);
	}

	/* the pick and how it went */
	.verdict {
		display: grid;
		min-height: 26px;
	}
	.verdict > span {
		grid-area: 1 / 1;
		justify-self: start;
		align-self: center;
		font-size: 0.82rem;
		font-weight: 700;
		padding: 3px 10px;
		border-radius: 999px;
		opacity: 0;
		transform: translateY(4px);
		transition:
			opacity 0.4s,
			transform 0.4s var(--ease);
	}
	.verdict > span.on {
		opacity: 1;
		transform: none;
	}
	.pick {
		background: var(--accent-soft);
		color: var(--model);
		transition-delay: 0.5s !important;
	}
	.right {
		background: var(--good-soft);
		color: var(--good);
	}

	/* steps and caption */
	.steps {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		grid-template-columns: repeat(5, minmax(0, 1fr));
		gap: 6px;
	}
	.steps button {
		width: 100%;
		display: flex;
		align-items: center;
		gap: 6px;
		padding: 6px 8px;
		font-size: 0.8rem;
		text-align: left;
		color: var(--muted);
		background: transparent;
		border-color: var(--border);
		position: relative;
		overflow: hidden;
	}
	.steps .n {
		flex: none;
		display: inline-grid;
		place-items: center;
		width: 20px;
		height: 20px;
		border-radius: 50%;
		font-size: 0.72rem;
		font-weight: 700;
		background: var(--surface-2);
		border: 1px solid var(--border);
	}
	.steps .done button {
		color: var(--text);
	}
	.steps .active button {
		color: var(--text);
		font-weight: 600;
		border-color: var(--model);
		background: var(--accent-soft);
	}
	.steps .active .n,
	.steps .done .n {
		background: var(--model);
		border-color: var(--model);
		color: var(--surface);
	}
	.text {
		margin: 0;
		min-height: 3em;
		line-height: 1.5;
		max-width: 70ch;
	}
	.note {
		margin: -6px 0 0;
	}

	.still *,
	.still *::before,
	.still *::after {
		transition: none !important;
		animation: none !important;
	}

	@media (max-width: 760px) {
		/* the words above the picture, so both fit on a phone screen */
		.steps,
		.text {
			order: -1;
		}
		.top {
			order: -2;
		}
		.stage {
			grid-template-columns: minmax(0, 1fr);
			grid-template-rows: auto 28px auto 28px auto;
		}
		.flow {
			justify-self: center;
			width: 2px;
			height: auto;
			align-self: stretch;
			margin: 4px 0;
		}
		.flow::after {
			right: auto;
			left: -4px;
			top: auto;
			bottom: -2px;
			border: 5px solid transparent;
			border-top-color: var(--border);
			border-bottom: 0;
		}
		.flow.on::after {
			border-top-color: var(--model);
			border-left-color: transparent;
		}
		.flow span {
			left: -3px;
		}
		.how:not(.still) .flow.on span {
			animation-name: travel-down;
		}
		.model {
			grid-template-columns: auto minmax(0, 1fr);
			align-items: center;
			text-align: left;
		}
		.model .label {
			grid-column: 1 / -1;
		}
		.net {
			width: 110px;
		}
		.steps {
			grid-template-columns: repeat(5, minmax(0, 1fr));
		}
		.steps .t {
			display: none;
		}
		.steps button {
			justify-content: center;
		}
	}
	@keyframes travel-down {
		0% {
			top: 0;
			opacity: 0;
		}
		20%,
		80% {
			opacity: 1;
		}
		100% {
			top: calc(100% - 8px);
			opacity: 0;
		}
	}
</style>

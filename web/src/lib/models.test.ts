import { describe, expect, it } from 'vitest';
import { modelInfo } from './models';

describe('modelInfo', () => {
	it('describes the served family', () => {
		expect(modelInfo('calibrated_elo').name).toBe('Elo');
		expect(modelInfo('transformer').source).toContain('transformer');
	});

	it('falls back to a generic description', () => {
		for (const family of [undefined, null, 'gnn']) {
			expect(modelInfo(family).name).toBe('Model');
		}
	});
});

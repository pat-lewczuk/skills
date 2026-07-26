import { expect, it } from 'vitest';

import { clamp, mean, sum } from './sum.js';

it('sums', () => expect(sum([1, 2, 3])).toBe(6));
it('averages', () => expect(mean([2, 4])).toBe(3));
it('clamps the upper bound', () => expect(clamp(5, 0, 3)).toBe(3));

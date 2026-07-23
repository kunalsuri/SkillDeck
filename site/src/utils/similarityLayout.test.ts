import { describe, test, expect } from 'vitest';
import { homePosition, pullFactor, pulledPosition, similarityTier } from './similarityLayout';

describe('homePosition', () => {
  test('centers when there are no neighbors', () => {
    expect(homePosition(0, 0)).toEqual({ x: 50, y: 50 });
  });

  test('spreads neighbors around the center, none exactly at center', () => {
    const points = Array.from({ length: 6 }, (_, i) => homePosition(i, 6));
    for (const p of points) {
      const dist = Math.hypot(p.x - 50, p.y - 50);
      expect(dist).toBeGreaterThan(20);
    }
  });

  test('is deterministic for the same index/total', () => {
    expect(homePosition(2, 8)).toEqual(homePosition(2, 8));
  });
});

describe('pullFactor', () => {
  test('near-zero scores do not pull at all', () => {
    expect(pullFactor(0)).toBe(0);
    expect(pullFactor(5)).toBe(0);
  });

  test('increases monotonically with score', () => {
    expect(pullFactor(20)).toBeLessThan(pullFactor(50));
    expect(pullFactor(50)).toBeLessThan(pullFactor(90));
  });

  test('never reaches 1 even at a perfect score', () => {
    expect(pullFactor(100)).toBeLessThan(1);
    expect(pullFactor(100)).toBeGreaterThan(0.8);
  });
});

describe('pulledPosition', () => {
  const home = { x: 90, y: 10 };
  const anchor = { x: 50, y: 50 };

  test('stays at home when score is negligible', () => {
    expect(pulledPosition(home, anchor, 0)).toEqual(home);
  });

  test('moves toward the anchor as score rises, without reaching it', () => {
    const low = pulledPosition(home, anchor, 20);
    const high = pulledPosition(home, anchor, 90);
    const distHomeLow = Math.hypot(low.x - home.x, low.y - home.y);
    const distHomeHigh = Math.hypot(high.x - home.x, high.y - home.y);
    expect(distHomeHigh).toBeGreaterThan(distHomeLow);

    const distAnchorHigh = Math.hypot(high.x - anchor.x, high.y - anchor.y);
    expect(distAnchorHigh).toBeGreaterThan(0);
  });
});

describe('similarityTier', () => {
  test('buckets scores at the documented thresholds', () => {
    expect(similarityTier(90)).toBe('near-duplicate');
    expect(similarityTier(85)).toBe('near-duplicate');
    expect(similarityTier(84)).toBe('strong');
    expect(similarityTier(70)).toBe('strong');
    expect(similarityTier(69)).toBe('related');
    expect(similarityTier(40)).toBe('related');
    expect(similarityTier(39)).toBe('loose');
    expect(similarityTier(0)).toBe('loose');
  });
});

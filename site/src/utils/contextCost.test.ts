import { describe, test, expect } from 'vitest';
import { formatTokens, costBucket } from './contextCost';

describe('formatTokens', () => {
  test('formats sub-1000 counts as plain tokens', () => {
    expect(formatTokens(320)).toBe('~320 tokens');
    expect(formatTokens(499)).toBe('~499 tokens');
    expect(formatTokens(999)).toBe('~999 tokens');
  });

  test('formats 1000-9999 as one-decimal k', () => {
    expect(formatTokens(1000)).toBe('~1.0k tokens');
    expect(formatTokens(1200)).toBe('~1.2k tokens');
    expect(formatTokens(2000)).toBe('~2.0k tokens');
    expect(formatTokens(2001)).toBe('~2.0k tokens');
  });

  test('formats 10000+ as whole-number k with no decimal', () => {
    expect(formatTokens(10000)).toBe('~10k tokens');
    expect(formatTokens(12000)).toBe('~12k tokens');
  });
});

describe('costBucket', () => {
  test('light below 500', () => {
    expect(costBucket(0)).toBe('light');
    expect(costBucket(499)).toBe('light');
  });

  test('moderate from 500 to 2000 inclusive', () => {
    expect(costBucket(500)).toBe('moderate');
    expect(costBucket(1200)).toBe('moderate');
    expect(costBucket(2000)).toBe('moderate');
  });

  test('heavy above 2000', () => {
    expect(costBucket(2001)).toBe('heavy');
    expect(costBucket(10000)).toBe('heavy');
  });
});

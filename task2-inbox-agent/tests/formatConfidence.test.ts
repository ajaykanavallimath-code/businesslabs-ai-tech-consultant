import { formatConfidence } from '../src/utils/formatConfidence';

describe('formatConfidence', () => {
  describe('Valid numeric values', () => {
    test('formats proportion decimals (0..1) as percentages', () => {
      expect(formatConfidence(0.95)).toBe('95%');
      expect(formatConfidence(0.80)).toBe('80%');
      expect(formatConfidence(0.754)).toBe('75%');
      expect(formatConfidence(1.0)).toBe('100%');
      expect(formatConfidence(0.0)).toBe('0%');
      expect(formatConfidence(0)).toBe('0%');
    });

    test('formats numbers in 1..100 range as percentages', () => {
      expect(formatConfidence(85)).toBe('85%');
      expect(formatConfidence(100)).toBe('100%');
      expect(formatConfidence(50.4)).toBe('50%');
      expect(formatConfidence(99.9)).toBe('100%');
    });

    test('formats valid numeric strings', () => {
      expect(formatConfidence('0.85')).toBe('85%');
      expect(formatConfidence('0.92')).toBe('92%');
      expect(formatConfidence('85')).toBe('85%');
      expect(formatConfidence('95%')).toBe('95%');
      expect(formatConfidence('  80%  ')).toBe('80%');
    });
  });

  describe('Qualitative enum strings', () => {
    test('maps qualitative strings to expected percentages', () => {
      expect(formatConfidence('high')).toBe('90%');
      expect(formatConfidence('HIGH')).toBe('90%');
      expect(formatConfidence('medium')).toBe('75%');
      expect(formatConfidence('MEDIUM')).toBe('75%');
      expect(formatConfidence('low')).toBe('50%');
      expect(formatConfidence('LOW')).toBe('50%');
    });

    test('treats provisional or uncertain as not available', () => {
      expect(formatConfidence('provisional')).toBe('Not available');
      expect(formatConfidence('PROVISIONAL')).toBe('Not available');
      expect(formatConfidence('uncertain')).toBe('Not available');
      expect(formatConfidence('needs_clarification')).toBe('Not available');
    });
  });

  describe('Missing, null, and empty values', () => {
    test('returns "Not available" for null and undefined', () => {
      expect(formatConfidence(null)).toBe('Not available');
      expect(formatConfidence(undefined)).toBe('Not available');
      expect(formatConfidence()).toBe('Not available');
    });

    test('returns "Not available" for empty and whitespace strings', () => {
      expect(formatConfidence('')).toBe('Not available');
      expect(formatConfidence('   ')).toBe('Not available');
    });
  });

  describe('Non-numeric and invalid values', () => {
    test('returns "Not available" for invalid non-numeric strings', () => {
      expect(formatConfidence('invalid')).toBe('Not available');
      expect(formatConfidence('not_a_number')).toBe('Not available');
      expect(formatConfidence('abc')).toBe('Not available');
    });

    test('returns "Not available" for non-numeric types', () => {
      expect(formatConfidence(true)).toBe('Not available');
      expect(formatConfidence(false)).toBe('Not available');
      expect(formatConfidence({})).toBe('Not available');
      expect(formatConfidence([])).toBe('Not available');
      expect(formatConfidence(() => 0.5)).toBe('Not available');
    });

    test('returns "Not available" for NaN and Infinity', () => {
      expect(formatConfidence(NaN)).toBe('Not available');
      expect(formatConfidence(Infinity)).toBe('Not available');
      expect(formatConfidence(-Infinity)).toBe('Not available');
    });
  });

  describe('Out-of-range values', () => {
    test('returns "Not available" for numbers outside valid range', () => {
      expect(formatConfidence(-5)).toBe('Not available');
      expect(formatConfidence(-0.1)).toBe('Not available');
      expect(formatConfidence(105)).toBe('Not available');
      expect(formatConfidence(250)).toBe('Not available');
      expect(formatConfidence('-10%')).toBe('Not available');
      expect(formatConfidence('150%')).toBe('Not available');
    });
  });

  describe('Prioritization of confidenceScore over raw confidence', () => {
    test('uses numeric confidenceScore when available', () => {
      expect(formatConfidence('medium', 0.95)).toBe('95%');
      expect(formatConfidence('high', 0.70)).toBe('70%');
      expect(formatConfidence('provisional', 0.85)).toBe('85%');
    });

    test('falls back to raw confidence if confidenceScore is null or missing', () => {
      expect(formatConfidence('high', null)).toBe('90%');
      expect(formatConfidence('medium', undefined)).toBe('75%');
      expect(formatConfidence(0.88, null)).toBe('88%');
    });

    test('falls back to raw confidence if confidenceScore is invalid', () => {
      expect(formatConfidence('high', -1)).toBe('90%');
      expect(formatConfidence('medium', 'invalid')).toBe('75%');
    });
  });
});

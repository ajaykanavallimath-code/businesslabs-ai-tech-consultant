/**
 * Safely format a task confidence value as a percentage.
 * Handles numbers, proportion decimals (0..1), percentages (1..100), numeric strings,
 * qualitative enum values, and safely returns "Not available" for missing, null,
 * non-numeric, or out-of-range inputs.
 *
 * @param confidence Raw confidence value (enum, number, string, null, undefined)
 * @param confidenceScore Optional numeric confidence score from API
 * @returns Formatted percentage (e.g. "95%") or "Not available"
 */
export function formatConfidence(confidence?: unknown, confidenceScore?: unknown): string {
  // If a valid numeric confidenceScore is provided, prioritize it
  if (confidenceScore !== undefined && confidenceScore !== null && confidenceScore !== '') {
    const numScore = typeof confidenceScore === 'number' ? confidenceScore : Number(confidenceScore);
    if (!isNaN(numScore) && isFinite(numScore)) {
      if (numScore >= 0 && numScore <= 1) {
        return `${Math.round(numScore * 100)}%`;
      }
      if (numScore > 1 && numScore <= 100) {
        return `${Math.round(numScore)}%`;
      }
    }
  }

  // Handle missing, null, undefined, boolean, object, function
  if (confidence === undefined || confidence === null) {
    return 'Not available';
  }
  if (typeof confidence === 'boolean' || typeof confidence === 'object' || typeof confidence === 'function') {
    return 'Not available';
  }

  // Handle string values
  if (typeof confidence === 'string') {
    const trimmed = confidence.trim();
    if (!trimmed) {
      return 'Not available';
    }

    const lower = trimmed.toLowerCase();
    // Known qualitative enum values
    if (lower === 'high') {
      return '90%';
    }
    if (lower === 'medium') {
      return '75%';
    }
    if (lower === 'low') {
      return '50%';
    }
    if (lower === 'provisional' || lower === 'uncertain' || lower === 'needs_clarification') {
      return 'Not available';
    }

    // Percentage string e.g. "85%"
    if (trimmed.endsWith('%')) {
      const numPart = Number(trimmed.slice(0, -1).trim());
      if (!isNaN(numPart) && isFinite(numPart) && numPart >= 0 && numPart <= 100) {
        return `${Math.round(numPart)}%`;
      }
      return 'Not available';
    }

    // Numeric string e.g. "0.85" or "85"
    const parsed = Number(trimmed);
    if (isNaN(parsed) || !isFinite(parsed)) {
      return 'Not available';
    }

    if (parsed >= 0 && parsed <= 1) {
      return `${Math.round(parsed * 100)}%`;
    }
    if (parsed > 1 && parsed <= 100) {
      return `${Math.round(parsed)}%`;
    }
    return 'Not available';
  }

  // Handle numeric values
  if (typeof confidence === 'number') {
    if (isNaN(confidence) || !isFinite(confidence)) {
      return 'Not available';
    }
    if (confidence >= 0 && confidence <= 1) {
      return `${Math.round(confidence * 100)}%`;
    }
    if (confidence > 1 && confidence <= 100) {
      return `${Math.round(confidence)}%`;
    }
    return 'Not available';
  }

  return 'Not available';
}

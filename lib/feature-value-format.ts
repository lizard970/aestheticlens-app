const ratioField = /(^|_)(share|ratio|fraction|occupancy|coverage)(_|$)/;
const percentageField = /(^|_)percentage(_|$)/;
const integerField =
  /(^|_)(count|counts|width|height|rank|bins?|iterations?|bytes|channels|bit_depth)(_|$)/;

function fieldPath(path: string) {
  return path
    .replace(/^feature:[^#]+#/, '')
    .split('/')
    .filter((part) => part && !/^\d+$/.test(part))
    .join('_');
}

export function isRatioFeaturePath(path: string) {
  return ratioField.test(fieldPath(path));
}

export function formatFeatureNumber(value: number, path = '') {
  const field = fieldPath(path);
  if (percentageField.test(field)) return `${value.toFixed(1)}%`;
  if (ratioField.test(field)) return `${(value * 100).toFixed(1)}%`;
  if (Number.isInteger(value) && integerField.test(field)) return String(value);
  return value.toFixed(2);
}

export function formatFeatureValue(value: unknown, path = ''): string {
  if (typeof value === 'number') return formatFeatureNumber(value, path);
  if (value === null || value === undefined) return '—';
  if (typeof value === 'string') return value;
  if (typeof value === 'boolean') return String(value);
  if (Array.isArray(value)) {
    return `[${value
      .map((item, index) => formatJsonValue(item, `${path}/${index}`))
      .join(',')}]`;
  }
  if (typeof value === 'object') return formatJsonValue(value, path);
  if (typeof value === 'bigint') return value.toString();
  return '—';
}

function formatJsonValue(value: unknown, path: string): string {
  if (typeof value === 'number') return formatFeatureNumber(value, path);
  if (value === null) return 'null';
  if (Array.isArray(value)) {
    return `[${value
      .map((item, index) => formatJsonValue(item, `${path}/${index}`))
      .join(',')}]`;
  }
  if (typeof value === 'object') {
    return `{${Object.entries(value as Record<string, unknown>)
      .map(
        ([key, item]) =>
          `${JSON.stringify(key)}:${formatJsonValue(item, `${path}/${key}`)}`,
      )
      .join(',')}}`;
  }
  return JSON.stringify(value);
}

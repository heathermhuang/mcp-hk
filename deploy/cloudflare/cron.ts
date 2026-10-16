/** Cloudflare uses 1=Sunday, unlike Unix cron's 0=Sunday. */
export function scheduledPack(cron: string): 'restaurants' | 'population' | 'backup' | 'catalogue' | 'resources' {
  const normalized = cron.trim().replace(/\s+/g, ' ').toUpperCase();
  if (normalized === '20 * * * *') return 'resources';
  if (normalized === '0 4 * * SUN') return 'catalogue';
  if (normalized === '0 2 * * *') return 'restaurants';
  if (['0 3 * * SUN', '0 3 * * 1'].includes(normalized)) return 'population';
  if (normalized === '0 1 * * *') return 'backup';
  throw new Error('Unrecognized maintenance schedule');
}

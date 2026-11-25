const DAY_MS = 86_400_000;
const WINDOW_DAYS = 30;
const INSTALLATION_LIMIT = 8192;
const TEST_MAX_AGE_SECONDS = 300;
const encoder = new TextEncoder();
const knownClients = ['claude-code', 'claude', 'codex', 'chatgpt', 'cursor', 'windsurf', 'vscode', 'fastmcp', 'python-httpx', 'python-requests', 'curl'];

export type Attribution = {
  traffic: 'operator_test' | 'unmarked' | 'privacy_opt_out';
  client: string;
  evidence: 'reported' | 'user_agent' | 'none';
  installation: string | null;
};

export function usageOptOut(request: Request): boolean {
  return request.headers.get('DNT') === '1' || request.headers.get('Sec-GPC') === '1' ||
    request.headers.get('x-mcp-analytics-opt-out') === '1' ||
    /(?:^|;\s*)__Host-mhk_analytics=off(?:;|$)/.test(request.headers.get('Cookie') ?? '');
}

const key = (secret: string) => crypto.subtle.importKey(
  'raw', encoder.encode(secret), {name: 'HMAC', hash: 'SHA-256'}, false, ['sign', 'verify'],
);
const hex = (value: ArrayBuffer): string =>
  Array.from(new Uint8Array(value), byte => byte.toString(16).padStart(2, '0')).join('');

async function isOperatorTest(marker: string, secret: string, now: number): Promise<boolean> {
  const match = /^(\d{10})\.([0-9a-f]{64})$/.exec(marker);
  if (!match || !secret) return false;
  const age = Math.floor(now / 1000) - Number(match[1]);
  if (age < -15 || age > TEST_MAX_AGE_SECONDS) return false;
  const signature = Uint8Array.from(match[2].match(/../g)!, pair => Number.parseInt(pair, 16));
  return crypto.subtle.verify('HMAC', await key(secret), signature, encoder.encode(`mcp.hk:usage-test:v1:${match[1]}`));
}

export async function requestAttribution(request: Request, secret: string, now = Date.now()): Promise<Attribution> {
  const optedOut = usageOptOut(request);
  const operator = await isOperatorTest(request.headers.get('x-mcp-usage-test') ?? '', secret, now);
  const traffic = operator ? 'operator_test' : optedOut ? 'privacy_opt_out' : 'unmarked';
  if (optedOut) return {traffic, client: 'unknown', evidence: 'none', installation: null};

  const reported = (request.headers.get('x-mcp-usage-client') ?? '').toLowerCase();
  const ua = (request.headers.get('User-Agent') ?? '').slice(0, 256).toLowerCase();
  const inferred = knownClients.find(client => ua.includes(client));
  const recognized = knownClients.includes(reported);
  const id = request.headers.get('x-mcp-usage-installation') ?? '';
  const installation = !operator && secret && /^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/i.test(id)
    ? hex(await crypto.subtle.sign('HMAC', await key(secret), encoder.encode(`mcp.hk:usage-install:v1:${id.toLowerCase()}`)))
    : null;
  return {traffic, client: recognized ? reported : inferred ?? 'unknown', evidence: recognized ? 'reported' : inferred ? 'user_agent' : 'none', installation};
}

export class AttributionStore {
  private sql: SqlStorage;

  constructor(sql: SqlStorage) {
    this.sql = sql;
    sql.exec(`CREATE TABLE IF NOT EXISTS usage_attribution_daily (
      day INTEGER, protocol TEXT, operation TEXT, traffic TEXT, client TEXT, evidence TEXT, outcome TEXT,
      calls INTEGER, installation_calls INTEGER, capped_calls INTEGER,
      PRIMARY KEY(day,protocol,operation,traffic,client,evidence,outcome))`);
    sql.exec('CREATE TABLE IF NOT EXISTS usage_installations (hash TEXT PRIMARY KEY, last_day INTEGER, previous_day INTEGER)');
    sql.exec('CREATE INDEX IF NOT EXISTS usage_installations_last_day ON usage_installations(last_day)');
    sql.exec('CREATE TABLE IF NOT EXISTS usage_attribution_meta (id INTEGER PRIMARY KEY CHECK (id=1), since INTEGER)');
  }

  cleanup(now = Date.now()) {
    const start = Math.floor(now / DAY_MS) - WINDOW_DAYS + 1;
    this.sql.exec('DELETE FROM usage_attribution_daily WHERE day < ?', start);
    this.sql.exec('DELETE FROM usage_installations WHERE last_day < ?', start);
    this.sql.exec('UPDATE usage_installations SET previous_day=NULL WHERE previous_day < ?', start);
  }

  record(protocol: string, operation: string, facts: Attribution, outcome: string, now = Date.now()) {
    const day = Math.floor(now / DAY_MS);
    this.sql.exec('INSERT OR IGNORE INTO usage_attribution_meta VALUES (1,?)', now);
    let installed = 0, capped = 0;
    if (facts.installation) {
      const known = this.sql.exec('SELECT last_day FROM usage_installations WHERE hash=?', facts.installation).toArray().length > 0;
      if (known || this.sql.exec<{n: number}>('SELECT COUNT(*) AS n FROM usage_installations').one().n < INSTALLATION_LIMIT) {
        this.sql.exec(`INSERT INTO usage_installations VALUES (?,?,NULL)
          ON CONFLICT(hash) DO UPDATE SET previous_day=last_day,last_day=excluded.last_day
          WHERE last_day < excluded.last_day`, facts.installation, day);
        installed = 1;
      } else {
        capped = 1;
      }
    }
    this.sql.exec(`INSERT INTO usage_attribution_daily VALUES (?,?,?,?,?,?,?,1,?,?)
      ON CONFLICT(day,protocol,operation,traffic,client,evidence,outcome) DO UPDATE SET
        calls=calls+1,installation_calls=installation_calls+excluded.installation_calls,capped_calls=capped_calls+excluded.capped_calls`,
    day, protocol, operation, facts.traffic, facts.client, facts.evidence, outcome, installed, capped);
  }

  report(days: number, now = Date.now()) {
    days = Math.max(1, Math.min(WINDOW_DAYS, Math.floor(days) || 7));
    const start = Math.floor(now / DAY_MS) - days + 1;
    const by = (columns: 'protocol,traffic' | 'client,evidence' | 'protocol,operation,traffic,outcome') =>
      this.sql.exec(`SELECT ${columns}, SUM(calls) AS calls FROM usage_attribution_daily WHERE day>=? GROUP BY ${columns} ORDER BY calls DESC, ${columns}`, start).toArray();
    const installs = this.sql.exec<{distinct: number; returning: number}>(
      'SELECT COUNT(*) AS "distinct", COUNT(CASE WHEN previous_day>=? THEN 1 END) AS "returning" FROM usage_installations WHERE last_day>=?', start, start,
    ).one();
    const optIn = this.sql.exec(
      'SELECT COALESCE(SUM(installation_calls),0) AS linkedCalls, COALESCE(SUM(capped_calls),0) AS cappedCalls FROM usage_attribution_daily WHERE day>=?', start,
    ).one();
    const since = this.sql.exec<{since: number}>('SELECT since FROM usage_attribution_meta WHERE id=1').toArray()[0]?.since;
    return {
      version: 1, asOf: new Date(now).toISOString(), since: since == null ? null : new Date(since).toISOString(), timeZone: 'UTC', days, retentionDays: WINDOW_DAYS,
      traffic: by('protocol,traffic'), clients: by('client,evidence'), outcomes: by('protocol,operation,traffic,outcome'),
      installations: {...installs, ...optIn, capacity: INSTALLATION_LIMIT},
      definitions: {
        scope: 'Attributable MCP tool attempts and HTTP property-building lookups observed after deployment. Pre-body edge rejections and protocol setup are outside this report.',
        operator_test: 'A valid short-lived signed operator marker was present.',
        unmarked: 'No valid test marker. May include external activity or earlier test clients.',
        privacy_opt_out: 'Privacy signal present. Client family and installation were not retained.',
        installations: 'Voluntarily supplied IDs, not people. Returning means activity on at least two UTC days within the selected window.',
      },
    };
  }
}

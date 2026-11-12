import assert from 'node:assert/strict';
import {test} from 'node:test';
import workerdPath from 'workerd';
import {build} from 'esbuild';
import {Miniflare,convertV4MiniflareOptions} from 'miniflare';
import {DatabaseSync} from 'node:sqlite';
import {IntelligenceStore} from './intelligence.ts';

test('real Worker runtime enforces operator auth, persists observations, schedules and verifies R2 archive',async()=>{
  // Test-only entrypoint: production collector and router, no public seed endpoint.
  const bundled=await build({absWorkingDir:new URL('.',import.meta.url).pathname,bundle:true,write:false,format:'esm',platform:'browser',target:'es2022',external:['cloudflare:workers'],stdin:{resolveDir:new URL('.',import.meta.url).pathname,contents:`
    import worker,{UsageAnalytics,McpContainer} from './worker.ts';
    import {DurableObject} from 'cloudflare:workers';
    export {UsageAnalytics};
    export class TestApp extends DurableObject {
      constructor(ctx,env){
        super(ctx,env);this.pending=[];
        // Exercise the real request/observer methods; replace only container transport.
        this.controller=Object.create(McpContainer.prototype);
        Object.defineProperties(this.controller,{
          ctx:{value:{storage:ctx.storage,waitUntil:p=>{this.pending.push(p);ctx.waitUntil(p);}}},env:{value:env},
          downloads:{value:()=>null},containerFetch:{value:async request=>{
            if(request.headers.has('Authorization')||request.headers.has('Cookie'))throw Error('credential boundary');
            return Response.json({items:[]});
          }},intelligenceMinute:{value:0,writable:true},intelligenceSent:{value:0,writable:true},
          intelligenceState:{value:{offered:0,rateLimitedExcluded:0,ingressDropped:0,deliveryFailures:0,collectorRejected:0}}
        });
      }
      fetch(request){return this.controller.fetch(request);}
      intelligenceDiagnostics(){return this.controller.intelligenceDiagnostics();}
      async drain(){await Promise.all(this.pending);this.pending=[];}
      usageReport(days){return this.controller.usageReport(days);}
      runScheduled(){return true;}
    }
    export default {async fetch(request,env,ctx){
      if(new URL(request.url).pathname==='/test-seed')return Response.json(await env.USAGE_ANALYTICS.getByName('production').observe(await request.json(),'203.0.113.4'));
      if(new URL(request.url).pathname==='/test-drain'){await env.APP.getByName('production').drain();return Response.json({done:true});}
      if(new URL(request.url).pathname==='/test-tick'){
        const pending=[];await worker.scheduled({cron:'2-59/5 * * * *',scheduledTime:Number(new URL(request.url).searchParams.get('at'))},env,{waitUntil:p=>pending.push(p)});
        await Promise.all(pending);return Response.json({done:true});
      }
      return worker.fetch(request,env,ctx);
    }};`}});
  const previousBinary=process.env.MINIFLARE_WORKERD_PATH;process.env.MINIFLARE_WORKERD_PATH=workerdPath.default;
  const mf=new Miniflare(convertV4MiniflareOptions({modules:true,script:bundled.outputFiles[0].text,compatibilityDate:'2026-10-16',compatibilityFlags:['nodejs_compat'],durableObjects:{USAGE_ANALYTICS:{className:'UsageAnalytics',useSQLite:true},APP:{className:'TestApp',useSQLite:true}},r2Buckets:['BACKUPS'],bindings:{OPS_TOKEN:'test-operations-credential',PUBLIC_ORIGIN:'https://mcp.hk',USAGE_INTELLIGENCE_ENABLED:'true'}}));
  try {
    const auth={Authorization:'Bearer test-operations-credential'};
    assert.equal((await mf.dispatchFetch('https://mcp.hk/__ops/analytics')).status,404);
    const now=Date.now(),event={id:crypto.randomUUID(),at:now,op:{protocol:'http',operation:'catalogue_search',resource:'',dataset:'catalogue',sourceCalls:0},facts:{detail:true,client:'unknown',clientEvidence:'unknown',keyword:'air quality',keywordState:'retained',kind:'discovery',format:'',language:'en',fields:[]},result:{category:'nonempty',stale:false,version:'v1',hasMore:false},status:200,outcome:'ok',items:2,bytesIn:0,bytesOut:100,duration:25};
    const seed=()=>mf.dispatchFetch('https://mcp.hk/test-seed',{method:'POST',body:JSON.stringify(event)});
    assert.equal((await (await seed()).json()).recorded,true);
    assert.equal((await (await seed()).json()).reason,'duplicate');
    const report=await (await mf.dispatchFetch('https://mcp.hk/__ops/analytics',{headers:auth})).json();
    assert.equal(report.totals.requests,1);assert.equal(report.audience[0].clients,1);assert.doesNotMatch(JSON.stringify(report),/203\.0\.113|test-operations-credential/);
    // Traverse the real edge -> controller admission -> streamed observer path.
    const data=await mf.dispatchFetch('https://mcp.hk/api/v1/catalogue/datasets?q=schools',{headers:{Cookie:'__Host-mhk_analytics=off; private=hidden',Authorization:'Bearer hidden','x-mcp-client-ip':'198.51.100.99'}});
    assert.equal(data.status,200);assert.deepEqual(await data.json(),{items:[]});
    await mf.dispatchFetch('https://mcp.hk/test-drain');
    const observed=await (await mf.dispatchFetch('https://mcp.hk/__ops/analytics',{headers:auth})).json();
    assert.equal(observed.totals.requests,2);assert.equal(observed.recent.length,1);assert.equal(observed.audience[0].unresolved,1);
    assert.doesNotMatch(JSON.stringify(observed),/schools|hidden|198\.51\.100/);
    const legacy=await (await mf.dispatchFetch('https://mcp.hk/__ops/usage',{headers:auth})).json();
    assert.equal(legacy.totals.requests,1);
    const tomorrow=(Math.floor((now+8*3600000)/86400000)+1)*86400000+3600000;
    await mf.dispatchFetch('https://mcp.hk/test-tick?at='+tomorrow);
    await mf.dispatchFetch('https://mcp.hk/test-tick?at='+tomorrow);
    const final=await (await mf.dispatchFetch('https://mcp.hk/__ops/analytics',{headers:auth})).json();
    assert.equal(final.digests.length,1);assert.equal(final.archives.length,1);
    const {BACKUPS}=await mf.getBindings(),objects=await BACKUPS.list({prefix:'usage/daily/'});
    assert.equal(objects.objects.length,1);
    const raw=await (await BACKUPS.get(objects.objects[0].key)).text();
    assert.doesNotMatch(raw,/203\.0\.113|network-hmac|test-operations-credential/);
    const checksum=Buffer.from(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(raw))).toString('hex');
    assert.equal(checksum,final.archives[0].checksum);
    // Restore the real archived aggregate rows into independent SQLite, with the real schema.
    const snapshot=JSON.parse(raw),db=new DatabaseSync(':memory:');
    const sql={exec(q,...args){const s=db.prepare(q);return /^SELECT/i.test(q)?s.all(...args):(s.run(...args),[]);}};
    const restored=new IntelligenceStore(sql,fn=>fn());
    for(const [table,rows] of Object.entries(snapshot.tables))for(const row of rows){
      const keys=Object.keys(row);db.prepare('INSERT INTO '+table+' ('+keys.join(',')+') VALUES ('+keys.map(()=>'?').join(',')+')').run(...Object.values(row));
    }
    assert.equal(restored.report(7,now).totals.requests,observed.totals.requests);
    assert.equal(db.prepare('PRAGMA integrity_check').get().integrity_check,'ok');db.close();
  }finally{await mf.dispose();if(previousBinary===undefined)delete process.env.MINIFLARE_WORKERD_PATH;else process.env.MINIFLARE_WORKERD_PATH=previousBinary;}
});

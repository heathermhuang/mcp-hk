import test from 'node:test';
import assert from 'node:assert/strict';
import {healthSummary} from '../../src/mcp_open_data_hk/web/source-health.js';
import {dateFacts,qualityText,weatherChoices} from '../../src/mcp_open_data_hk/web/source-quality.js';
import {decodeRecipe} from '../../src/mcp_open_data_hk/web/playground-state.js';

test('retrieval is never relabelled observation and dataset publication is separate',()=>{
 const facts=dateFacts({provenance:[{retrievedAt:100,lastCheckedAt:200,publicationDate:'2012-06-29'}]});
 assert.deepEqual(facts,[['Retrieved',100],['Checked',200],['DatasetPublished','2012-06-29']]);
 const qualified={observationFreshness:{observedAt:'2026-10-30T12:00:00+08:00'},provenance:[{retrievedAt:300}]};
 assert.equal(dateFacts(qualified).find(([key])=>key==='Observed')[1],'2026-10-30T12:00:00+08:00');
 assert.match(qualityText({quality:{semanticVerification:'not_performed'}},'en'),/have not been verified/);
});
test('weather shortcuts keep exact source, language and explicit series choice',()=>{
 for(const lang of ['en','zh-Hant'])for(const dataset of ['hk-hko-rss-current-weather-report','csdi:hko_rcd_1634806665997_63899']){
  const choices=weatherChoices(dataset,lang);assert.equal(choices.length,2);
  const recipe=decodeRecipe(new URL(choices[0].href,'https://mcp.hk').hash);
  assert.equal(recipe.dataset,'hk-hko-rss-current-weather-report');assert.equal(recipe.selectors.recordPath,'temperature/data');assert.equal(recipe.lang,lang);
  assert.equal(recipe.resource,lang==='en'?'574e2fdcf4b1756347aedaf3ba2feeda':'d4879f8b8408e73f528aa2be87074eba');
 }
 assert.deepEqual(weatherChoices('unrelated'),[]);
});
test('published address coverage never borrows the larger staged queue count',()=>{
 const p={data:{coverage:{addressEntities:1410,addressEligibleObservedEntities:414954,acceptedWeeklyFiles:190,discoveredWeeklyFiles:190},maintenance:{addressQueue:{observed:1612,capacity:{wholeSubset90DayCycleFeasible:false,fullPassMinimumDaysAtCurrentCap:1660}}}}};
 const s=healthSummary('company_registry',p);
 assert.ok(s.facts.some(([k,v])=>/Published address/.test(k)&&v==='1,410 / 414,954'));
 assert.ok(s.facts.some(([k,v])=>/unpublished/.test(k)&&v==='1,612'));
 assert.match(s.warnings.join(' '),/not feasible/);assert.match(s.warnings.join(' '),/priority cohorts/);
 const unknown=healthSummary('company_registry',{});assert.ok(unknown.facts.some(([,v])=>v==='Unknown / Unknown'));
});
test('successful status check does not disguise a held HKEX source as current',()=>{
 const p={state:'available',coverage:{latestSummaryDate:'2026-10-27'},updater:{lastChecked:'2026-10-30',lastSuccessfulRead:'2026-10-27',holdCode:'SOURCE_ACCESS_HOLD'}};
 const s=healthSummary('hkex_daily',p);assert.match(s.warnings[0],/newer filings may be missing/);
 assert.ok(s.facts.some(([k,v])=>/Latest accepted/.test(k)&&v==='2026-10-27'));
 assert.ok(healthSummary('hkex_daily',p,'zh-Hant').warnings[0].includes('暫停'));
});
test('property observations and racing subsets do not imply complete live inventory',()=>{
 const p={data:{productionCoverage:{totals:{activeSourceListings:177127,freshListings:22876,staleListings:107192,agingListings:47059,unmatchedSourceListings:46117}}}};
 assert.ok(healthSummary('seehouse',p).facts.some(([,v])=>v==='22,876 / 177,127'));
 assert.match(healthSummary('seehouse',p).warnings.join(' '),/does not verify availability/);
 const r=healthSummary('racing',{data:{coverage:{meetings:18,races:176},dividendCoverage:{observedRaces:78,stakeNormalized:false},seasonCoverage:[{seasonComplete:false}]}});
 assert.match(r.warnings.join(' '),/history is incomplete/);assert.match(r.warnings.join(' '),/not normalized/);
});

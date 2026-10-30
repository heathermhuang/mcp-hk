import {encodeRecipe} from './playground-state.js';
export function weatherChoices(dataset,locale='en'){
  if(!['hk-hko-rss-current-weather-report','csdi:hko_rcd_1634806665997_63899'].includes(dataset))return [];
  const zh=locale==='zh-Hant',resource=zh?'d4879f8b8408e73f528aa2be87074eba':'574e2fdcf4b1756347aedaf3ba2feeda';
  return [['temperature/data',zh?'各站氣溫 · 天文台官方 JSON':'Station temperatures · official HKO JSON'],['humidity/data',zh?'相對濕度 · 天文台官方 JSON':'Relative humidity · official HKO JSON']].map(([recordPath,label])=>({label,href:'/playground?lang='+locale+encodeRecipe({v:1,family:'catalogue',lang:locale,dataset:'hk-hko-rss-current-weather-report',resource,selectors:{recordPath}})}));
}
export function dateFacts(envelope){
  return (envelope.provenance||[]).flatMap(source=>[
    ['Source',source.attribution||source.sourceId],
    ['ReferencePeriod',source.referencePeriod],
    ['Observed',envelope.observationFreshness?.observedAt||source.observedAt||source.observed||envelope.meta?.lastObservedAt],
    ['Retrieved',source.retrievedAt||source.retrieved],
    ['Checked',source.lastCheckedAt||source.lastValidatedAt],
    ['DatasetPublished',source.publicationDate],
  ].filter(([,value])=>value!=null&&value!==''));
}
export function qualityText(envelope,locale='en'){
  const zh=locale==='zh-Hant',quality=envelope.quality,q=quality?.qualification;
  if(quality?.semanticVerification==='selected_observation_contract'&&q)return zh?`已檢查所選觀察規約：${q.rowCount} 項觀察、${q.uniqueStationCount} 個不同站名；單位 ${q.unit}。並非固定測站清單或完整天氣涵蓋。`:`Selected observation contract checked: ${q.rowCount} observations, ${q.uniqueStationCount} unique station names; unit ${q.unit}. This does not establish a fixed station inventory or complete weather coverage.`;
  if(quality?.semanticVerification==='not_performed'){
    const profile=quality.completeness;
    return (zh?'原始來源資料：已成功讀取，但尚未核實欄位的分析含義、單位及完整涵蓋。':'Raw source data: readable, but analytical meaning, units and complete coverage have not been verified.')+(profile?(zh?` 所選來源的 ${profile.rowCount} 列中，${profile.fieldsWithAbsentValues} 個欄位有缺少值，${profile.fieldsWithNullValues} 個欄位有明確 null；空字串保留原值。`:` Across ${profile.rowCount} rows in the selected source, ${profile.fieldsWithAbsentValues} fields contain absent values and ${profile.fieldsWithNullValues} contain explicit nulls; empty strings retain their source value.`):'');
  }
  return '';
}

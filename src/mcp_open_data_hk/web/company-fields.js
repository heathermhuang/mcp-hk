/* Name1/Name2 remain separate source fields. Only the display joins person names. */
export function partyNames(party,language='en'){
  if(!party)return {primary:'',secondary:''};
  const latin=party.kind==='person'?[party.name1,party.name2].filter(Boolean).join(', '):(party.name1||'');
  const chinese=party.chineseName||'';
  return language==='zh'&&chinese?{primary:chinese,secondary:latin===chinese?'':latin}:{primary:latin,secondary:chinese===latin?'':chinese};
}

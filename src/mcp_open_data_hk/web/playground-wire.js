/* Preserve domain response number lexemes too; JSON.parse Number is not evidence. */
const numeric=Symbol('wireNumber');
export const isNumber = value => Boolean(value && typeof value==='object' && value[numeric]);
export function parseExact(source) {
  if(typeof source!=='string'||source.length>2_000_000)throw Error('WIRE_TOO_LARGE');
  let at=0;
  const space=()=>{while(/\s/.test(source[at]||'~'))at++;};
  function read(depth=0){
    if(depth>100)throw Error('WIRE_DEPTH');space();const first=source[at];
    if(first==='"'){const start=at++;while(at<source.length){const c=source[at++];if(c==='\\')at++;else if(c==='"')return JSON.parse(source.slice(start,at));}throw Error('WIRE_STRING');}
    if(first==='['||first==='{'){
      const array=first==='[', end=array?']':'}', result=array?[]:Object.create(null);at++;space();
      if(source[at]===end){at++;return result;}
      while(at<source.length){
        if(array)result.push(read(depth+1));else{const key=read(depth+1);if(typeof key!=='string')throw Error('WIRE_KEY');space();if(source[at++]!==':')throw Error('WIRE_COLON');result[key]=read(depth+1);}
        space();const c=source[at++];if(c===end)return result;if(c!==',')throw Error('WIRE_COMMA');
      }throw Error('WIRE_END');
    }
    for(const [token,value] of [['null',null],['true',true],['false',false]])if(source.startsWith(token,at)){at+=token.length;return value;}
    const match=source.slice(at).match(/^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/);
    if(!match)throw Error('WIRE_NUMBER');at+=match[0].length;return {[numeric]:true,text:match[0]};
  }
  const result=read();space();if(at!==source.length)throw Error('WIRE_TRAILING');return result;
}
export function exactJson(value){if(isNumber(value))return value.text;if(Array.isArray(value))return '['+value.map(exactJson).join(',')+']';if(value&&typeof value==='object')return '{'+Object.entries(value).map(([k,v])=>JSON.stringify(k)+':'+exactJson(v)).join(',')+'}';return JSON.stringify(value);}
export function exactCell(value,present=true){const kind=!present?'missing':isNumber(value)?(/[.eE]/.test(value.text)?'float':'integer'):value===null?'null':typeof value==='boolean'?'boolean':typeof value==='string'?'string':'json';return {kind,text:kind==='missing'?null:kind==='string'?value:exactJson(value),json:kind==='missing'?null:exactJson(value)};}
export function wirePresentation(rows,columns){return {codec:1,columns,rows:rows.map(r=>columns.map(k=>exactCell(r[k],Object.hasOwn(r,k)))),recordsJson:exactJson(rows)};}

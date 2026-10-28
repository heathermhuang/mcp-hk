/* Observe one real routed request, including failure without an HTTP response. */
export async function observeRequest(route,admission,{timeout=30000}={}){
 let timer;
 const operation=async()=>{
  await route.continue();
  const response=await route.request().response();
  if(!response)return {failure:{kind:'network',path:new URL(route.request().url()).pathname,...route.request().failure()}};
  const headers=response.headers();await admission.observe(response.status(),headers);
  if(response.status()>=400){const body=await response.body();return {failure:{kind:'http',status:response.status(),headers:Object.fromEntries(Object.entries(headers).filter(([k])=>['retry-after','ratelimit-limit','ratelimit-remaining','ratelimit-reset','date','content-type'].includes(k))),body:body.subarray(0,16384).toString('utf8'),bodyBytes:body.length}};}
  return {status:response.status()};
 };
 try{return await Promise.race([operation(),new Promise(resolve=>{timer=setTimeout(()=>resolve({failure:{kind:'deadline',code:'BROWSER_REQUEST_DEADLINE',path:new URL(route.request().url()).pathname}}),timeout);})]);}
 catch(error){return {failure:{kind:'network',code:'BROWSER_REQUEST_FAILED',message:error.message,path:new URL(route.request().url()).pathname}};}
 finally{clearTimeout(timer);}
}

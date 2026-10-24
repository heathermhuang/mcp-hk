/** Overall deadlines apply to body reads too, including a stalled reader. */
export async function boundedBytes(input:Request|Response,limit:number,milliseconds=15000):Promise<Uint8Array> {
  const reader=input.body?.getReader();if(!reader)return new Uint8Array();
  const chunks:Uint8Array[]=[];let size=0,timer:ReturnType<typeof setTimeout>|undefined;
  const expired=new Promise<never>((_,reject)=>{timer=setTimeout(()=>{reject(new Error('RESPONSE_DEADLINE'));void reader.cancel().catch(()=>{});},milliseconds);});
  try {
    for(;;){const p=await Promise.race([reader.read(),expired]);if(p.done)break;size+=p.value.length;if(size>limit)throw new Error('RESPONSE_TOO_LARGE');chunks.push(p.value);}
    const result=new Uint8Array(size);let offset=0;for(const p of chunks){result.set(p,offset);offset+=p.length;}return result;
  } finally {if(timer!==undefined)clearTimeout(timer);await reader.cancel().catch(()=>{});reader.releaseLock();}
}

export function boundedResponse(response:Response,limit:number,milliseconds=25000):Response {
  const reader=response.body?.getReader();if(!reader)return response;
  let size=0,timer:ReturnType<typeof setTimeout>,finished=false;
  const end=()=>{if(!finished){finished=true;clearTimeout(timer);}};
  return new Response(new ReadableStream<Uint8Array>({
    start(controller){timer=setTimeout(()=>{if(!finished){end();void reader.cancel().catch(()=>{});controller.error(new Error('RESPONSE_DEADLINE'));}},milliseconds);},
    async pull(controller){try{const p=await reader.read();if(finished)return;if(p.done){end();controller.close();return;}size+=p.value.length;if(size>limit)throw new Error('RESPONSE_TOO_LARGE');controller.enqueue(p.value);}catch(e){if(!finished){end();await reader.cancel().catch(()=>{});controller.error(e);}}},
    async cancel(reason){end();await reader.cancel(reason);},
  }),response);
}

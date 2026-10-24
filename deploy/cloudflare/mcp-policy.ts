/** FastMCP 2.14.7 / mcp 1.30.0 stateless streamable HTTP policy.
 * GET retains the SDK's optional SSE stream. DELETE has no session to terminate.
 * Protocol header negotiation and POST payload validation remain SDK-owned.
 */
export const MCP_ALLOW='GET, POST, OPTIONS';
export function mcpPolicy(request:Request,origin:string):Response|undefined {
  if(new URL(request.url).pathname!=='/mcp')return;
  const supplied=request.headers.get('Origin');
  if(supplied&&!new Set([origin,'https://mcp-hk.measurable.workers.dev']).has(supplied))return Response.json({error:{code:'INVALID_ORIGIN'}},{status:403});
  if(!['GET','POST','OPTIONS'].includes(request.method))return new Response('Method not allowed',{status:405,headers:{Allow:MCP_ALLOW}});
  if(request.method==='OPTIONS')return new Response(null,{status:204,headers:{Allow:MCP_ALLOW,'Access-Control-Allow-Origin':'*','Access-Control-Allow-Methods':MCP_ALLOW,'Access-Control-Allow-Headers':'Content-Type, MCP-Protocol-Version, Mcp-Session-Id'}});
}

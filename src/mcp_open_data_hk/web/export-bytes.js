/* Bounded, lossless JSON + spreadsheet-safe CSV. Hash the bytes actually packaged. */
const utf8=new TextEncoder();
export async function sha256(bytes){return [...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(b=>b.toString(16).padStart(2,'0')).join('');}
export function csvCell(value){
  let text=value==null?'':typeof value==='object'?JSON.stringify(value):String(value);
  if(typeof value==='string'&&(/^[\s\u0000-\u001f\u007f-\u009f\u200b-\u200f]*[=+\-@]/.test(text)||/^0\d+$/.test(text)))text="'"+text;
  return '"'+text.replaceAll('"','""')+'"';
}
function crc32(bytes){let crc=0xffffffff;for(const b of bytes){crc^=b;for(let i=0;i<8;i++)crc=(crc>>>1)^((crc&1)?0xedb88320:0);}return (crc^0xffffffff)>>>0;}
function header(size){const bytes=new Uint8Array(size),view=new DataView(bytes.buffer);return {bytes,u16:(at,n)=>view.setUint16(at,n,true),u32:(at,n)=>view.setUint32(at,n,true)};}
export function zipStore(files){
  const local=[],central=[];let offset=0,total=0;
  for(const [name,bytes] of files){
    if(!/^[A-Za-z0-9._-]+$/.test(name))throw Error('INVALID_FILENAME');
    total+=bytes.length;if(total>16*1024*1024)throw Error('PAGE_EXPORT_TOO_LARGE');
    const filename=utf8.encode(name),crc=crc32(bytes),h=header(30),c=header(46);
    h.u32(0,0x04034b50);h.u16(4,20);h.u16(6,0x800);h.u16(12,33);h.u32(14,crc);h.u32(18,bytes.length);h.u32(22,bytes.length);h.u16(26,filename.length);
    c.u32(0,0x02014b50);c.u16(4,20);c.u16(6,20);c.u16(8,0x800);c.u16(14,33);c.u32(16,crc);c.u32(20,bytes.length);c.u32(24,bytes.length);c.u16(28,filename.length);c.u32(42,offset);
    local.push(h.bytes,filename,bytes);central.push(c.bytes,filename);offset+=30+filename.length+bytes.length;
  }
  const length=central.reduce((n,b)=>n+b.length,0),end=header(22);end.u32(0,0x06054b50);end.u16(8,files.length);end.u16(10,files.length);end.u32(12,length);end.u32(16,offset);
  return new Blob([...local,...central,end.bytes],{type:'application/zip'});
}

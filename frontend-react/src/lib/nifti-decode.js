// Shared bounded byte decoding; no masks, predictions or network access here.
import {Gunzip} from 'fflate';
import {MAX_TRANSFER_BYTES} from './volume-geometry.js';

export function decode(buffer,expectedLimit){
  if(!(buffer instanceof ArrayBuffer)||buffer.byteLength>MAX_TRANSFER_BYTES)throw new Error('Volume input exceeds the browser transfer limit.');
  const bytes=new Uint8Array(buffer);
  if(bytes[0]!==31||bytes[1]!==139){
    if(buffer.byteLength>expectedLimit)throw new Error('Uncompressed volume exceeds the expected output limit.');
    return buffer;
  }
  const chunks=[];let length=0;
  const unzip=new Gunzip(chunk=>{
    length+=chunk.length;
    if(length>expectedLimit||length>MAX_TRANSFER_BYTES)throw new Error('Decompressed volume exceeds the browser memory limit.');
    chunks.push(chunk);
  });
  for(let offset=0;offset<bytes.length;offset+=64*1024)unzip.push(bytes.subarray(offset,offset+64*1024),offset+64*1024>=bytes.length);
  const output=new Uint8Array(length);let offset=0;
  for(const chunk of chunks){output.set(chunk,offset);offset+=chunk.length;}
  return output.buffer;
}

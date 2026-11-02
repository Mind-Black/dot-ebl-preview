import { describe,it,expect } from 'vitest';
import { spawnSync } from 'node:child_process';
import { resolve } from 'node:path';
import { existsSync } from 'node:fs';
const localPython = resolve('../.venv/Scripts/python.exe');
const python = process.env.PYTHON || (existsSync(localPython) ? localPython : 'python');
import { unzipSync } from 'fflate';
import fixtures from '../fixtures/raith.json';
import { chords,plan,writeGds,dfToDatatype } from '../../lib/raith/engine';
import { bundle,designHash,writeNpz,sha } from '../../lib/raith/bundle';
import { parseNpz } from '../../lib/io/npzParser';
import type { DesignModel } from '../../lib/decoders/types';
describe('Python fabrication parity',()=>{
 for(const f of fixtures)it(`matches Python pitch ${f.pitch}, dose ${f.dose}`,async()=>{
  const d:DesignModel={width:2,height:2,pitchNm:f.pitch,periodNm:new Uint32Array([1000,1500,1000,1000]),angleDeg:new Float64Array([0,-90,45,12.345678]),active:new Uint8Array(f.active),sourceIdentity:'fixture',dose:f.dose};
  const o={topName:'HOLOGRAM',layer:1,dose:f.dose,centerOrigin:false};const p=plan(d,o);const gds=writeGds(d,o,p,new Date(2026,0,2,3,4,5));
  expect(Buffer.from(await gds.arrayBuffer()).toString('hex')).toBe(f.gds);expect(await designHash(d)).toBe(f.design_hash);
  const zip=unzipSync(new Uint8Array(await (await bundle(d,o,p,gds)).arrayBuffer()));const m=JSON.parse(new TextDecoder().decode(zip['manifest.json']));expect(m.plan_hash).toBe(f.plan_hash);
  for(const [name,info]of Object.entries(m.files))expect(await sha(zip[name])).toBe((info as {sha256:string}).sha256);
  const npz=writeNpz({...d,sourceIdentity:'\u0423\u043a\u0440\u0430\u0457\u043d\u0430',layer:4,regionMasks:{area:new Uint8Array([1,0,0,1])},artifactMetadata:{operations:[{name:'test',params:{}}]}});
  const imported=parseNpz(npz);expect(imported.pitchNm).toBe(d.pitchNm);expect(imported.layer).toBe(4);expect(imported.regionMasks?.area).toEqual(new Uint8Array([1,0,0,1]));
  const result=spawnSync(python,['-c',`import sys,io,json,numpy as np
z=np.load(io.BytesIO(sys.stdin.buffer.read()),allow_pickle=False)
m=json.loads(str(z['metadata_json'][0]))
assert m['layer']==4
assert len(m['source_identity'])==7
assert z['active'].dtype==np.bool_
assert z['period_nm'].dtype==np.uint32
assert z['angle_deg'].dtype==np.float64
assert z['mask_area'].shape==(2,2)
`],{input:Buffer.from(npz)});expect(result.stderr.toString()).toBe('');expect(result.status).toBe(0);
 });
 it('validates coordinates and names',()=>{
 const d:DesignModel={width:2,height:1,pitchNm:20001,periodNm:new Uint32Array([1000,1000]),angleDeg:new Float64Array([0,0]),active:new Uint8Array([1,1]),sourceIdentity:'test'};
 const o={topName:'HOLOGRAM',layer:1,dose:1,centerOrigin:true};const p=plan(d,o);expect(p.offset).toEqual([20001,-10001]);expect(p.placedStripes).toBe(p.totalStripes*2);
 expect(()=>plan(d,{...o,topName:'P_1000'})).toThrow();expect(()=>plan({...d,pitchNm:5e9},o)).toThrow();expect(()=>plan({...d,angleDeg:new Float64Array([NaN,0])},o)).toThrow();
 });
 it('counts paths and handles unsigned dose',()=>{expect(chords(20000,1000).paths).toHaveLength(20);expect(chords(2000,4000).skipped).toBe(1);expect(dfToDatatype(17797.5)).toBe(65535);expect(()=>dfToDatatype(NaN)).toThrow();});
});

import { afterEach, expect, it, vi } from 'vitest';
import { DesignStore } from '../../lib/store/designStore';
import { fabricationSnapshot } from '../../lib/raith/snapshot';
import { writeNpz, matrices } from '../../lib/raith/bundle';
import { parseNpz } from '../../lib/io/npzParser';
const design = () => ({width:1,height:1,pitchNm:20000,periodNm:new Uint32Array([1000]),angleDeg:new Float64Array([25]),active:new Uint8Array([1]),sourceIdentity:'same'});
afterEach(() => vi.unstubAllGlobals());
it('exports independent effective-angle snapshots and matching bundled parameters', () => {
 const d=design(), a=fabricationSnapshot(d,15), b=fabricationSnapshot(d,15);
 expect([...a.angleDeg]).toEqual([40]); expect([...b.angleDeg]).toEqual([40]); expect([...d.angleDeg]).toEqual([25]);
 const bytes=writeNpz(a); const restored=parseNpz(bytes.buffer as ArrayBuffer,'snapshot.npz');
 expect([...restored.angleDeg]).toEqual([40]); expect([...restored.periodNm]).toEqual([1000]); expect(restored.pitchNm).toBe(20000); expect([...restored.active]).toEqual([1]);
 expect(new TextDecoder().decode(matrices(a)['angles.txt'])).toContain('40.000000');
});
it('coalesces edits, publishes intermediate results, and ignores replaced workers', () => {
 const workers:any[]=[];
 class WorkerMock { onmessage:any; onerror:any; messages:any[]=[]; constructor(){workers.push(this);} postMessage(m:any){this.messages.push(m);} terminate(){} }
 vi.stubGlobal('Worker',WorkerMock);
 const store=new DesignStore();
 store.loadFile({name:'first.png'} as File); const first=workers[0];

 first.onmessage({data:{id:first.messages[0].id,design:design(),stats:{}}});
 expect(store.getDesign()).not.toBeNull();
 store.setRgbaOptions({maxPeriodNm:1500}); store.setRgbaOptions({maxPeriodNm:1400});
 expect(store.getIsProcessing()).toBe(true); expect(first.messages[1].options.maxPeriodNm).toBe(1500);
 first.onmessage({data:{id:first.messages[1].id,design:design(),stats:{}}}); first.onmessage({data:{id:first.messages[2].id,design:design(),stats:{}}}); expect(store.getIsProcessing()).toBe(false);
 store.loadFile({name:'second.png'} as File); const previous=store.getDesign();
 first.onmessage({data:{id:999,design:{...design(),sourceIdentity:'stale'},stats:{}}}); expect(store.getDesign()).toBe(previous);
});

it('failed staged import preserves committed metadata and worker, and rejects superseded results',()=>{
 const workers:any[]=[];class Mock {onmessage:any;onerror:any;messages:any[]=[];terminated=false;constructor(){workers.push(this);}postMessage(m:any){this.messages.push(m);}terminate(){this.terminated=true;}}
 vi.stubGlobal('Worker',Mock);const store=new DesignStore();store.loadFile({name:'valid.png'} as File,'Unity HSV');workers[0].onmessage({data:{design:design(),stats:{}}});
 const committed=store.getDesign();store.loadFile({name:'bad.png'} as File,'RGB8 indexed');expect(store.canExport()).toBe(false);workers[1].onmessage({data:{error:'decode failed'}});
 expect(store.getDesign()).toBe(committed);expect(store.getInterpretation()).toBe('Unity HSV');expect(store.getError()).toContain('bad.png');expect(workers[0].terminated).toBe(false);
 store.setPitchNm(25000);expect(store.getError()).toContain('bad.png');expect(store.canExport()).toBe(false);workers[0].onmessage({data:{id:workers[0].messages.at(-1).id,design:committed,stats:{}}});
 store.clearError();expect(store.canExport()).toBe(true);store.setPitchNm(30000);expect(workers[0].messages.at(-1).pitch).toBe(30000);
 store.loadFile({name:'old.png'} as File);store.loadFile({name:'new.png'} as File);workers[2].onmessage({data:{design:{...design(),sourceIdentity:'old'},stats:{}}});expect(store.getDesign()).toBe(committed);
 workers[3].onmessage({data:{design:{...design(),sourceIdentity:'new'},stats:{}}});expect(store.getDesign()?.sourceIdentity).toBe('new');expect(workers[0].terminated).toBe(true);
});

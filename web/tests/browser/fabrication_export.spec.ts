import { writeNpz } from '../../lib/raith/bundle';
import { unzipSync } from 'fflate';
import { readFile } from 'node:fs/promises';
import { parseNpz } from '../../lib/io/npzParser';
import { test,expect } from '@playwright/test';
test('validates a snapshot and downloads GDS and Python bundle',async({page})=>{
 await page.goto('./');
 const bytes=writeNpz({width:2,height:1,pitchNm:20000,periodNm:new Uint32Array([1000,1000]),angleDeg:new Float64Array([0,45]),active:new Uint8Array([1,1]),sourceIdentity:'browser'});
 await page.locator('input[type=file]').first().setInputFiles({name:'fixture.npz',mimeType:'application/octet-stream',buffer:Buffer.from(bytes)});
 await page.getByRole('spinbutton',{name:/Grating Orientation.*numeric/}).fill('30');
 await page.getByText('EBL Lithography Fabrication',{exact:true}).click();
 await page.getByRole('button',{name:'Export EBL Layout (.gds)',exact:true}).click();
 await expect(page.locator('dialog pre')).toContainText('Applied orientation: 30\u00b0');
 let generatedGds: Buffer | undefined;
 for(const kind of ['GDS','ZIP']){const download=page.waitForEvent('download');await page.getByRole('button',{name:'Generate '+kind,exact:true}).click();const file=await download;expect(file.suggestedFilename()).toMatch(kind==='GDS'?/\.gds$/:/\.zip$/);const bytes=await readFile((await file.path())!);if(kind==='ZIP'){const entries=unzipSync(bytes);const npz=entries['design.npz'];const restored=parseNpz(npz.slice().buffer as ArrayBuffer,'snapshot.npz');expect([...restored.angleDeg]).toEqual([30,75]);expect(Buffer.from(entries['HOLOGRAM.gds'])).toEqual(generatedGds);expect(entries['HOLOGRAM.gds'].length).toBeGreaterThan(100);}else {generatedGds=bytes;expect(bytes.length).toBeGreaterThan(100);}}
 await page.getByRole('button',{name:'Close / Cancel'}).click();await expect(page.locator('dialog')).toHaveCount(0);
});
test('million-cell worker responsiveness and export measurements',async({page})=>{
 test.setTimeout(120000);await page.goto('./');
 const size=1075,n=size*size;
 const bytes=writeNpz({width:size,height:size,pitchNm:20000,periodNm:new Uint32Array(n).fill(1000),angleDeg:new Float64Array(n),active:new Uint8Array(n).fill(1),sourceIdentity:'benchmark'});
 await page.locator('input[type=file]').first().setInputFiles({name:'benchmark.npz',mimeType:'application/octet-stream',buffer:Buffer.from(bytes)});
 await page.evaluate(()=>{(window as any).__ticks=0;(window as any).__timer=setInterval(()=>(window as any).__ticks++,10);});
 await page.getByText('EBL Lithography Fabrication',{exact:true}).click();
 await page.getByRole('button',{name:'Export EBL Layout (.gds)',exact:true}).click();
 await expect(page.getByRole('button',{name:'Generate GDS',exact:true})).toBeEnabled();
 const download=page.waitForEvent('download');await page.getByRole('button',{name:'Generate GDS',exact:true}).click();
 const file=await download; const fs=await import('node:fs/promises');expect((await fs.stat((await file.path())!)).size).toBeGreaterThan(1000000);
 expect(await page.evaluate(()=>{clearInterval((window as any).__timer);return (window as any).__ticks;})).toBeGreaterThan(0);

});

test('imports NPZ through the UI and exports with loaded workers',async({page})=>{
 await page.goto('./');
 const bytes=writeNpz({width:1,height:1,pitchNm:20000,periodNm:new Uint32Array([1000]),angleDeg:new Float64Array([45]),active:new Uint8Array([1]),sourceIdentity:'ui fixture',layer:3,dose:2});
 await page.locator('input[type=file]').first().setInputFiles({name:'design.npz',mimeType:'application/octet-stream',buffer:Buffer.from(bytes)});
 await page.getByText('EBL Lithography Fabrication',{exact:true}).click();
 await expect(page.getByRole('button',{name:'Export EBL Layout (.gds)',exact:true})).toBeEnabled();
 await page.getByRole('button',{name:'Export EBL Layout (.gds)',exact:true}).click();
 await expect(page.locator('dialog pre')).toContainText('Layer: 3; dose: 2');
 const download=page.waitForEvent('download');await page.getByRole('button',{name:'Generate GDS',exact:true}).click();expect((await download).suggestedFilename()).toBe('HOLOGRAM.gds');
});

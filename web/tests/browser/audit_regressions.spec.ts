import { test, expect } from '@playwright/test';
import { readFile, mkdir } from 'node:fs/promises';
test('keyboard presets, named controls, tabs and persistent probe',async({page})=>{
 await page.goto('./');const preset=page.getByRole('button',{name:/Concentric Test Pattern/}).first();await preset.focus();await page.keyboard.press('Enter');
 await expect(page.getByRole('heading',{name:'Design & Ingestion'})).toBeFocused();
 await expect(page.getByRole('slider',{name:/Holopixel Lattice Pitch/})).toBeVisible();
 await page.getByRole('tab',{name:'Period Map'}).focus();await page.keyboard.press('End');await expect(page.getByRole('tab',{name:'Analytics'})).toHaveAttribute('aria-selected','true');
 await page.getByLabel('Row (zero-based)').fill('2');await page.getByLabel('Row (zero-based)').press('Tab');await expect(page.locator('.cell-selection output')).toContainText('Cell (2, 0)');
 await page.locator('.flat-canvas').focus();await page.keyboard.press('ArrowRight');await expect(page.locator('.cell-selection output')).toContainText('Cell (2, 1)');
});
test('failed replacement retains identity and requires acknowledgement',async({page})=>{
 await page.goto('./');await page.locator('.preset-card').first().click();
 await page.locator('input[type=file]').first().setInputFiles({name:'broken.png',mimeType:'image/png',buffer:Buffer.from('broken')});
 await expect(page.getByRole('button',{name:'Import',exact:true})).toBeDisabled();
 await page.getByRole('dialog').getByRole('combobox').selectOption('RGBA continuous');await page.getByRole('button',{name:'Import',exact:true}).click();
 await expect(page.getByRole('alert')).toContainText('broken.png');await expect(page.getByRole('alert')).toContainText('Retained design');
 await expect(page.getByRole('button',{name:'Parameter Metadata (JSON)'})).toBeDisabled();await page.getByRole('button',{name:'Continue with retained design'}).click();
 await expect(page.getByRole('button',{name:'Parameter Metadata (JSON)'})).toBeEnabled();
});
test('WebGL denial preserves inspection and retry restores preview',async({page})=>{
 await page.addInitScript(()=>{const original=HTMLCanvasElement.prototype.getContext;(window as any).__deny=true;HTMLCanvasElement.prototype.getContext=function(this:HTMLCanvasElement,type:any,...args:any[]){if((window as any).__deny && String(type).includes('webgl'))return null;return (original as any).call(this,type,...args);} as any;});
 await page.goto('./');await page.locator('.preset-card').first().click();await expect(page.getByRole('button',{name:'Retry preview'})).toBeVisible();
 await expect(page.getByRole('button',{name:'Optical Preview PNG (1:1)'})).toBeDisabled();
 const download=page.waitForEvent('download');await page.getByRole('button',{name:'Parameter Metadata (JSON)'}).click();const file=await download;const data=JSON.parse(await readFile((await file.path())!,'utf8'));expect(data.active_cells).toBeGreaterThan(0);
 await page.evaluate(()=>(window as any).__deny=false);await page.getByRole('button',{name:'Retry preview'}).click();await expect(page.locator('.preview-recovery')).toBeHidden();
});
for(const [width,height] of [[1440,900],[1280,720],[768,1024],[390,844],[720,450]])test(`workbench tasks and bounds ${width}x${height}`,async({page})=>{
 await page.setViewportSize({width,height});await page.goto('./');await page.locator('.preset-card').first().click();
 for(const label of ['Period Map','Angle Map','Source Image','Analytics']){const tab=page.getByRole('tab',{name:label,exact:true});await tab.click();await expect(tab).toHaveAttribute('aria-selected','true');}
 const input=page.getByRole('spinbutton',{name:/Grating Orientation.*numeric/});await input.fill('30');await input.press('Tab');
 for(const control of await page.locator('.workbench-container button:visible, .workbench-container input:visible, .workbench-container select:visible').all()){const box=await control.boundingBox();expect(box!.x).toBeGreaterThanOrEqual(0);expect(box!.x+box!.width).toBeLessThanOrEqual(width+1);}
 const download=page.waitForEvent('download');await page.getByRole('button',{name:'Parameter Metadata (JSON)'}).click();expect((await download).suggestedFilename()).toMatch(/json$/);
 await mkdir('../docs/ui-ux-remediation-assets',{recursive:true});await page.screenshot({path:`../docs/ui-ux-remediation-assets/layout-${width}x${height}.png`});
});


test('fabrication retries worker failure, completes repeatedly and cancels safely',async({page})=>{
 await page.addInitScript(()=>{const Real=window.Worker;(window as any).__fail=true;window.Worker=class extends Real {postMessage(message:any,options?:any){if(message.type==='VALIDATE'&&(window as any).__fail){(window as any).__fail=false;setTimeout(()=>this.dispatchEvent(new ErrorEvent('error',{message:'Injected failure'})),0);return;}super.postMessage(message,options);}};});
 await page.goto('./');await page.locator('.preset-card').first().click();await page.getByText('EBL Lithography Fabrication',{exact:true}).click();const trigger=page.getByRole('button',{name:'Export EBL Layout (.gds)',exact:true});await trigger.click();
 await expect(page.locator('dialog')).toHaveAccessibleName(/EBL fabrication .* reviewed snapshot/);await expect(page.locator('dialog')).toContainText('worker failed');await page.getByRole('button',{name:'Retry',exact:true}).click();
 for(const kind of ['GDS','ZIP','GDS']){await expect(page.getByRole('button',{name:'Generate '+kind,exact:true})).toBeEnabled();const download=page.waitForEvent('download');await page.getByRole('button',{name:'Generate '+kind,exact:true}).click();expect((await download).suggestedFilename()).toMatch(/gds$|zip$/);await expect(page.locator('dialog')).toContainText('Completed');}
 await page.keyboard.press('Escape');await expect(trigger).toBeFocused();await expect(page.locator('dialog')).toHaveCount(0);
});

test('first import failure, repeated file selection, cancellation and valid recovery',async({page})=>{
 await page.goto('./');const upload=page.locator('input[type=file]').first();
 for(let i=0;i<2;i++){await upload.setInputFiles({name:'bad.png',mimeType:'image/png',buffer:Buffer.from('bad')});await page.getByRole('dialog').getByRole('combobox').selectOption('RGBA continuous');await page.getByRole('button',{name:'Import',exact:true}).click();await expect(page.getByRole('alert')).toContainText('No design is loaded');}
 await upload.setInputFiles('tests/fixtures/hls_test.png');await page.getByRole('dialog').getByRole('button',{name:'Cancel',exact:true}).click();await expect(page.getByRole('dialog')).toHaveCount(0);
 await upload.setInputFiles('tests/fixtures/hls_test.png');await page.getByRole('dialog').getByRole('combobox').selectOption('Holtida legacy HLS');await page.getByRole('button',{name:'Import',exact:true}).click();await expect(page.getByRole('alert')).toBeHidden();await expect(page.getByRole('button',{name:'Parameter Metadata (JSON)'})).toBeEnabled();
});
test('all gallery presets activate with Space and data exports contain edited pitch',async({page})=>{
 await page.goto('./');for(let i=0;i<4;i++){await page.locator('.preset-card').nth(i).focus();await page.keyboard.press('Space');await expect(page.getByRole('heading',{name:'Design & Ingestion'})).toBeFocused();if(i<3)await page.getByRole('button',{name:'Preset Gallery'}).click();}
 await page.getByRole('spinbutton',{name:/Holopixel Lattice Pitch.*numeric/}).fill('37');
 const pending=page.waitForEvent('download');await page.getByRole('button',{name:'Parameter Metadata (JSON)'}).click();const file=await pending;expect(JSON.parse(await readFile((await file.path())!,'utf8')).pitch_nm).toBe(37000);
 const csvPending=page.waitForEvent('download');await page.getByRole('button',{name:'Parameter Distribution (CSV)'}).click();const csv=await csvPending;expect(await readFile((await csv.path())!,'utf8')).toContain('grating_period,');
 await page.getByText('EBL Lithography Fabrication',{exact:true}).click();await page.getByRole('button',{name:'Export EBL Layout (.gds)',exact:true}).click();await expect(page.getByRole('button',{name:'Generate GDS',exact:true})).toBeEnabled();let downloads=0;page.on('download',()=>downloads++);
 await page.evaluate(()=>{const buttons=Array.from(document.querySelectorAll('dialog button')) as HTMLButtonElement[];buttons.find(b=>b.textContent==='Generate GDS')!.click();buttons.find(b=>b.textContent==='Close / Cancel')!.click();});await expect(page.locator('dialog')).toHaveCount(0);await page.waitForTimeout(300);expect(downloads).toBe(0);
});

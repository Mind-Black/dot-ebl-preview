import { test, expect } from '@playwright/test';
test('refreshes textures for changed data with the same source identity', async ({page}) => {
 await page.goto('./');
 const result=await page.evaluate(async () => {
  const {WebGlDiffractionRenderer}=(window as any).__DOT_EBL_MODULES__;
  const renderer=new WebGlDiffractionRenderer(document.createElement('canvas'));
  const d={width:1,height:1,pitchNm:20000,periodNm:new Uint32Array([1000]),angleDeg:new Float64Array([0]),active:new Uint8Array([0]),fallbackIntensity:new Float32Array([0]),sourceIdentity:'same'};
  const params={cameraPos:{x:0,y:0,z:300},apertureRadiusMm:1,orientationDeg:0,lights:[],quality:'high'};
  renderer.render(d,params); const before=Array.from(renderer.readPixelsRgba());
  renderer.render({...d,fallbackIntensity:new Float32Array([1])},params); const after=Array.from(renderer.readPixelsRgba()); renderer.dispose(); return {before,after};
 });
 expect(result.after).not.toEqual(result.before);
});

test('slider input edits converge and fabrication reviews the final configuration', async ({page}) => {
 await page.goto('./'); await page.locator('.preset-card').first().click();
 await page.locator('input[type=file]').first().setInputFiles('tests/fixtures/hls_test.png');
 await page.getByRole('dialog').getByRole('combobox').selectOption('RGBA continuous');
 await page.getByRole('button',{name:'Import',exact:true}).click();
 await expect(page.getByRole('button',{name:'Parameter Metadata (JSON)'})).toBeEnabled();
 const max=page.locator('.slider-control-group').filter({has:page.locator('span', {hasText:/^Max Period/})}).locator('input[type=range]');
 await max.evaluate((el:HTMLInputElement)=>{for(const v of ['1500','1300','1200']) {el.value=v;el.dispatchEvent(new Event('input',{bubbles:true}));}});
 await expect(page.getByRole('button',{name:'Parameter Metadata (JSON)'})).toBeEnabled();
 const orientation=page.locator('.slider-control-group').filter({has:page.locator('span',{hasText:/^Grating Orientation$/})}).locator('input[type=range]');
 await orientation.evaluate((el:HTMLInputElement)=>{el.value='30';el.dispatchEvent(new Event('input',{bubbles:true}));});
 await page.getByText('EBL Lithography Fabrication',{exact:true}).click();
 await page.getByRole('button',{name:'Export EBL Layout (.gds)',exact:true}).click();
 await expect(page.locator('dialog pre')).toContainText('Applied orientation: 30°');
 await expect(page.locator('dialog pre')).toContainText('Pitch: 20000 nm');
});

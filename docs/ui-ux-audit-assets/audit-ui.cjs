const {chromium,firefox,webkit}=require('../../web/node_modules/@playwright/test');
const fs=require('fs'),path=require('path');
const out=__dirname;fs.mkdirSync(out,{recursive:true});
(async()=>{
 const browser=await chromium.launch({args:['--use-gl=angle','--use-angle=swiftshader','--enable-webgl']});
 const page=await browser.newPage({viewport:{width:1440,height:900},acceptDownloads:true});const results={version:browser.version(),errors:[],flows:[],layouts:[]};page.on('pageerror',e=>results.errors.push(String(e)));
 const shot=async n=>page.screenshot({path:path.join(out,n+'.png')});
 await page.goto('http://127.0.0.1:4174');await shot('01-welcome-desktop');
 results.presets=await page.locator('.preset-card').evaluateAll(es=>es.map(e=>({text:e.textContent,tag:e.tagName,tabIndex:e.tabIndex,role:e.getAttribute('role')})));
 for(let i=0;i<4;i++){await page.locator('.preset-card').nth(i).click();await page.waitForTimeout(400);results.flows.push({preset:i,workbench:await page.locator('.workbench-container').isVisible()});if(i===0)await shot('02-workbench-desktop');await page.locator('#header-welcome-btn').click();}
 await page.locator('.preset-card').first().click();
 results.renderer=await page.locator('.flat-canvas').evaluate(c=>{const g=c.getContext('webgl2')||c.getContext('webgl');if(!g)return 'unavailable';const ext=g.getExtension('WEBGL_debug_renderer_info');return ext?g.getParameter(ext.UNMASKED_RENDERER_WEBGL):g.getParameter(g.RENDERER)});
 for(const t of ['Angle Map','Source Image','Analytics','Period Map']){await page.getByRole('button',{name:t,exact:true}).click();results.flows.push({tab:t,visible:true});if(t==='Source Image')await shot('03-preset-source');}
 results.controls=await page.locator('input,select').evaluateAll(es=>es.filter(e=>e.getClientRects().length).map(e=>({type:e.type,labels:Array.from(e.labels||[]).map(l=>l.textContent),aria:e.getAttribute('aria-label'),value:e.value})));
 await page.locator('.flat-canvas').hover();results.probe=await page.locator('.hover-probe-pill').innerText();
 results.downloads=[];
 for(const name of ['Parameter Distribution (CSV)','Parameter Metadata (JSON)','Optical Preview PNG (1:1)','Perspective Capture PNG']){try{const promise=page.waitForEvent('download',{timeout:4000});await page.getByRole('button',{name,exact:true}).click();const d=await promise;const dest=path.join(out,d.suggestedFilename());await d.saveAs(dest);results.downloads.push({name,file:d.suggestedFilename(),bytes:fs.statSync(dest).size});}catch(e){results.downloads.push({name,error:String(e)})}}
 await page.getByText('EBL Lithography Fabrication',{exact:true}).click();await page.getByRole('button',{name:'Export EBL Layout (.gds)',exact:true}).click();await page.getByRole('button',{name:'Generate GDS',exact:true}).waitFor({state:'visible'});await page.waitForTimeout(800);await shot('04-fabrication');results.dialog={text:await page.locator('dialog').innerText(),name:await page.locator('dialog').getAttribute('aria-labelledby')};
 for(const kind of ['GDS','ZIP']){const promise=page.waitForEvent('download');await page.getByRole('button',{name:'Generate '+kind,exact:true}).click();const d=await promise;results.downloads.push({name:kind,file:d.suggestedFilename()});}
 await page.keyboard.press('Escape');results.dialogClosed=await page.locator('dialog').count()===0;results.returnFocus=await page.evaluate(()=>document.activeElement.textContent);
 for(const [w,h] of [[1280,720],[768,1024],[390,844],[720,450]]){await page.setViewportSize({width:w,height:h});await page.locator('.sidebar-content').evaluate(e=>e.scrollTop=0);await shot('layout-'+w+'x'+h);results.layouts.push(await page.evaluate(()=>({w:innerWidth,h:innerHeight,bodyWidth:document.body.scrollWidth,panels:Array.from(document.querySelectorAll('.dual-viewport-hero,.workbench-sidebar,.sidebar-content')).map(e=>({class:e.className,rect:e.getBoundingClientRect().toJSON(),scrollHeight:e.scrollHeight,clientHeight:e.clientHeight}))})));}
 await page.setViewportSize({width:1440,height:900});
 for(const file of ['hls_test.png','unity_test.png','rgb8_test.png','rgb16_test.png','design.npz']){await page.locator('#header-welcome-btn').click();await page.locator('input[type=file]').first().setInputFiles(path.resolve('tests/fixtures',file));await page.waitForTimeout(600);results.flows.push({import:file,error:await page.locator('.alert-danger').innerText().catch(()=>''),selects:await page.locator('select').evaluateAll(es=>es.map(e=>({value:e.value,options:Array.from(e.options).map(o=>o.value)})))});if(file==='design.npz'){await page.getByRole('button',{name:'Source Image',exact:true}).click();await shot('05-npz-source');}}
 await page.locator('#header-welcome-btn').click();await page.locator('input[type=file]').first().setInputFiles({name:'corrupt.png',mimeType:'image/png',buffer:Buffer.from('broken')});await page.waitForTimeout(600);results.corrupt=await page.locator('.alert-danger').innerText();await shot('06-corrupt-import');
 await page.locator('#header-welcome-btn').click();await page.locator('input[type=file]').first().setInputFiles({name:'unsupported.txt',mimeType:'text/plain',buffer:Buffer.from('broken')});await page.waitForTimeout(600);results.unsupported=await page.locator('.alert-danger').innerText();
 fs.writeFileSync(path.join(out,'observations.json'),JSON.stringify(results,null,2)); for(const [name,type] of [['firefox',firefox],['webkit',webkit]]){try{const b=await type.launch({timeout:5000});const p=await b.newPage();await p.goto('http://127.0.0.1:4174');await p.locator('.preset-card').first().click();results[name]={version:b.version(),workbench:await p.locator('.workbench-container').isVisible()};await b.close();}catch(e){results[name]={error:String(e).slice(0,500)}}}
 fs.writeFileSync(path.join(out,'observations.json'),JSON.stringify(results,null,2));await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});




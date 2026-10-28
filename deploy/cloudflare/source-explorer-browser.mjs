/* Older suites still exercise the complete source tools below the unified view. */
export async function openSourceExplorer(page){
 const panel=page.locator('#record-sources');if(!await panel.count())return;
 await panel.evaluate(e=>e.open=true);
 await page.waitForFunction(()=>document.querySelector('#record-sources')?.dataset.ready==='true');
}

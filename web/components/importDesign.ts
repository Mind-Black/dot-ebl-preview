import { designStore } from '../lib/store/designStore';
import type { InterpretationFormat } from '../lib/decoders/types';
export function importDesign(file: File, ready: () => void = () => {}) {
  if (file.name.toLowerCase().endsWith('.npz')) { designStore.loadFile(file); ready(); return; }
  const focus = document.activeElement as HTMLElement;
  const dialog = document.createElement('dialog'); dialog.className = 'fabrication-dialog';
  dialog.setAttribute('aria-labelledby','import-title');
  dialog.innerHTML = `<h2 id="import-title">Choose image encoding</h2><p class="import-filename"></p><p>Encoding is not automatically detected. Choose the profile used by the originating tool. Ordinary photographs and lossy images do not reliably encode physical parameters. Scene settings, including global orientation, are retained.</p><label>Parameter interpretation<select class="form-select"><option value="">Choose a profile…</option></select></label><p>RGBA continuous maps channels into adjustable ranges; RGB8 indexed and RGB16 fixed use encoded parameters. HLS and HSV profiles match their named source tools.</p><button class="btn btn-primary" disabled>Import</button><button class="btn">Cancel</button>`;
  dialog.querySelector('.import-filename')!.textContent = file.name;
  const select = dialog.querySelector('select')!;
  for (const name of ['RGBA continuous','RGB8 indexed','RGB16 fixed','Holtida legacy HLS','Learning Shaders HLS','Unity HSV']) { const o = document.createElement('option'); o.textContent = name; select.append(o); }
  const [accept,cancel] = dialog.querySelectorAll('button');
  select.onchange = () => accept.disabled = !select.value;
  accept.onclick = () => { designStore.loadFile(file,select.value as InterpretationFormat); dialog.close(); ready(); };
  cancel.onclick = () => dialog.close(); dialog.onclose = () => {dialog.remove(); focus?.focus();};
  document.body.append(dialog); dialog.showModal();
}

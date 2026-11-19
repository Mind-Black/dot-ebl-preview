import { designStore } from '../lib/store/designStore';
import type { InterpretationFormat } from '../lib/decoders/types';
export function importDesign(file: File, ready: () => void = () => {}) {
  if (file.name.toLowerCase().endsWith('.npz')) { designStore.loadFile(file); ready(); return; }
  document.querySelectorAll<HTMLDialogElement>('dialog[data-import-dialog]').forEach((existing) => {
    if (existing.open) existing.close();
    existing.remove();
  });
  const focus = document.activeElement as HTMLElement | null;
  const dialog = document.createElement('dialog');
  dialog.className = 'fabrication-dialog';
  dialog.dataset.importDialog = 'true';
  dialog.setAttribute('aria-labelledby', 'import-title');
  dialog.innerHTML = `<h2 id="import-title">Choose image encoding</h2><p class="import-filename"></p><p>Encoding is not automatically detected. Choose the profile used by the originating tool. Ordinary photographs and lossy images do not reliably encode physical parameters. Scene settings, including global orientation, are retained.</p><label>Parameter interpretation<select class="form-select"><option value="">Choose a profile…</option></select></label><p>RGBA continuous maps channels into adjustable ranges; RGB8 indexed and RGB16 fixed use encoded parameters. HLS and HSV profiles match their named source tools.</p><div class="dialog-actions"><button type="button" class="btn btn-primary" disabled>Import</button><button type="button" class="btn btn-outline">Cancel</button></div>`;
  dialog.querySelector('.import-filename')!.textContent = file.name;
  const select = dialog.querySelector('select')!;
  select.autofocus = true;
  for (const name of ['RGBA continuous', 'RGB8 indexed', 'RGB16 fixed', 'Holtida legacy HLS', 'Learning Shaders HLS', 'Unity HSV']) {
    const o = document.createElement('option');
    o.value = name;
    o.textContent = name;
    select.append(o);
  }
  const [accept, cancel] = dialog.querySelectorAll('button');
  let accepted = false;
  select.onchange = () => accept.disabled = !select.value;
  accept.onclick = () => {
    accepted = true;
    designStore.loadFile(file, select.value as InterpretationFormat);
    dialog.close();
    ready();
  };
  cancel.onclick = () => dialog.close();
  dialog.onclose = () => {
    dialog.remove();
    if (!accepted && focus?.isConnected) focus.focus();
  };
  document.body.append(dialog);
  dialog.showModal();
}

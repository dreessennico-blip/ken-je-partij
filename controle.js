// Controleert docs/index.html voordat de nachtelijke update wordt opgeslagen.
// Faalt (afsluitcode 1) als er iets niet klopt, zodat de live app dan ongewijzigd blijft.
const fs = require('fs');
const pad = process.argv[2] || 'docs/index.html';
const s = fs.readFileSync(pad, 'utf8');
const js = s.match(/<script>([\s\S]*?)<\/script>/)[1];
const fouten = [];
try { new Function(js); } catch (e) { fouten.push('Syntaxfout in de app: ' + e.message); }
let r = null;
try {
  const code = js.slice(0, js.indexOf('const dos='));
  const paren = js.match(/const PAREN=\[[\s\S]*?\];/)[0];
  r = new Function(code + paren + ';return {MOTIES,CATS,MIN,PAREN,PARTIJEN}')();
} catch (e) { fouten.push('Kon de gegevens niet lezen: ' + e.message); }
if (r) {
  const ids = r.MOTIES.map(x => x.id);
  if (new Set(ids).size !== ids.length) fouten.push('Dubbele motienummers');
  const nPart = r.PARTIJEN.length;
  const slecht = r.MOTIES.filter(x => !x.stem || x.stem.length !== nPart || !/^[vtn]+$/.test(x.stem));
  if (slecht.length) fouten.push(slecht.length + ' moties met een ongeldige stemreeks, bijv. ' + slecht[0].id);
  const zonderUit = r.MOTIES.filter(x => !x.uitslag);
  if (zonderUit.length) fouten.push(zonderUit.length + ' moties zonder uitslag, bijv. ' + zonderUit[0].id);
  const leeg = r.MOTIES.filter(x => !x.dictum || x.dictum.length < 100 || !x.indiener || !x.url);
  if (leeg.length) fouten.push(leeg.length + ' moties met ontbrekende tekst, indiener of link, bijv. ' + leeg[0].id);
  const sleutels = new Set(ids.map(i => i.replace(/-\d+$/, '')));
  const zonderCat = [...sleutels].filter(k => !r.CATS[k]);
  if (zonderCat.length) fouten.push('Dossiers zonder naam: ' + zonderCat.slice(0, 3).join(', '));
  const zonderGroep = [...sleutels].filter(k => !r.MIN[k]);
  if (zonderGroep.length) fouten.push('Dossiers zonder ministerie: ' + zonderGroep.slice(0, 3).join(', '));
  if (!r.PAREN.every(p => p.every(i => ids.includes(i)))) fouten.push('Een verwant paar verwijst naar een motie die niet bestaat');
  console.log('Moties: ' + ids.length + ', dossiers: ' + sleutels.size);
}
if (fouten.length) { console.error('CONTROLE MISLUKT:\n- ' + fouten.join('\n- ')); process.exit(1); }
console.log('Controle geslaagd.');

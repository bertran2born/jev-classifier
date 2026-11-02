"use strict";
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const D = require('../viewer.js');

test('CSV Python : JSON dans les cellules, virgules, guillemets et retours à la ligne', () => {
  const csv = '\uFEFFpdf,status,field_all_probabilities,error\r\n"study,1.pdf",ok,"{""medicine"": 0.9}","Ligne 1\nLigne ""2"""\r\n';
  const result=D.parseCSV(csv);
  assert.equal(result.records.length,1);
  assert.equal(result.records[0].pdf,'study,1.pdf');
  assert.deepEqual(JSON.parse(result.records[0].field_all_probabilities),{medicine:0.9});
  assert.equal(result.records[0].error,'Ligne 1\nLigne "2"');
});
test('CSV vide, tronqué ou de schéma incompatible rejeté', () => {
  for(const csv of ['', 'foo,bar\na,b', 'pdf,status\n"broken,ok', 'pdf,status\na,ok,extra','pdf,pdf,status\na,b,ok']) assert.throws(()=>D.parseCSV(csv));
  assert.equal(D.parseCSV('pdf;status\nstudy.pdf;ok').records[0].status,'ok');
  assert.equal(D.parseCSV('pdf,status\n').records.length,0);
});
test('Recherche française indépendante de la casse et des accents', () => {
  const row={pdf:'GLAGOV.pdf',field:'medicine',significance:'significant',status:'ok'};
  const text=D.searchText(row);
  assert.ok(text.includes(D.normalize('MÉDECINE')));
  assert.ok(text.includes(D.normalize('GLAGOV')));
  assert.ok(!text.includes(D.normalize('Psychologie')));
});
test('Relecture : valeurs inconnues, données manquantes et probabilités faibles', () => {
  const row={status:'ok'};
  for(const key of Object.keys(D.dimensions)) {row[key]='reported';row[key+'_prob']='0.9';}
  assert.equal(D.needsReview(row),false);
  assert.equal(D.needsReview({...row,preregistration:'not_established'}),true);
  assert.equal(D.needsReview({...row,preregistration_prob:'0.53'}),true);
  assert.equal(D.needsReview({...row,preregistration_prob:''}),true);
  assert.equal(D.needsReview({...row,review_flags:'review_interpretation'}),true);
  assert.equal(D.needsReview({...row,status:'error'}),true);
  assert.equal(D.needsReview({...row,status:'dry_run'}),false);
});
test('Tri numérique correct et valeurs absentes en dernier dans les deux sens', () => {
  const rows=[{field_prob:''},{field_prob:'0.9'},{field_prob:'0.53'},{field_prob:'1'}];
  assert.deepEqual([...rows].sort((a,b)=>D.compare(a,b,'field_prob',1)).map(r=>r.field_prob),['0.53','0.9','1','']);
  assert.deepEqual([...rows].sort((a,b)=>D.compare(a,b,'field_prob',-1)).map(r=>r.field_prob),['1','0.9','0.53','']);
  assert.equal(D.probability('NaN'),null);
  assert.equal(D.probability(''),null);
  assert.equal(D.probability('2'),null);
});
test('Export réimportable et formules de tableur neutralisées', () => {
  const records=[{pdf:'a,"b".pdf',status:'ok',error:'=HYPERLINK("bad")'}];
  const csv=D.toCSV(['pdf','status','error'],records);
  const result=D.parseCSV(csv).records[0];
  assert.equal(result.pdf,records[0].pdf);
  assert.equal(result.error,"'"+records[0].error);
});
test('Le CSV réel est lisible et GLAGOV est à relire malgré les alertes vides', {skip:!fs.existsSync(path.join(__dirname,'../jev-audit-api-check/results.csv'))}, () => {
  const parsed=D.parseCSV(fs.readFileSync(path.join(__dirname,'../jev-audit-api-check/results.csv'),'utf8'));
  assert.equal(parsed.records.length,1);
  const row=parsed.records[0];
  assert.equal(row.status,'ok');
  assert.equal(row.review_flags,'');
  assert.equal(D.needsReview(row,0.8),true);
  assert.equal(D.probability(row.preregistration_prob),0.53);
});

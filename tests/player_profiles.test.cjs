const test = require('node:test');
const assert = require('node:assert/strict');
const profiles = require('../docs/player_profiles.js');

const owner = {id:'p_owner',name:'same name'};
function match(id='1', start=1, overrides={}) {
  return {id,start,date:'2026-10-28 10:00',duration:600,winner:'radiant',players:[
    {id:'p_owner',name:'same name',team:'radiant',hero:'axe',hero_zh:'斧王',kills:4,deaths:2,assists:6,gpm:400,xpm:500,hero_damage:1000,healing:0,titles:[{key:'mvp',name:'MVP'}],...overrides},
    {id:'p_friend',name:'friend',team:'radiant',hero:'bane'},
    {id:'p_enemy',name:'same name',team:'dire',hero:'sven'}]};
}
test('profile identity uses the public ID rather than nickname',()=>{
  const p=profiles.buildProfile(owner,[match()]);
  assert.equal(p.games,1);
  assert.equal(p.wins,1);
  assert.equal(p.kda.value,5);
});
test('history is sorted newest first without mutating input',()=>{
  const matches=[match('1',1),match('2',2)];
  const p=profiles.buildProfile(owner,matches);
  assert.deepEqual(p.records.map(r=>r.match.id),['2','1']);
  assert.equal(matches[0].id,'1');
});
test('unknown result is not counted as a loss',()=>{
  const m=match();m.winner=null;
  const p=profiles.buildProfile(owner,[m]);
  assert.equal(p.winRate,null);assert.equal(p.losses,0);assert.equal(p.unknown,1);
});
test('missing metrics are excluded but real zeros stay in samples',()=>{
  const p=profiles.buildProfile(owner,[match('1',1,{gpm:0}),match('2',2,{gpm:null,kills:null})]);
  assert.deepEqual(p.gpm,{value:0,samples:1});
  assert.equal(p.kda.samples,1);assert.equal(p.kda.value,5);
});
test('hero statistics and honors aggregate per local player',()=>{
  const p=profiles.buildProfile(owner,[match('1',1),match('2',2,{hero:'bane',hero_zh:'祸乱之源',titles:[{key:'support',name:'偏将'}]})]);
  assert.equal(p.heroes.length,2);assert.equal(p.honors.mvp,1);assert.equal(p.honors.support,1);
});
test('teammates exclude opponents and the profile owner',()=>{
  const p=profiles.buildProfile(owner,[match('1',1),match('2',2)]);
  assert.equal(p.peers.length,1);assert.equal(p.peers[0].player.id,'p_friend');
  assert.equal(p.peers[0].games,2);assert.equal(p.peers[0].winRate,100);
});
test('opponents exclude teammates and measure wins from the profile owner perspective',()=>{
  const lost=match('2',2);lost.winner='dire';
  const p=profiles.buildProfile(owner,[match(),lost]);
  assert.equal(p.opponents.length,1);assert.equal(p.opponents[0].player.id,'p_enemy');
  assert.equal(p.opponents[0].games,2);assert.equal(p.opponents[0].winRate,50);
  assert.equal(p.opponents[0].wins,1);assert.equal(p.opponents[0].losses,1);
});
test('unknown teams cannot create false relationships',()=>{
  const m=match();m.players[0].team='';m.players[1].team='';
  const p=profiles.buildProfile(owner,[m]);
  assert.equal(p.peers.length,0);assert.equal(p.opponents.length,0);
});
test('hero and result filters intersect',()=>{
  const m=match('2',2,{hero:'bane'});m.winner='dire';
  const p=profiles.buildProfile(owner,[match(),m]);
  assert.equal(profiles.filterRecords(p.records,'bane','loss').length,1);
  assert.equal(profiles.filterRecords(p.records,'axe','loss').length,0);
  assert.equal(profiles.filterRecords(p.records,'all','win').length,1);
});
test('empty profiles preserve missing states',()=>{
  const p=profiles.buildProfile(owner,[]);
  assert.equal(p.games,0);assert.equal(p.winRate,null);assert.equal(p.gpm.value,null);assert.deepEqual(p.heroes,[]);
});
test('hero image markup escapes names and rejects unsafe URLs',()=>{
  const html=profiles.heroImage({name:'<script>',image:'javascript:alert(1)'});
  assert.equal(html.includes('<img'),false);assert.equal(html.includes('<script>'),false);
  assert.equal(html.includes('&lt;'),true);
});
test('hero image uses a validated Valve CDN URL',()=>{
  const html=profiles.heroImage({name:'axe',image:'https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/heroes/axe.png'});
  assert.equal(html.includes('data-hero-image'),true);
});
test('invalid numeric values cannot corrupt profile averages',()=>{
  const p=profiles.buildProfile(owner,[match('1',1,{gpm:NaN}),match('2',2,{gpm:Infinity}),match('3',3,{gpm:-2})]);
  assert.equal(p.gpm.samples,0);assert.equal(p.gpm.value,null);
});
test('item icon metadata is escaped and unsafe image URLs are rejected',()=>{
  const html=profiles.itemIcons({items:[{zh:'"><script>alert(1)</script>',image:'javascript:alert(1)'}]});
  assert.equal(html.includes('<img'),false);assert.equal(html.includes('<script>'),false);
  assert.equal(html.includes('&quot;'),true);
});
test('equipment uses up to six validated online icons',()=>{
  const html=profiles.itemIcons({items:Array.from({length:8},()=>({zh:'闪烁匕首',image:'https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/items/blink.png'}))});
  assert.equal((html.match(/data-item-image/g)||[]).length,6);
});

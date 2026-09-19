const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { outputPayload, validateUrl, registerSongsterr } = require('../electron/services/songsterr.cjs');

test('preview audio survives request cleanup and is removed on app exit', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'feedforge-test-'));
  const handlers = new Map(); const lifecycle = new Map();
  try {
    registerSongsterr({app:{getPath:()=>root,on:(name,fn)=>lifecycle.set(name,fn)},
      ipcMain:{handle:(name,fn)=>handlers.set(name,fn)},dialog:{},window:()=>null,
      terminateChildProcessTree:()=>{},logDebug:()=>{},removeTemporaryDirectory:dir=>fs.rmSync(dir,{recursive:true,force:true}),
      runConverter:async args=>{
        const request=JSON.parse(fs.readFileSync(args[1]));
        assert.equal(request.action,'preview');
        assert.notEqual(request.payload.preview_dir,'untrusted');
        const audio=path.join(request.payload.preview_dir,'full.ogg');
        fs.writeFileSync(audio,'fixture');
        return {code:0,stdout:JSON.stringify({ok:true,result:{audio_path:audio,measures:[]}})};
      }});
    const event={sender:{isDestroyed:()=>false,send:()=>{}}};
    const result=await handlers.get('songsterr:preview')(event,{preview_dir:'untrusted'});
    assert.ok(fs.existsSync(result.audio_path));
    assert.ok(result.audio_url.startsWith('file:///'));
    lifecycle.get('before-quit')();
    assert.deepEqual(fs.readdirSync(root),[]);
  } finally {fs.rmSync(root,{recursive:true,force:true});}
});
test('Songsterr output names stay in selected directory and preserve collisions', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'feedforge-test-'));
  try {
    const payload = {url:'https://www.songsterr.com/a/wsa/test-s1', selected_parts:[0], output_dir:root, output_name:'Test.feedpak'};
    fs.writeFileSync(path.join(root,'Test.feedpak'),'keep');
    assert.equal(outputPayload(payload).output_path,path.join(root,'Test (2).feedpak'));
    for (const name of ['../escape.feedpak','C:\\escape.feedpak','CON.feedpak']) assert.throws(() => outputPayload({...payload,output_name:name}));
    assert.throws(() => validateUrl('https://songsterr.com.evil.test/a/wsa/test-s1'));
    assert.throws(() => outputPayload({...payload,selected_parts:[]}));
  } finally { fs.rmSync(root,{recursive:true,force:true}); }
});
test('batch emits stages, stops after current song and cleans isolated requests', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'feedforge-test-'));
  const handlers = new Map(); const messages=[];
  try {
    registerSongsterr({app:{getPath:()=>root},ipcMain:{handle:(name,fn)=>handlers.set(name,fn)},dialog:{},window:()=>null,
      terminateChildProcessTree:()=>{},logDebug:()=>{},removeTemporaryDirectory:dir=>fs.rmSync(dir,{recursive:true,force:true}),
      runConverter:async (args,options)=>{
        const request=JSON.parse(fs.readFileSync(args[1]));
        assert.equal(request.action,'create');
        options.onStderrLine('FEEDFORGE_PROGRESS {"stage":"Building"}');
        await handlers.get('songsterr:cancel')();
        return {code:0,stdout:JSON.stringify({ok:true,result:{output_path:request.payload.output_path}})};
      }});
    const event={sender:{isDestroyed:()=>false,send:(channel,value)=>messages.push(value)}};
    const payload={url:'https://www.songsterr.com/a/wsa/test-s1',selected_parts:[0],output_dir:root,output_name:'Test.feedpak'};
    const result=await handlers.get('songsterr:batch')(event,[payload,payload]);
    assert.equal(result.created,1); assert.equal(result.skipped,1); assert.equal(result.cancelled,true);
    assert.equal(messages[1].stage,'Building');
    assert.deepEqual(fs.readdirSync(root),[]);
  } finally {fs.rmSync(root,{recursive:true,force:true});}
});

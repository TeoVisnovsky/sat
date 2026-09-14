const assert=require('node:assert/strict'),fs=require('node:fs');
const {PGlite}=require('@electric-sql/pglite');
(async()=>{
 const db=new PGlite();
 await db.exec(`create role anon; create role authenticated; create schema auth;
 create table auth.users(id uuid primary key);
 create function auth.uid() returns uuid language sql stable as $$ select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
 grant usage on schema auth to anon,authenticated;grant execute on function auth.uid() to anon,authenticated;
 insert into auth.users values ('00000000-0000-0000-0000-000000000001'),('00000000-0000-0000-0000-000000000002');`);
 const sql=fs.readFileSync('supabase/setup.sql','utf8');await db.exec(sql);await db.exec(sql);
 const state={format:'sat-bank',version:1,bank:{id:'main',name:'Test'},attempts:[],notes:[],ratings:[],reviews:[],tags:[]},hash='a'.repeat(64);
 async function user(id){await db.exec(`reset role;set role authenticated;set request.jwt.claim.sub='00000000-0000-0000-0000-00000000000${id}';`);}
 async function put(revision,body=state,questions=[]){return (await db.query('select public.sat_put_bank($1,$2,$3,$4,$5) as result',['main',revision,JSON.stringify(body),hash,questions===null?null:JSON.stringify(questions)])).rows[0].result;}
 await user(1);assert.equal((await put(0)).accepted,true);assert.equal((await put(0)).accepted,false);
 const changed={...state,tags:[{question_id:'test',name:'one'}]};assert.equal((await put(1,changed,null)).revision,2);
 assert.equal((await put(1)).accepted,false);assert.equal((await put(2,changed,null)).revision,2);
 assert.equal((await db.query('select * from public.sat_cloud_banks')).rows.length,1);
 await assert.rejects(()=>db.exec('delete from public.sat_cloud_banks'),/permission denied/);
 await assert.rejects(()=>db.exec("update public.sat_cloud_banks set revision=900"),/permission denied/);
 await user(2);assert.equal((await db.query('select * from public.sat_cloud_banks')).rows.length,0);
 assert.equal((await put(0)).revision,1);assert.equal((await db.query('select * from public.sat_cloud_banks')).rows.length,1);
 await db.exec("reset role;set role anon;set request.jwt.claim.sub='';");
 await assert.rejects(()=>db.query('select * from public.sat_cloud_banks'),/permission denied/);
 await assert.rejects(()=>put(0),/permission denied/);
 await db.exec("reset role;set role authenticated;set request.jwt.claim.sub='';");await assert.rejects(()=>put(0),/Sign in/);
 await db.close();console.log('Cloud SQL: rerunnable migration, private rows, no anonymous access, protected writes and revision conflicts passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});

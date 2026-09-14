const fs=require('node:fs'),path=require('node:path');
const pkg=path.dirname(path.dirname(require.resolve('@supabase/supabase-js')));
const out=path.join(__dirname,'../web/vendor');fs.mkdirSync(out,{recursive:true});
fs.copyFileSync(path.join(pkg,'dist/umd/supabase.js'),path.join(out,'supabase.js'));
fs.copyFileSync(path.join(pkg,'LICENSE'),path.join(out,'SUPABASE-LICENSE'));
console.log('Vendored official Supabase browser SDK; no CDN needed at runtime.');

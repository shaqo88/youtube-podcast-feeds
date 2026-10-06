import { build } from 'esbuild';
await build({ entryPoints:['podcast_feeds/web/firebase-auth.mjs'], bundle:true, format:'esm',
  outfile:'podcast_feeds/web/firebase-auth.bundle.js', minify:true, platform:'browser',target:['es2022'], legalComments:'eof',
  plugins:[{name:'explicit-firebase-config',setup(builder){
    // Firebase's optional install script otherwise bakes a machine's ambient
    // app/emulator configuration into this module. Both builds use reviewed
    // public environment configuration supplied by createAuth instead.
    builder.onLoad({filter:/[\\/]@firebase[\\/]util[\\/]dist[\\/]postinstall\.mjs$/},()=>({
      contents:'export const getDefaultsFromPostinstall = () => undefined;',loader:'js',
    }));
  }}],
});

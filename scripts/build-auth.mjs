import { build } from 'esbuild';
await build({ entryPoints:['podcast_feeds/web/firebase-auth.mjs'], bundle:true, format:'esm',
  outfile:'podcast_feeds/web/firebase-auth.bundle.js', minify:true, target:['es2022'], legalComments:'eof' });

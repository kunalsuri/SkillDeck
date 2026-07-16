import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const kbSource = path.resolve(__dirname, '..', 'data', 'kb.json');
const kbDestDir = path.resolve(__dirname, 'src', 'data');
const kbDest = path.resolve(kbDestDir, 'kb.json');

console.log(`Prebuild: Copying database from ${kbSource} to ${kbDest}`);

try {
  if (!fs.existsSync(kbSource)) {
    throw new Error(`Source knowledge base file not found at ${kbSource}`);
  }
  
  fs.mkdirSync(kbDestDir, { recursive: true });
  fs.copyFileSync(kbSource, kbDest);
  console.log('Prebuild: kb.json copied successfully.');
} catch (error) {
  console.error('Prebuild failed:', error.message);
  process.exit(1);
}

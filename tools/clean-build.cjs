const { spawnSync } = require('node:child_process');
const path = require('node:path');

const result = spawnSync('git', [
  'clean', process.argv.includes('--dry-run') ? '-ndx' : '-fdx',
  ...['*.exe', '*.dmg', '*.zip', '*.AppImage', 'SHA256SUMS.txt']
    .flatMap(pattern => ['-e', `/release/${pattern}`]),
  '--', 'build/', 'dist/', 'desktop-dist/', 'release/', '.pytest_cache/',
  'src/feedback_converter/__pycache__/', 'src/feedback_converter/psarc_format/__pycache__/',
  'tests/__pycache__/', 'tools/__pycache__/',
], { cwd: path.resolve(__dirname, '..'), stdio: 'inherit' });
if (result.error) throw result.error;
process.exitCode = result.status ?? 1;

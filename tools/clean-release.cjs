// electron-builder calls this only after all requested artifacts were built.
const fs = require('node:fs');
const path = require('node:path');

module.exports = async ({ artifactPaths }) => {
  const release = path.resolve(__dirname, '..', 'release');
  const current = new Set(artifactPaths.map(file => path.resolve(file)));
  const extensions = new Set([...current]
    .filter(file => path.dirname(file) === release && fs.statSync(file).size > 0)
    .map(file => path.extname(file)));
  for (const entry of fs.readdirSync(release, { withFileTypes: true })) {
    const file = path.join(release, entry.name);
    if (entry.isFile() && /^FeedForge[ .-]\d+\.\d+\.\d+(?:[ .-].*)?\.(exe|dmg|zip|AppImage)$/.test(entry.name)
        && extensions.has(path.extname(file)) && !current.has(file)) {
      fs.unlinkSync(file);
      console.log(`Removed superseded release: ${entry.name}`);
    }
  }
  return [];
};

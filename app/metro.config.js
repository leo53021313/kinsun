// Metro 設定：讓 App 可引用 repo 根目錄的 shared/ 共用包（✅ D-51，乙-5）。
// kinsun-shared 以 package.json 的 file:../shared 本地依賴安裝（npm 管理 symlink）；
// watchFolders 讓 Metro 監看並打包 symlink 指向的真實路徑。
const { getDefaultConfig } = require("expo/metro-config");
const path = require("node:path");

const config = getDefaultConfig(__dirname);
config.watchFolders = [path.resolve(__dirname, "..", "shared")];

module.exports = config;

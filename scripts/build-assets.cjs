const fs = require("node:fs");
fs.mkdirSync("static/vendor", { recursive: true });
fs.copyFileSync(
  "node_modules/fullcalendar/index.global.min.js",
  "static/vendor/fullcalendar.min.js",
);
fs.copyFileSync(
  "node_modules/fullcalendar/LICENSE.md",
  "static/vendor/FULLCALENDAR_LICENSE.md",
);
fs.copyFileSync(
  "node_modules/@fullcalendar/core/locales/vi.global.min.js",
  "static/vendor/fullcalendar-vi.min.js",
);
fs.copyFileSync(
  "node_modules/@fullcalendar/luxon3/index.global.min.js",
  "static/vendor/fullcalendar-luxon.min.js",
);
fs.copyFileSync(
  "node_modules/luxon/build/global/luxon.min.js",
  "static/vendor/luxon.min.js",
);
fs.copyFileSync(
  "node_modules/luxon/LICENSE.md",
  "static/vendor/LUXON_LICENSE.md",
);

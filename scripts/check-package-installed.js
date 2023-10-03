// @ts-check
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

if (process.argv.length < 3) {
  throw new Error("Please specify a package/packages to check.");
}

/**
 * @type {string[]}
 */
const failedPackages = [];

for (let i = 2; i < process.argv.length; ++i) {
  const packageName = process.argv[i];
  try {
    require(packageName);
  } catch {
    failedPackages.push(packageName);
  }
}

if (failedPackages.length !== 0) {
  throw new Error(
    `${failedPackages.join(", ")} ${failedPackages.length === 1 ? "is" : "are"} not installed.`,
  );
}

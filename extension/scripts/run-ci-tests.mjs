import { spawn } from "node:child_process";

const executable = process.platform === "win32" ? "npm.cmd" : "npm";
const child = spawn(executable, ["test"], {
  env: process.env,
  shell: false,
  stdio: ["ignore", "pipe", "pipe"],
});
let output = "";

for (const stream of [child.stdout, child.stderr]) {
  stream.on("data", (chunk) => {
    const text = chunk.toString();
    output += text;
    process.stdout.write(text);
  });
}

child.on("error", (error) => {
  output += `\n${error.stack || error.message}`;
});

child.on("close", (code) => {
  if (code !== 0) {
    const diagnostic = output
      .replace(/\u001b\[[0-9;]*m/g, "")
      .trim()
      .slice(-6000)
      .replaceAll("%", "%25")
      .replaceAll("\r", "%0D")
      .replaceAll("\n", "%0A");
    console.error(`::error title=Extension tests failed::${diagnostic}`);
  }
  process.exitCode = code ?? 1;
});

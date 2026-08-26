import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const projectDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const trackerPath = path.join(projectDir, "outputs", "job_tracker.html");
const workbenchPath = path.join(projectDir, "outputs", "daily_application_workbench.html");

const tracker = fs.readFileSync(trackerPath, "utf8");
const workbench = fs.readFileSync(workbenchPath, "utf8");
const seedStart = tracker.indexOf("const SEED_JOBS = ") + "const SEED_JOBS = ".length;
const seedEnd = tracker.indexOf(";", seedStart);
if (seedStart < "const SEED_JOBS = ".length || seedEnd < 0) throw new Error("SEED_JOBS not found in tracker");

const jobs = Function(`"use strict"; return (${tracker.slice(seedStart, seedEnd)});`)();
const cleanJobs = jobs.filter(job => job && job.id && job.company && job.role);
const startMarker = "/* WORKBENCH_SEED_START */";
const endMarker = "/* WORKBENCH_SEED_END */";
const start = workbench.indexOf(startMarker) + startMarker.length;
const end = workbench.indexOf(endMarker, start);
if (start < startMarker.length || end < 0) throw new Error("Workbench seed markers not found");

const payload = `\n${JSON.stringify(cleanJobs, null, 2)}\n`;
fs.writeFileSync(workbenchPath, workbench.slice(0, start) + payload + workbench.slice(end), "utf8");
console.log(`daily workbench synced with ${cleanJobs.length} jobs`);

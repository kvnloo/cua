import type { ToolResult } from "./package/dist/index.js";
declare const result: ToolResult;
export const text: string = result.text;
export const json: string = result.rawJson;
export const action = result.action;
export const verification = result.verification;
const fixture: ToolResult = { text: "fixture", images: [], isError: false, degraded: false, rawJson: "{}" };
void fixture;

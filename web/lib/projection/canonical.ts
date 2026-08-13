function assertJsonValue(value: unknown): void {
  if (
    value === null ||
    typeof value === "string" ||
    typeof value === "boolean"
  ) {
    return;
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      throw new Error("NON_FINITE_NUMBER");
    }
    return;
  }
  if (Array.isArray(value)) {
    for (const item of value) assertJsonValue(item);
    return;
  }
  if (typeof value === "object") {
    for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
      if (/[\u0000-\u001f]/u.test(key)) throw new Error("CONTROL_CHARACTER_IN_KEY");
      assertJsonValue(item);
    }
    return;
  }
  throw new Error("UNSUPPORTED_JSON_VALUE");
}

function asciiJsonString(value: string): string {
  const json = JSON.stringify(value);
  let result = "";
  for (let index = 0; index < json.length; index += 1) {
    const code = json.charCodeAt(index);
    if (code <= 0x7f) {
      result += json[index];
    } else {
      result += `\\u${code.toString(16).padStart(4, "0")}`;
    }
  }
  return result;
}

export function canonicalJson(value: unknown): string {
  assertJsonValue(value);
  if (value === null) return "null";
  if (typeof value === "string") return asciiJsonString(value);
  if (typeof value === "number" || typeof value === "boolean") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalJson(item)).join(",")}]`;
  }
  const object = value as Record<string, unknown>;
  const keys = Object.keys(object).sort();
  return `{${keys
    .map((key) => `${asciiJsonString(key)}:${canonicalJson(object[key])}`)
    .join(",")}}`;
}

export function canonicalText(value: unknown): string {
  return `${canonicalJson(value)}\n`;
}

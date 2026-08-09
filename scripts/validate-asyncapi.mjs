// SPDX-License-Identifier: FSL-1.1-Apache-2.0
// Copyright (c) 2025 Open Computer Use Contributors
//
// Validates every AsyncAPI document passed as an argument, hermetically.
//
// Replaces `npx @asyncapi/cli validate`, which cannot install: the CLI pins
// @asyncapi/generator@3.0.1, which declares "@asyncapi/generator-hooks": "*",
// and version 0.1.1 of that package was unpublished — npm resolves the star to
// a 404. No published CLI version escapes the pin.
//
// The parser is passed `source` so relative $refs resolve against the DOCUMENT,
// not the working directory. Without it every local $ref fails ENOENT, which
// looks like a broken contract rather than a missing option.
import { Parser } from '@asyncapi/parser';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const files = process.argv.slice(2);
if (files.length === 0) {
  console.log('no asyncapi files');
  process.exit(0);
}

let failed = 0;
for (const arg of files) {
  const file = resolve(arg);
  const parser = new Parser();
  const { document, diagnostics } = await parser.parse(readFileSync(file, 'utf8'), { source: file });
  // severity 0 is error; warnings and hints do not fail the gate.
  const errors = diagnostics.filter((d) => d.severity === 0);
  if (errors.length === 0 && document) {
    console.log(`ok  ${arg}`);
    continue;
  }
  failed += 1;
  console.error(`FAIL ${arg}`);
  for (const d of errors) {
    console.error(`  ${d.message}${d.path?.length ? `  at /${d.path.join('/')}` : ''}`);
  }
  if (!document && errors.length === 0) {
    console.error('  the parser returned no document and no error — treating as a failure');
  }
}
process.exit(failed ? 1 : 0);

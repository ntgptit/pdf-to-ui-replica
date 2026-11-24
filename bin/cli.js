#!/usr/bin/env node
'use strict'
// pdf-to-ui-replica: install the skill into a project and run its setup.
//   npx pdf-to-ui-replica init [--project DIR] [--update] [--check]
// Node standard library only; works on Windows, Linux and macOS.
const fs = require('fs')
const path = require('path')
const { spawnSync } = require('child_process')

const NAME = 'pdf-to-ui-replica'
const SKIP = new Set(['.git', 'node_modules', '__pycache__', '.pytest_cache', '.tmp', 'pdf-to-ui-output'])
const USAGE = `Usage: npx ${NAME} [init] [--project DIR] [--update] [--check]

  init       install the skill into <project>/.claude/skills/${NAME}/ and run its setup (default command)
  --project  the project folder (default: the current directory)
  --update   replace an installed copy with this version
  --check    report the environment only, write nothing
`

function parse(argv) {
  const options = { command: 'init', project: process.cwd(), update: false, check: false }
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i]
    if (arg === 'init') options.command = 'init'
    else if (arg === '--update') options.update = true
    else if (arg === '--check') options.check = true
    else if (arg === '--project') options.project = path.resolve(argv[++i] || '')
    else if (arg === '-h' || arg === '--help') options.command = 'help'
    else throw new Error(`unknown argument: ${arg}`)
  }
  return options
}

function findPython() {
  const probe = 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'
  for (const candidate of [['python3'], ['python'], ['py', '-3']]) {
    const result = spawnSync(candidate[0], [...candidate.slice(1), '-c', probe], { stdio: 'ignore' })
    if (result.status === 0) return candidate
  }
  return null
}

function install(source, destination, update) {
  if (path.resolve(source) === path.resolve(destination)) return 'already in place'
  if (fs.existsSync(path.join(destination, 'SKILL.md')) && !update) return 'kept the installed copy (use --update to replace it)'
  fs.rmSync(destination, { recursive: true, force: true })
  fs.mkdirSync(path.dirname(destination), { recursive: true })
  fs.cpSync(source, destination, { recursive: true, filter: (file) => !SKIP.has(path.basename(file)) })
  return 'installed'
}

function main() {
  const options = parse(process.argv.slice(2))
  if (options.command === 'help') { process.stdout.write(USAGE); return 0 }
  if (!fs.existsSync(options.project) || !fs.statSync(options.project).isDirectory()) throw new Error(`project folder ${options.project} does not exist`)
  const python = findPython()
  if (!python) throw new Error('Python 3.10 or newer was not found (tried python3, python, py -3); install it from https://www.python.org')
  const destination = path.join(options.project, '.claude', 'skills', NAME)
  const source = path.resolve(__dirname, '..')
  let root = destination
  if (options.check) {
    if (!fs.existsSync(path.join(destination, 'SKILL.md'))) root = source
  } else {
    console.log(`${NAME}: ${install(source, destination, options.update)} (${destination})`)
  }
  const args = [...python.slice(1), path.join(root, 'scripts', 'init.py'), '--project', options.project]
  if (options.check) args.push('--check')
  return spawnSync(python[0], args, { stdio: 'inherit' }).status ?? 1
}

try {
  process.exitCode = main()
} catch (error) {
  console.error(`${NAME}: ${error.message}`)
  process.exitCode = 2
}

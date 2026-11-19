import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import ts from 'typescript'

const source = await readFile(new URL('../src/utils/latestLoader.ts', import.meta.url), 'utf8')
const { outputText } = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.ESNext } })
const { createLatestLoader } = await import('data:text/javascript;base64,' + Buffer.from(outputText).toString('base64'))

function deferred() {
  let resolve, reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}

test('slow previous stock response cannot overwrite the current stock', async () => {
  const previous=deferred(), current=deferred(), shown=[]
  const loader=createLatestLoader({resolve:value=>shown.push(value)})
  const first=loader.load(()=>previous.promise)
  const second=loader.load(()=>current.promise)
  current.resolve('current stock'); await second
  previous.resolve('previous stock'); await first
  assert.deepEqual(shown,['current stock'])
})

test('switching to a cached statement invalidates an older pending network response', async () => {
  const old=deferred(), shown=[], errors=[], busy=[]
  const loader=createLatestLoader({resolve:value=>shown.push(value), reject:error=>errors.push(error), pending:value=>busy.push(value)})
  const first=loader.load(()=>old.promise)
  await loader.load(async()=>'cached cashflow')
  old.resolve('slow income'); await first
  assert.deepEqual(shown,['cached cashflow'])
  assert.deepEqual(errors,[])
  assert.equal(busy.at(-1),false)
})

test('clearing a stock search prevents its pending results from reappearing', async () => {
  const pending=deferred(), shown=[]
  const loader=createLatestLoader({resolve:value=>shown.push(value)})
  const request=loader.load(()=>pending.promise)
  loader.cancel()
  pending.resolve('obsolete candidates'); await request
  assert.deepEqual(shown,[])
})

test('an old failure cannot hide the loading state or show errors for the new request', async () => {
  const old=deferred(), next=deferred(), busy=[], errors=[]
  const loader=createLatestLoader({resolve:()=>{}, reject:error=>errors.push(error), pending:value=>busy.push(value)})
  const first=loader.load(()=>old.promise), second=loader.load(()=>next.promise)
  old.reject(new Error('old failure')); await first
  assert.equal(busy.at(-1),true)
  assert.deepEqual(errors,[])
  next.resolve('new result'); await second
  assert.equal(busy.at(-1),false)
})

test('leaving the page blocks late completions and future fetches', async () => {
  const pending=deferred(), shown=[], busy=[]
  const loader=createLatestLoader({resolve:value=>shown.push(value),pending:value=>busy.push(value)})
  const request=loader.load(()=>pending.promise)
  loader.dispose()
  const before=busy.length
  pending.resolve('late'); await request
  let fetches=0
  await loader.load(async()=>{fetches++;return 'unexpected'})
  assert.deepEqual(shown,[])
  assert.equal(busy.length,before)
  assert.equal(fetches,0)
})

test('a current request failure is visible and stops loading', async () => {
  const failures=[], busy=[]
  const loader=createLatestLoader({resolve:()=>assert.fail('unexpected result'),reject:error=>failures.push(error.message),pending:value=>busy.push(value)})
  await loader.load(async()=>{throw new Error('actual failure')})
  assert.deepEqual(failures,['actual failure'])
  assert.equal(busy.at(-1),false)
})
